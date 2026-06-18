"""T6 — the swarm wind-tunnel loop end-to-end, ON the kernel.

Proves the full create -> run -> judge -> gate loop joins up in ``mode="sim"``:

    candidate lead-finder MandateType
      -> SimAdapters bound, RunInvoker.invoke(mode="sim") executes ON the kernel  (produces a Trace)
      -> the promptfoo Judge grades that REAL kernel trace into a Scorecard (origin="synthetic")
      -> the PromotionGate BARS synthetic-only promotion, and would ALLOW it with real + human approval

The Judge here runs its deterministic OFFLINE path (``enabled=False``) so the loop is reproducible with
no Node/network/keys. When OPENROUTER_API_KEY + JUDGE_MODEL_ID are set the same Judge shells out to
promptfoo instead (covered by tests/.../test_phase1_swarm.py and exercised live in scripts/).
"""

import os
from datetime import UTC, datetime

import pytest
from agentx_contracts import (
    DeadlineTrigger,
    InstanceBinding,
    Rubric,
    RubricCriterion,
    Scorecard,
)
from agentx_contracts.config import Settings
from agentx_contracts.enums import Ring
from agentx_kernel.bootstrap import build_phase1_runinvoker
from agentx_mandate.library.lead_finder import build_lead_finder_type
from agentx_swarm import (
    PromotionGate,
    PromotionGateInput,
    build_promptfoo_judge,
    build_sim_registry,
    load_builtin_scenario_pack,
)

NOW = datetime(2026, 6, 17, tzinfo=UTC)


def _rubric() -> Rubric:
    # Criteria worded to match the real sim trace (a research read + a draft_email syscall).
    return Rubric(
        name="lead_quality",
        pass_threshold=0.5,
        criteria=[
            RubricCriterion(id="research", description="Performed research on candidate leads", weight=0.5),
            RubricCriterion(id="draft", description="Produced a draft email for human review", weight=0.5),
        ],
    )


def _instance(ring: Ring = "L2") -> InstanceBinding:
    return InstanceBinding(
        instance_id="inst_swarm_sim",
        type_ref="lead-finder@0.1.0",
        ring=ring,
        heap_region_id="heap_swarm",
    )


@pytest.mark.asyncio
async def test_swarm_sim_run_judged_and_gate_bars_synthetic_only() -> None:
    # --- create: a candidate + the deterministic sim registry (SimAdapters bound) ---
    pack = load_builtin_scenario_pack("indian_b2b_leads_v1")
    registry = build_sim_registry(pack)
    invoker = build_phase1_runinvoker(registry=registry)
    mandate = build_lead_finder_type()

    # --- run: ON the kernel via RunInvoker in sim mode (L2 so draft_email runs via the SimAdapter) ---
    result = await invoker.invoke(
        mandate=mandate,
        instance=_instance("L2"),
        trigger=DeadlineTrigger(ts=NOW, reason="swarm wind-tunnel sweep", entity_id="sim_icp"),
        mode="sim",
    )
    assert result.state == "settled", result.state
    assert result.settlement is not None and result.settlement.facts
    assert all(fact.provenance.run_id == result.run_id for fact in result.settlement.facts)
    # The SimAdapter actually fulfilled the effectful draft_email (proves the run executed on the kernel).
    assert any(
        event.kind == "syscall_result" and event.summary == "draft_email" for event in result.trace.events
    )

    # --- judge: grade the REAL kernel trace (offline/deterministic path) ---
    judge = build_promptfoo_judge(enabled=False, case_origin="synthetic")
    scorecard = await judge.grade(result.trace, _rubric())
    assert scorecard.run_id == result.run_id
    assert scorecard.origin == "synthetic"
    assert scorecard.passed, scorecard.failure_reasons  # the synthetic run passes the rubric

    # --- gate: a PASSING synthetic scorecard is still BARRED from customer-facing promotion ---
    gate = PromotionGate(min_score=0.5)
    blocked = gate.evaluate(PromotionGateInput(scorecards=[scorecard], human_approved=True))
    assert not blocked.allowed
    assert "synthetic-only evidence cannot promote customer-facing versions" in blocked.reasons

    # --- gate: real evidence + human approval WOULD open the gate ---
    real_pass = Scorecard(
        run_id="real_gym_case", rubric_name="lead_quality", score=0.82, passed=True, origin="real"
    )
    allowed = gate.evaluate(PromotionGateInput(scorecards=[scorecard, real_pass], human_approved=True))
    assert allowed.allowed
    assert allowed.live_ring == "L0"


@pytest.mark.live
@pytest.mark.asyncio
async def test_real_promptfoo_judge_returns_scorecard(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.environ.get("RUN_LIVE_PROMPTFOO") != "1":
        pytest.skip("set RUN_LIVE_PROMPTFOO=1 to run the real promptfoo/OpenRouter judge")

    settings = Settings()
    if not settings.judge_model_id or settings.openrouter_api_key is None:
        pytest.skip("JUDGE_MODEL_ID and OPENROUTER_API_KEY are required")
    monkeypatch.setenv("JUDGE_MODEL_ID", settings.judge_model_id)
    monkeypatch.setenv("OPENROUTER_API_KEY", settings.openrouter_api_key.get_secret_value())
    monkeypatch.delenv("FACULTY_MODEL_ID", raising=False)

    invoker = build_phase1_runinvoker(
        registry=build_sim_registry(load_builtin_scenario_pack("indian_b2b_leads_v1"))
    )
    result = await invoker.invoke(
        mandate=build_lead_finder_type(),
        instance=_instance("L2"),
        trigger=DeadlineTrigger(ts=NOW, reason="live promptfoo proof", entity_id="sim_icp"),
        mode="sim",
    )

    scorecard = await build_promptfoo_judge(enabled=True, case_origin="synthetic").grade(
        result.trace,
        _rubric(),
    )

    assert scorecard.run_id == result.run_id
    assert scorecard.rubric_name == "lead_quality"
    assert scorecard.origin == "synthetic"
    assert len(scorecard.criteria) == len(_rubric().criteria)
