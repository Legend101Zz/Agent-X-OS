"""agentx_swarm — CODEX LANE (Session B).

The Swarm REPL: scenario packs (10–30 synthetic lead/company cases), the SimAdapter (simulated
counterparties + sandboxed syscalls, bound in sim mode), the promptfoo bridge as the ``Judge`` (run
promptfoo as a SUBPROCESS; wire the kernel's ``RunInvoker`` as a promptfoo custom provider), trace
data for a viewer, and the PromotionGate (synthetic cases BARRED from real promotion — invariant #7).

Implements ``agentx_contracts.Judge``; drives the kernel via ``agentx_contracts.RunInvoker``. Build
against the FROZEN contracts only. See AGENTS.md and BUILD-PLAN.md.
"""
