"""In-memory implementations of the storage ports — fast, deterministic, no Mongo.

Used by the default test suite and by ``mode="sim"`` runs. Semantics mirror the Mongo impl exactly
(per-instance ``seq`` total order, UNIQUE idempotency, idempotent projection upserts) so a sim run
exercises the same kernel behaviour a live run does.
"""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Literal, cast

from agentx_contracts import JournalEvent
from agentx_contracts.security import Credential

from ..continuations import RunContinuation
from ..errors import DuplicateIdempotencyKey, IdempotencyRequestConflict
from ..receipts import SyscallReceipt
from ..scheduler import ApprovalWork, ScheduledWork, SchedulerWorkStatus, TriggerWork


class InMemoryJournalStore:
    """The append-only journal as a list, with a per-instance ``seq`` counter + a global idempotency set."""

    def __init__(self) -> None:
        self._events: list[JournalEvent] = []
        self._seq_by_instance: dict[str, int] = {}
        self._idem_keys: set[str] = set()

    async def append(self, event: JournalEvent) -> JournalEvent:
        key = event.idempotency_key
        if key is not None and key in self._idem_keys:
            raise DuplicateIdempotencyKey(key)
        seq = self._seq_by_instance.get(event.instance_id, 0) + 1
        stamped: JournalEvent = event.model_copy(update={"seq": seq})
        self._seq_by_instance[event.instance_id] = seq
        if key is not None:
            self._idem_keys.add(key)
        self._events.append(stamped)
        return stamped

    async def read_instance(self, instance_id: str) -> list[JournalEvent]:
        return sorted(
            (e for e in self._events if e.instance_id == instance_id),
            key=lambda e: e.seq,
        )

    async def read_run(self, run_id: str) -> list[JournalEvent]:
        return sorted(
            (e for e in self._events if e.run_id == run_id),
            key=lambda e: e.seq,
        )

    async def max_seq(self, instance_id: str) -> int:
        return self._seq_by_instance.get(instance_id, 0)


class InMemoryProjectionStore:
    """Nested ``{collection: {doc_id: document}}`` maps. Upsert replaces; find does equality matching."""

    def __init__(self) -> None:
        self._collections: dict[str, dict[str, dict[str, object]]] = {}

    async def upsert(self, collection: str, doc_id: str, document: dict[str, object]) -> None:
        self._collections.setdefault(collection, {})[doc_id] = copy.deepcopy(document)

    async def get(self, collection: str, doc_id: str) -> dict[str, object] | None:
        doc = self._collections.get(collection, {}).get(doc_id)
        return copy.deepcopy(doc) if doc is not None else None

    async def find(self, collection: str, query: dict[str, object]) -> list[dict[str, object]]:
        return [
            copy.deepcopy(doc)
            for doc in self._collections.get(collection, {}).values()
            if all(doc.get(k) == v for k, v in query.items())
        ]


class InMemorySyscallReceiptStore:
    """Process-local receipt store with the same conflict semantics as Mongo."""

    def __init__(self) -> None:
        self._receipts: dict[str, SyscallReceipt] = {}

    async def save(self, receipt: SyscallReceipt) -> None:
        prior = self._receipts.get(receipt.idempotency_key)
        if prior is not None and prior != receipt:
            raise IdempotencyRequestConflict(receipt.idempotency_key)
        self._receipts[receipt.idempotency_key] = receipt.model_copy(deep=True)

    async def get(self, idempotency_key: str) -> SyscallReceipt | None:
        receipt = self._receipts.get(idempotency_key)
        return receipt.model_copy(deep=True) if receipt is not None else None


class InMemoryRunContinuationStore:
    """Process-local continuation store with atomic replacement by run id."""

    def __init__(self) -> None:
        self._continuations: dict[str, RunContinuation] = {}

    async def save(self, continuation: RunContinuation) -> None:
        self._continuations[continuation.run_id] = continuation.model_copy(deep=True)

    async def get(self, run_id: str) -> RunContinuation | None:
        continuation = self._continuations.get(run_id)
        return continuation.model_copy(deep=True) if continuation is not None else None

    async def delete(self, run_id: str) -> None:
        self._continuations.pop(run_id, None)


class InMemorySchedulerStore:
    """Deterministic process-local scheduler queue."""

    def __init__(self) -> None:
        self._work: dict[str, ScheduledWork] = {}
        self._status: dict[str, str] = {}

    async def enqueue(self, work: ScheduledWork) -> None:
        if work.work_id not in self._work:
            self._work[work.work_id] = work.model_copy(deep=True)
            self._status[work.work_id] = "pending"

    async def claim_next(self, now: datetime) -> ScheduledWork | None:
        due = [
            work
            for work_id, work in self._work.items()
            if self._status[work_id] == "pending" and work.available_at <= now
        ]
        if not due:
            return None
        work = min(due, key=lambda item: (item.available_at, item.work_id))
        self._status[work.work_id] = "claimed"
        return work.model_copy(deep=True)

    async def complete(self, work_id: str) -> None:
        if self._status.get(work_id) == "claimed":
            self._status[work_id] = "completed"

    async def fail(self, work_id: str, *, retry_at: datetime) -> None:
        if self._status.get(work_id) == "claimed":
            work = self._work[work_id]
            self._work[work_id] = work.model_copy(update={"available_at": retry_at}, deep=True)
            self._status[work_id] = "pending"

    async def status(self, work_id: str) -> SchedulerWorkStatus | None:
        work = self._work.get(work_id)
        if work is None:
            return None
        status_value = self._status.get(work_id, "pending")
        run_id: str | None = None
        instance_id: str | None = None
        type_ref: str | None = None
        if work.kind == "trigger":
            # mypy narrows ScheduledWork -> TriggerWork via the Literal discriminator on kind,
            # so the cast is redundant for mypy but kept for clarity and to satisfy LSP type checkers.
            trigger_work = cast("TriggerWork", work)  # type: ignore[redundant-cast]
            run_id = (
                f"{trigger_work.instance.instance_id}"
                f":{trigger_work.trigger.kind}"
                f":{int(trigger_work.available_at.timestamp())}"
            )
            instance_id = trigger_work.instance.instance_id
            type_ref = trigger_work.mandate.id
        else:
            approval_work = cast("ApprovalWork", work)  # type: ignore[redundant-cast]
            run_id = approval_work.approval.run_id
            instance_id = approval_work.approval.instance_id
        return SchedulerWorkStatus(
            work_id=work.work_id,
            kind=work.kind,
            status=cast(Literal["pending", "claimed", "completed", "failed"], status_value),
            attempts=1 if status_value == "completed" else 0,
            available_at=work.available_at,
            run_id=run_id,
            instance_id=instance_id,
            type_ref=type_ref,
            updated_at=work.available_at,
        )


class InMemoryVault:
    """Phase-1 credential stub. Returns a ``manual``-kind ``Credential`` handle carrying no secret.

    Real adapters that need a secret receive ``material`` here once a real vault is wired; for Phase 1
    every effect either drafts (no secret) or lands in the human-task queue (``manual``), so an empty
    handle is correct — and it keeps the credential-injection POINT exercised end-to-end.
    """

    async def get(self, ref: str, tenant_id: str) -> Credential | None:
        return Credential(ref=ref, kind="manual", material=None)
