"""F3 — demand-clustering faculty (LLM-on-scratchpad).

F3 turns the F2-surviving pain clusters into MandateCandidates. The LLM
PROPOSES the candidate shape (mandate_name, who_buys_it, process_steps,
measurable done-state, input/output artifact, recurring_or_oneoff,
pain_score_0to1). The deterministic gate (``filter_mandate_candidates``)
in ``mandate_discovery_quality.py`` drops the bad shapes:

  - input_artifact == output_artifact (transformation, not process)
  - not recurring (one-off work is a feature, not a mandate)
  - pain_score < 0.4
  - mandate_name in anti-portfolio

The faculty's job is just the LLM invocation shape — read pain clusters
from scratchpad, write candidates. The gate runs AFTER.
"""

from __future__ import annotations

from agentx_contracts.faculty import Faculty, HarnessAdapterSpec, RoutingHint

from agentx_mandate.harness import FacultyContext, HarnessAction, Think

FACULTY = Faculty(
    name="mandate_discovery_demand_clustering",
    skill_pack="skill_pack:mandate-discovery/demand-clustering@0.1.0",
    tool_manifest=["llm_propose_mandate_candidates"],
    eval_slice="gym:mandate-discovery/demand-clustering",
    routing_hint=RoutingHint(strong_model=True, latency_tolerance="tolerant"),
    harness_adapter=HarnessAdapterSpec(
        harness="hermes",
        native_skills_enabled=["structured_planning", "process_modeling"],
        effectful_tools_to_gateway=True,
        memory_mode="per_run_scratch",
    ),
)


def propose(ctx: FacultyContext) -> list[HarnessAction]:
    """Record the F3 invocation in the trace; the LLM work happens in scratchpad.

    In live mode the harness's structured_planning skill reads
    ``ctx.scratchpad['pain_clusters']`` and writes
    ``ctx.scratchpad['mandate_candidates']``. In sim mode the fixture
    pre-populates the same scratchpad key. The deterministic gate
    (``filter_mandate_candidates``) runs AFTER this Think yields.
    """
    return [
        Think(
            summary="F3 demand-clustering: LLM proposes mandate candidates from pain clusters",
            detail={
                "input_key": "pain_clusters",
                "output_key": "mandate_candidates",
                "instance_id": ctx.instance_id,
                "run_id": ctx.run_id,
            },
        )
    ]
