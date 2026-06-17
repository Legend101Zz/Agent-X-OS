"""Phase-1 syscall registry bootstrap (STUB — Codex implements in Session B, PROMPT 2).

``build_phase1_registry`` returns a ``SyscallRegistry`` populated with the Phase-1 adapters and the
HumanTaskAdapter as the guaranteed terminal fallback (``is_terminal_fallback=True``) — so
``resolve`` never fails to return an adapter (invariant #5).
"""

from agentx_contracts import SyscallRegistry


def build_phase1_registry() -> SyscallRegistry:
    """Build the live Phase-1 ladder: lead_research_batch, read_url, draft_email, queue_manual_action,
    mark_outcome, + HumanTaskAdapter (tail). Session B implements; Session A raises."""
    raise NotImplementedError(
        "agentx_syscall.registry.build_phase1_registry: Codex implements the Adapter framework, "
        "the Phase-1 adapters, and the HumanTaskAdapter tail (invariant #5). Build vs FROZEN contracts."
    )
