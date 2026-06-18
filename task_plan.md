# Task Plan — Session F · STEP A (G1): make the LLM actually drive the run loop

## Goal (one sentence)
The live kernel stays dumb/deterministic, but its trajectory comes from `HarnessRunner.step(observation)`
where MiniMax emits Think/Call/Claim/Finish and the kernel DISPOSES (ring-checks + journals effectful
Calls, fulfils reads + traces, feeds SyscallResult back) — replacing the hardcoded faculty order + hardcoded
draft. LLM proposes; deterministic code disposes (invariant #4).

## Hard constraints
- TDD. Offline gate + seam proof GREEN at every step; commit-as-you-go; push to main after each major proof.
- Do NOT touch `packages/contracts`. Keep `agentx_kernel` lane-pure; `lint-imports` stays 3/3.
- `tests/integration/test_seam_proof.py` stays green on the OwnHarness double.
- Don't weaken tests. External/web content (MiniMax API research) → findings.md ONLY.
- Live runs cost real money (authorized). Judge lead quality HONESTLY vs the rubric; don't overclaim.
- Integration model: push DIRECTLY to main (no PR). Working in main checkout, gate-green before each push.

## Architecture decisions (verified against tree)
- Live Hermes runner lives kernel-side (`agentx_kernel`, needs creds), implements the mandate-defined
  `HarnessRunner` Protocol (kernel→mandate import is allowed).
- Lead-finder PLAYBOOK = a GENERATOR over the shared-by-reference `ctx`: each `yield` of a read Call
  suspends until the run-loop fulfils it (mutating `ctx.scratchpad`), so downstream faculties see leads.
- Move the hardcoded draft (`_first_lead_id`/`_draft_args`) OUT of run_loop INTO the mandate playbook.
- mode selects: live → HermesRunner + live registry; sim → OwnHarness(playbook) + sim registry.
- `OwnHarness(recorded=...)` path + all existing harness tests stay byte-for-byte green.

## Phases
- [ ] **F0 — Baseline gate** GREEN (mypy --strict / ruff / pytest -q / lint-imports). Record in proof doc.
- [ ] **F1 — Research MiniMax API** (subagent → findings.md): tool-calling vs structured output /
      response_format; reliable single-action-per-step JSON; reasoning/think field; M2 vs M3 on api.minimax.io.
- [ ] **F2 — Step-driven run loop + playbook (TDD, sim/OwnHarness FIRST)**: drive `session.step(obs)`;
      dispose Think/Call/Claim/Escalate/Finish; bound max_steps; feed SyscallResult back. Generator playbook
      in mandate. mode-select sim path. Keep seam proof + harness tests + run_loop tests green.
- [ ] **F3 — Live Hermes runner (kernel-side, TDD with fake transport)**: HermesRunner/HermesSession.step
      parses MiniMax structured output → HarnessAction. System prompt = playbook-as-instructions (form query,
      reject competitors, ground personalization in cited evidence, draft-only). Wire at edge (run_lead_finder).
- [ ] **F4 — Offline gate + seam GREEN**; commit + push to main.
- [ ] **F5 — LIVE PROOF (money, main thread)**: rerun 2 Session-E ICPs (run_lead_finder dogfood + _eval_d_inspect
      with AGENTX_EVAL_ICP_JSON vendor ICP + dental ICP). Target ≥1 founder-SENDABLE draft per ICP. Judge honestly.
- [ ] **F6 — Live Hermes gate** (RUN_LIVE_HERMES=1) + reconcile docs (flip G1; flip G4 → ✅ ONLY if truly
      sendable, else keep honest) + append progress.md.
- [ ] **F7 — SHIP**: full gate + seam green; push to main; emit next-session prompt.
- [ ] **(optional) STEP B (G2)** if context/time remain: first-class kernel parked-run resume + scheduler-min worker.

## Status
- F0 DONE: baseline gate green (mypy 91, ruff, pytest 81+2skip, lint 3/3).
- F1 DONE: MiniMax-M3 API researched → findings.md. Use OpenAI tool-calling (4 tools, tool_choice auto);
  preserve `<think>` reasoning across turns; parse tool_calls[].function.arguments (JSON string).
- F2 DONE: step-driven run loop (drives HarnessRunner.step, disposes Think/Call/Claim/Escalate/Finish,
  bound max_steps=24, feeds SyscallResult back). Lead-finder PLAYBOOK generator (mandate) + lazy
  PlaybookHarnessSession. Draft moved out of run loop → build_outreach_call. `runner` field + bootstrap arg.
- F3 DONE: kernel-side HermesRunner/HermesSession (HarnessRunner Protocol); MiniMax tool-calling → HarnessAction;
  kernel stamps fact provenance. HermesClient.complete_chat transport. 3 scripts wired to runner=HermesRunner(...).
- F4 DONE: offline gate GREEN (ruff · mypy 95 · pytest 97+2skip · lint 3/3 · seam proof green). G1 machinery
  implemented + offline-proven. Committing + pushing to main now.
Current phase: F5 — money-spending LIVE runs (2 ICPs) for the honest founder-sendable verdict.

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| (none yet) | | |
