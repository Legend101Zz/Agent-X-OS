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
from agentx_mandate.harness import HarnessRunner
from agentx_mandate.library.lead_finder import build_lead_finder_type
from agentx_syscall import ManualTaskRepository, build_phase1_registry
from agentx_syscall.adapters import ManualTaskStore

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
    scheduler_driver: OperatorSchedulerDriver
    runner: HarnessRunner | None
    harness_runner_factory: Any | None
    database: Any | None
    client: Any | None
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
) -> OperatorRuntime:
    """Construct the live or in-memory operator runtime.

    ``runner_factory`` is a no-arg callable returning a ``HarnessRunner``. When ``None``,
    ``Phase1RunInvoker`` falls back to its OwnHarness default — appropriate for sim API + tests.
    """
    settings = settings or get_settings()
    if database is not None:
        return _compose_mongo_runtime(
            settings=settings,
            database=database,
            client=client,
            runner_factory=runner_factory,
        )
    return _compose_memory_runtime(
        settings=settings,
        database=None,
        client=None,
        runner_factory=runner_factory,
    )


def _compose_mongo_runtime(
    *,
    settings: Settings,
    database: Any,
    client: Any | None,
    runner_factory: Any | None,
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
    )


def _compose_memory_runtime(
    *,
    settings: Settings,
    database: Any | None,
    client: Any | None,
    runner_factory: Any | None,
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
) -> OperatorRuntime:
    projections = Projections(projection_store, journal)
    registry = build_phase1_registry()
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
    invoker = Phase1RunInvoker(
        journal=journal,
        projections=projections,
        hydration=hydration,
        gateway=gateway,
        settlement=settlement,
        verifier=verifier,
        continuations=continuations,
        runner=runner,
    )
    scheduler_driver = OperatorSchedulerDriver(scheduler_store)
    control = KernelControl(
        journal=journal,
        projections=projections,
        projection_store=projection_store,
        continuations=continuations,
    )
    # KernelControl implements ApprovalEnqueuer/TriggerEnqueuer via duck-typed hooks (we extend
    # resolve_approval and enqueue_trigger to call them). The driver implements the Protocols.
    # These attributes are read inside the kernel's resolve_approval / enqueue_trigger methods
    # via ``getattr(self, ...)``; mypy can't see them on the KernelControl protocol. We assign via
    # ``vars()`` so the type checker accepts the dynamic write without a suppression.
    vars(control)["_approval_enqueuer"] = scheduler_driver
    vars(control)["_trigger_enqueuer"] = scheduler_driver
    worker = SchedulerWorker(store=scheduler_store, invoker=invoker)

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
        control=control,
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
        await asyncio.sleep(interval_seconds)


__all__ = [
    "OperatorRuntime",
    "OperatorSchedulerDriver",
    "RuntimeKind",
    "build_runtime",
    "build_lead_finder_type",
]
