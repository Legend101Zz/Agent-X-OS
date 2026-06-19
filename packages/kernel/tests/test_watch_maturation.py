"""Phase-2 tests for the deferred-settle / WATCH -> gym maturation worker.

These tests are the spec for HERMES_BUILD_PLAN §Phase 2 (Step-D reality feedback). The kernel's
deferred-settle loop is the LAST remaining Phase-1 engine gap (G3): a matured watch (deadline fires,
or ``mark_outcome``) must promote the run's probation facts to verified, update the trust/résumé,
and emit exactly ONE ``EvalCase(origin="real")`` carrying the real scorecard + hydration snapshot.
The synthetic-origin promotion bar (invariant #7) must then ALLOW a real+human candidate.

Done-when (one assertion per test):
  1. A matured watch (simulate deadline / mark_outcome="success") -> probation facts flip to
     verified in the heap projection; a trust delta is applied to the instance résumé.
  2. Exactly ONE EvalCase(origin="real") is written for that run (count delta == 1), with the real
     scorecard + hydration snapshot.
  3. PromotionGate.evaluate(PromotionGateInput(eval_cases=[that real case], human_approved=True))
     now ALLOWS (the inverse of Session I's synthetic bar) — proving reality opens the gate.
  4. A matured watch with mark_outcome="failure" demotes/does not promote, records the negative
     case (EvalCase.origin="real" still, but trust_confirmed=False).

Full-gate green is asserted by the project-wide pytest pass; this file is the focused Phase-2 proof.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from agentx_contracts import (
    DeferredSettled,
    EvalCase,
    Fact,
    HydrationSnapshot,
    Provenance,
    Rubric,
    Scorecard,
    Thread,
    Trace,
    Watch,
    WatchFired,
    WatchRegistered,
)
from agentx_contracts.journal import RunCreated, RunHydrated, RunSettled, SyscallAttempted, SyscallSettled
from agentx_contracts.trigger import DeadlineTrigger
from agentx_kernel.projections import Projections
from agentx_kernel.stores.memory import (
    InMemoryJournalStore,
    InMemoryProjectionStore,
)
from agentx_kernel.watch_maturation import WatchMaturationWorker

# --- Fakes --------------------------------------------------------------


class FakeJudge:
    """Deterministic Judge that mirrors ``PromptfooJudge`` fallback grading."""

    def __init__(self, *, score: float = 0.95, passed: bool = True) -> None:
        self._score = score
        self._passed = passed
        self.calls = 0

    async def grade(self, trace: Trace, rubric: Rubric) -> Scorecard:
        self.calls += 1
        return Scorecard(
            run_id=trace.run_id,
            rubric_name=rubric.name,
            score=self._score,
            passed=self._passed,
            criteria=[],
        )


def _now() -> datetime:
    return datetime.now(UTC)


def _ts(offset_seconds: int = 0) -> datetime:
    return _now() + timedelta(seconds=offset_seconds)


def _thread() -> Thread:
    return Thread(
        id="thread_demo",
        instance_id="inst_phase2",
        entity_id="lead_1",
        state="engaged",
        updated_at=_ts(),
    )


def _hydration_snapshot() -> HydrationSnapshot:
    return HydrationSnapshot(
        facts=[],
        thread=_thread(),
        recent_journal=[],
        skill_pack_refs=[],
        domain_pack=None,
        frozen_at=_ts(),
    )


def _fact(fact_id: str, predicate: str = "qualified_lead", value: str = "yes") -> Fact:
    return Fact(
        id=fact_id,
        instance_id="inst_phase2",
        subject="lead_1",
        predicate=predicate,
        object=value,
        confidence=0.7,
        source="agent-inferred",
        provenance=Provenance(run_id="run_phase2", evidence=["research:abc"], note="phase2"),
        status="probation",
        created_at=_ts(),
    )


async def _seed_settled_run(
    *,
    journal: InMemoryJournalStore,
    instance_id: str = "inst_phase2",
    run_id: str = "run_phase2",
    fact_ids: tuple[str, ...] = ("fact_p1", "fact_p2"),
    watch_deadline_offset_hours: int = 72,
) -> Watch:
    """Seed the minimum journal events a maturation worker needs to operate on a real run.

    Events written:
      - RunCreated
      - RunHydrated (carries the hydration snapshot)
      - SyscallAttempted + SyscallSettled (gives the Trace at least one event)
      - RunSettled (writes the probation facts; the heap projector writes them as probation)
      - WatchRegistered (the watch is now pending)
    """
    trigger = DeadlineTrigger(ts=_ts(-3600), reason="phase2 seed", entity_id="lead_1")
    await journal.append(
        RunCreated(
            event_id=f"{run_id}:created",
            seq=0,
            ts=trigger.ts,
            instance_id=instance_id,
            run_id=run_id,
            type_ref="lead-finder@0.1.0",
            trigger=trigger,
        )
    )
    await journal.append(
        RunHydrated(
            event_id=f"{run_id}:hydrated",
            seq=0,
            ts=trigger.ts,
            instance_id=instance_id,
            run_id=run_id,
            fact_count=len(fact_ids),
            thread_id=_thread().id,
        )
    )
    await journal.append(
        SyscallAttempted(
            event_id=f"{run_id}:sys:attempt",
            seq=0,
            ts=trigger.ts,
            instance_id=instance_id,
            run_id=run_id,
            syscall="lead_research_batch",
            args={},
            ring_required="L0",
        )
    )
    await journal.append(
        SyscallSettled(
            event_id=f"{run_id}:sys:settled",
            seq=0,
            ts=trigger.ts,
            instance_id=instance_id,
            run_id=run_id,
            syscall="lead_research_batch",
            status="ok",
            fulfilled_by="lead_research_batch",
            maturity_used=3,
        )
    )
    facts = [_fact(fid) for fid in fact_ids]
    watch = Watch(
        id=f"{run_id}:watch:reality",
        run_id=run_id,
        instance_id=instance_id,
        condition="lead_replied",
        deadline=_ts(watch_deadline_offset_hours * 3600),
    )
    await journal.append(
        RunSettled(
            event_id=f"{run_id}:settled",
            seq=0,
            ts=trigger.ts,
            instance_id=instance_id,
            run_id=run_id,
            facts=facts,
            billing_amount=None,
            trust_delta=1,
            watch_ids=[watch.id],
            spawned=[],
        )
    )
    await journal.append(
        WatchRegistered(
            event_id=f"{watch.id}:registered",
            seq=0,
            ts=trigger.ts,
            instance_id=instance_id,
            run_id=run_id,
            watch_id=watch.id,
            condition=watch.condition,
            deadline=watch.deadline,
        )
    )
    return watch


async def _build_worker(
    *,
    journal: InMemoryJournalStore,
    projection_store: InMemoryProjectionStore,
    judge: FakeJudge | None = None,
    score: float = 0.95,
    passed: bool = True,
) -> tuple[WatchMaturationWorker, FakeJudge]:
    judge = judge or FakeJudge(score=score, passed=passed)
    projections = Projections(projection_store, journal)
    worker = WatchMaturationWorker(
        journal=journal,
        projection_store=projection_store,
        judge=judge,
        projections=projections,
    )
    return worker, judge


async def _seed_and_project(
    *,
    journal: InMemoryJournalStore,
    projection_store: InMemoryProjectionStore,
    watch_deadline_offset_hours: int = 72,
    fact_ids: tuple[str, ...] = ("fact_p1", "fact_p2"),
    instance_id: str = "inst_phase2",
    run_id: str = "run_phase2",
) -> Watch:
    """Seed events AND replay them through Projections so the resume/heap/watch projections exist.

    The maturation worker reads from the projections (resume trust baseline, watch deadline); the
    unit test mirrors the live flow by running the projector fold after appending events.
    """
    watch = await _seed_settled_run(
        journal=journal,
        instance_id=instance_id,
        run_id=run_id,
        watch_deadline_offset_hours=watch_deadline_offset_hours,
        fact_ids=fact_ids,
    )
    projections = Projections(projection_store, journal)
    for event in await journal.read_instance(instance_id):
        await projections.apply(event)
    return watch


# --- Done-when #1: facts flip probation -> verified; trust delta applied --------------


async def test_matured_watch_promotes_facts_and_updates_resume_trust() -> None:
    journal = InMemoryJournalStore()
    projection_store = InMemoryProjectionStore()
    watch = await _seed_and_project(journal=journal, projection_store=projection_store)
    worker, _ = await _build_worker(journal=journal, projection_store=projection_store)

    fired = WatchFired(
        event_id=f"{watch.id}:fired",
        seq=0,
        ts=_now(),
        instance_id=watch.instance_id,
        run_id=watch.run_id,
        watch_id=watch.id,
        outcome="success",
    )
    await journal.append(fired)

    summary = await worker.mature(fired)

    assert summary.trust_confirmed is True
    assert set(summary.promoted_fact_ids) == {"fact_p1", "fact_p2"}

    # Heap projection: both facts now read as promoted (verified).
    promoted_facts = await projection_store.find("heap_fact", {"status": "promoted"})
    assert {doc["id"] for doc in promoted_facts} == {"fact_p1", "fact_p2"}

    # Resume projection: RunSettled trust_delta=1 (projection baseline) + maturation +1 = 2.
    resume = cast(dict[str, Any], await projection_store.get("resume", watch.instance_id))
    assert resume is not None
    assert resume["trust_score"] == 2
    assert resume["counts"]["verified_success"] == 1

    # Journal: a DeferredSettled event was appended.
    deferred = [e for e in await journal.read_run(watch.run_id) if isinstance(e, DeferredSettled)]
    assert len(deferred) == 1
    assert deferred[0].trust_confirmed is True
    assert set(deferred[0].promoted_fact_ids) == {"fact_p1", "fact_p2"}


# --- Done-when #2: exactly ONE EvalCase(origin="real") with real scorecard + hydration -


async def test_matured_watch_emits_exactly_one_real_eval_case_with_scorecard_and_hydration() -> None:
    journal = InMemoryJournalStore()
    projection_store = InMemoryProjectionStore()
    watch = await _seed_and_project(journal=journal, projection_store=projection_store)
    worker, judge = await _build_worker(
        journal=journal, projection_store=projection_store, score=0.88, passed=True
    )

    fired = WatchFired(
        event_id=f"{watch.id}:fired",
        seq=0,
        ts=_now(),
        instance_id=watch.instance_id,
        run_id=watch.run_id,
        watch_id=watch.id,
        outcome="success",
    )
    await journal.append(fired)
    before = len(await projection_store.find("eval_case", {}))
    summary = await worker.mature(fired)
    after = len(await projection_store.find("eval_case", {}))

    # Exactly one new EvalCase row.
    assert after - before == 1
    assert summary.eval_case_id is not None

    # The persisted case has origin="real" + a real-origin scorecard + the run's hydration shape.
    cases = await projection_store.find("eval_case", {"id": summary.eval_case_id})
    assert cases, "eval_case doc missing"
    case_doc = cast(dict[str, Any], cases[0])
    assert case_doc["origin"] == "real"
    assert case_doc["scorecard"]["passed"] is True
    assert case_doc["scorecard"]["score"] == 0.88
    # Hydration: the snapshot reconstructed from the journal carries the thread (the projection
    # key is ``{instance_id}:{entity_id}`` — the live ThreadProjector sets this from the trigger).
    assert case_doc["hydration"]["thread"]["id"] == "inst_phase2:lead_1"
    assert case_doc["hydration"]["thread"]["entity_id"] == "lead_1"
    # Reality outcome stamped from the watch.
    assert case_doc["reality_outcome"] == "success"
    # Top-level score/passed for the dashboard (mirrors run-swarm write shape).
    assert case_doc["score"] == 0.88
    assert case_doc["passed"] is True
    # Judge was consulted exactly once for this run.
    assert judge.calls == 1


# --- Done-when #3: PromotionGate allows a real+human candidate -----------------------


async def test_real_eval_case_unlocks_promotion_gate() -> None:
    """Phase-2 closes the Phase-1 inverse test: the SAME gate that bars synthetic cases ALLOWS real."""
    from agentx_swarm.gate import PromotionGate, PromotionGateInput

    journal = InMemoryJournalStore()
    projection_store = InMemoryProjectionStore()
    watch = await _seed_and_project(journal=journal, projection_store=projection_store)
    worker, _ = await _build_worker(journal=journal, projection_store=projection_store)

    fired = WatchFired(
        event_id=f"{watch.id}:fired",
        seq=0,
        ts=_now(),
        instance_id=watch.instance_id,
        run_id=watch.run_id,
        watch_id=watch.id,
        outcome="success",
    )
    await journal.append(fired)
    summary = await worker.mature(fired)
    assert summary.eval_case_id is not None

    cases = await projection_store.find("eval_case", {"id": summary.eval_case_id})
    assert cases
    case_doc = cast(dict[str, Any], cases[0])
    assert case_doc["origin"] == "real"

    gate = PromotionGate(min_score=0.7)
    # Reconstruct the EvalCase from the projection doc, accepting the top-level score/passed as
    # extra metadata (the worker writes them for the dashboard; the contract field is scorecard).
    eval_payload = {k: v for k, v in case_doc.items() if k not in {"score", "passed"}}
    case = EvalCase.model_validate(eval_payload)
    assert case.origin == "real"

    decision = gate.evaluate(
        PromotionGateInput(eval_cases=[case], human_approved=True),
    )
    assert decision.allowed is True, decision.reasons


# --- Done-when #4: failure outcome does NOT promote; records the negative case ------


async def test_matured_watch_with_failure_does_not_promote_and_records_negative_case() -> None:
    journal = InMemoryJournalStore()
    projection_store = InMemoryProjectionStore()
    watch = await _seed_and_project(journal=journal, projection_store=projection_store)
    worker, _ = await _build_worker(journal=journal, projection_store=projection_store, passed=False)

    fired = WatchFired(
        event_id=f"{watch.id}:fired",
        seq=0,
        ts=_now(),
        instance_id=watch.instance_id,
        run_id=watch.run_id,
        watch_id=watch.id,
        outcome="failure",
    )
    await journal.append(fired)
    summary = await worker.mature(fired)

    # Failure: no facts promoted; trust NOT confirmed; resume trust moves DOWN.
    assert summary.trust_confirmed is False
    assert summary.promoted_fact_ids == []

    promoted = await projection_store.find("heap_fact", {"status": "promoted"})
    assert promoted == [], "failure must not promote probation facts"

    resume = cast(dict[str, Any], await projection_store.get("resume", watch.instance_id))
    assert resume is not None
    # RunSettled +1 then DeferredSettled -1 = 0 net. (Trust ladder is honest.)
    assert resume["trust_score"] == 0

    # The negative case IS recorded (so the gym has ground truth on what failed).
    cases = await projection_store.find("eval_case", {})
    assert len(cases) == 1
    case_doc = cast(dict[str, Any], cases[0])
    assert case_doc["origin"] == "real"
    assert case_doc["scorecard"]["passed"] is False
    assert case_doc["reality_outcome"] == "failure"


# --- Bonus: scan_and_emit_watch_fires converts past-deadline watches into WatchFired -


async def test_scan_picks_up_watch_with_past_deadline_and_emits_watch_fired() -> None:
    journal = InMemoryJournalStore()
    projection_store = InMemoryProjectionStore()
    # Seed a watch whose deadline is already in the past (offset = -3600s).
    watch = await _seed_and_project(
        journal=journal,
        projection_store=projection_store,
        watch_deadline_offset_hours=0,  # deadline = now
    )
    # Push the deadline into the past by overwriting the projection directly (defensive — the
    # run loop normally writes a future deadline; the test forces a past one).
    await projection_store.upsert(
        "watch",
        watch.id,
        {
            "id": watch.id,
            "run_id": watch.run_id,
            "instance_id": watch.instance_id,
            "condition": watch.condition,
            "deadline": (_now() - timedelta(hours=1)).isoformat(),
            "status": "pending",
        },
    )
    worker, _ = await _build_worker(journal=journal, projection_store=projection_store)

    fired_count = await worker.scan_and_emit_watch_fires(now=_now())
    assert fired_count == 1

    # A WatchFired event was appended to the journal with outcome="no_signal".
    fired_events = [
        e
        for e in await journal.read_instance(watch.instance_id)
        if isinstance(e, WatchFired) and e.watch_id == watch.id
    ]
    assert len(fired_events) == 1
    assert fired_events[0].outcome == "no_signal"
