"""SwarmRunner — drive one sim swarm run from the API composition edge.

This wraps the already-proven swarm loop (``tests/integration/test_swarm_end_to_end.py``) behind a
single ``run`` call so ``POST /commands/run-swarm`` can compose it:

    load_builtin_scenario_pack(pack_id)
      -> build_sim_registry(pack)                       (deterministic SimAdapter)
      -> build_phase1_runinvoker(registry=...)          (a SECOND, sim-bound invoker)
      -> invoker.invoke(mandate, instance, trigger, mode="sim")   -> RunResult + Trace
      -> build_promptfoo_judge(...).grade(trace, rubric)          -> Scorecard(origin="synthetic")
      -> PromotionGate.evaluate(...)                              -> PromotionDecision (BARS synthetic)

The sim invoker is fully self-contained (its own in-memory journal/projections via the kernel
bootstrap), so the operator's LIVE registry and journal are never touched — every effect is fulfilled
by the ``sim_adapter``. ``agentx_api`` is the composition edge (neither lane), so importing
``agentx_swarm`` here is allowed by the import-linter lane fence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from agentx_contracts.enums import Ring
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.mandate import HydrationSnapshot, InstanceBinding, MandateType
from agentx_contracts.run import RunResult
from agentx_contracts.trigger import DeadlineTrigger
from agentx_contracts.verification import Rubric, RubricCriterion, Scorecard
from agentx_kernel.bootstrap import build_phase1_runinvoker
from agentx_mandate.faculties import get_faculty
from agentx_swarm import (
    PromotionDecision,
    PromotionGate,
    PromotionGateInput,
    build_promptfoo_judge,
    build_sim_registry,
    load_builtin_scenario_pack,
    trace_to_viewer_payload,
)


def build_lead_quality_rubric() -> Rubric:
    """The Phase-1 swarm rubric, worded to match the real sim trace (a research read + a draft_email).

    Mirrors ``tests/integration/test_swarm_end_to_end.py`` — the swarm grades the candidate's run
    against the same two checkable dimensions.
    """
    return Rubric(
        name="lead_quality",
        pass_threshold=0.5,
        criteria=[
            RubricCriterion(id="research", description="Performed research on candidate leads", weight=0.5),
            RubricCriterion(id="draft", description="Produced a draft email for human review", weight=0.5),
        ],
    )


@dataclass(frozen=True)
class SwarmRunReport:
    """Everything the route needs to persist the EvalCase and render the §5 timeline."""

    run_id: str
    type_ref: str
    pack_id: str
    trace_payload: JsonObject
    scorecard: Scorecard
    gate_decision: PromotionDecision
    hydration: HydrationSnapshot
    output: JsonObject


class SwarmRunner:
    """Composes a sim-bound run + judge + gate. Stateless: each ``run`` builds its own isolated invoker."""

    def __init__(self, *, gate: PromotionGate | None = None) -> None:
        # min_score 0.5 matches the proven integration-test gate; the synthetic bar is independent
        # of the threshold (invariant #7).
        self._gate = gate or PromotionGate(min_score=0.5)

    async def run(
        self,
        *,
        mandate: MandateType,
        pack_id: str,
        ring: Ring = "L2",
        judge_enabled: bool | None = None,
    ) -> SwarmRunReport:
        type_ref = f"{mandate.name}@{mandate.version}"
        pack = load_builtin_scenario_pack(pack_id)
        registry = build_sim_registry(pack)
        invoker = build_phase1_runinvoker(registry=registry)

        # A unique sim instance id per call keeps each run (and its derived EvalCase id) distinct.
        instance = InstanceBinding(
            instance_id=f"inst_swarm_{uuid4().hex[:10]}",
            type_ref=type_ref,
            ring=ring,
            heap_region_id="heap_swarm",
        )
        trigger = DeadlineTrigger(
            ts=datetime.now(UTC),
            reason="swarm wind-tunnel sweep",
            entity_id="sim_icp",
        )

        # Capture the REAL hydration snapshot the run starts from (empty sim heap) via the kernel's
        # own HydrationLoader — not a fabricated one. EvalCase requires a HydrationSnapshot.
        snapshot = await invoker.hydration.hydrate(
            instance_id=instance.instance_id,
            entity_id=trigger.entity_id,
            skill_pack_refs=[get_faculty(binding.faculty_name).skill_pack for binding in mandate.faculties],
            domain_pack=mandate.domain_pack,
            now=trigger.ts,
        )

        result: RunResult = await invoker.invoke(
            mandate=mandate,
            instance=instance,
            trigger=trigger,
            mode="sim",
        )

        judge = build_promptfoo_judge(enabled=judge_enabled, case_origin="synthetic")
        scorecard = await judge.grade(result.trace, build_lead_quality_rubric())

        # Evaluate the gate WITH human approval so the sole operative reason is the synthetic bar —
        # proving invariant #7 holds even when a human would otherwise approve.
        gate_decision = self._gate.evaluate(
            PromotionGateInput(scorecards=[scorecard], human_approved=True)
        )

        return SwarmRunReport(
            run_id=result.run_id,
            type_ref=type_ref,
            pack_id=pack_id,
            trace_payload=trace_to_viewer_payload(result.trace, scorecard=scorecard),
            scorecard=scorecard,
            gate_decision=gate_decision,
            hydration=snapshot,
            output=result.output,
        )


__all__ = ["SwarmRunReport", "SwarmRunner", "build_lead_quality_rubric"]
