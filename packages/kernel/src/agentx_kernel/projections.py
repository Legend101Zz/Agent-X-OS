"""K2 — projection builders: fold the append-only journal into derived read-state.

Event sourcing (BLUEPRINT §2): the journal is the source of truth; heap/thread/résumé/watch/billing/
trace are projections. Each projector is an idempotent fold keyed by a deterministic id, so replaying
the journal converges — ``rebuild(instance_id)`` reconstructs a projection from events alone.

INVARIANT #1 is structural here: ``heap_fact`` is written ONLY by ``HeapProjector`` from ``RunSettled``/
``DeferredSettled`` events, and every fact carries its ``provenance``. No other projector — and no
other code path — writes the heap.
"""

from __future__ import annotations

import agentx_db.collections as c
from agentx_contracts import (
    DeferredSettled,
    JournalEvent,
    ManagerAction,
    RunCreated,
    RunSettled,
    SyscallAttempted,
    SyscallSettled,
    WatchFired,
    WatchRegistered,
)

from .ports import JournalStore, ProjectionStore


def _as_int(value: object, default: int = 0) -> int:
    """Coerce a projection-document value (typed ``object``) to ``int``, defaulting if it is not one."""
    return value if isinstance(value, int) else default


class _BaseProjector:
    """Common fold machinery: subclasses set ``target_collection`` and override ``apply``."""

    target_collection: str = ""

    def __init__(self, store: ProjectionStore, journal: JournalStore) -> None:
        self._store = store
        self._journal = journal

    async def apply(self, event: JournalEvent) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    async def rebuild(self, instance_id: str) -> None:
        for event in await self._journal.read_instance(instance_id):
            await self.apply(event)


class HeapProjector(_BaseProjector):
    """journal (RunSettled/DeferredSettled) → ``heap_fact`` — facts with provenance (invariant #1)."""

    target_collection = c.HEAP_FACT

    async def apply(self, event: JournalEvent) -> None:
        if isinstance(event, RunSettled):
            for fact in event.facts:
                await self._store.upsert(c.HEAP_FACT, fact.id, fact.model_dump(mode="json"))
        elif isinstance(event, DeferredSettled):
            for fid in event.promoted_fact_ids:
                doc = await self._store.get(c.HEAP_FACT, fid)
                if doc is not None:
                    doc["status"] = "promoted"
                    await self._store.upsert(c.HEAP_FACT, fid, doc)


class TraceProjector(_BaseProjector):
    """journal (Syscall* events) → ``syscall_trace`` — the auditable effect ledger per run."""

    target_collection = c.SYSCALL_TRACE

    async def apply(self, event: JournalEvent) -> None:
        if isinstance(event, SyscallAttempted):
            await self._store.upsert(
                c.SYSCALL_TRACE,
                event.event_id,
                {
                    "id": event.event_id, "run_id": event.run_id, "instance_id": event.instance_id,
                    "kind": "attempt", "syscall": event.syscall, "args": event.args,
                    "ring_required": event.ring_required, "seq": event.seq, "ts": event.ts.isoformat(),
                },
            )
        elif isinstance(event, SyscallSettled):
            await self._store.upsert(
                c.SYSCALL_TRACE,
                event.event_id,
                {
                    "id": event.event_id, "run_id": event.run_id, "instance_id": event.instance_id,
                    "kind": "settled", "syscall": event.syscall, "status": event.status,
                    "fulfilled_by": event.fulfilled_by, "maturity_used": event.maturity_used,
                    "output": event.output,
                    "seq": event.seq, "ts": event.ts.isoformat(),
                },
            )


class WatchProjector(_BaseProjector):
    """journal (WatchRegistered/WatchFired) → ``watch`` — drives deferred (reality-rung) settlement."""

    target_collection = c.WATCH

    async def apply(self, event: JournalEvent) -> None:
        if isinstance(event, WatchRegistered):
            await self._store.upsert(
                c.WATCH,
                event.watch_id,
                {
                    "id": event.watch_id, "run_id": event.run_id, "instance_id": event.instance_id,
                    "condition": event.condition, "deadline": event.deadline.isoformat(),
                    "status": "pending",
                },
            )
        elif isinstance(event, WatchFired):
            doc = await self._store.get(c.WATCH, event.watch_id)
            if doc is not None:
                doc["status"] = "fired"
                doc["outcome"] = event.outcome
                await self._store.upsert(c.WATCH, event.watch_id, doc)


class BillingProjector(_BaseProjector):
    """journal (RunSettled.billing_amount) → ``billing_line`` — the atom of every P&L query."""

    target_collection = c.BILLING_LINE

    async def apply(self, event: JournalEvent) -> None:
        if isinstance(event, RunSettled) and event.billing_amount is not None:
            await self._store.upsert(
                c.BILLING_LINE,
                event.run_id or event.event_id,
                {
                    "id": event.run_id or event.event_id, "run_id": event.run_id,
                    "instance_id": event.instance_id, "amount": event.billing_amount,
                    "currency": "INR", "description": "run settlement", "ts": event.ts.isoformat(),
                },
            )


class ResumeProjector(_BaseProjector):
    """journal (RunSettled trust deltas / set_ring ManagerAction) → ``resume`` — earned authority."""

    target_collection = c.RESUME

    async def apply(self, event: JournalEvent) -> None:
        if isinstance(event, RunSettled):
            prior = await self._store.get(c.RESUME, event.instance_id)
            trust, streak, settled, ring = 0, 0, 0, "L0"
            if prior is not None:
                trust = _as_int(prior.get("trust_score"))
                streak = _as_int(prior.get("streak"))
                ring_val = prior.get("ring")
                ring = ring_val if isinstance(ring_val, str) else "L0"
                counts = prior.get("counts")
                settled = _as_int(counts.get("settled")) if isinstance(counts, dict) else 0
            trust += event.trust_delta
            streak = streak + 1 if event.trust_delta > 0 else (0 if event.trust_delta < 0 else streak)
            settled += 1
            await self._store.upsert(
                c.RESUME,
                event.instance_id,
                {
                    "instance_id": event.instance_id, "ring": ring, "trust_score": trust,
                    "streak": streak, "counts": {"settled": settled}, "success_rates": {},
                    "updated_at": event.ts.isoformat(),
                },
            )
        elif isinstance(event, ManagerAction) and event.action == "set_ring":
            new_ring = event.detail.get("ring")
            if isinstance(new_ring, str):
                prior = await self._store.get(c.RESUME, event.instance_id) or {
                    "instance_id": event.instance_id, "trust_score": 0, "streak": 0,
                    "counts": {"settled": 0}, "success_rates": {},
                }
                prior["ring"] = new_ring
                prior["updated_at"] = event.ts.isoformat()
                await self._store.upsert(c.RESUME, event.instance_id, prior)


class ThreadProjector(_BaseProjector):
    """journal (RunCreated for an entity) → ``thread`` — minimal Phase-1 relational state per entity.

    Richer thread advancement (settlement-time ``ThreadUpdate``) needs a journal event kind that the
    frozen Phase-1 set does not carry; it is an additive, post-Phase-1 change (stop-and-coordinate).
    """

    target_collection = c.THREAD

    async def apply(self, event: JournalEvent) -> None:
        if isinstance(event, RunCreated):
            entity = event.trigger.entity_id
            if entity is not None:
                tid = f"{event.instance_id}:{entity}"
                await self._store.upsert(
                    c.THREAD,
                    tid,
                    {
                        "id": tid, "instance_id": event.instance_id, "entity_id": entity,
                        "state": "engaged", "history": [], "updated_at": event.ts.isoformat(),
                    },
                )


class Projections:
    """The projection fan-out: applies one journal event to every projector, idempotently."""

    def __init__(self, store: ProjectionStore, journal: JournalStore) -> None:
        self._journal = journal
        self.heap = HeapProjector(store, journal)
        self.trace = TraceProjector(store, journal)
        self.watch = WatchProjector(store, journal)
        self.billing = BillingProjector(store, journal)
        self.resume = ResumeProjector(store, journal)
        self.thread = ThreadProjector(store, journal)
        self._all: tuple[_BaseProjector, ...] = (
            self.heap, self.trace, self.watch, self.billing, self.resume, self.thread,
        )

    async def apply(self, event: JournalEvent) -> None:
        for projector in self._all:
            await projector.apply(event)

    async def rebuild(self, instance_id: str) -> None:
        for event in await self._journal.read_instance(instance_id):
            await self.apply(event)
