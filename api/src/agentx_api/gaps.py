from __future__ import annotations

from typing import Final

from agentx_contracts.jsontypes import JsonObject

CORE_GAPS: Final[list[JsonObject]] = [
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
]  # end CORE_GAPS — C7 (2026-06-21) closed command.edit_approval; the live /commands/edit route
#   now accepts edited_args, rewrites continuation.pending_call.args, and journals
#   ApprovalResolved(edited=True) before the same approve + enqueue path as /commands/approve.
#   The id remains in KNOWN_CLOSED below so older dashboards/fixtures still get a stable answer.


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
# Phase C7 (2026-06-21) closed command.edit_approval — /commands/edit is now a real route.
KNOWN_CLOSED: Final[frozenset[str]] = frozenset(
    {
        "command.instantiate",
        "command.trigger_run",
        "command.reject_approval",
        "command.run_swarm",
        "command.promote",
        "command.edit_approval",
        "projection.manual_queue_durable",
    }
)
