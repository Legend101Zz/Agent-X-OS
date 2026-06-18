from __future__ import annotations

from typing import Final

from agentx_contracts.jsontypes import JsonObject

CORE_GAPS: Final[list[JsonObject]] = [
    {
        "id": "command.edit_approval",
        "title": "Edit parked approval",
        "detail": (
            "KernelControl exposes approve only; no existing edit command resumes a parked run with edited effect args."
        ),
        "needed_core_surface": "KernelControl.edit_approval or equivalent journaled ManagerAction + resume path.",
    },
    {
        "id": "command.reject_approval",
        "title": "Reject parked approval",
        "detail": "ApprovalResolved supports reject in contracts, but KernelControl does not expose a reject command.",
        "needed_core_surface": (
            "KernelControl.reject_approval that journals ManagerAction and ApprovalResolved(decision='reject')."
        ),
    },
    {
        "id": "command.instantiate",
        "title": "Instantiate mandate type",
        "detail": "MandateInstance exists in contracts/db, but there is no existing kernel command that creates one.",
        "needed_core_surface": "Journaled instantiate command that writes the instance projection through the kernel.",
    },
    {
        "id": "command.trigger_run",
        "title": "Trigger live run",
        "detail": (
            "RunInvoker can invoke a run when handed a MandateType and InstanceBinding; no control command resolves "
            "catalog rows and starts a live run."
        ),
        "needed_core_surface": "KernelControl.trigger_run over the existing RunInvoker with a journaled ManagerAction.",
    },
    {
        "id": "command.run_swarm",
        "title": "Run swarm test from dashboard",
        "detail": (
            "Swarm tests exist in packages/swarm, but no existing control command exposes a dashboard-safe "
            "run-swarm action."
        ),
        "needed_core_surface": (
            "Journaled run_swarm command that calls the existing swarm runner and returns scorecards."
        ),
    },
    {
        "id": "command.promote",
        "title": "Promote mandate version",
        "detail": "PromotionGate exists, but no kernel control command records a promotion decision or canary ring.",
        "needed_core_surface": "Journaled promote command gated by real eval evidence and human approval.",
    },
    {
        "id": "projection.full_trace_snapshot",
        "title": "Persist full run result trace",
        "detail": (
            "RunResult.trace is rich in memory, but durable run detail must reconstruct a timeline from "
            "journal/syscall projections."
        ),
        "needed_core_surface": (
            "Optional run trace projection if the operator needs exact in-memory trace events after process exit."
        ),
    },
    {
        "id": "projection.manual_queue_durable",
        "title": "Durable manual task queue",
        "detail": (
            "ManualTaskStore is in-memory inside the syscall registry bootstrap; API can expose only the tasks "
            "queued in this process."
        ),
        "needed_core_surface": "DB-backed manual task projection/store behind the existing Adapter interface.",
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
