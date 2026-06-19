"""Scheduling faculty — sets the cadence at which the Creator emits drafts.

The Creator's ``Charter.target`` carries ``cadence_days`` (how often the operator wants a
draft refreshed). The scheduling faculty reads the brief from ``ctx.target``, decides whether
to emit a draft-now ``Call`` (always — this is the Creator's heart-beat), and records the
cadence in the trace so the human reviewer sees the rhythm. The draft itself is produced by
``draft_candidate_type`` — we don't build MandateTypes in the faculty lane (that would couple
the kernel lane to the syscall lane).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agentx_contracts.faculty import Faculty, HarnessAdapterSpec
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.syscall import SyscallRequest

from agentx_mandate.harness import Call, FacultyContext, HarnessAction

FACULTY = Faculty(
    name="scheduling",
    skill_pack="skill_pack:creator/scheduling@0.1.0",
    tool_manifest=["draft_candidate_type"],
    eval_slice="gym:creator/scheduling",
    harness_adapter=HarnessAdapterSpec(
        harness="hermes",
        native_skills_enabled=["structured_planning"],
        effectful_tools_to_gateway=True,
        memory_mode="per_run_scratch",
    ),
)


def _cadence_days(target: JsonObject, default: int = 7) -> int:
    raw = target.get("cadence_days")
    if isinstance(raw, int) and 1 <= raw <= 90:
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        value = int(raw.strip())
        if 1 <= value <= 90:
            return value
    return default


def _scenario_pack(target: JsonObject) -> str:
    raw = target.get("scenario_pack")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    # Default to the swarm's built-in pack (the only one shipping today).
    return "indian-smb-leads"


def _icp(target: JsonObject) -> str:
    raw = target.get("icp")
    return raw.strip() if isinstance(raw, str) and raw.strip() else "qualified B2B prospects"


def _goal(target: JsonObject) -> str:
    raw = target.get("candidate_goal")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return f"Find and qualify leads for {_icp(target)}."


def propose(ctx: FacultyContext) -> list[HarnessAction]:
    """Emit the ``draft_candidate_type`` Call (this is the Creator's central heartbeat).

    The call's args are the structured brief assembled from ``ctx.target``:
      - ``goal`` (charter goal)
      - ``icp``, ``scenario_pack``, ``cadence_days`` (target keys)
      - ``faculties`` (the §5 set, by default — overridable from target)

    The adapter is responsible for materialising the candidate MandateType; this faculty
    NEVER builds a MandateType itself (kernel lane + mandate contract boundary).
    """
    target = ctx.target if isinstance(ctx.target, dict) else {}
    args: JsonObject = {
        "goal": _goal(target),
        "icp": _icp(target),
        "scenario_pack": _scenario_pack(target),
        "cadence_days": _cadence_days(target),
        "creator_instance_id": ctx.instance_id,
        "creator_run_id": ctx.run_id,
        "faculties": ["research", "judgment", "memory-craft", "escalation"],
        "target_schema": target,
        "now": datetime.now(UTC).isoformat(),
        "next_due_at": (datetime.now(UTC) + timedelta(days=_cadence_days(target))).isoformat(),
    }
    return [
        Call(
            request=SyscallRequest(
                name="draft_candidate_type",
                args=args,
                instance_id=ctx.instance_id,
                run_id=ctx.run_id,
                idempotency_key=f"{ctx.run_id}:creator:draft_candidate_type",
                ring=ctx.ring,
                risk_class="irreversible",
            )
        )
    ]
