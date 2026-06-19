"""Conversation faculty — interviews the operator to elicit the brief for a new mandate.

The Creator (Phase-3, BLUEPRINT §5) needs an operator-facing interview: the human describes
what they want, the faculty extracts the structured brief (goal, icp, scenario_pack, faculties).
This faculty emits a single ``Think`` action that records the interview summary in the trace;
the structured brief is built by the downstream ``scheduling`` and ``draft_candidate_type``
syscall, not fabricated here. We don't fabricate leads / briefs — that's invariant #4 (no
brain in the live kernel) and the Phase-1 discipline for ``research``.
"""

from __future__ import annotations

from typing import cast

from agentx_contracts.faculty import Faculty, HarnessAdapterSpec
from agentx_contracts.jsontypes import JsonObject

from agentx_mandate.harness import FacultyContext, HarnessAction, Think

FACULTY = Faculty(
    name="conversation",
    skill_pack="skill_pack:creator/conversation@0.1.0",
    tool_manifest=[],
    eval_slice="gym:creator/conversation",
    harness_adapter=HarnessAdapterSpec(
        harness="hermes",
        native_skills_enabled=["structured_interview"],
        effectful_tools_to_gateway=True,
        memory_mode="per_run_scratch",
    ),
)


def _summary(ctx: FacultyContext) -> str:
    """A single-line summary that the trace can render — never invents content, only the
    shape of what was asked for."""
    target = ctx.target
    icp = str(target.get("icp", "")).strip() if isinstance(target, dict) else ""
    if icp:
        return f"interview captured: brief for icp={icp!r}"
    return "interview captured: awaiting brief"


def _detail(ctx: FacultyContext) -> JsonObject:
    target = ctx.target if isinstance(ctx.target, dict) else {}
    return cast(
        JsonObject,
        {
            "interview_keys": sorted(target.keys()),
            "instance_id": ctx.instance_id,
            "run_id": ctx.run_id,
        },
    )


def propose(ctx: FacultyContext) -> list[HarnessAction]:
    return [Think(summary=_summary(ctx), detail=_detail(ctx))]
