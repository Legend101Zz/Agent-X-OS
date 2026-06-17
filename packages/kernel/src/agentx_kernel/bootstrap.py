"""Phase-1 kernel bootstrap — the entry point the integration seam-proof drives.

STUB (Session A): ``build_phase1_runinvoker`` raises ``NotImplementedError`` describing the seam.
Session B (PROMPT 1) replaces the body with the real wiring: scheduler + heap/journal (PyMongo async)
+ verifier + gateway (calling the ``SyscallRegistry`` from ``agentx_syscall``) + the live/sim run-loop.
"""

from agentx_contracts import RunInvoker, SyscallRegistry

SEAM_PROOF_TODO = (
    "Phase-1 seam NOT IMPLEMENTED. Target (tests/integration/test_seam_proof.py):\n"
    "  candidate lead-finder MandateType\n"
    "    -> kernel RunInvoker.invoke(mode='sim') hydrates a frozen snapshot from the heap\n"
    "    -> a faculty proposes a syscall (intent) via its tool_manifest\n"
    "    -> the GATEWAY ring-checks; at L1 it PARKS for a human approval card\n"
    "    -> approval resumes the run; the effect executes (idempotent) and is journaled\n"
    "    -> SETTLEMENT commits ONE atomic RunSettled event (facts w/ provenance, trust, billing, watch)\n"
    "    -> the swarm's promptfoo Judge grades the trace into a Scorecard\n"
    "Implement in agentx_kernel (Claude) + agentx_syscall/agentx_swarm (Codex). Build vs FROZEN contracts."
)


def build_phase1_runinvoker(registry: SyscallRegistry | None = None) -> RunInvoker:
    """Construct the Phase-1 live/sim ``RunInvoker`` wired to the syscall ``registry``.

    Session B: in ``sim`` mode the swarm passes a registry of SimAdapters; in ``live`` mode the kernel
    passes the production registry. The loop is identical — only the registry differs.
    """
    raise NotImplementedError(SEAM_PROOF_TODO)
