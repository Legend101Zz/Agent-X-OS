# Session F — STEP A (G1) Live Proof

*Companion evidence log for Session F. Goal: make the LLM actually DRIVE the run loop via
`HarnessRunner.step(observation)` (MiniMax emits Think/Call/Claim/Finish; the kernel disposes),
replacing the hardcoded faculty order + hardcoded draft. Builds on
[SESSION_E_LIVE_PROOF.md](./SESSION_E_LIVE_PROOF.md). Every command's real output is appended here as
work proceeds; pushed after each major proof.*

> Integration model: push directly to `main` (no PR), gate-green before each push, commit-as-you-go.

---

## F0 — Baseline gate (GREEN starting point)

`main` synced to `origin/main` at `95a087e` (PR #3 squash-merge of Session E). Worktrees confirmed clean.

```text
$ uv run mypy --strict packages db tests
Success: no issues found in 91 source files

$ uv run ruff check
All checks passed!

$ uv run pytest -q
81 passed, 2 skipped in 0.49s
  SKIPPED tests/integration/test_swarm_end_to_end.py  (RUN_LIVE_PROMPTFOO=1 opt-in)
  SKIPPED tests/kernel/test_hermes_client.py          (RUN_LIVE_HERMES=1 opt-in)

$ uv run lint-imports
Analyzed 83 files, 346 dependencies.
  mandate holds no credentials (invariant #2) KEPT
  Claude lane (kernel/mandate) never imports Codex lane (syscall/swarm) KEPT
  Codex lane (syscall/swarm) never imports Claude lane (kernel/mandate) KEPT
Contracts: 3 kept, 0 broken.
```

Baseline confirmed green. Build starts from here.

---

## F1 — MiniMax API research (→ findings.md "Session F")

Subagent web-research confirmed: configured `MiniMax-M3` is the correct, current model id (don't swap to M2).
For a single-action-per-step loop, use **OpenAI tool-calling with 4 function tools** (`tool_choice:"auto"`),
NOT `response_format` (silently ignored on the native endpoint for M2/M3). **Preserve `<think>` reasoning
in history across turns** (interleaved-thinking model). Parse `tool_calls[].function.arguments` (JSON string);
assistant tool-call messages have `content:null`; every `tool_call_id` needs a `role:"tool"` reply.

## F2 — Step-driven run loop + lead-finder playbook (TDD, sim/OwnHarness first)

The run loop no longer iterates a hardcoded faculty order + hardcoded draft. It now drives
`HarnessRunner.step(observation)`: disposes Think→trace, Claim→facts, Escalate→crash, Call→gateway (read =
sim-native/gateway, effectful = ring-check+journal), Finish→verify+settle. Bounded by `max_steps=24`; the
`SyscallResult` of each Call is fed back as the next observation.

- New `lead-finder PLAYBOOK` (mandate) is a GENERATOR over the shared-by-reference `ctx`: each yielded read
  Call suspends until the loop fulfils it (mutating `ctx.scratchpad`), so downstream faculties see leads. The
  hardcoded draft moved out of the kernel into `build_outreach_call`.
- New lazy `PlaybookHarnessSession` in the harness seam (recorded `_surface` path unchanged → 6 harness tests stay green).
- `mode` selects: live → injected runner; sim/default → `OwnHarness(playbook)`. `runner` field on the invoker + bootstrap arg.
- New tests: `test_lead_finder_playbook.py` (4), `test_run_loop::...disposes_an_injected_runner_trajectory...` (proves the
  trajectory comes from the runner, not a hardcoded order), `test_harness::...playbook...lazily...`.

## F3 — Live Hermes runner (kernel-side, TDD with a fake transport)

`agentx_kernel/hermes_runner.py`: `HermesRunner`/`HermesSession` implement the mandate-defined `HarnessRunner`
Protocol (kernel→mandate import is allowed; lane purity preserved). MiniMax emits one of think/call_tool/
claim_facts/finish per turn → one `HarnessAction`. The kernel STAMPS provenance on claimed facts (run_id /
created_at / status=probation — LLM proposes content, kernel disposes run-identity, invariant #1). Reasoning is
preserved across turns; `call_tool` awaits the real `SyscallResult` as its tool reply, others get a synthetic ack.
`HermesClient.complete_chat` adds the tool-calling transport. Wired into `run_lead_finder.py` + `_eval_d_inspect.py`.

- Unit tests (9, fake transport, no network): think/call_tool/claim_facts/finish parsing, risk-class classification,
  implicit-think fallback, observation feedback + reasoning preservation, and an **end-to-end offline integration**
  driving the loop in LIVE mode through read→gateway→observation→claim→LLM-authored-draft → approval park.

## F4 — Offline gate + seam GREEN (after G1 build)

```text
$ uv run ruff check            ->  All checks passed!
$ uv run mypy --strict packages db tests  ->  Success: no issues found in 95 source files
$ uv run pytest -q             ->  97 passed, 2 skipped     (was 81; +16 new tests for G1)
$ uv run lint-imports          ->  Contracts: 3 kept, 0 broken
$ uv run pytest tests/integration/test_seam_proof.py  ->  1 passed (on the OwnHarness double)
```

G1 machinery is implemented + offline-proven. **Next: F5 — money-spending LIVE runs to judge whether the
LLM-driven loop now produces a founder-SENDABLE lead per ICP (the honest quality verdict).**

---
<!-- F5..F7 live evidence appended below -->
