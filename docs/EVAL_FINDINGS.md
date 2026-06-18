# Agent-X — Session D Shakedown & Evaluation Findings

*Evidence-based fix punch-list produced by the Session D evaluation (2026-06-18) on branch
`session-c/integration-go-live` (b44e45b). Companion to [STATE_AND_ROADMAP.md](./STATE_AND_ROADMAP.md)
(the G1–G13 gap map) and [BLUEPRINT.md](./BLUEPRINT.md) (canonical). Full raw evidence is in `findings.md`
(Session D section). All live runs made real Minimax + Firecrawl + Mongo + OpenRouter calls.*

> **⟶ SESSION E UPDATE (2026-06-18, branch `session-e/p0-p1-fixes`, PR #3 merged):** every P0/P1 item below
> was fixed **and live-proven** — see [SESSION_E_LIVE_PROOF.md](./SESSION_E_LIVE_PROOF.md). P0-1/P0-2/P0-3 are
> reproduced as FIXED; P1-2 (real promptfoo Scorecard over OpenRouter) and P1-3 (real non-demo instance on
> `/instances`) are proven. **P1-1 is the honest exception:** the actionable-lead *machinery* is proven on 2
> live ICPs (real orgs, reachable contacts, cited evidence), but **reliably-founder-sendable** leads are NOT
> proven — for a vendor-shaped ICP it returns competitors, and personalization is sometimes ungrounded; this is
> **blocked on G1** (make the LLM drive the loop). The §1 "0/6 actionable" verdict below is the *Session D*
> record; read it as superseded by the Session E proof. Each P0/P1 entry is tagged with its Session E status.

---

## 0. TL;DR — what works, what's weak, top 3 to fix first

**What genuinely works (proven this session, with evidence):**
- The **gate is green**: `mypy --strict` (85 files), `ruff`, `lint-imports` 3/3, `pytest` 65p+1skip, live
  Hermes↔Minimax 3p.
- The **kernel mechanics are sound**: rings park/execute correctly (L0/L1 park `draft_email`, L2 executes);
  the human-task tail catches every unsupported intent (nothing "unimplemented"); idempotency does not
  double-effect; the journal is append-only with strictly-monotonic per-instance `seq`, and the
  heap/trace/resume projections are deterministic folds that match the journal.
- The **live loop end-to-end**: a real run hydrates → researches (Firecrawl) → scores → claims provenance
  facts → parks `draft_email` at L1 → approve → executes at L2 → settles with `probation` facts in Mongo.
- The **swarm grading loop (offline) + PromotionGate**: synthetic-only evidence is barred from promotion;
  real + human approval opens the gate; real without human is barred. Invariant #7 holds.
- The **dashboard API** is a clean, honest HTTP face over `KernelControl`/projections and self-documents
  its missing commands (`api/src/agentx_api/gaps.py`).

**What's weak (the honest part):**
- **Lead quality is poor — the headline.** Across two live ICPs, **0 of 6 leads were actionable**. They are
  articles, YouTube videos, and competitor SaaS pages — not real orgs with a person/role + reachable contact +
  genuine buying signal. A founder would not send any of the drafts. (See §1 verdict.)
- **The LLM does not drive the loop** (G1): Minimax emits one decorative `<think>` note; faculty order +
  a hardcoded draft do all the work.
- **The reality→growth loop can never fire** (G3): settlement silently drops the watch it computes, so no
  `WatchRegistered` is ever journaled.
- **The human-approval surface is not truthful**: on a real parked run the dashboard cannot show the draft the
  manager is approving.
- **The real (npx) promptfoo judge has never actually run** and looks incomplete; only a fake-runner unit test exercises it.

**Top 3 to fix first:**
1. **P1-1 — Make leads actionable (G4).** This is the entire Phase-1 WIN. Everything else is plumbing around it.
2. **P0-1 — Fix settlement to actually register watches (and advance threads) (G3).** Without it the reality
   rung, probation→verified promotion, and the real gym corpus are all dead on arrival.
3. **P0-3 — Make the approval card truthful (G9).** The trust ladder's bottom rung is "owner taps Approve";
   today they'd be approving blind. (BLUEPRINT §8 kill-condition.)

---

## 1. E2 — LEAD QUALITY VERDICT (the crux)

**Rubric (a lead is ACTIONABLE only if all four hold):** (a) names a **real organization** (the prospect, not
an article about the topic); (b) a **person or role** to contact; (c) a **real, reachable contact path/URL**
for that org; (d) a **genuine buying signal** tied to that org. Then: **would a founder actually send the draft?**

### Run #1 — ICP "founders/agencies/SMB operators buying an AI lead-finder; US+India" (instance `agentx_evald_1781754910`)
| # | Lead subject | Real org? | Person/role? | Reachable contact? | Buying signal? | Verdict |
|---|---|---|---|---|---|---|
| 1 | "How to Get Your First AI Lead Gen Agency Client (2026) — **YouTube**" | ❌ (a video) | ❌ | ❌ (youtube watch URL) | ❌ | **FAIL** |
| 2 | "10 Best AI Lead Finders… — Oppora AI" (listicle) | ❌ (a blog) | ❌ | ❌ | ❌ | **FAIL** |
| 3 | "Buy Business Leads: 18 Places… — Cognism" (article) | ❌ (a blog) | ❌ | ❌ | ❌ | **FAIL** |

### Run #2 — ICP "independent dental clinics; Pune, India" (instance `agentx_evald_1781755009`)
| # | Lead subject | Real org? | Person/role? | Reachable contact? | Buying signal? | Verdict |
|---|---|---|---|---|---|---|
| 1 | "Leads Generation For Dentists… 2024 — **YouTube**" (marketing video) | ❌ | ❌ | ❌ | ❌ | **FAIL** |
| 2 | "Go beyond the cleaning… — **Instagram**" post | ❌ (the *post* is the lead; real clinics — "Galaxy Dental Clinic", "Jehangir Oracare Dental Centre" — appear only buried in the evidence snippet, never extracted) | ❌ | ❌ | ❌ | **FAIL** |
| 3 | "Lead Generation for Dentists — Leadee" (competitor SaaS) | ❌ (a vendor, not a prospect) | ❌ | ❌ | ❌ | **FAIL** |

**Verdict: 0 / 6 actionable. A founder would send 0 of these drafts.** The draft for every run is a fixed
one-liner — `"Draft only. Candidate: <article title>. Source: <url>. Why it may fit Agent-X lead-finder:
<snippet>."` — addressed to a hardcoded internal address `founder-review@agent-x.local`. It names a YouTube
video / blog as the "Candidate". It is not outreach; it is a label on a search result.

**Why (precisely):**
1. **Generic single-shot query.** `research.propose` (`packages/mandate/.../faculties/research.py:41-56`) emits
   ONE `lead_research_batch` with `criteria = {icp, location}` verbatim, `count`. A single web search on the raw
   ICP string returns SEO content *about* the topic, not the prospect orgs. (Run #2 proves the data is reachable:
   real Pune clinics appeared *inside* a result snippet but were never picked.)
2. **No enrichment / extraction.** `read_url` exists as an adapter but is never called; nothing visits a candidate
   page to extract `{org, decision-maker/role, buying signal, contact}`. The "lead" is just the search-result title;
   "evidence" is the result snippet.
3. **Stub scoring.** `judgment.propose` (`faculties/judgment.py:31-42`) assigns a flat `0.7` to every lead with
   reason `"evidence-backed candidate"` — no discrimination of article vs. real org.
4. **Template draft.** `_draft_args` (`packages/kernel/.../run_loop.py:338-352`) renders the same template for any
   lead, to a hardcoded address.
5. **No quality gate.** The mandate's postconditions (`packages/mandate/.../library/lead_finder.py:23-36`) only
   require `claimed_facts >= 1` and `fact:qualified_lead_score exists` — nothing bars a non-actionable lead.

This maps exactly to **G4** and **STATE_AND_ROADMAP §3 Step C**.

---

## 2. PRIORITIZED PUNCH-LIST

Priorities: **P0 = correctness bugs / blockers · P1 = quality (esp. leads) · P2 = polish.**
Each item: symptom · repro · where (`file:line`) · suggested fix · gap.

### P0 — correctness bugs

#### P0-1 · Settlement silently drops the WATCH (and the thread advance) → G3 can never fire — ✅ FIXED + LIVE-PROVEN (Session E)
> **Session E:** `SettlementCommitter.commit` now journals + projects a `WatchRegistered` per watch. Live proof:
> a real settle appends `watch_registered` (seq 16, after `run_settled`) and creates **one `WATCH` doc in Mongo
> (count=1, was 0)**. Thread-advance stays deferred (no frozen Phase-1 thread event); the maturation loop is Step D.
- **Symptom:** Every settled run computes a `Watch` (72h) and a `ThreadUpdate`, but `WATCH` docs = 0 and threads
  stay `engaged`/`history=[]` forever. The reality rung / deferred-settle / probation→verified promotion / real
  eval-case emission are therefore impossible — the whole G3 loop is dead at the source.
- **Repro:** `uv run python scripts/_eval_d_inspect.py` → `WATCH docs (count=0)`; THREAD `history=[]`.
- **Where:** `packages/kernel/src/agentx_kernel/settlement.py:21-40` — `SettlementCommitter.commit` appends only a
  `RunSettled` with `watch_ids=[w.id …]` and emits **no `WatchRegistered`**; it ignores `settlement.thread_update`
  entirely. `build_settlement` *does* produce the rich `Watch`/`ThreadUpdate` (`packages/mandate/.../settlement.py:93-117`).
  `WatchProjector` only projects from `WatchRegistered`/`WatchFired` (`packages/kernel/.../projections.py:103-119`).
- **Fix:** In `commit`, after the `RunSettled`, also append a `WatchRegistered` per `settlement.watches` (carrying
  `condition`/`deadline`) and project it. Decide a Phase-1 path for `thread_update` (either add a thread-advance
  journal event kind — a deliberate frozen-contract change, stop-and-coordinate — or document threads as inert in
  Phase-1). At minimum the watch must materialize.
- **Maps to:** G3. BLUEPRINT §2 step 6 ("register WATCH"), §2 step 7 (deferred settle).

#### P0-2 · Gateway idempotency replay is lossy (returns `output={}`) — ✅ FIXED + PROVEN (Session E)
> **Session E:** a kernel-owned `SyscallReceiptStore` persists the full `SyscallResult`; a replay returns the
> ORIGINAL output (verified: `REPLAY_LOSSY = False`), journals no second attempt/settled, and leaves exactly one
> `SyscallSettled` for the key (no double effect).
- **Symptom:** Re-invoking a syscall with the same `idempotency_key` correctly avoids a double effect, but the
  replayed `SyscallResult` has an **empty** `output` — the original draft body / research leads are gone. Any
  crash-resume or replay path silently loses the payload.
- **Repro:** `uv run python scripts/_eval_d_kernel_stress.py` → section 1: `SyscallSettled events for idem key = 1`
  (good) but `REPLAY_LOSSY = True`, second `output={}`.
- **Where:** `packages/kernel/src/agentx_kernel/gateway.py:176-186` (`_prior_result` rebuilds `SyscallResult` from
  `SyscallSettled`, which has no `output` field — `packages/contracts/.../journal.py:64-72`).
- **Fix:** Persist the syscall output so replay is faithful — either add an `output`/`output_ref` to `SyscallSettled`
  (frozen-contract change → stop-and-coordinate) or have the gateway store/fetch the result in a projection keyed by
  idempotency_key. (Also note `_prior_result` is an O(n) full `read_instance` scan per call; index/short-circuit later.)
- **Maps to:** kernel correctness; supports G2 (resume).

#### P0-3 · Dashboard approval card shows the wrong/empty effect — manager approves blind — ✅ FIXED + PROVEN (Session E)
> **Session E:** the gateway now journals a `syscall_attempted(draft_email)` BEFORE `run_parked`, and the
> approval inbox carries the exact durable card. Live proof: at park the journal is `[…, syscall_attempted,
> run_parked]` and `api/state.py:_drafted_effect` returns `draft_email` with the full draft body (was null/wrong).
- **Symptom:** On a **real** parked `draft_email` run, the dashboard cannot show the draft being approved. The card
  reconstructs the effect from the last `SyscallAttempted` in the journal, but the gateway parks for low ring
  **before** journaling any `SyscallAttempted`. So: sim → card effect = `null`; live → card effect = the earlier
  `lead_research_batch` read (wrong). The actual draft lives only in the in-memory `approval_card` and is never journaled.
- **Repro:** `uv run python scripts/_eval_d_dashboard.py` → `JOURNAL_KINDS_AT_PARK=[run_created, run_hydrated,
  run_parked]`, `drafted_effect = null`, while the in-memory `approval_card` holds the real draft. The api `seed_demo`
  hides this by hand-inserting a `SyscallAttempted(draft_email)` before `RunParked` (`api/.../state.py:260-293`) — a
  sequence the real kernel never produces.
- **Where:** root cause kernel-side: `gateway.py:78-85` (park returns before the attempt append at `:122-136`) and
  `run_loop.py:269-279` (the card is attached to the in-memory `RunResult`, not journaled; `RunParked` omits it,
  `journal.py:75-84`). Consumer: `api/src/agentx_api/state.py:563-567` (`_drafted_effect`); `KernelControl.approval_inbox`
  exposes only `{run_id, reason, required_ring, seq}` (`control.py:54-70`).
- **Fix:** Make the parked card durable: include the pending syscall name+args (the draft) on `RunParked` (frozen-contract
  change → stop-and-coordinate) or journal a `SyscallAttempted` *before* the ring-park, then have `KernelControl`/`approval_inbox`
  return the card so the dashboard need not reverse-engineer it.
- **Maps to:** G9. BLUEPRINT §6 (approval inbox), §8 kill-condition ("if owners won't tap Approve, the bottom rung is broken").

### P1 — quality (especially leads)

#### P1-1 · Leads are not actionable (THE one) → real orgs/people/contact + usable drafts — 🟢 MACHINERY LIVE-PROVEN; SENDABLE LEADS NOT PROVEN → blocked on G1 (Session E)
> **Session E:** the actionable-lead pipeline (bounded `read_url` enrichment, pure `lead_quality`
> extraction/scoring, `fact:actionable_lead exists` postcondition, person-addressed draft) is **live-proven on 2
> ICPs**: it now produces real organizations with genuinely reachable contact paths and cited evidence — a real
> improvement over the Session-D content-pages-with-no-contact problem. **But a founder still could not reliably
> send these drafts:** the lead-finder ICP returned competitors (Callbox/Belkins, themselves lead-gen agencies,
> citing their own sales copy); the dental ICP found a correct reachable clinic but fabricated an ungrounded
> salutation. Root cause = the LLM is side-lined; query formulation / relevance / grounding are heuristic.
> **G4 stays open, blocked on G1.** Full per-lead verdict in SESSION_E_LIVE_PROOF.md §3.
- **Symptom:** see §1 — 0/6 actionable; articles/videos/competitors; generic non-sendable drafts.
- **Repro:** `uv run python scripts/run_lead_finder.py`; `AGENTX_EVAL_ICP_JSON='{"icp":"independent dental clinics","location":"Pune, India","count":3}' uv run python scripts/_eval_d_inspect.py`.
- **Where & fix (multi-part, matches STATE_AND_ROADMAP §3 Step C):**
  - Query: build a *prospect-finding* query (not a topic query) and/or multi-step search →
    `packages/mandate/.../faculties/research.py:41-56`.
  - Enrichment: call `read_url` on top candidates and **extract** `{company, decision-maker/role, buying signal,
    contact/URL}` (the `read_url` adapter already exists in `packages/syscall/.../adapters.py`).
  - Scoring: replace the flat-`0.7` stub with real signal scoring → `faculties/judgment.py:31-42`.
  - Draft: per-lead, person-addressed outreach referencing the real signal → `run_loop.py:338-352`.
  - Gate: add a postcondition barring non-actionable leads (require real URL + org-name + cited signal) →
    `packages/mandate/.../library/lead_finder.py:23-36` (+ `verifier.py`).
- **Maps to:** G4 (and depends on G1 for the agent to actually do multi-step research).

#### P1-2 · Real promptfoo judge has never run and looks incomplete (+ unwired to config) — ✅ FIXED + LIVE-PROVEN (Session E)
> **Session E:** on Node v24.13.1 the real `npx promptfoo@latest eval` subprocess over OpenRouter returned a
> genuine `Scorecard(score=1.0, passed=True, origin=synthetic)`; `RUN_LIVE_PROMPTFOO=1 pytest …
> test_swarm_end_to_end.py` passes the live test; the PromotionGate bars synthetic-only and requires human approval.
- **Symptom:** Only the offline fallback + a **fake-runner** unit test exercise the judge. Driving the real path
  fails, and on inspection wouldn't produce a `Scorecard` even with a supported runtime.
- **Repro:** `uv run python scripts/_eval_d_swarm_judge.py` → `npx promptfoo` fails: *"requires Node ^20.20.0 ||
  >=22.22.0; detected v20.18.0"*; also raises `JUDGE_MODEL_ID is required` until `.env` is bridged into `os.environ`.
- **Where:** `packages/swarm/src/agentx_swarm/judge.py` — `_promptfoo_env` reads raw `os.environ` not Settings
  (`:150-167`); generated config has **no `assert:` block** and the provider just echoes the trace (`:170-209`);
  base command uses `--output json` (promptfoo treats `--output` as a *file*, not stdout) and
  `_extract_scorecard_payload` expects a `Scorecard`-shaped stdout (`:212-227`). The only enabled-path test uses a
  fake runner (`packages/swarm/tests/test_phase1_swarm.py:146-181`).
- **Fix:** (a) upgrade the dev Node to a supported version; (b) bridge `.env`→`os.environ` (or pass env) for the
  enabled path at the worker edge; (c) make the bridge actually grade — add a `model-graded`/`llm-rubric` assert and
  parse promptfoo's real `--output <file>` JSON into a `Scorecard`; (d) add an integration test that runs real `npx`
  behind an opt-in env gate (like `RUN_LIVE_HERMES`).
- **Maps to:** swarm/grading quality; supports G3 (real eval cases) and the compiler (G12) later.

#### P1-3 · Mandate registry never persisted → live dashboard `/instances` is empty — ✅ FIXED + LIVE-PROVEN (Session E)
> **Session E:** a projection-backed `MandateRegistry` persists `MandateType`/`MandateInstance` via
> `KernelControl`. Live proof: a real non-`inst_demo` instance (`agentx_dogfood_…`, customer "Agent-X dogfood")
> is in Mongo `mandate_instance` and is surfaced by `/instances` with its settled run, facts, and watch ids.
- **Symptom:** Real runs never write `mandate_type`/`mandate_instance`/`mandate_run`; the dashboard `/instances`
  (and thus `/approvals` enumeration, system overview ring counts) read `MANDATE_INSTANCE` and show **nothing** after
  real runs. Only `seed_demo` populates them.
- **Repro:** after `scripts/_eval_d_inspect.py`, query Mongo: `mandate_instance` has no row for the run's instance.
- **Where:** `scripts/run_lead_finder.py` + `run_loop.py` build the mandate/instance inline and never persist;
  collections exist (`db/src/agentx_db/collections.py:9-11`) but nothing reads/writes them.
- **Fix:** persist a `MandateInstance` (and `MandateType`/`MandateRun`) on run start via a `MandateRegistry` behind a
  Protocol + `KernelControl` (STATE_AND_ROADMAP §3 Step E).
- **Maps to:** G5 (also makes G9 usable on real data).

### P2 — polish

| ID | Symptom | Where | Fix | Gap |
|---|---|---|---|---|
| P2-1 | `resume.ring` stays `L0` for an L1-bound instance; `floor()` misreports the ring | `projections.py:148-153` (seeds `ring="L0"`, only `set_ring` updates), `control.py:81-89` | seed/track resume ring from the instance binding, or have `floor()` fall back to the instance's bound ring | G6 |
| P2-2 | `score_lead` is in gateway `_POLICY` but has no adapter → silently degrades to `human_task` | `gateway.py:41`; no adapter in `syscall/adapters.py` | either implement a `score_lead` adapter or remove it from policy and keep scoring in-pod | G7 |
| P2-3 | `DraftEmailAdapter.required_ring="L1"` is dead metadata (gateway forces L2 for `external_message`) | `adapters.py:374` vs `gateway.py:44` | align adapter metadata with gateway policy (or document policy as authoritative) | — |
| P2-4 | `Fact.decay_at` is always `null`; no decay/GC of probation facts | `faculties/memory_craft.py`, heap projector | set a decay horizon and a GC/decay pass when the heap matters | G3-adjacent |
| P2-5 | Cost/usage not surfaced from Minimax/Firecrawl/OpenRouter wrappers | `scripts/run_lead_finder.py:223` (`COST_OBSERVED=not_available`) | capture token/credit usage from API responses into billing lines | — |
| P2-6 | Manual queue is in-memory (process-local) — a dashboard in another process sees an empty queue | `adapters.py:124-134` | DB-backed manual-task store behind the `Adapter` interface | already in `api/gaps.py: projection.manual_queue_durable` |
| P2-7 | Syscall `settled` trace row + run trace are not persisted (only attempt args are) | `projections.py:85-95` | optional trace projection if operators need post-exit detail | already in `api/gaps.py: projection.full_trace_snapshot` |
| P2-8 | Live outreach can invent numeric results or capabilities absent from evidence | Session G Dental Sphere draft claimed “20–40 additional booked consultations/month” and active treatment-intent identification without proof | add deterministic draft truthfulness checks: reject unsupported numeric performance claims and product capabilities not present in an approved capability manifest | G4 quality guardrail |

*(Already-documented dashboard command gaps — edit/reject/instantiate/trigger-run/run-swarm/promote — are correctly
captured in `api/src/agentx_api/gaps.py` and surfaced as honest `501`s; they are not re-listed here. They map to
G2/G5/G6/G8/G10.)*

---

## 3. Note on inline fixes
Per the eval constraints, **no committed code was changed** this session: every finding is non-trivial (settlement,
gateway, the run-loop/draft pipeline, the dashboard contract, the judge bridge) and a quick edit would have risked the
green gate or a frozen contract. The four `scripts/_eval_d_*.py` instruments are untracked scratch and exist only to
reproduce the evidence above.

---

## 4. SESSION E — Fix punch-list prompt (ready to paste)

```text
SESSION E — Fix the P0/P1 punch-list from the Session D shakedown
working dir: /Volumes/Mrigesh SSD/Startup/Agent-X-OS

GOAL
Clear the P0 correctness bugs and the P1 lead-quality gap from docs/EVAL_FINDINGS.md. This IS a build
session (TDD), but stay inside Phase 1: no money/WhatsApp/voice/browser; draft = draft only. Keep the gate
green and the seam proof green on the OwnHarness double at every step. Frozen-contract changes
(packages/contracts) are a STOP-AND-COORDINATE event — call them out explicitly before making them.

REQUIRED READING
- docs/EVAL_FINDINGS.md (this punch-list — P0/P1/P2 with repro + file:line + G#).
- findings.md (Session D section: full traces, leads, drafts, root-causes).
- docs/STATE_AND_ROADMAP.md §2 (G-table) + §3 Steps C/D/E. docs/BLUEPRINT.md §2, §4 (invariants), §7.

PRECONDITION
.env is filled (verified in Session D). Live runs cost real money — authorized. For the real judge, a
supported Node (^20.20.0 || >=22.22.0) is required (Session D had v20.18.0 — install/switch first).

ORDER OF WORK (low-risk correctness first, then the quality crux)
1. P0-1 settlement watch+thread (TDD): SettlementCommitter.commit must journal a WatchRegistered per
   settlement.watches and project it; decide thread_update handling (frozen-contract change if adding a
   thread event kind — coordinate). Prove: a live settle now creates a watch doc. (kernel/settlement.py:21-40)
2. P0-2 idempotency replay fidelity (TDD): persist syscall output so a replay returns the original payload,
   not {}. (gateway.py:176-186; SyscallSettled output is a contract change — coordinate.)
3. P0-3 truthful approval card (TDD): make the parked draft durable (RunParked carries the pending
   syscall+args, OR journal SyscallAttempted before the ring-park) and expose it via KernelControl.approval_inbox
   so the dashboard shows the real draft. Re-run scripts/_eval_d_dashboard.py: drafted effect == draft_email.
4. P1-1 actionable leads (G4 / STATE_AND_ROADMAP Step C) — the main event:
   - research.py: prospect-finding (multi-step) search, not a topic query.
   - call read_url on top candidates; extract {company, decision-maker/role, buying signal, contact/URL}.
   - judgment.py: real signal scoring (kill the flat 0.7).
   - run_loop draft: per-lead, person-addressed outreach citing the real signal.
   - lead_finder.py + verifier: postcondition barring non-actionable leads (require real URL + org + cited signal).
   - PROVE with 2 live ICPs: paste leads + drafts; target >=1 actionable lead per run that a founder would send.
   NOTE: doing this well likely needs G1 (LLM drives the loop) at least partially — scope honestly; if you
   only wire the deterministic multi-step pipeline this session, say so and leave G1 on the roadmap.
5. P1-2 real promptfoo judge: upgrade Node, bridge .env->env for the enabled path, fix the bridge to actually
   grade (assert + parse promptfoo --output file), add an opt-in live integration test. Prove a real Scorecard.
6. P1-3 persist MandateInstance on run start (G5 / Step E) so the dashboard shows real instances.
7. P2 items as time allows (resume.ring, score_lead, decay, cost) — don't let them block P0/P1.

METHOD
verification-before-completion: paste real command output / traces / leads — no claims without evidence.
Don't weaken any test. Re-run the full gate (mypy --strict packages db tests; ruff; pytest -q; lint-imports)
and RUN_LIVE_HERMES=1 hermes test at the end and paste it.

DONE WHEN
P0-1/P0-2/P0-3 fixed with tests + live proof; leads are actionable on 2 live ICPs (paste them); gate + seam
proof green; STATE_AND_ROADMAP G-table updated to reflect what's now closed.
```

---

## 5. Session E outcome (resolution of this punch-list)

The Session D corrections drove the Session E P0/P1 work, which is now **implemented, merged (PR #3), and
live-proven** (evidence: [SESSION_E_LIVE_PROOF.md](./SESSION_E_LIVE_PROOF.md)). Status of each item:

| Item | Session D state | Session E outcome |
|---|---|---|
| **P0-1** settlement drops WATCH (G3) | broken — watch never registered | ✅ fixed + live-proven (`watch_registered`; WATCH doc count=1) |
| **P0-2** lossy idempotency replay | broken — replay returns `{}` | ✅ fixed + proven (`REPLAY_LOSSY=False`, 1 settled per key) |
| **P0-3** non-truthful approval card (G9) | broken — wrong/empty effect | ✅ fixed + proven (`syscall_attempted` before park; card = draft_email) |
| **P1-1** leads not actionable (G4) | 0/6 actionable | 🟢 machinery live-proven (real orgs/contacts/evidence) — but **sendable leads NOT proven; blocked on G1** |
| **P1-2** real promptfoo judge | never run | ✅ live-proven (real Scorecard over OpenRouter, Node v24.13.1) |
| **P1-3** mandate registry not persisted (G5) | `/instances` empty | ✅ live-proven (real non-demo instance on `/instances`) |

**STATE_AND_ROADMAP.md reconciled:** G3 → source fixed + watch live-proven (maturation loop still ❌);
G4 → pipeline live-proven but **open, blocked on G1** (sendable leads); G5 → ✅ live-proven; G9 → ✅ card
truthful + live-proven at the API path. The finish-line checklist and Steps C/D/E were updated to match.

**P2 items — all still OPEN (deferred polish; none were in Session E's P0/P1 scope):**
- P2-1 (`resume.ring` misreport), P2-2 (`score_lead` has no adapter → G7), P2-4 (`Fact.decay_at` always null / no GC),
  P2-6 (in-memory manual queue), P2-7 (settled trace not persisted) — **open**.
- P2-3 (`DraftEmailAdapter.required_ring` dead metadata) — Session E's P1-1 work aligned the draft adapter
  metadata to the gateway L2 policy; treat as **addressed-in-passing, verify if revisited**.
- P2-5 (cost/usage not surfaced) — **confirmed still open**: live `run_lead_finder.py` still prints
  `COST_OBSERVED=not_available_from_current_wrappers`.

**Next session (per STATE_AND_ROADMAP §3):** Step A = **G1** (make the LLM actually drive the run loop — this is
what unblocks G4's sendable leads), then Step B = **G2** (scheduler + kernel parked-run resume). Step D needs
only its maturation half (watch matures → probation→verified → real `eval_case`).
