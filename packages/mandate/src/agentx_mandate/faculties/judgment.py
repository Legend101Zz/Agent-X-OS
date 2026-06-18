"""Judgment faculty — scores cached research candidates in scratch memory."""

from __future__ import annotations

from agentx_contracts.faculty import Faculty, HarnessAdapterSpec, RoutingHint

from agentx_mandate.harness import FacultyContext, HarnessAction
from agentx_mandate.lead_quality import score_lead

FACULTY = Faculty(
    name="judgment",
    skill_pack="skill_pack:lead-finder/judgment@0.1.0",
    tool_manifest=["score_lead"],
    eval_slice="gym:lead-finder/judgment",
    routing_hint=RoutingHint(strong_model=True),
    harness_adapter=HarnessAdapterSpec(
        harness="hermes",
        native_skills_enabled=["structured_judgment"],
        effectful_tools_to_gateway=True,
        memory_mode="per_run_scratch",
    ),
)


def _lead_id(lead: object) -> str | None:
    if not isinstance(lead, dict):
        return None
    value = lead.get("id")
    return value if isinstance(value, str) else None


def propose(ctx: FacultyContext) -> list[HarnessAction]:
    raw_leads = ctx.scratchpad.get("leads")
    if not isinstance(raw_leads, list):
        return []

    scores: dict[str, dict[str, float | str]] = {}
    for lead in raw_leads:
        lead_id = _lead_id(lead)
        if lead_id is not None:
            score, reason = score_lead(lead)
            scores[lead_id] = {"score": score, "reason": reason}
    ctx.scratchpad["scores"] = scores
    return []
