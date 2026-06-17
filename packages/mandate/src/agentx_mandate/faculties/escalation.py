"""Escalation faculty — converts supervised errors into upward crash actions."""

from __future__ import annotations

from agentx_contracts.faculty import Faculty, HarnessAdapterSpec

from agentx_mandate.harness import Escalate, FacultyContext, HarnessAction

FACULTY = Faculty(
    name="escalation",
    skill_pack="skill_pack:lead-finder/escalation@0.1.0",
    tool_manifest=[],
    eval_slice="gym:lead-finder/escalation",
    harness_adapter=HarnessAdapterSpec(
        harness="hermes",
        native_skills_enabled=["failure_summarization"],
        effectful_tools_to_gateway=True,
        memory_mode="per_run_scratch",
    ),
)


def propose(ctx: FacultyContext) -> list[HarnessAction]:
    if ctx.error is None:
        return []
    return [
        Escalate(
            reason=ctx.error,
            detail={
                "instance_id": ctx.instance_id,
                "run_id": ctx.run_id,
            },
        )
    ]
