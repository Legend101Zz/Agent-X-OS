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

## Session E — LIVE PROOF (Task 7, 2026-06-18) — ✅ DONE. Full evidence: docs/SESSION_E_LIVE_PROOF.md
- Discovered the branch lives in a git worktree (.config/superpowers/worktrees/.../session-e-p0-p1-fixes);
  main-repo dir was on `main`. Topology clean: session-e is a linear descendant of local main (257c8ce).
- STEP 1 offline+seam gate GREEN: mypy --strict 91 files · ruff clean · pytest 81p+2skip · lint-imports 3/3 ·
  seam proof 1p (on OwnHarness double). Nothing regressed on checkout.
- STEP 2 P0 repro — all three Session-D bugs reproduced as FIXED:
  - P0-2 (_eval_d_kernel_stress.py): REPLAY_LOSSY=False, replay returns original output, 1 settled/key.
  - P0-3 (_eval_d_dashboard.py): journal=[…,syscall_attempted,run_parked]; drafted_effect=draft_email (CORRECT).
  - P0-1 (_eval_d_inspect.py, LIVE): watch_registered seq 16; WATCH doc count=1 in Mongo (was 0).
- STEP 3 P1-1 lead quality — 2 live ICPs (+ run_lead_finder.py). HONEST verdict: the actionable-lead MACHINERY
  works (real orgs, reachable contacts, cited evidence) — but leads are NOT reliably founder-SENDABLE: vendor-ICP
  returned competitors (Callbox/Belkins); dental-ICP found a correct clinic (Smile Inn, Pune) but with an
  ungrounded salutation. Trace shows the LLM is told to "think briefly… then stop, do not call tools" → query/
  relevance/grounding are heuristic. **G4 cannot close — blocked on G1.** (Materially better than Session D's 0/6.)
- STEP 4 P1-2 real promptfoo judge (Node v24.13.1, nvm use 24): real npx promptfoo eval over OpenRouter →
  Scorecard(score=1.0, passed=True, origin=synthetic); RUN_LIVE_PROMPTFOO=1 swarm e2e test PASSED. PromotionGate
  bars synthetic-only + requires human approval. PROVEN.
- STEP 5 P1-3 real MandateInstance: agentx_dogfood_1781781644 (customer "Agent-X dogfood") in Mongo
  mandate_instance + surfaced by /instances (inst_demo NOT present). PROVEN.
- STEP 6 live Hermes gate: RUN_LIVE_HERMES=1 → 3 passed (test_live_hermes_chat_completion PASSED).
- DOCS reconciled to proven reality: STATE_AND_ROADMAP (G3/G5/G9 → ✅; G4 → open/blocked-on-G1) + EVAL_FINDINGS
  (§5 + P0/P1 punch-list tagged with Session E outcome; P2 all still open) + this log.
- SHIP: full ship gate rerun green; PR #3 squash-merged to main. Next session = STEP A (G1) then STEP B (G2).

## Session F (2026-06-18) — STEP A (G1): make the LLM actually drive the run loop. Full proof: docs/SESSION_F_LIVE_PROOF.md
- Working in main checkout (integration model: push directly to main, no PR). Baseline gate GREEN at 95a087e.
- F1: MiniMax-M3 API researched (subagent → findings.md): OpenAI tool-calling (4 tools, tool_choice auto), preserve
  `<think>` across turns, parse tool_calls[].function.arguments. M3 confirmed correct id.
- F2 (TDD): run loop is now step-driven — drives HarnessRunner.step(obs), disposes Think/Call/Claim/Escalate/Finish,
  bound max_steps=24, feeds SyscallResult back. Removed the decorative reasoner + hardcoded faculty order + hardcoded
  draft. New lead-finder PLAYBOOK generator (mandate) over shared ctx; lazy PlaybookHarnessSession; draft → build_outreach_call.
  `runner` field + bootstrap arg; mode selects live runner vs OwnHarness(playbook).
- F3 (TDD, fake transport): kernel-side HermesRunner/HermesSession implement the mandate HarnessRunner Protocol; MiniMax
  emits think/call_tool/claim_facts/finish → one HarnessAction; kernel stamps fact provenance (run_id, probation).
  HermesClient.complete_chat transport. Wired run_lead_finder.py + _eval_d_inspect.py to runner=HermesRunner(...).
- F4 OFFLINE GATE GREEN: ruff clean · mypy --strict 95 files · pytest 97 passed +2 skip (+16 new G1 tests) · lint-imports
  3/3 · seam proof green on the OwnHarness double. Frozen contracts UNTOUCHED. Committed + pushed to main.
- F5 LIVE (real money, 5 live runs): root-caused + TDD-fixed 3 bugs the live loop exposed — (1) adapter exception
  crashed the run → gateway now returns an error result; (2) loop crashed on syscall errors → now FEEDS them back so
  the LLM recovers; (3) LLM sent empty args to free-form `call_tool` → replaced with CONCRETE per-syscall tools
  (search_leads/read_url/draft_email) with real schemas. Plus: prompt orders claim_facts BEFORE draft_email; transport
  retries once on transient MiniMax timeout (timeout 180s). After fixes BOTH Session-E ICPs produced founder-SENDABLE,
  evidence-grounded drafts: dental = Microdent Dentistry, Pune (SETTLED, 2 provenance facts, watch registered); vendor =
  AMP, DeKalb IL (parked→settles on approval; COMPETITOR REJECTION fixed — picked a buyer, not Callbox/Belkins). vs
  Session E 0/6. Honest caveats: depends on search quality; dental signal partly interpretive.
- F6: live Hermes gate (RUN_LIVE_HERMES=1) 4 passed; offline gate after fixes: ruff · mypy 95 · pytest 100+2skip ·
  lint-imports 3/3 · seam proof green. Scratch instruments kept: scripts/_f_diag_live.py, _f_smoke_hermes_tools.py.
- DOCS reconciled: STATE_AND_ROADMAP G1→✅, G4→✅ (Step A done, Step C sendable-proven), Phase-1 checklist updated,
  Session F banner; SESSION_F_LIVE_PROOF.md (F0–F6 full evidence); findings.md (MiniMax API + live root-causes).
- SHIP: pushed to main (no PR). NEXT SESSION = Step B (G2): repeatable runner + first-class kernel parked-run resume
  + scheduler-min worker (build on Session E's SyscallReceiptStore) toward ~100 settles; then Step D maturation half.
