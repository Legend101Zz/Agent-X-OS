"""promptfoo Judge bridge (STUB — Codex implements in Session B, PROMPT 2).

``build_promptfoo_judge`` returns a ``Judge`` that runs promptfoo as a subprocess
(``npx promptfoo@latest eval ...``) with the kernel's ``RunInvoker`` wired as a Python custom
provider (``file://kernel_provider.py`` → ``call_api(prompt, options, context) -> {"output": ...}``).
The same engine powers the swarm (synthetic cases) AND the real gym's promotion gate.
"""

from agentx_contracts import Judge


def build_promptfoo_judge() -> Judge:
    """Build the promptfoo-backed Judge. Session B implements; Session A raises."""
    raise NotImplementedError(
        "agentx_swarm.judge.build_promptfoo_judge: Codex wires promptfoo (subprocess) as the Judge "
        "rung and enforces the PromotionGate (synthetic barred — invariant #7). Build vs FROZEN contracts."
    )
