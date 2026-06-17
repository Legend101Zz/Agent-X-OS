<!-- ───────────────────────────────────────────────────────────────────────────
  ⚠️ ROUTER (2026-06-17): this repo has TWO build lanes.
  • If your task is to CONTINUE THE KERNEL + MANDATE build (Session B handoff),
    STOP reading this file — read `HANDOFF-CODEX.md` then `CLAUDE.md`. The lane
    spec below does NOT apply to that task.
  • The spec below is the SYSCALL + SWARM lane, kept for when that work is done.
─────────────────────────────────────────────────────────────────────────── -->

# AGENTS.md — Agent-X-OS (Codex: the SYSCALL + SWARM lane)

You build the **syscall** and **swarm** halves of Agent-X Phase 1, against the FROZEN
`packages/contracts`. Hold the syscall/swarm architecture in the main thread; use git worktrees +
subagents for bounded parallel work (e.g. one adapter per worktree).

## Commands (lead with these)
```bash
# setup
uv sync                                   # install workspace (shared venv, editable members)
# test
uv run pytest                             # asyncio_mode=auto
uv run pytest packages/syscall packages/swarm
# lint / types
uv run ruff check .
uv run mypy packages/syscall packages/swarm
uv run lint-imports                       # import-linter: lane isolation + invariant #2
# eval (the Judge) — promptfoo runs as a SUBPROCESS, not a Python dep
npx promptfoo@latest eval -c promptfooconfig.yaml
```
Research-provider keys come from `.env` via `from agentx_contracts.config import get_settings`
(`EXA_API_KEY` / `FIRECRAWL_API_KEY`). Driver for any DB access is **PyMongo async** (not Motor — EOL).

## Your lane (own these; never touch the rest)
- **Own:** `packages/syscall` (the `Adapter` framework + `SyscallRegistry` + fulfillment-ladder resolution with the **HumanTaskAdapter as the tail of EVERY ladder**; health checks; fixtures; Phase-1 adapters: `lead_research_batch`, `read_url`, `draft_email` (draft mode only — no send), `queue_manual_action`, `mark_outcome`) and `packages/swarm` (Swarm REPL · scenario packs (10–30 synthetic cases) · `SimAdapter` · the **promptfoo bridge as the `Judge`** (subprocess; wire the kernel's `RunInvoker` as a promptfoo custom provider) · trace data · `PromotionGate`).
- **Read-only:** `packages/contracts`. **Never edit** `packages/kernel` or `packages/mandate` (Claude's lane). You connect to the kernel only through the Protocols: implement `Adapter`/`SyscallRegistry`/`Judge`; drive runs via `RunInvoker`.
- Wrap any MCP server **behind** the gateway's `Adapter` interface — never hand raw MCP to the harness.

## The 8 invariants — inviolable (BLUEPRINT §4)
1. No fact without a commit. 2. No credential in user space — **credentials are injected by the kernel gateway at `Adapter.execute(req, cred)`; the adapter caller/pod never holds them.** 3. No raw fact crosses customers. 4. No brain in the live kernel — **adapters are actuators, not brains: no adapter runs its own autonomous decision loop.** 5. **A syscall is intent; fulfillment is swappable; the human-task queue is always the bottom rung — nothing is ever "unimplemented"** (`is_terminal_fallback`; `SyscallRegistry.resolve` never returns None). 6. Money is API-only, idempotent, never LLM/browser (no money adapters in Phase 1). 7. **No synthetic (swarm) case may promote a customer-facing version — enforce in `PromotionGate` via `Scorecard.origin`/`EvalCase.origin`.** 8. The business is the sender of record (per-instance channel identity).

## Scope: **Phase 1 ONLY**
Lead-finder support only. **Do NOT build** money/WhatsApp/voice/browser adapters, the compiler, or any Phase 2–5 capability. Money is never an LLM or browser path.

## Discipline
Four-part per task: Goal · Context · Constraints · Done-when. Every adapter ships fixtures + a passing `health_check`. Write tests and RUN them; review your own diff against the invariants before claiming done. If `packages/contracts` seems wrong, **STOP** — it's a stop-and-coordinate event (edit contracts, both agents re-pull, resume); never edit another lane or work around the seam.
