"""F4 — competitor-stress-test faculty.

For each mandate candidate, F4 emits a READ intent (``competitor_search``)
that the gateway fulfils via web search / ProductHunt / G2 / Exa. The result
populates ``ctx.scratchpad['moat_assessments']`` with:

  - existing_solutions (direct competitors + adjacent tools + workarounds)
  - saturation_score_0to1
  - defensibility_0to1
  - differentiation_axis
  - build_cost_estimate_story_points

The deterministic gate (``filter_moat_assessments``) drops the saturated+no-moat
dead-zone: saturation > 0.7 AND defensibility < 0.3.

Faculty responsibility is bounded: F4 only proposes the read intent; the LLM's
moat assessment happens in scratchpad (the harness reads the search results
and writes the moat dicts).
"""

from __future__ import annotations

from typing import cast

from agentx_contracts.faculty import Faculty, HarnessAdapterSpec
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.syscall import SyscallRequest

from agentx_mandate.harness import Call, FacultyContext, HarnessAction

FACULTY = Faculty(
    name="mandate_discovery_competitor_stress",
    skill_pack="skill_pack:mandate-discovery/competitor-stress@0.1.0",
    tool_manifest=["competitor_search"],
    eval_slice="gym:mandate-discovery/competitor-stress",
    harness_adapter=HarnessAdapterSpec(
        harness="hermes",
        native_skills_enabled=["web_research", "structured_comparison", "exa_search"],
        effectful_tools_to_gateway=True,
        memory_mode="per_run_scratch",
    ),
)


def propose(ctx: FacultyContext) -> list[HarnessAction]:
    """Emit one ``competitor_search`` Call per surviving mandate candidate.

    In sim mode the candidate IDs are pre-known; the gateway routes per
    candidate to the right adapter (web_search for saturation signal, exa_search
    for adjacent tools, g2_reviews for buyer-reported weaknesses). The result
    is the moat_assessments dict the playbook reads AFTER this Call surfaces.
    """
    raw_candidates = ctx.scratchpad.get("mandate_candidates", [])
    candidate_ids: list[str] = []
    if isinstance(raw_candidates, list):
        for c in raw_candidates:
            if isinstance(c, dict):
                cid = c.get("candidate_id") or c.get("mandate_name")
                if isinstance(cid, str) and cid:
                    candidate_ids.append(cid)
    if not candidate_ids:
        return []  # nothing to assess — F3 didn't produce any candidates
    args = cast(JsonObject, {
        "candidate_ids": candidate_ids,
        "include_pricing": True,
        "include_weaknesses": True,
    })
    return [
        Call(
            request=SyscallRequest(
                name="competitor_search",
                args=args,
                instance_id=ctx.instance_id,
                run_id=ctx.run_id,
                idempotency_key=f"{ctx.run_id}:md:f4:competitor_search",
                ring=ctx.ring,
                risk_class="read",
            )
        )
    ]
