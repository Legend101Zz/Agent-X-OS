# Session E P0/P1 Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the Session D correctness bugs, make Phase-1 leads actionable, prove the real promptfoo judge, and persist real mandate instances without changing frozen contracts.

**Architecture:** Keep the journal as source of truth. Use existing journal events for watches and parked intent, and a kernel-owned durable receipt store for syscall outputs that cannot fit the frozen event. Keep lead intelligence in pure mandate code: search, explicit bounded enrichment, evidence extraction, scoring, actionable-only claims, and drafts. Persist catalog type/instance state at the live kernel edge; continue deriving run summaries from the journal.

**Tech Stack:** Python 3.12, Pydantic, pytest, PyMongo async, Firecrawl/Exa, promptfoo via `npx`, Ruff, mypy strict, import-linter.

---

## Task 1: P0-1 register settlement watches

- [ ] Add a failing test in `tests/kernel/test_settlement_commit.py` with one settlement `Watch`.
- [ ] Run the focused test and confirm only `run_settled` exists.
- [ ] Update `packages/kernel/src/agentx_kernel/settlement.py` to append/project `RunSettled`, then one deterministic `WatchRegistered` per watch.
- [ ] Leave thread advancement explicitly deferred because the frozen Phase-1 journal has no thread-update event.
- [ ] Run focused tests, seam proof, and the full gate.

## Task 2: P0-2 faithful idempotency replay

- [ ] Add a failing gateway test asserting replay output equals the original output and one settlement exists.
- [ ] Add a kernel-owned `SyscallReceiptStore` port plus memory and Mongo implementations keyed by the current globally unique idempotency key.
- [ ] Store request identity and the complete `SyscallResult`; validate request identity on replay.
- [ ] Return the receipt only when a matching settlement exists. Fail explicitly for legacy settled events without a receipt.
- [ ] Wire the receipt store through bootstrap, live scripts, and evaluation scripts.
- [ ] Run store/gateway tests, seam proof, and the full gate.

## Task 3: P0-3 truthful approval cards

- [ ] Add failing gateway tests asserting a gated call journals/reuses one `SyscallAttempted` before `RunParked`.
- [ ] Add a failing control test asserting `ApprovalItem.approval_card` contains syscall, args, and idempotency key.
- [ ] Add gateway `_ensure_attempt()` and return the attempt in parked outcomes; never append a second attempt on approved execution.
- [ ] Build approval cards from the nearest preceding attempt for the parked run.
- [ ] Update `api/src/agentx_api/state.py` to consume the direct card, with historical reverse-scan fallback.
- [ ] Run kernel/API focused tests, dashboard repro, seam proof, and the full gate.

## Task 4: P1-1 actionable lead pipeline

- [ ] Add failing tests for a prospect-finding query with contact intent and content-domain exclusions.
- [ ] Add an enrichment faculty between research and judgment that emits at most three `read_url` calls for candidate HTTP URLs.
- [ ] Add pure lead-quality helpers that reject content/competitors, extract organization, person-or-role, reachable contact path, buying signal, and cited evidence, and fail closed if incomplete.
- [ ] Preserve `lead_id` through `read_url`; apply enriched output to the matching scratchpad lead in live and sim modes.
- [ ] Replace flat scoring with evidence-field scoring.
- [ ] Claim `qualified_lead_score` and `actionable_lead` only for complete leads; require `fact:actionable_lead exists`.
- [ ] Draft only the highest-scoring actionable lead, addressing the person/role and citing the signal/contact path.
- [ ] Request Firecrawl markdown during search and use official query operators; cap enrichment at three URLs.
- [ ] Align draft adapter metadata to gateway L2 policy.
- [ ] Run mandate/kernel/syscall tests, seam proof, swarm integration, and the full gate.

## Task 5: P1-2 real promptfoo judge

- [ ] Add failing fake-runner tests for `--output <temp>/results.json`, `llm-rubric`, and version-3 output parsing.
- [ ] Generate one model-graded assertion per Agent-X rubric criterion and use the configured judge provider.
- [ ] Parse promptfoo result-file assertion grades into `CriterionResult`, weighted score, comments, and failure reasons.
- [ ] Add `RUN_LIVE_PROMPTFOO=1` integration coverage; bridge `.env` only at the script/test edge.
- [ ] Preserve the offline fallback.
- [ ] Run promptfoo config validation, swarm tests, real judge proof, and the full gate.

## Task 6: P1-3 persist mandate instances

- [ ] Add failing registry tests for type registration, instantiate/get/list, idempotency, and conflicts.
- [ ] Implement projection-backed `MandateRegistry` in the kernel.
- [ ] Expose register/instantiate/list operations through `KernelControl`.
- [ ] At the live edge, persist the canonical type and a full `MandateInstance`, then derive `InstanceBinding`; mutate only a customer-target copy.
- [ ] Do not duplicate `MANDATE_RUN`: dashboard run summaries already fold the journal, while durable run checkpoints belong to G2 resume.
- [ ] Add API coverage proving `/instances` exposes a non-demo persisted instance.
- [ ] Run focused/API tests, seam proof, and the full gate.

## Task 7: proof, docs, and ship

- [ ] Run P0 repro scripts and verify watch existence, faithful replay, and truthful draft card.
- [ ] Run two live ICPs and require at least one real actionable lead and sendable draft per run before closing G4.
- [ ] Run the real promptfoo judge on Node `v24.13.1`.
- [ ] Verify Mongo and dashboard contain the real mandate instance.
- [ ] Update `docs/EVAL_FINDINGS.md` and `docs/STATE_AND_ROADMAP.md` only with proven claims.
- [ ] Run mypy, Ruff, full pytest, import-linter, seam proof, and live Hermes.
- [ ] Review the final diff against all eight invariants, commit all Session E work, merge to `main`, rerun ship gates, and push.
