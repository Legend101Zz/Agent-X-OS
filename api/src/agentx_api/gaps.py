from __future__ import annotations

from typing import Final

from agentx_contracts.jsontypes import JsonObject

CORE_GAPS: Final[list[JsonObject]] = [
    {
        "id": "command.edit_approval",
        "title": "Edit parked approval arguments",
        "detail": (
            "Approve/reject are journaled and ApprovalWork enqueued for approve, but the API does "
            "not yet expose an edit-with-modified-args path. The KernelControl.resolve_approval "
            "command already accepts an ``edited`` flag; a thin HTTP route over it is the only gap."
        ),
        "needed_core_surface": (
            "POST /commands/edit that validates edited args against the syscall schema and "
            "journals ApprovalResolved(edited=True) before the same enqueue + resume path."
        ),
    },
    {
        "id": "projection.full_trace_snapshot",
        "title": "Persist full run result trace",
        "detail": (
            "RunResult.trace is rich in memory; durable run detail currently reconstructs a "
            "timeline from journal/syscall projections."
        ),
        "needed_core_surface": (
            "Optional run trace projection if the operator needs exact in-memory trace events after "
            "process exit. Not blocking Phase 1 dashboard operability."
        ),
    },
]


def gap_by_id(gap_id: str) -> JsonObject:
    for gap in CORE_GAPS:
        if gap["id"] == gap_id:
            return gap
    return {
        "id": gap_id,
        "title": "Missing core capability",
        "detail": "This command is not exposed by the current kernel control surface.",
        "needed_core_surface": "Add a journaled kernel command before wiring this dashboard action.",
    }


# Stale ids that older dashboards or fixtures still reference. Kept here so /core-gaps returns a
# stable response — Phase H closed instantiate, trigger_run, reject_approval in the kernel.
# Phase-4 closed command.promote (HERMES_BUILD_PLAN §Phase 4 — the candidate→live bridge).
KNOWN_CLOSED: Final[frozenset[str]] = frozenset(
    {
        "command.instantiate",
        "command.trigger_run",
        "command.reject_approval",
        "command.run_swarm",
        "command.promote",
        "projection.manual_queue_durable",
    }
)
