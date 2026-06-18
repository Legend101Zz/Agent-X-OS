"""Enrichment faculty — reads a bounded set of plausible prospect pages."""

from __future__ import annotations

from agentx_contracts.faculty import Faculty, HarnessAdapterSpec
from agentx_contracts.syscall import SyscallRequest

from agentx_mandate.harness import Call, FacultyContext, HarnessAction
from agentx_mandate.lead_quality import is_candidate_url

FACULTY = Faculty(
    name="enrichment",
    skill_pack="skill_pack:lead-finder/enrichment@0.1.0",
    tool_manifest=["read_url"],
    eval_slice="gym:lead-finder/enrichment",
    harness_adapter=HarnessAdapterSpec(
        harness="hermes",
        native_skills_enabled=["web_research", "structured_extraction"],
        effectful_tools_to_gateway=True,
        memory_mode="per_run_scratch",
    ),
)


def propose(ctx: FacultyContext) -> list[HarnessAction]:
    raw_leads = ctx.scratchpad.get("leads")
    if not isinstance(raw_leads, list):
        return []
    actions: list[HarnessAction] = []
    for lead in raw_leads:
        if not isinstance(lead, dict):
            continue
        lead_id = lead.get("id")
        url = lead.get("url")
        title = lead.get("company")
        if (
            not isinstance(lead_id, str)
            or not isinstance(url, str)
            or not isinstance(title, str)
            or not is_candidate_url(url, title)
        ):
            continue
        actions.append(
            Call(
                request=SyscallRequest(
                    name="read_url",
                    args={"lead_id": lead_id, "url": url},
                    instance_id=ctx.instance_id,
                    run_id=ctx.run_id,
                    idempotency_key=f"{ctx.run_id}:research:read_url:{lead_id}",
                    ring=ctx.ring,
                    risk_class="read",
                )
            )
        )
        if len(actions) == 3:
            break
    return actions
