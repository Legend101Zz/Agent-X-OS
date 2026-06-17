"""agentx_kernel — CLAUDE LANE (Session B).

The live, deterministic kernel: scheduler, heap+journal, verifier (rules+human rungs), gateway
(ring/idempotency/channel-rules/adapter-selection/cred-injection/journaling), supervision, the
run-loop in BOTH live and sim modes (implements ``RunInvoker``), and a typed command/query API.

Session A scaffold: entry points are stubs raising ``NotImplementedError``. Build against the FROZEN
``agentx_contracts`` only. See CLAUDE.md (lane + invariants) and BUILD-PLAN.md (task graph).
"""
