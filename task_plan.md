# Task Plan — Session D: Shakedown & Evaluation (NOT a build session)

## Goal
Empirically exercise EVERYTHING built (lead mandate live, swarm, kernel, memory, dashboard
contract). Judge it HONESTLY — especially lead QUALITY, not just "it ran". Produce a single
prioritized FIX PUNCH-LIST (docs/EVAL_FINDINGS.md) + a ready-to-paste SESSION E fix prompt.
Make ONLY trivial obvious fixes inline; everything non-trivial goes on the list. Be brutally honest.

## Hard constraints
- Evaluation session: NO big builds/refactors. Trivial fixes OK but must keep gate green.
- Don't weaken any test. Seam proof must stay green on the OwnHarness double.
- No Phase 2–5 capabilities. draft = draft only.
- verification-before-completion: paste REAL command output / traces / leads. No claims w/o evidence.
- External/web content → findings.md ONLY (task_plan.md is auto-read by hooks).

## Precondition — PASSED
.env has all required: MONGODB_URI, MINIMAX_API_KEY, FACULTY_MODEL_BASE_URL, FACULTY_MODEL_ID,
FIRECRAWL_API_KEY (keyed fallback; EXA off), OPENROUTER_API_KEY, JUDGE_MODEL_ID. Live runs authorized.

## Phases
- [ ] **E0 — Baseline gate**: mypy --strict / ruff / pytest -q / lint-imports + RUN_LIVE_HERMES=1 hermes test.
      Paste all output. Any red = first punch-list item.
- [ ] **E1 — Run lead mandate LIVE x2**: default dogfood ICP + one DIFFERENT ICP. Paste both full traces.
      Query Mongo for settled heap facts (subject/predicate/provenance) + draft_email BODY. Record latency/cost.
- [ ] **E2 — JUDGE LEAD QUALITY (the crux)**: score each lead vs rubric (real org + person/role + reachable
      URL + genuine buying signal). Actionable prospect or article/listicle/video? Would a founder send the
      draft? pass/fail + reason per lead. Capture WHY weak (query? no read_url? no contact extraction? draft?).
- [ ] **E3 — Stress the KERNEL**: idempotency replay (same idem key, no double-effect); rings L0/L1/L2
      (draft_email parks <L2, executes @L2, approve→resume); unsupported intent → human_task tail;
      event-sourcing (journal kinds, seq monotonic per instance, projections match journal).
- [ ] **E4 — Swarm e2e**: pytest test_swarm_end_to_end.py (offline judge). Real judge if npx+keys present
      (PromptfooJudge shells npx promptfoo over OpenRouter). Confirm gate bars synthetic-only, allows real+human.
- [ ] **E5 — Dashboard contract**: locate dashboard/ + api/; verify KernelControl (approval_inbox,
      instance_file, floor, approve, set_ring) + ManualTaskStore reachable. Note shape mismatches / missing reads.
- [ ] **E6 — Memory/heap health**: settled instance facts carry provenance(run_id+evidence), on probation,
      nothing promotes (G3 open). Note decay/GC, thread state, resume doc behavior.
- [ ] **E7 — WRITE PUNCH-LIST → docs/EVAL_FINDINGS.md**: P0/P1/P2, each: symptom + repro cmd + file:line +
      suggested fix + G# mapping. End w/ ready-to-paste SESSION E prompt. Update STATE_AND_ROADMAP.md if reality differs.
- [ ] **FINAL — report**: what works, what's weak, top 3 to fix first.

## Known going-in (from Session C findings.md + STATE_AND_ROADMAP G-table)
- G1 LLM does NOT drive loop (Hermes = one decorative note; faculty order + draft hardcoded). ❌
- G2 No scheduler/worker; no kernel resume API (script resumes draft_email by hand). ❌
- G3 facts sit on probation; watch never fires → no promotion / real eval case. 🟡
- G4 LIVE leads were ARTICLES/VIDEOS, not actionable prospects. 🟡  ← expect E2 to confirm poor quality
- G5 mandate_* collections exist but no code reads/writes them; mandates inline. 🟡
- G6 set_ring manual; no promote/demote mechanics. G7 score_lead declared, no adapter. 🟡
- G9 Dashboard "DONE" in parallel — VERIFY contract (dashboard/ + api/ dirs exist).

## Method / order
E0 gate first (must be green or it's P0). Then E1 live runs (real API $). E2 quality verdict (most important
output). E3/E4/E5/E6 stress + contract checks (mostly offline/fast). E7 write the doc. Trivial fixes inline only.

## Status
DONE+EVIDENCED: E0 gate (all green) · E1 (2 live runs, full traces+heap+draft captured) · E2 (quality judged) ·
E3 (idempotency/rings/human-tail/event-sourcing) · E4 (swarm offline+gate proven; real judge BLOCKED by Node) ·
E5 (dashboard contract + NEW approval-card bug) · E6 (memory health; watch/thread drop root-caused).
Evidence all in findings.md (Session D section). NO inline code fixes made — every finding is non-trivial
(settlement/gateway/dashboard/quality) and would risk the gate; all go on the punch-list per eval constraints.
DONE: E7 — docs/EVAL_FINDINGS.md written (lead-quality verdict 0/6 + P0/P1/P2 punch-list + Session E prompt);
STATE_AND_ROADMAP.md updated (G3→❌ worse, G9→built-not-truthful, header+§5 updated, EVAL_FINDINGS linked).
FINAL gate RE-RUN GREEN: mypy --strict 85 files · ruff All checks passed (fixed import order in 1 scratch script) ·
pytest 65p+1skip · lint-imports 3/3. Scratch instruments kept in scripts/_eval_d_*.py (pass ruff; not in gate's
mypy scope; serve as EVAL_FINDINGS repro commands). Committed product code UNTOUCHED.
Current phase: COMPLETE — delivering report.
