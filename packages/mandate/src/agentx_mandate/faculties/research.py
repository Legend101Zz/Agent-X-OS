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


def _target_str(target: JsonObject, key: str, default: str) -> str:
    value = target.get(key)
    return value if isinstance(value, str) else default


def _target_count(target: JsonObject, default: int = 3) -> int:
    value = target.get("count")
    if isinstance(value, int) and value > 0:
        return min(value, 10)
    return default


def propose(ctx: FacultyContext) -> list[HarnessAction]:
    count = _target_count(ctx.target)
    icp = _target_str(ctx.target, "icp", "target")
    location = _target_str(ctx.target, "location", "unknown")
    leads: list[JsonObject] = [
        {
            "id": f"lead_{index}",
            "company": f"{icp} lead {index}",
            "location": location,
            "evidence": [f"lead_research_batch:{ctx.run_id}:{index}"],
        }
        for index in range(1, count + 1)
    ]
    ctx.scratchpad["leads"] = leads
    return [
        Call(
            request=SyscallRequest(
                name="lead_research_batch",
                args=dict(ctx.target),
                instance_id=ctx.instance_id,
                run_id=ctx.run_id,
                idempotency_key=f"{ctx.run_id}:research:lead_research_batch",
                ring=ctx.ring,
                risk_class="read",
            )
        )
    ]
