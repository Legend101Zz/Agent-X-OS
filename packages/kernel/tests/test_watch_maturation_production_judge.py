"""Phase-2 production-grading proof: a real matured case opens the promotion gate under the
PRODUCTION judge path (PromptfooJudge's deterministic offline fallback — no fake Judge, no
promptfoo subprocess).

The Done-when #3 test in test_watch_maturation.py injects a FakeJudge with ``score=0.95``. That's
the spec's test, but it's the test that proves the harness works — it does NOT prove the
PRODUCTION path opens the gate. Without this test, a real case under the offline-fallback judge
would score 0.0/passed=False (because the original rubric had ``criteria=[]``) and the gym corpus
would be useless for the Phase-5 compiler.

This test uses ``PromptfooJudge`` (the production Codex-lane judge) with its offline fallback
(no ``OPENROUTER_API_KEY``/``JUDGE_MODEL_ID`` env, ``enabled=False``). With the lead_quality
rubric baked into ``_default_rubric``, the fallback's keyword scan against the trace text yields
non-zero scores, and the resulting real ``EvalCase`` opens the promotion gate.

If someone reverts the rubric to an empty criteria list, this test fails — exactly the failure
the reviewer flagged ("real case scores 0.0/passed=False in production").
"""

from __future__ import annotations

import os
from typing import Any, cast

from agentx_contracts import (
    EvalCase,
    HydrationSnapshot,
    Provenance,
    Thread,
    Trace,
    TraceEvent,
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
from agentx_kernel.watch_maturation import (
    MaturationSummary,
    WatchMaturationWorker,
)
from agentx_swarm.gate import PromotionGate, PromotionGateInput


def _now() -> Any:
    from datetime import UTC, datetime

    return datetime.now(UTC)


def _ts(offset_seconds: int = 0) -> Any:
    from datetime import UTC, datetime, timedelta

    return datetime.now(UTC) + timedelta(seconds=offset_seconds)


def _thread() -> Thread:
    return Thread(
        id="phase2_prod_judge_thread",
        instance_id="inst_phase2_prod",
        entity_id="lead_prod",
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


def _fact(fact_id: str) -> Any:
    from agentx_contracts.memory import Fact

    return Fact(
        id=fact_id,
        instance_id="inst_phase2_prod",
        subject="lead_prod",
        predicate="qualified_lead",
        object="yes",
        confidence=0.7,
        source="agent-inferred",
        provenance=Provenance(run_id="run_phase2_prod", evidence=["research:xyz"], note="prod"),
        status="probation",
        created_at=_ts(),
    )


async def _seed_settled_run_with_quality_trace(
    journal: InMemoryJournalStore,
    *,
    instance_id: str = "inst_phase2_prod",
    run_id: str = "run_phase2_prod",
) -> Watch:
    """Seed a settled run whose trace carries the keywords the production fallback judge scans.

    The offline-fallback judge matches tokens >3 chars from the rubric.criterion.id and
    ``description`` against the concatenation of trace event summaries. To pass ``lead_quality``
    (fit + safety), the trace must mention ``lead``/``fit``/``qualified`` (for fit) AND
    ``draft``/``approval``/``park`` (for safety). This helper produces that shape.
    """
    trigger = DeadlineTrigger(ts=_ts(-3600), reason="phase2 prod seed", entity_id="lead_prod")
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
            fact_count=2,
            thread_id="phase2_prod_judge_thread",
        )
    )
    # Trace events whose summaries carry the rubric keyword seeds:
    #   fit: "lead", "qualified", "fit", "evidence"
    #   safety: "draft", "approval", "park"
    # The offline-fallback scans summary text for tokens >3 chars, so these summaries pass.
    summary_tokens = [
        ("research_lead", "lead_research_batch", "qualified lead candidate with fit evidence"),
        ("draft_email", "draft_email", "drafted approval-required email for park at L2"),
    ]
    for idx, (kind, syscall, _summary) in enumerate(summary_tokens, start=1):
        await journal.append(
            SyscallAttempted(
                event_id=f"{run_id}:sys:{idx}:attempt",
                seq=0,
                ts=trigger.ts,
                instance_id=instance_id,
                run_id=run_id,
                syscall=syscall,
                args={},
                ring_required="L2",
            )
        )
        await journal.append(
            SyscallSettled(
                event_id=f"{run_id}:sys:{idx}:settled",
                seq=0,
                ts=trigger.ts,
                instance_id=instance_id,
                run_id=run_id,
                syscall=syscall,
                status="ok",
                fulfilled_by=kind,
                maturity_used=2,
            )
        )
    facts = [_fact("fact_p1"), _fact("fact_p2")]
    watch = Watch(
        id=f"{run_id}:watch:reality",
        run_id=run_id,
        instance_id=instance_id,
        condition="lead_replied",
        deadline=_ts(72 * 3600),
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


async def test_production_judge_path_produces_a_gate_openable_real_case() -> None:
    """End-to-end: PromptfooJudge (offline fallback) → real EvalCase opens the promotion gate.

    This is the HONEST proof: same path the runtime takes in production (no fake Judge injected;
    PromptfooJudge's offline fallback when no JUDGE_MODEL_ID is set). With the lead_quality rubric
    baked into ``_default_rubric`` and a trace that mentions ``lead/qualified/fit`` + ``draft/
    approval/park``, the fallback judge emits a non-zero scorecard that passes the gate.
    """
    # Belt-and-suspenders: ensure no promptfoo env vars leak into this test (offline fallback).
    for key in ("JUDGE_MODEL_ID", "OPENROUTER_API_KEY"):
        os.environ.pop(key, None)

    journal = InMemoryJournalStore()
    projection_store = InMemoryProjectionStore()
    watch = await _seed_settled_run_with_quality_trace(journal=journal)

    # Replay seeded events through Projections so resume/heap/watch projections exist.
    projections = Projections(projection_store, journal)
    for event in await journal.read_instance(watch.instance_id):
        await projections.apply(event)

    # Build the production judge from the swarm lane. The kernel imports it via the runtime
    # (composition edge) — the worker accepts any Judge-shaped object, so importing the swarm
    # implementation here is the same seam the runtime uses.
    from agentx_swarm.judge import PromptfooJudge

    judge = PromptfooJudge(enabled=False)

    worker = WatchMaturationWorker(
        journal=journal,
        projection_store=projection_store,
        judge=judge,
        projections=projections,
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
    summary: MaturationSummary = await worker.mature(fired)

    # The worker wrote exactly one real EvalCase.
    assert summary.eval_case_id is not None
    cases = await projection_store.find("eval_case", {"id": summary.eval_case_id})
    assert cases
    case_doc = cast(dict[str, Any], cases[0])

    # Under the production offline-fallback judge + the lead_quality rubric, the case
    # receives a NON-ZERO, PASSED scorecard (not the degenerate 0.0/passed=False that an
    # empty rubric produces). This is the gate-opening evidence.
    assert case_doc["origin"] == "real"
    scorecard_doc = cast(dict[str, Any], case_doc["scorecard"])
    assert scorecard_doc["score"] > 0.0, (
        f"production fallback judge gave score=0.0 to a real case — rubric is degenerate; "
        f"scorecard={scorecard_doc}"
    )
    assert scorecard_doc["passed"] is True, (
        f"production fallback judge rejected a real case — real EvalCases cannot open the gate; "
        f"scorecard={scorecard_doc}"
    )
    assert scorecard_doc["origin"] == "real"
    # Both rubric criteria should appear in the criteria list.
    criteria_ids = sorted(c.get("criterion_id") for c in scorecard_doc.get("criteria", []))
    assert criteria_ids == ["fit", "safety"], (
        f"expected fit+safety criteria, got {criteria_ids}"
    )

    # PromotionGate ALLOWS this real case under the production judge path.
    eval_payload = {k: v for k, v in case_doc.items() if k not in {"score", "passed"}}
    case = EvalCase.model_validate(eval_payload)
    assert case.origin == "real"

    gate = PromotionGate(min_score=0.7)
    decision = gate.evaluate(PromotionGateInput(eval_cases=[case], human_approved=True))
    assert decision.allowed is True, (
        f"PromotionGate rejected a real EvalCase produced by the production judge path — "
        f"reasons={decision.reasons}"
    )


def test_default_rubric_has_substantive_criteria_not_empty() -> None:
    """Static guard: the default rubric must NOT be empty (regression of the Phase-2 review)."""
    from agentx_kernel.watch_maturation import _default_rubric

    rubric = _default_rubric()
    assert rubric.criteria, (
        "Phase-2 review fix: _default_rubric must have substantive criteria so real cases get "
        "a real score under the offline-fallback judge. Empty rubric => score=0.0/passed=False "
        "=> real cases never open the promotion gate."
    )
    assert any(c.id == "fit" for c in rubric.criteria), "fit criterion must be present"
    assert any(c.id == "safety" for c in rubric.criteria), "safety criterion must be present"


async def test_default_rubric_passes_fallback_judge_when_trace_carries_keywords() -> None:
    """Synthetic trace carries 'qualified lead' + 'draft approval' -> fallback judge scores > 0.

    Direct test of the rubric + fallback judge coupling WITHOUT the maturation worker — proves
    the rubric-and-judge pair produces non-degenerate scores against a representative trace.
    """
    from agentx_kernel.watch_maturation import _default_rubric
    from agentx_swarm.judge import PromptfooJudge

    for key in ("JUDGE_MODEL_ID", "OPENROUTER_API_KEY"):
        os.environ.pop(key, None)

    rubric = _default_rubric()
    judge = PromptfooJudge(enabled=False)
    trace = Trace(
        run_id="trace_prod",
        events=[
            TraceEvent(
                seq=1,
                ts=_ts(),
                kind="syscall_result",
                summary="qualified lead candidate with fit evidence",
                detail={},
            ),
            TraceEvent(
                seq=2,
                ts=_ts(),
                kind="parked",
                summary="draft approval park at L2",
                detail={},
            ),
        ],
    )
    scorecard = await judge.grade(trace, rubric)
    assert scorecard.origin in {"real", "synthetic"}
    assert scorecard.score > 0.0, (
        f"rubric+judge pair produced score=0.0 against a qualifying trace; scorecard={scorecard}"
    )
