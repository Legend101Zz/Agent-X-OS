"""Research faculty — proposes the Phase-1 lead research read intent."""

from __future__ import annotations

from agentx_contracts.faculty import Faculty, HarnessAdapterSpec
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.syscall import SyscallRequest

from agentx_mandate.harness import Call, FacultyContext, HarnessAction

FACULTY = Faculty(
    name="research",
    skill_pack="skill_pack:lead-finder/research@0.1.0",
    tool_manifest=["lead_research_batch", "read_url"],
    eval_slice="gym:lead-finder/research",
    harness_adapter=HarnessAdapterSpec(
        harness="hermes",
        native_skills_enabled=["web_research", "mcp_tools"],
        effectful_tools_to_gateway=True,
        memory_mode="per_run_scratch",
    ),
)


def _target_count(target: JsonObject, default: int = 3) -> int:
    value = target.get("count")
    if isinstance(value, int) and value > 0:
        return min(value, 10)
    return default


def _prospect_subject(icp: str) -> str:
    normalized = icp.lower()
    if "dental" in normalized or "clinic" in normalized:
        return "dental clinic"
    if "agency" in normalized or "lead-finder" in normalized or "lead generation" in normalized:
        return "lead generation agency"
    return icp


def propose(ctx: FacultyContext) -> list[HarnessAction]:
    """Emit the lead-research READ INTENT only — never fabricate leads (invariant: LLM proposes,
    deterministic code disposes; real leads come from the harness/gateway, not from the faculty).

    Real leads are produced where the read is FULFILLED: in live mode the gateway routes this intent to
    the Exa/Firecrawl adapter (kernel-injected credential); in sim mode the kernel fulfills it natively
    with clearly-synthetic fixtures. Either way the leads land in ``ctx.scratchpad['leads']`` for the
    judgment + memory-craft faculties downstream.
    """
    target = dict(ctx.target)
    count = _target_count(target)
    criteria: JsonObject = {key: value for key, value in target.items() if key != "count"}
    icp = str(criteria.get("icp", "qualified B2B prospects"))
    location = str(criteria.get("location", "")).strip()
    subject = _prospect_subject(icp)
    criteria["query"] = " ".join(
        part for part in (location, subject, "official website contact book appointment consultation") if part
    )
    criteria["exclude_domains"] = [
        "youtube.com",
        "instagram.com",
        "facebook.com",
        "linkedin.com",
        "reddit.com",
        "medium.com",
    ]
    return [
        Call(
            request=SyscallRequest(
                name="lead_research_batch",
                args={"criteria": criteria, "count": count},
                instance_id=ctx.instance_id,
                run_id=ctx.run_id,
                idempotency_key=f"{ctx.run_id}:research:lead_research_batch",
                ring=ctx.ring,
                risk_class="read",
            )
        )
    ]
