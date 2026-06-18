# Progress Log — Session C

## Session 1 (2026-06-18)
- Created planning files. Repo: Agent-X-OS, branch main (clean), GitHub remote present.
- Starting T0 audit: baseline checks + subsystem reading.

### Done
- T0 audit complete (table in findings.md + delivered to user).
- T1: confirmed mypy --strict already clean (0 errors) — premise stale.
- T5: hardened MongoJournalStore.append — retry on (instance_id,seq) collision, disambiguate from
  idempotency violation via exc.details keyPattern/keyValue + index-name fallback; new JournalSeqContention.
  Files: kernel/stores/mongo.py, kernel/errors.py, tests/kernel/test_mongo_stores.py (+3 tests).

### Test/check results
- tests/kernel/test_mongo_stores.py + test_journal_store.py → 11 passed.
- mypy --strict (mongo.py, errors.py, test_mongo_stores.py) → clean. ruff packages/kernel → clean.

- T4: ConfigVault (config-backed, kernel) — research refs → real api_key credential from Settings; others
  → manual. Wired into scripts/run_lead_finder.py (was MongoVault stub). +4 tests. Also fixed pre-existing
  redundant-cast in the script.
- T3: killed fabrication. research.propose emits read intent only (args={criteria,count}); sim native-read
  synthesizes CLEARLY-SYNTHETIC leads in the kernel (sim_lead_*, [sim] …, sim://, sim-native-read evidence);
  live path unchanged (real Firecrawl/Exa via gateway). Updated test_faculties to assert NO fabrication.
- T6: tests/integration/test_swarm_end_to_end.py — swarm loop proven in sim (offline judge). PASS.
- T7: live Hermes test PASS; scripts/run_lead_finder.py LIVE run PASS — real Firecrawl leads, parked L1,
  approved, settled w/ provenance facts in Mongo (instance agentx_dogfood_1781724195). 3 real leads logged.
- T8: CLAUDE.md + AGENTS.md updated with Session C status.
- T2: PARTIAL/deferred (documented) — live mode-aware wiring proven; step()-driven trajectory not done.

### FINAL gate: pytest 65 passed +1 skip · mypy --strict 85 files clean (+scripts) · ruff clean ·
  lint-imports 3/3 · seam proof green on double.
### COMMIT+PUSH: branch session-c/integration-go-live, commit b44e45b, pushed to origin (PR available).
### Planning files (task_plan/findings/progress) left UNTRACKED (session scratch, not committed).

### Gate after T3 (full): pytest 64 passed +1 skipped · mypy --strict 84 files clean · ruff clean ·
  lint-imports 3/3 · seam proof GREEN on OwnHarness double.

### Files created/modified
- task_plan.md, findings.md, progress.md (new)
- T5: kernel/stores/mongo.py, kernel/errors.py, tests/kernel/test_mongo_stores.py
- T4: kernel/vault.py (new), tests/kernel/test_vault.py (new), scripts/run_lead_finder.py
- T3: mandate/faculties/research.py, kernel/run_loop.py, tests/mandate/test_faculties.py

## Session D (2026-06-18) — SHAKEDOWN & EVAL (no build)
- E0 gate GREEN: mypy --strict 85 files, ruff clean, lint-imports 3/3, pytest 65p+1skip, live hermes 3p.
- E1: 2 live runs (run_lead_finder + scripts/_eval_d_inspect.py). ICP override via AGENTX_EVAL_ICP_JSON.
  Default ICP -> 3 article/video "leads"; dental-clinics ICP -> 1 YT marketing video + 1 IG post + 1 SaaS vendor.
  Captured full traces, draft bodies, heap facts, thread/resume/watch, journal seq.
- E2 VERDICT: 6/6 leads FAIL actionability (all articles/videos/competitors; none = real org+person+reachable URL+
  genuine buying signal). A founder would NOT send any draft. Root cause = generic single-search query + no
  read_url/contact extraction + stub 0.7 scoring + template draft + no postcondition gate. (G4)
- E3: idempotency no-double-effect ✓ but replay LOSSY (output={}); rings L0/L1 park, L2 executes ✓; unknown intent
  + score_lead -> human_task tail ✓; journal seq strictly monotonic, projections match ✓.
- E4: offline swarm e2e ✓ + PromotionGate correct ✓; REAL promptfoo judge BLOCKED (node v20.18.0 < ^20.20.0) and
  bridge likely incomplete (no asserts; --output json writes a file; expects Scorecard stdout) + unwired to .env.
- E5: agentx_api + Next dashboard present & honest (gaps.py lists 8 gaps). NEW bug: real parked run journals no
  draft SyscallAttempted, so dashboard approval card shows null(sim)/research(live) effect, never the draft.
  MANDATE_INSTANCE never written -> live /instances empty.
- E6: facts on probation w/ provenance ✓ (nothing promotes, G3). WATCH=0: SettlementCommitter drops watches +
  thread_update (emits only RunSettled.watch_ids) -> G3 blocked at source. resume.ring stuck L0. decay unset.
- Scratch instruments (untracked, scripts/): _eval_d_inspect.py, _eval_d_kernel_stress.py, _eval_d_swarm_judge.py,
  _eval_d_dashboard.py. Committed code UNTOUCHED (no inline fixes — all findings non-trivial). Deliverable: docs/EVAL_FINDINGS.md.

## Session E (2026-06-18) — P0/P1 FIXES (build; Tasks 1–6 of the plan)
- Plan: docs/superpowers/plans/2026-06-18-session-e-p0-p1-fixes.md (7 tasks). Tasks 1–6 DONE & committed; Task 7
  (proof/docs/ship) NOT done — Codex ran out of context window before it.
- P0-1 (796cda2): SettlementCommitter.commit now journals + projects a WatchRegistered per settlement watch
  (thread-advance still deferred — no frozen Phase-1 thread event). settlement.py.
- P0-2 (3d88eba): kernel-owned SyscallReceiptStore (memory + Mongo) keyed by idempotency key; gateway replay
  returns the original SyscallResult, not {}. gateway.py, ports.py, stores/, receipts.py.
- P0-3 (455271b): gateway journals SyscallAttempted before ring-park; KernelControl.approval_inbox returns the
  real draft card; api/state.py consumes it. control.py, gateway.py, run_loop.py, api/state.py.
- P1-1 (c7dfcf4): enrichment faculty (bounded read_url) + pure lead_quality extraction/scoring + actionable-only
  claims + postcondition gate (fact:actionable_lead exists) + per-lead person-addressed draft. faculties/,
  lead_quality.py, library/lead_finder.py.
- P1-2 (fe93d7b): promptfoo bridge generates llm-rubric asserts, parses --output JSON into a Scorecard; opt-in
  RUN_LIVE_PROMPTFOO=1 test; offline fallback preserved. swarm/judge.py.
- P1-3 (bd63c6f): projection-backed MandateRegistry persists MandateType/MandateInstance; KernelControl
  register/instantiate/list; /instances exposes real instances. registry.py, control.py, collections.py.
- OFFLINE GATE GREEN: mypy --strict 91 files · ruff clean · lint-imports 3/3 · pytest 81 passed + 2 skipped
  (RUN_LIVE_HERMES, RUN_LIVE_PROMPTFOO opt-in). Frozen contracts UNCHANGED.
- SHIP STATE: branch session-e/p0-p1-fixes pushed; PR #3 open vs main (https://github.com/Legend101Zz/Agent-X-OS/pull/3).
- ⏳ LIVE VERIFICATION STILL LEFT (next session, Task 7): 2 live ICP runs requiring ≥1 actionable lead each;
  real promptfoo judge on Node ≥22.22; Mongo/dashboard /instances proof; P0 repro scripts; then reconcile
  EVAL_FINDINGS + STATE_AND_ROADMAP to proven reality, run live Hermes gate, and merge PR #3.
