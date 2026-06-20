<!-- ──────────────────────────────────────────────────────────────────────────
  ⚠️ UPDATED 2026-06-21 — under the Hermes-managed workflow.

  OLD model: Codex CLI worked the syscall/swarm lane directly.
  NEW model: HERMES (this orchestrator) is in the loop. When the task body
             for this lane comes via Kanban, it was DECIDED BY HERMES that
             Codex is the right engine for it. You are executing one of those
             decisions, not making routing choices yourself.

  The syscall/swarm lane is still yours. The contracts seam is still frozen.
  The gate is still law. But routing/planning/status live with Hermes,
  not with you.
────────────────────────────────────────────────────────────────────────── -->

# AGENTS.md — Agent-X-OS (Codex: SYSCALL + SWARM lane)

You are the engine for the **syscall** and **swarm** halves of Agent-X. You
were chosen for this task because Hermes (the orchestrator) decided your
strengths match it: Python adapter frameworks, AsyncIO service code, MCP-shaped
tool manifests, deterministic sim harnesses, promptfoo-as-subprocess judge
bridges, scenario pack authoring.

> **You are one engine in a fleet.** Hermes owns routing. The other engine in
> the fleet is Claude Code (via `agentx-claude-coder`), which handles
> kernel/mandate. Don't try to coordinate with Claude Code — Hermes does that.

## The seam (inviolable)

- `packages/contracts` is **FROZEN**. Build against it. If you think a contract
  is wrong, STOP and emit `BLOCKED: contract change needed` in your handoff.
  Hermes will coordinate the stop-and-coordinated change across both engines.
- `packages/syscall` and `packages/swarm` are YOUR lane.
- You **MUST NOT** import from `agentx_kernel`, `agentx_mandate`,
  `agentx_db`, or any credential/config root. Invariant #2 (no creds in user
  space) is enforced by `uv run lint-imports`.
- The api/ composition edge is **not yours**; `agentx_api` is the seam where
  lanes meet.

## Stack

Python 3.12 · uv workspace · Pydantic v2 (`>=2.13`) · pytest 9 +
pytest-asyncio (`asyncio_mode="auto"`) · MCP SDK `mcp>=1.27,<2` · promptfoo
(npm, **runs as a subprocess — NOT a Python dep**). Provider keys: Exa
`exa-py>=2.14` · Firecrawl `firecrawl-py>=4.30`. **No Motor — EOL.**
Driver is PyMongo async via the api composition edge.

## Commands (lead with these)

```bash
uv sync
uv run pytest -q
uv run pytest packages/syscall packages/swarm
uv run ruff check .
uv run mypy --strict packages db tests
uv run lint-imports                          # 3 kept / 0 broken expected
npx promptfoo@latest eval -c promptfooconfig.yaml
```

> **Node ≥18 for promptfoo + dashboard:** prefix
> `PATH=/opt/homebrew/bin:$PATH` (system node is v16; Homebrew's is v25).

## Per-task discipline (the four-part contract)

Every Kanban card that lands on you gives you four fields; treat them as
non-negotiable:

1. **Goal** — one sentence. What does "done" look like?
2. **Context** — files, contracts, prior decisions. Read before coding.
3. **Constraints** — the 8 invariants, the lane fence, the contracts seam,
   whatever the card body calls out.
4. **Done-when** — the assertions the gate will check. Write the failing
   tests FIRST that encode these assertions.

Then:

- Implement the smallest change to go GREEN.
- Self-review your diff against the 8 invariants and the lane fence.
- Commit small and often. Prefix `[codex]` so it's greppable.
- Every adapter ships fixtures + a passing `health_check`. The
  `HumanTaskAdapter` is the guaranteed tail (`is_terminal_fallback=True`):
  `SyscallRegistry.resolve` NEVER returns None — invariant #5.
- Mark the Kanban card `done` with `summary=` and structured `metadata=`
  per the kanban-worker skill.
- If you hit a wall: STOP, emit `BLOCKED: <one-line reason>` in your
  handoff. Hermes will route the block.

## The 8 invariants (BLUEPRINT §4)

1. No fact without a commit. Every heap write is verified + provenance-stamped.
2. No credential in user space. The gateway injects credentials at
   `Adapter.execute(req, cred)` from the vault. **You may NOT import
   `agentx_contracts.security`/`config`, `agentx_db`, or `pymongo`.**
3. No raw fact crosses customers. Learning crosses as graded patterns only.
4. No brain in the live kernel. Adapters are actuators, not decision loops.
5. A syscall is intent; fulfillment is swappable; the human-task queue is the
   bottom rung — `SyscallRegistry.resolve` never returns None.
6. Money is API-only, idempotent, never LLM/browser. No money adapters in
   Phase 1.
7. No synthetic (swarm) case may promote a customer-facing version.
   Enforced in `PromotionGate` via `Scorecard.origin` / `EvalCase.origin`.
   The Creator emits **candidates only**; promote needs real+human.
8. The business is the sender of record. The send adapter MUST use the
   instance's own sender identity; idempotency MUST prevent double-send.
   See `send_email` adapter — your model for any future channel.

## What is already built — reuse, do NOT rebuild

Read `docs/STATE_AND_ROADMAP.md` first. The verified-current state on `main`
includes the syscall ladder (`_AdapterBase` in `adapters.py`,
`DraftEmailAdapter` and `SendEmailAdapter` patterns, `registry.py`'s
`build_phase1_registry`, the `human_task` terminal tail), the swarm/Foundry
(`SimAdapter`, the promptfoo `Judge` with offline fallback, `PromotionGate`,
scenario packs, `trace_to_viewer_payload`), and 8 syscall adapters including
the LIVE `send_email` via Gmail SMTP (2026-06-20 send-loop live proof).

Do not reimplement any of the above. Extend through the existing Protocols
and registries.

## Workspace handling (from kanban-worker skill)

Tasks assigned to you will have `HERMES_KANBAN_WORKSPACE` set. The default
for the agent-x-os board is `worktree` — you'll get an isolated git worktree
at the path, and you'll create a branch (typically `wt/<task-id>`). Commit
your work there. Hermes will merge/cherry-pick back to main after review.

You may use git worktrees + subagents for bounded parallel work (e.g. one
adapter per worktree). Don't try to coordinate with the kernel/mandate
lane — Hermes does that.

## Stop-and-coordinate protocol (the seam is sacred)

If you find the seam is wrong: **STOP — do not work around it.**

1. Emit `BLOCKED: contract change needed — <reason>` in your handoff.
2. Describe what should change and why in your card comment.
3. Hermes will coordinate with Claude Code to land the contract change
   FIRST, then re-dispatch dependent work.

That's the new flow. Old "open as a coordination event" prose in
`BUILD-PLAN.md` is superseded by this.

## Honest limits

- You do not own the dashboard. TSX/Next.js work goes to `agentx-claude-coder`
  (Claude is strong on TS, but you don't pick that — Hermes does).
- You do not own the visual status HTML. That's `agentx-status`.
- You do not own routing/planning/decomposition. That's the orchestrator.
- You DO own: adapter framework, registry + ladder resolution, sim
  counterparts, promptfoo bridge, scenario packs, trace data, the
  `PromotionGate`.
