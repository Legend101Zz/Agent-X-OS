# Session E P0/P1 Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **STATUS (2026-06-18):** Tasks 1–6 (all P0/P1 implementation) are **DONE and committed** — offline gate
> GREEN (mypy --strict 91 files, ruff, lint-imports 3/3, pytest 81 passed + 2 opt-in-live skipped). Branch
> `session-e/p0-p1-fixes` pushed; PR #3 open against `main`.
> **Task 7 (proof + docs + ship) is NOT DONE** — the previous (Codex) session ran out of context window before
> it. The remaining work is LIVE VERIFICATION (2 live ICP runs, real promptfoo on Node ≥22.22, Mongo/dashboard
> checks), doc reconciliation, and merge. See the ready-to-paste "SESSION E — FINISH" prompt handed to the user.

**Goal:** Fix the Session D correctness bugs, make Phase-1 leads actionable, prove the real promptfoo judge, and persist real mandate instances without changing frozen contracts.

**Architecture:** Keep the journal as source of truth. Use existing journal events for watches and parked intent, and a kernel-owned durable receipt store for syscall outputs that cannot fit the frozen event. Keep lead intelligence in pure mandate code: search, explicit bounded enrichment, evidence extraction, scoring, actionable-only claims, and drafts. Persist catalog type/instance state at the live kernel edge; continue deriving run summaries from the journal.

**Tech Stack:** Python 3.12, Pydantic, pytest, PyMongo async, Firecrawl/Exa, promptfoo via `npx`, Ruff, mypy strict, import-linter.

---

## Task 1: P0-1 register settlement watches — ✅ DONE (committed `796cda2`)

- [x] Add a failing test in `tests/kernel/test_settlement_commit.py` with one settlement `Watch`.
- [x] Run the focused test and confirm only `run_settled` exists.
- [x] Update `packages/kernel/src/agentx_kernel/settlement.py` to append/project `RunSettled`, then one deterministic `WatchRegistered` per watch.
- [x] Leave thread advancement explicitly deferred because the frozen Phase-1 journal has no thread-update event.
- [x] Run focused tests, seam proof, and the full gate. *(offline gate green; live settle→watch proof = Task 7)*

## Task 2: P0-2 faithful idempotency replay — ✅ DONE (committed `3d88eba`)

- [x] Add a failing gateway test asserting replay output equals the original output and one settlement exists.
- [x] Add a kernel-owned `SyscallReceiptStore` port plus memory and Mongo implementations keyed by the current globally unique idempotency key.
- [x] Store request identity and the complete `SyscallResult`; validate request identity on replay.
- [x] Return the receipt only when a matching settlement exists. Fail explicitly for legacy settled events without a receipt.
- [x] Wire the receipt store through bootstrap, live scripts, and evaluation scripts.
- [x] Run store/gateway tests, seam proof, and the full gate.

## Task 3: P0-3 truthful approval cards — ✅ DONE (committed `455271b`)

- [x] Add failing gateway tests asserting a gated call journals/reuses one `SyscallAttempted` before `RunParked`.
- [x] Add a failing control test asserting `ApprovalItem.approval_card` contains syscall, args, and idempotency key.
- [x] Add gateway `_ensure_attempt()` and return the attempt in parked outcomes; never append a second attempt on approved execution.
- [x] Build approval cards from the nearest preceding attempt for the parked run.
- [x] Update `api/src/agentx_api/state.py` to consume the direct card, with historical reverse-scan fallback.
- [x] Run kernel/API focused tests, dashboard repro, seam proof, and the full gate. *(offline; live dashboard repro = Task 7)*

## Task 4: P1-1 actionable lead pipeline — ✅ DONE (committed `c7dfcf4`)

- [x] Add failing tests for a prospect-finding query with contact intent and content-domain exclusions.
- [x] Add an enrichment faculty between research and judgment that emits at most three `read_url` calls for candidate HTTP URLs.
- [x] Add pure lead-quality helpers that reject content/competitors, extract organization, person-or-role, reachable contact path, buying signal, and cited evidence, and fail closed if incomplete.
- [x] Preserve `lead_id` through `read_url`; apply enriched output to the matching scratchpad lead in live and sim modes.
- [x] Replace flat scoring with evidence-field scoring.
- [x] Claim `qualified_lead_score` and `actionable_lead` only for complete leads; require `fact:actionable_lead exists`.
- [x] Draft only the highest-scoring actionable lead, addressing the person/role and citing the signal/contact path.
- [x] Request Firecrawl markdown during search and use official query operators; cap enrichment at three URLs.
- [x] Align draft adapter metadata to gateway L2 policy.
- [x] Run mandate/kernel/syscall tests, seam proof, swarm integration, and the full gate. *(offline; 2 live ICP proof = Task 7)*

## Task 5: P1-2 real promptfoo judge — ✅ DONE (committed `fe93d7b`)

- [x] Add failing fake-runner tests for `--output <temp>/results.json`, `llm-rubric`, and version-3 output parsing.
- [x] Generate one model-graded assertion per Agent-X rubric criterion and use the configured judge provider.
- [x] Parse promptfoo result-file assertion grades into `CriterionResult`, weighted score, comments, and failure reasons.
- [x] Add `RUN_LIVE_PROMPTFOO=1` integration coverage; bridge `.env` only at the script/test edge.
- [x] Preserve the offline fallback.
- [x] Run promptfoo config validation, swarm tests, real judge proof, and the full gate. *(offline + fake-runner; REAL npx judge on Node ≥22.22 = Task 7)*

## Task 6: P1-3 persist mandate instances — ✅ DONE (committed `bd63c6f`)

- [x] Add failing registry tests for type registration, instantiate/get/list, idempotency, and conflicts.
- [x] Implement projection-backed `MandateRegistry` in the kernel.
- [x] Expose register/instantiate/list operations through `KernelControl`.
- [x] At the live edge, persist the canonical type and a full `MandateInstance`, then derive `InstanceBinding`; mutate only a customer-target copy.
- [x] Do not duplicate `MANDATE_RUN`: dashboard run summaries already fold the journal, while durable run checkpoints belong to G2 resume.
- [x] Add API coverage proving `/instances` exposes a non-demo persisted instance. *(test-level done; live Mongo/dashboard proof = Task 7)*
- [x] Run focused/API tests, seam proof, and the full gate.

## Task 7: proof, docs, and ship — ⏳ NOT DONE (Codex ran out of context here; next session)

- [ ] Run P0 repro scripts and verify watch existence, faithful replay, and truthful draft card.
- [ ] Run two live ICPs and require at least one real actionable lead and sendable draft per run before closing G4.
- [ ] Run the real promptfoo judge on Node `v24.13.1` (Session D had v20.18.0 — switch first).
- [ ] Verify Mongo and dashboard contain the real mandate instance.
- [ ] Update `docs/EVAL_FINDINGS.md` and `docs/STATE_AND_ROADMAP.md` only with proven claims.
- [ ] Run mypy, Ruff, full pytest, import-linter, seam proof, and live Hermes.
- [ ] Review the final diff against all eight invariants, commit all Session E work, merge to `main`, rerun ship gates, and push.
