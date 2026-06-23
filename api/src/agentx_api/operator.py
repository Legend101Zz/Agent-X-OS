"""Lifespan-owned operator runtime.

One process-global ``OperatorRuntime`` owns:

- the append-only journal (kernel source of truth)
- the projection store + projection fan-out
- the durable manual-task repository (DB-backed for live mode, in-memory for sim/tests)
- the syscall registry + receipts + vault
- the mandate catalog (KernelControl) wired to the SAME journal/projections
- the Phase1 run invoker, run continuations, scheduler store, scheduler worker

The intent: an HTTP request never constructs a fresh registry, journal, or invoker. The lifespan
``startup`` composes everything once; requests only call methods.

This is also the place where the background ``SchedulerWorker`` loop lives: started in ``startup``,
stopped in ``shutdown``. Phase 1 has one operator per process, so a deterministic per-tick pump is
sufficient — every work item is durable in Mongo so a worker restart is safe.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from agentx_contracts.config import Settings, get_settings
from agentx_contracts.journal import ApprovalResolved
from agentx_contracts.mandate import InstanceBinding, MandateType
from agentx_contracts.protocols import SyscallRegistry
from agentx_contracts.trigger import Trigger
from agentx_kernel.books_review import BooksReviewResolver
from agentx_kernel.bootstrap import build_books_review_resolver
from agentx_kernel.control import (
    ApprovalEnqueuer,
    KernelControl,
    TriggerEnqueuer,
)
from agentx_kernel.gateway import Gateway
from agentx_kernel.hydration import HydrationLoader
from agentx_kernel.projections import Projections
from agentx_kernel.run_loop import Phase1RunInvoker
from agentx_kernel.scheduler import (
    ApprovalWork,
    SchedulerStore,
    SchedulerWorker,
    TriggerWork,
)
from agentx_kernel.settlement import SettlementCommitter
from agentx_kernel.stores.memory import (
    InMemoryJournalStore,
    InMemoryProjectionStore,
    InMemoryRunContinuationStore,
    InMemorySchedulerStore,
    InMemorySyscallReceiptStore,
)
from agentx_kernel.stores.mongo import (
    MongoJournalStore,
    MongoProjectionStore,
    MongoRunContinuationStore,
    MongoSchedulerStore,
    MongoSyscallReceiptStore,
)
from agentx_kernel.verifier import RulesVerifier
from agentx_kernel.watch_maturation import WatchMaturationWorker
from agentx_mandate.harness import HarnessRunner
from agentx_mandate.library.lead_finder import build_lead_finder_type
from agentx_syscall import ManualTaskRepository, build_phase1_registry
from agentx_syscall.adapters import ManualTaskStore

from .swarm_runner import SwarmRunner

logger = logging.getLogger(__name__)


@runtime_checkable
class _VaultLike(Protocol):
    async def get(self, ref: str, tenant_id: str) -> Any: ...


@dataclass(frozen=True)
class RuntimeKind:
    name: str  # "mongo" | "memory"


class OperatorSchedulerDriver(ApprovalEnqueuer, TriggerEnqueuer):
    """API-side glue: implements the two Protocol types KernelControl accepts without coupling
    KernelControl to the scheduler module's specific store/enqueue wiring.

    Lane-pure: this object lives in the API composition edge; ``agentx_kernel`` only sees it as a
    Protocol.
    """

    def __init__(self, store: SchedulerStore) -> None:
        self._store = store

    async def enqueue(self, work: Any) -> None:
        await self._store.enqueue(work)

    def build_approval_work(self, approval: ApprovalResolved) -> ApprovalWork:
        return ApprovalWork.schedule(approval)

    def build_trigger_work(
        self,
        *,
        mandate: MandateType,
        instance: InstanceBinding,
        trigger: Trigger,
        mode: str,
    ) -> TriggerWork:
        from typing import cast as _cast

        from agentx_contracts.enums import RunMode

        return TriggerWork.schedule(
            mandate=mandate,
            instance=instance,
            trigger=trigger,
            mode=_cast(RunMode, mode),
        )


@dataclass
class OperatorRuntime:
    """The lifespan-owned composition of every component the API needs."""

    backend: RuntimeKind
    settings: Settings
    journal: Any
    projection_store: Any
    projections: Projections
    manual_tasks: ManualTaskRepository
    registry: SyscallRegistry
    receipts: Any
    vault: _VaultLike
    gateway: Gateway
    hydration: HydrationLoader
    settlement: SettlementCommitter
    verifier: RulesVerifier
    continuations: Any
    scheduler_store: SchedulerStore
    invoker: Phase1RunInvoker
    worker: SchedulerWorker
    control: KernelControl
    review_resolver: BooksReviewResolver
    swarm_runner: SwarmRunner
    scheduler_driver: OperatorSchedulerDriver
    runner: HarnessRunner | None
    harness_runner_factory: Any | None
    database: Any | None
    client: Any | None
    watch_maturation_worker: WatchMaturationWorker
    _worker_task: asyncio.Task[None] | None = None
    _stopped: bool = False

    async def start_worker(self, *, interval_seconds: float = 0.5) -> None:
        if self._worker_task is not None and not self._worker_task.done():
            return
        self._stopped = False
        self._worker_task = asyncio.create_task(
            _worker_loop(self, interval_seconds=interval_seconds),
            name="agentx-operator-worker",
        )

    async def stop_worker(self) -> None:
        self._stopped = True
        task = self._worker_task
        if task is None:
            return
        task.cancel()
        try:
            await task
        except BaseException:  # noqa: BLE001
            pass
        self._worker_task = None

    async def close(self) -> None:
        await self.stop_worker()
        close = getattr(self.client, "close", None)
        if callable(close):
            result = close()
            if asyncio.iscoroutine(result):
                await result


def build_runtime(
    *,
    settings: Settings | None = None,
    database: Any | None = None,
    client: Any | None = None,
    runner_factory: Any | None = None,
    send_email_transport: Any | None = None,
) -> OperatorRuntime:
    """Construct the live or in-memory operator runtime.

    ``runner_factory`` is a no-arg callable returning a ``HarnessRunner``. When ``None``,
    ``Phase1RunInvoker`` falls back to its OwnHarness default — appropriate for sim API + tests.

    ``send_email_transport`` is the Phase-1 composition edge: when supplied (test fake) or
    auto-built from ``RUN_LIVE_EMAIL=1`` + ``RESEND_API_KEY``, the runtime registers exactly one
    ``SendEmailAdapter`` per ``MandateInstance`` whose ``channel_binding`` is set (invariant #8).
    When unconfigured, no SendEmailAdapter is registered and the human_task tail handles
    send_email (invariant #5 — resolve never returns None).
    """
    settings = settings or get_settings()
    if database is not None:
        return _compose_mongo_runtime(
            settings=settings,
            database=database,
            client=client,
            runner_factory=runner_factory,
            send_email_transport=send_email_transport,
        )
    return _compose_memory_runtime(
        settings=settings,
        database=None,
        client=None,
        runner_factory=runner_factory,
        send_email_transport=send_email_transport,
    )


def _compose_mongo_runtime(
    *,
    settings: Settings,
    database: Any,
    client: Any | None,
    runner_factory: Any | None,
    send_email_transport: Any | None,
) -> OperatorRuntime:
    from agentx_kernel.vault import ConfigVault
    from agentx_syscall.manual_tasks import MongoManualTaskRepository

    journal = MongoJournalStore(database)
    projection_store = MongoProjectionStore(database)
    receipts = MongoSyscallReceiptStore(database)
    continuations = MongoRunContinuationStore(database)
    scheduler_store: SchedulerStore = MongoSchedulerStore(database)
    vault: _VaultLike = ConfigVault(settings)
    manual_tasks: ManualTaskRepository = MongoManualTaskRepository(database)
    return _compose(
        backend_name="mongo",
        settings=settings,
        database=database,
        client=client,
        journal=journal,
        projection_store=projection_store,
        receipts=receipts,
        vault=vault,
        continuations=continuations,
        scheduler_store=scheduler_store,
        manual_tasks=manual_tasks,
        runner_factory=runner_factory,
        send_email_transport=send_email_transport,
    )


def _compose_memory_runtime(
    *,
    settings: Settings,
    database: Any | None,
    client: Any | None,
    runner_factory: Any | None,
    send_email_transport: Any | None,
) -> OperatorRuntime:
    from agentx_kernel.vault import ConfigVault

    journal = InMemoryJournalStore()
    projection_store = InMemoryProjectionStore()
    receipts = InMemorySyscallReceiptStore()
    continuations = InMemoryRunContinuationStore()
    scheduler_store: SchedulerStore = InMemorySchedulerStore()
    vault: _VaultLike = ConfigVault(settings)
    manual_tasks: ManualTaskRepository = _ManualTaskStoreAdapter(ManualTaskStore())
    return _compose(
        backend_name="memory",
        settings=settings,
        database=database,
        client=client,
        journal=journal,
        projection_store=projection_store,
        receipts=receipts,
        vault=vault,
        continuations=continuations,
        scheduler_store=scheduler_store,
        manual_tasks=manual_tasks,
        runner_factory=runner_factory,
        send_email_transport=send_email_transport,
    )


def _compose(
    *,
    backend_name: str,
    settings: Settings,
    database: Any | None,
    client: Any | None,
    journal: Any,
    projection_store: Any,
    receipts: Any,
    vault: _VaultLike,
    continuations: Any,
    scheduler_store: SchedulerStore,
    manual_tasks: ManualTaskRepository,
    runner_factory: Any | None,
    send_email_transport: Any | None,
) -> OperatorRuntime:
    projections = Projections(projection_store, journal)
    send_email_adapters = _build_send_email_adapters(
        projection_store=projection_store,
        send_email_transport=send_email_transport,
    )
    registry = build_phase1_registry(
        send_email_adapters=send_email_adapters,
        books_intake_dir=settings.books_intake_dir or None,
        books_output_dir=settings.books_output_dir or None,
    )
    gateway = Gateway(
        journal=journal,
        vault=vault,
        registry=registry,
        receipts=receipts,
    )
    hydration = HydrationLoader(projection_store, journal)
    settlement = SettlementCommitter(journal=journal, projections=projections)
    verifier = RulesVerifier()
    runner: HarnessRunner | None = runner_factory() if callable(runner_factory) else None
    live_runner = _resolve_live_runner(settings)
    logger.info(
        "live model runner: %s",
        "configured" if live_runner else "absent (live will use deterministic harness)",
    )
    invoker = Phase1RunInvoker(
        journal=journal,
        projections=projections,
        hydration=hydration,
        gateway=gateway,
        settlement=settlement,
        verifier=verifier,
        continuations=continuations,
        runner=runner,
        live_runner=live_runner,
    )
    scheduler_driver = OperatorSchedulerDriver(scheduler_store)
    control = KernelControl(
        journal=journal,
        projections=projections,
        projection_store=projection_store,
        continuations=continuations,
    )
    # Per-row CA review resolution (books-prep Flag #1): shares the SAME journal + projection store
    # as the run-loop, so a CA-approved row commits to the same heap the dashboard reads and the
    # gym case lands in the same eval_case projection.
    review_resolver = build_books_review_resolver(
        journal=journal,
        projection_store=projection_store,
    )
    # KernelControl implements ApprovalEnqueuer/TriggerEnqueuer via duck-typed hooks (we extend
    # resolve_approval and enqueue_trigger to call them). The driver implements the Protocols.
    # These attributes are read inside the kernel's resolve_approval / enqueue_trigger methods
    # via ``getattr(self, ...)``; mypy can't see them on the KernelControl protocol. We assign via
    # ``vars()`` so the type checker accepts the dynamic write without a suppression.
    vars(control)["_approval_enqueuer"] = scheduler_driver
    vars(control)["_trigger_enqueuer"] = scheduler_driver
    worker = SchedulerWorker(store=scheduler_store, invoker=invoker)
    # The swarm runner is sim-only and self-contained: it builds its own sim-bound invoker per run,
    # so it never touches the live registry/journal composed above.
    swarm_runner = SwarmRunner()

    # Phase-2 deferred-settle worker (HERMES_BUILD_PLAN §Phase 2 — closes G3). It grades the
    # trace of every matured watch via the promptfoo Judge, promotes probation facts to verified,
    # updates the trust/résumé, and emits exactly one EvalCase(origin="real") into the gym.
    try:
        from agentx_contracts.protocols import Judge
        from agentx_swarm.judge import PromptfooJudge

        judge: Judge | None = PromptfooJudge()
    except Exception:  # noqa: BLE001 - judge import is best-effort (tests / sandbox)
        judge = None
    watch_maturation_worker = WatchMaturationWorker(
        journal=journal,
        projection_store=projection_store,
        judge=judge,
        projections=projections,
    )

    # Replace the per-adapter in-memory store with the shared manual_tasks repo. This keeps the
    # adapters contract-pure while letting the API read what the gateway wrote.
    if database is not None:
        _replace_adapter_stores(registry, manual_tasks)

    return OperatorRuntime(
        backend=RuntimeKind(name=backend_name),
        settings=settings,
        journal=journal,
        projection_store=projection_store,
        projections=projections,
        manual_tasks=manual_tasks,
        registry=registry,
        receipts=receipts,
        vault=vault,
        gateway=gateway,
        hydration=hydration,
        settlement=settlement,
        verifier=verifier,
        continuations=continuations,
        scheduler_store=scheduler_store,
        invoker=invoker,
        worker=worker,
        watch_maturation_worker=watch_maturation_worker,
        control=control,
        review_resolver=review_resolver,
        swarm_runner=swarm_runner,
        scheduler_driver=scheduler_driver,
        runner=runner,
        harness_runner_factory=runner_factory,
        database=database,
        client=client,
    )


def _replace_adapter_stores(registry: SyscallRegistry, durable: ManualTaskRepository) -> None:
    """Point every adapter that uses a ManualTaskStore at the shared durable repo."""
    for adapter in registry.adapters():
        store = getattr(adapter, "_store", None)
        if store is not None and hasattr(store, "enqueue"):
            # The adapters carry their _store as a plain attribute set in __init__; mypy sees it
            # as missing on the Adapter Protocol. Use vars() so the assignment is type-safe.
            vars(adapter)["_store"] = durable


def _resolve_live_runner(settings: Settings) -> Any | None:
    """Build the model-driven HarnessRunner from faculty-model env, or None.

    Returns None (→ live degrades to the deterministic OwnHarness) when neither the Gemini toggle nor
    a MiniMax key is usable. Never raises: a missing-key ConfigError from build_faculty_transport is
    swallowed so the api boots without a model in dev/sim.
    """
    try:
        from agentx_kernel.hermes import build_faculty_transport
        from agentx_kernel.hermes_runner import HermesRunner

        transport = build_faculty_transport(settings)  # raises ConfigError if no usable keys
    except Exception:  # noqa: BLE001 — no model configured is a valid (sim-only) state
        return None
    return HermesRunner(transport=transport)


def _resolve_live_email_transport(supplied: Any | None) -> Any | None:
    """Pick the transport: caller-supplied (test fake) wins, else build from env, else None.

    This is the composition edge that lets the runtime auto-build a Resend transport when
    ``RUN_LIVE_EMAIL=1`` and ``RESEND_API_KEY`` are set, and otherwise stay quiet so the human_task
    tail handles send_email (invariant #5 — never returns ``None`` on resolve).
    """
    if supplied is not None:
        return supplied
    try:
        from agentx_syscall.email_transports import build_configured_email_transport
    except Exception:  # noqa: BLE001 - missing dep / sandbox: never crash bootstrap
        return None
    return build_configured_email_transport()


def _build_send_email_adapters(
    *,
    projection_store: Any,
    send_email_transport: Any | None,
) -> list[Any]:
    """Build ONE SendEmailAdapter that resolves the per-instance sender on every call.

    Phase-1 invariant #8: each instance has its own ``ChannelBinding.sender_identity``; the adapter
    looks up the right one for ``req.instance_id`` at execute time, so a single adapter handles all
    instances without ever sharing a global From address. The kernel run-loop ALSO stamps
    ``req.args["sender_identity"]`` from the instance's ``ChannelBinding``; the adapter's local
    check (``requested_sender == resolved_sender``) keeps it honest against a misbehaving harness.

    When no transport is configured (test fake absent AND no live env), no adapter is registered —
    the human_task tail handles send_email (invariant #5 — resolve never returns None).
    """
    from agentx_syscall.adapters import SendEmailAdapter

    transport = _resolve_live_email_transport(send_email_transport)
    if transport is None:
        return []

    async def _resolve_sender(instance_id: str) -> str | None:
        try:
            docs = await projection_store.find("mandate_instance", {"id": instance_id})
        except Exception:  # noqa: BLE001 - projection store best-effort
            return None
        for doc in docs:
            binding = doc.get("channel_binding") if isinstance(doc, dict) else None
            if not isinstance(binding, dict):
                continue
            sender = binding.get("sender_identity")
            if isinstance(sender, str) and sender:
                return sender
        return None

    return [
        SendEmailAdapter(
            transport=transport,
            instance_sender_resolver=_resolve_sender,
        )
    ]


def _build_send_email_adapters_sync(
    *,
    projection_store: Any,
    send_email_transport: Any | None,
    sync_docs: list[dict[str, Any]] | None = None,
) -> list[Any]:
    """Test/sync helper: same as ``_build_send_email_adapters`` but resolves senders synchronously.

    The composition edge can boot in either async (lifespan) or sync (tests) contexts; both must
    register the same SendEmailAdapter with the same resolver contract. When ``sync_docs`` is given
    (typically a list of in-memory MandateInstance dicts), the resolver looks them up locally;
    otherwise it falls back to async lookup against the projection store.
    """
    from agentx_syscall.adapters import SendEmailAdapter

    transport = _resolve_live_email_transport(send_email_transport)
    if transport is None:
        return []

    async def _resolve_sender(instance_id: str) -> str | None:
        if sync_docs is not None:
            for doc in sync_docs:
                if isinstance(doc, dict) and doc.get("id") == instance_id:
                    binding = doc.get("channel_binding")
                    if isinstance(binding, dict):
                        sender = binding.get("sender_identity")
                        if isinstance(sender, str) and sender:
                            return sender
            return None
        try:
            docs = await projection_store.find("mandate_instance", {"id": instance_id})
        except Exception:  # noqa: BLE001
            return None
        for doc in docs:
            if isinstance(doc, dict) and doc.get("id") == instance_id:
                binding = doc.get("channel_binding")
                if isinstance(binding, dict):
                    sender = binding.get("sender_identity")
                    if isinstance(sender, str) and sender:
                        return sender
        return None

    return [
        SendEmailAdapter(
            transport=transport,
            instance_sender_resolver=_resolve_sender,
        )
    ]


# Backwards-compatible alias for tests that import this directly.
_build_send_email_adapters_async = _build_send_email_adapters


class _ManualTaskStoreAdapter:
    """Bridges the existing in-memory ManualTaskStore to the ManualTaskRepository Protocol.

    Used by the memory backend (tests/sim). The Mongo backend has its own native repository.
    """

    def __init__(self, store: ManualTaskStore) -> None:
        self._store = store

    def enqueue(self, req: Any, *, source_adapter: str) -> Any:
        return self._store.enqueue(req, source_adapter=source_adapter)

    def mark_outcome(self, task_id: str, outcome: str, detail: Any = None) -> Any:
        return self._store.mark_outcome(task_id, outcome, detail)

    def get(self, task_id: str) -> Any:
        return self._store.get(task_id)

    def list_open(self) -> list[Any]:
        return self._store.list_open()

    async def aclose(self) -> None:
        return None


async def _worker_loop(runtime: OperatorRuntime, *, interval_seconds: float) -> None:
    while not runtime._stopped:
        try:
            await runtime.worker.run_once(datetime.now(UTC))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - one bad item must never kill the worker
            logger.exception("operator worker tick failed")
        # Phase-2: tick the deferred-settle worker on every loop. It scans for past-deadline
        # un-fired watches and matures whatever the scheduler hasn't yet touched. One watch per
        # tick is bounded by construction.
        try:
            await runtime.watch_maturation_worker.run_once(datetime.now(UTC))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("watch maturation tick failed")
        await asyncio.sleep(interval_seconds)


__all__ = [
    "OperatorRuntime",
    "OperatorSchedulerDriver",
    "RuntimeKind",
    "build_runtime",
    "build_lead_finder_type",
]
