# CLAUDE.md — Agent-X-OS (Claude Code: the KERNEL + MANDATE lane)

You are the brain building the **kernel** and **mandate** halves of Agent-X. Hold the architecture;
dispatch subagents for bounded parallel work; integrate.

## Read first (canonical docs live in `docs/`)
- **`docs/BLUEPRINT.md` — CANONICAL. When any doc conflicts, this wins.** Then `docs/MANDATE.md`, `docs/SYSCALLS.md`, `docs/ARCHITECTURE.md`, `docs/README.md`, `docs/BUILD-KIT.md`.
- `BUILD-PLAN.md` — your task graph, the CLAUDE/CODEX split, and each task's definition-of-done.
- `packages/contracts` — **the seam. FROZEN.** Build against it; never change it unilaterally (see "Stop-and-coordinate").

## Your lane (own these; never touch the rest)
- **Own:** `packages/kernel` (scheduler · heap+journal · verifier rules+human rungs · gateway policy: ring L0–L2, idempotency, channel-rule hooks, adapter selection via the `SyscallRegistry`/`Adapter` Protocols, credential-injection point, journaling · supervision · run-loop in **live + sim** implementing `RunInvoker` · typed command/query API) and `packages/mandate` (Type/Instance/Run · seven organs · faculties framework · memory layer · hydration · settlement engine · the four faculties: research, judgment, memory-craft, escalation).
- **Read-only:** `packages/contracts`. **Never edit** `packages/syscall` or `packages/swarm` (Codex's lane). Call adapters only through the `Adapter`/`SyscallRegistry` Protocols.

## The 8 invariants — inviolable (verbatim, BLUEPRINT §4)
1. **No fact without a commit** — every heap write is verified + provenance-stamped.
2. **No credential in user space** — every effect is a gated syscall.
3. **No raw fact crosses customers** — only graded behavior (gym) + distilled patterns (domain pack) travel between instances.
4. **No brain in the live kernel** — intelligence is gated, scoped tool calls. (The founder's **Operator Agent**, §6.1, operates the kernel from *outside* as a gated privileged user — never from within it.)
5. **A syscall is intent; fulfillment is swappable** — and the bottom rung is always a human.
6. **Money is API-only, idempotent, never LLM-executed, never browser** — L4 + human gate by default.
7. **No synthetic case promotes a customer-facing version** — the swarm pre-trains and tests; reality alone opens the gate.
8. **The business is the sender of record** — channel identity is per-instance, never shared (no shared-ban blast radius).

Structural encodings already in place (keep them honest): #2 → `agentx_mandate` may not import `agentx_contracts.security`/`config`, `agentx_db`, or `pymongo` (`tests/test_credential_boundary.py` + `.importlinter`). #1 → facts reach the heap only via the settlement engine appending a `RunSettled` event with provenance. #5 → `Adapter.is_terminal_fallback` + `SyscallRegistry.resolve` never returns None.

## Scope rule: **Phase 1 ONLY** (BLUEPRINT §7)
One lead-finder mandate · manual projection · rings L0–L2 · MongoDB + worker loop. **Do NOT build ahead:** no money, WhatsApp, voice, browser-as-default, ads, or compiler. The architecture makes Phases 2–5 additions, never rewrites — there is zero cost to deferring and real cost to building early.

## Commands
```bash
uv sync                       # install the workspace (shared venv, editable members)
uv run pytest                 # run tests (asyncio_mode=auto)
uv run mypy packages/contracts packages/kernel packages/mandate
uv run ruff check .           # lint
uv run lint-imports           # import-linter: invariant #2 + lane isolation
```
Config loader: `from agentx_contracts.config import get_settings` (reads `.env`; kernel/infra only — never from a pod). Driver: **PyMongo async `AsyncMongoClient`** (not Motor — EOL).

## Stop-and-coordinate (the seam is sacred)
If you discover `packages/contracts` is wrong: **STOP.** Do not work around it. It is a coordination event — edit `contracts`, both agents re-pull, then resume. Contract changes merge first. No agent edits the other's package.

## Subagents (`.claude/agents/`)
`kernel-module-builder` (opus) · `faculty-builder` (sonnet) · `test-writer` (sonnet) · `contract-guardian` (opus, read-only) · `doc-researcher` (haiku). Use the superpowers skills: test-driven-development, writing-plans, subagent-driven-development, using-git-worktrees, verification-before-completion. **Verify by running** (paste output) before claiming anything done.
