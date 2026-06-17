"""K2 — projection builders fold the journal into derived state.

The DoD: applying a ``RunSettled`` updates ``heap_fact`` WITH provenance (invariant #1); every
projector is idempotent (re-applying converges); ``rebuild(instance_id)`` reconstructs a projection
from the journal alone. Syscall/watch/billing projections are exercised too.
"""

from datetime import UTC, datetime, timedelta

import agentx_db.projections as dbp
from agentx_contracts import (
    Fact,
    Provenance,
    RunCreated,
    RunSettled,
    SyscallAttempted,
    SyscallSettled,
    WatchFired,
    WatchRegistered,
)
from agentx_contracts.trigger import DeadlineTrigger
from agentx_kernel.projections import Projections
from agentx_kernel.stores.memory import InMemoryJournalStore, InMemoryProjectionStore

NOW = datetime(2026, 6, 17, tzinfo=UTC)


def _fact(fid: str = "f1") -> Fact:
    return Fact(
        id=fid,
        instance_id="inst_a",
        subject="lead_1",
        predicate="interested_in",
        object="cleaning",
        confidence=0.6,
        source="agent-inferred",
        provenance=Provenance(run_id="run_1", evidence=["trace_1"]),
        created_at=NOW,
    )


def _settled(facts: list[Fact], *, billing: float | None = None, trust: int = 0) -> RunSettled:
    return RunSettled(
        event_id="ev_settled",
        seq=0,
        ts=NOW,
        instance_id="inst_a",
        run_id="run_1",
        facts=facts,
        billing_amount=billing,
        trust_delta=trust,
    )


async def _make() -> tuple[InMemoryJournalStore, InMemoryProjectionStore, Projections]:
    journal = InMemoryJournalStore()
    store = InMemoryProjectionStore()
    return journal, store, Projections(store, journal)


async def test_runsettled_projects_fact_to_heap_with_provenance() -> None:
    journal, store, proj = await _make()
    ev = await journal.append(_settled([_fact()]))
    await proj.apply(ev)
    doc = await store.get("heap_fact", "f1")
    assert doc is not None
    assert doc["instance_id"] == "inst_a"
    assert isinstance(doc["provenance"], dict)
    assert doc["provenance"]["run_id"] == "run_1"  # invariant #1: provenance present in the heap


async def test_heap_projection_is_idempotent() -> None:
    journal, store, proj = await _make()
    ev = await journal.append(_settled([_fact()]))
    await proj.apply(ev)
    await proj.apply(ev)  # replay
    assert len(await store.find("heap_fact", {"instance_id": "inst_a"})) == 1


async def test_rebuild_replays_journal_to_reconstruct_heap() -> None:
    journal, _store, _proj = await _make()
    await journal.append(_settled([_fact("f1"), _fact("f2")]))
    fresh = InMemoryProjectionStore()
    proj2 = Projections(fresh, journal)
    await proj2.rebuild("inst_a")
    assert {d["id"] for d in await fresh.find("heap_fact", {"instance_id": "inst_a"})} == {"f1", "f2"}


async def test_syscall_events_project_to_trace() -> None:
    journal, store, proj = await _make()
    a = await journal.append(
        SyscallAttempted(
            event_id="a1", seq=0, ts=NOW, instance_id="inst_a", run_id="run_1",
            syscall="draft_email", ring_required="L2",
        )
    )
    s = await journal.append(
        SyscallSettled(
            event_id="s1", seq=0, ts=NOW, instance_id="inst_a", run_id="run_1", idempotency_key="idem-1",
            syscall="draft_email", status="ok", fulfilled_by="stub_draft", maturity_used=1,
        )
    )
    await proj.apply(a)
    await proj.apply(s)
    rows = await store.find("syscall_trace", {"run_id": "run_1"})
    assert len(rows) == 2
    assert {r["kind"] for r in rows} == {"attempt", "settled"}


async def test_watch_registered_then_fired_projection() -> None:
    journal, store, proj = await _make()
    reg = await journal.append(
        WatchRegistered(
            event_id="w1", seq=0, ts=NOW, instance_id="inst_a", run_id="run_1",
            watch_id="watch_1", condition="lead_replied", deadline=NOW + timedelta(hours=72),
        )
    )
    await proj.apply(reg)
    assert (await store.get("watch", "watch_1"))["status"] == "pending"
    fired = await journal.append(
        WatchFired(
            event_id="w2", seq=0, ts=NOW, instance_id="inst_a", run_id="run_1",
            watch_id="watch_1", outcome="replied",
        )
    )
    await proj.apply(fired)
    doc = await store.get("watch", "watch_1")
    assert doc is not None and doc["status"] == "fired" and doc["outcome"] == "replied"


async def test_runsettled_billing_line_projection() -> None:
    journal, store, proj = await _make()
    ev = await journal.append(_settled([], billing=49.0))
    await proj.apply(ev)
    rows = await store.find("billing_line", {"run_id": "run_1"})
    assert len(rows) == 1 and rows[0]["amount"] == 49.0


async def test_runcreated_touches_thread_for_entity() -> None:
    journal, store, proj = await _make()
    ev = await journal.append(
        RunCreated(
            event_id="rc1", seq=0, ts=NOW, instance_id="inst_a", run_id="run_1",
            type_ref="lead-finder@0.1.0",
            trigger=DeadlineTrigger(ts=NOW, reason="sweep", entity_id="lead_1"),
        )
    )
    await proj.apply(ev)
    rows = await store.find("thread", {"instance_id": "inst_a", "entity_id": "lead_1"})
    assert len(rows) == 1


async def test_kernel_projectors_satisfy_db_protocols() -> None:
    _journal, store, proj = await _make()
    assert isinstance(proj.heap, dbp.HeapProjector)
    assert isinstance(proj.trace, dbp.TraceProjector)
    assert isinstance(proj.watch, dbp.WatchProjector)
    assert isinstance(proj.billing, dbp.BillingProjector)
    assert isinstance(proj.resume, dbp.ResumeProjector)
    assert isinstance(proj.thread, dbp.ThreadProjector)
