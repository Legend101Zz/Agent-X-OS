<!-- ──────────────────────────────────────────────────────────────────────────
  ⚠️ UPDATED 2026-06-21 — under the Hermes-managed workflow.

  OLD model: Claude Code CLI worked the kernel/mandate lane directly.
  NEW model: HERMES (this orchestrator) is in the loop. When the task body
             for this lane comes via Kanban, it was DECIDED BY HERMES that
             Claude Code is the right engine for it. You are executing
             one of those decisions, not making routing choices yourself.

  The kernel/mandate lane is still yours. The contracts seam is still
  frozen. The gate is still law. But routing/planning/status live with
  Hermes, not with you.
────────────────────────────────────────────────────────────────────────── -->

# CLAUDE.md — Agent-X-OS (Claude Code: KERNEL + MANDATE lane)

You are the engine for the **kernel** and **mandate** halves of Agent-X. You were
chosen for this task because Hermes (the orchestrator) decided your strengths
match it: deep reasoning over Python type systems, Pydantic v2 models, async
Mongo (PyMongo async), event-sourced projections, verifier/rung design,
mandate/faculty architecture.

> **You are one engine in a fleet.** Hermes owns routing. The other engine in
> the fleet is Codex (via `agentx-codex-coder`), which handles syscall/swarm.
> Don't try to coordinate with Codex — Hermes does that.

## The seam (inviolable)

- `packages/contracts` is **FROZEN**. Build against it. If you think a contract
  is wrong, STOP and emit a `BLOCKED: contract change needed` in your handoff.
  Hermes will coordinate the stop-and-coordinated change across both engines.
- `packages/kernel` and `packages/mandate` are YOUR lane.
- You **MUST NOT** import from `agentx_syscall`, `agentx_swarm`, `agentx_db`,
  `pymongo` (the storage layer is wired in via DI at the api edge), or any
  credential/config root. Invariant #2 (no creds in user space) is enforced by
  `uv run lint-imports` and is non-negotiable.
- The api/ composition edge is **not yours**; `agentx_api` is the seam where
  lanes meet. Don't touch it from this lane.

## Stack (do not rely on memory — confirm via package files)

Python 3.12 · uv workspace · Pydantic v2 (`>=2.13`) + pydantic-settings
(`>=2.14`) · pytest 9 + pytest-asyncio (`asyncio_mode="auto"`) · ruff 0.15 ·
mypy 2.1 (strict) · PyMongo async (`pymongo>=4.17,<5`) — **not Motor, which
reached EOL 2026-05-14**. Full stack table in `BUILD-PLAN.md` §Stack.

## Commands (lead with these)

```bash
uv sync                                       # install workspace
uv run pytest -q                              # workspace tests
cd api && uv run pytest -q && cd ..            # api tests (separate)
uv run ruff check .                           # lint
uv run mypy --strict packages db tests        # workspace types
cd api && uv run mypy --strict src tests && cd ..
uv run lint-imports                           # 3 kept / 0 broken expected
```

## Per-task discipline (the four-part contract)

Every Kanban card that lands on you gives you four fields; treat them as
non-negotiable:

1. **Goal** — one sentence. What does "done" look like?
2. **Context** — files, contracts, prior decisions. Read before coding.
3. **Constraints** — the 8 invariants, the lane fence, the contracts seam,
   whatever the card body calls out.
4. **Done-when** — the assertions the gate will check. Write the failing
   tests FIRST that encode these assertions. They ARE the spec.

Then:

- Implement the smallest change to go GREEN.
- Self-review your diff against the 8 invariants (BLUEPRINT §4) and the lane
  fence (lint-imports).
- Commit small and often. Prefix `[claude]` so it's greppable.
- Mark the Kanban card `done` with `summary=` and structured `metadata=`
  (changed_files, tests_run, tests_passed, decisions) per the kanban-worker
  skill.
- If you hit a wall: STOP, emit `BLOCKED: <one-line reason>` in your
  handoff. Hermes will route the block to the operator.

## The 8 invariants (BLUEPRINT §4)

1. No fact without a commit. Every heap write is verified + provenance-stamped.
2. No credential in user space. Pods/adapters NEVER see secrets; the gateway
   injects credentials at `Adapter.execute(req, cred)` from the vault.
3. No raw fact crosses customers. Learning crosses as graded patterns only.
4. No brain in the live kernel. Adapters are actuators, not decision loops.
5. A syscall is intent; fulfillment is swappable; the human-task queue is the
   bottom rung — `SyscallRegistry.resolve` never returns None.
6. Money is API-only, idempotent, never LLM/browser. No money adapters in
   Phase 1.
7. No synthetic (swarm) case may promote a customer-facing version. Enforced
   in `PromotionGate` via `Scorecard.origin` / `EvalCase.origin`.
8. The business is the sender of record. Per-instance channel identity.

## What is already built — reuse, do NOT rebuild

Read `docs/STATE_AND_ROADMAP.md` first. The verified-current state on `main`
includes the kernel (run-loop, gateway, verifier, settlement, projections,
hydration, durable resume, scheduler worker), the four Phase-1 faculties
(research/judgment/memory-craft/escalation + enrichment), and the lead-finder
`MandateType`. Phase 1 is LIVE-PROVEN end-to-end with one real Gmail send
(2026-06-20). Read `docs/AGENTX_STATUS_V2.html` for the clickable architecture
diagram.

Do not reimplement any of the above. Extend through the existing Protocols
and registries.

## Workspace handling (from kanban-worker skill)

Tasks assigned to you will have `HERMES_KANBAN_WORKSPACE` set. The default
for the agent-x-os board is `worktree` — you'll get an isolated git worktree
at the path, and you'll create a branch (typically `wt/<task-id>`). Commit
your work there. Hermes will merge/cherry-pick back to main after review.

## Stop-and-coordinate protocol (the seam is sacred)

If you find the seam is wrong: **STOP — do not work around it.**

1. Emit `BLOCKED: contract change needed — <reason>` in your handoff.
2. Describe what should change and why in your card comment.
3. Hermes will coordinate with Codex to land the contract change FIRST,
   then re-dispatch dependent work. Both engines re-pull contracts.

That's the new flow. Old "open as a coordination event" prose in `BUILD-PLAN.md`
is superseded by this — Hermes does the cross-engine coordination now.

## Honest limits

- You do not own the dashboard. TSX/Next.js work goes to Codex or a
  Hermes-self subagent via `agentx-claude-coder` (Claude is strong on TS
  but you don't pick that — Hermes does).
- You do not own the visual status HTML. That's `agentx-status`.
- You do not own routing/planning/decomposition. That's the orchestrator.
- You DO own: kernel correctness, mandate semantics, faculty library, and
  the verifier/settlement contract.
