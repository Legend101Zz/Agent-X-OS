"""Deep-research faculty — proposes the in-OS multi-hop ``deep_research`` read intent.

A mandate binds this faculty to get a *bounded multi-hop web-research* capability:
the faculty emits a ``deep_research`` Call with a focused question; the gateway
fulfils it (Codex lane) by fanning out across Exa + Brave + Firecrawl over a
couple of hops and returning a cited *research pack*. The mandate's harness then
synthesizes that pack into a brief — every claim citing a source url. The faculty
NEVER fabricates findings (LLM proposes, deterministic code disposes); the
sources come from the gateway, not from here.
"""

from __future__ import annotations

from agentx_contracts.faculty import Faculty, HarnessAdapterSpec
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.syscall import SyscallRequest

from agentx_mandate.harness import Call, FacultyContext, HarnessAction

FACULTY = Faculty(
    name="deep_research",
    skill_pack="skill_pack:shared/deep-research@0.1.0",
    tool_manifest=["deep_research"],
    eval_slice="gym:shared/deep-research",
    harness_adapter=HarnessAdapterSpec(
        harness="hermes",
        native_skills_enabled=["web_research", "mcp_tools"],
        effectful_tools_to_gateway=True,
        memory_mode="per_run_scratch",
    ),
)


def _question_from_target(target: JsonObject) -> str:
    """Pick the research question from the target, or synthesize one from the segment/ICP."""
    explicit = target.get("research_question")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    segment = str(target.get("segment") or target.get("icp") or "").strip()
    if segment:
        return f"What are the most painful, recurring, expensive problems for {segment}, and who already sells to them?"
    return "What recurring business problems are underserved and who buys solutions for them?"


def propose(ctx: FacultyContext) -> list[HarnessAction]:
    """Emit the deep_research READ INTENT. The gateway returns a cited research pack
    into ``ctx.scratchpad['research_pack']``; downstream faculties synthesize it."""
    target = dict(ctx.target) if isinstance(ctx.target, dict) else {}
    question = _question_from_target(target)
    max_hops = target.get("deep_research_hops")
    args: JsonObject = {
        "question": question,
        "max_hops": max_hops if isinstance(max_hops, int) and 1 <= max_hops <= 3 else 2,
        "results_per_hop": 6,
        "read_top": 3,
    }
    return [
        Call(
            request=SyscallRequest(
                name="deep_research",
                args=args,
                instance_id=ctx.instance_id,
                run_id=ctx.run_id,
                idempotency_key=f"{ctx.run_id}:deep_research",
                ring=ctx.ring,
                risk_class="read",
            )
        )
    ]
