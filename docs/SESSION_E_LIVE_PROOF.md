# Session E — Live Proof Log

> Context-survival log. Every command's **real** output/trace for Task 7 is appended here as it runs,
> so evidence lives on disk (and in git) rather than only in chat. Branch `session-e/p0-p1-fixes`,
> started from HEAD `d2efb66`. Working dir: the session-e git worktree.
>
> Environment at start: Python via `uv` (0.11.15); Node default v20.18.0 (will `nvm use` v24.13.1 for the
> real promptfoo judge, since promptfoo needs `^20.20.0 || >=22.22.0` and v22.14.0 does NOT satisfy it).
> `.env` present with: AGENTX_ENV, MONGODB_URI, MONGODB_DB_NAME, MINIMAX_API_KEY, FACULTY_MODEL_BASE_URL,
> FACULTY_MODEL_ID, FIRECRAWL_API_KEY, OPENROUTER_API_KEY, JUDGE_MODEL_ID. (EXA_API_KEY absent — Firecrawl path used.)

## Step 0 — Orientation (DONE)

- Branch `session-e/p0-p1-fixes` exists local + origin at `d2efb66`; checked out in git worktree
  `/Users/comreton/.config/superpowers/worktrees/Agent-X-OS/session-e-p0-p1-fixes` (main repo dir is on `main`).
- Topology: session-e is a linear descendant of local `main` (257c8ce, Session D findings), which is itself
  origin/main (ebfddf2) + 1 commit. Merging PR #3 brings in 257c8ce + the 8 session-e commits cleanly.
- All required `.env` keys present. Plan Task 7 is the work; Tasks 1–6 committed.

---

## Step 1 — Offline gate (mypy --strict, ruff, pytest, lint-imports, seam proof) — ✅ GREEN

Ran in the session-e worktree against HEAD `d2efb66`. Real output:

```
$ uv run mypy --strict packages db tests
Success: no issues found in 91 source files
EXIT_CODE=0

$ uv run ruff check
EXIT_CODE=0            # (no findings)

$ uv run pytest -q
81 passed, 2 skipped in 0.20s
EXIT_CODE=0
# the 2 skips are the opt-in live tests, exercised in Steps 4 & 6:
#   SKIPPED tests/integration/test_swarm_end_to_end.py:111  (set RUN_LIVE_PROMPTFOO=1)
#   SKIPPED tests/kernel/test_hermes_client.py:36           (set RUN_LIVE_HERMES=1)

$ uv run lint-imports
Analyzed 83 files, 346 dependencies.
  mandate holds no credentials (invariant #2)                              KEPT
  Claude lane (kernel/mandate) never imports Codex lane (syscall/swarm)    KEPT
  Codex lane (syscall/swarm) never imports Claude lane (kernel/mandate)    KEPT
Contracts: 3 kept, 0 broken.
EXIT_CODE=0

$ uv run pytest tests/integration/test_seam_proof.py -q
1 passed in 0.06s     # seam proof green on the OwnHarness double
EXIT_CODE=0
```

**Verdict: offline + seam gate GREEN.** Matches the inherited claim; nothing regressed on checkout.

## Step 2 — P0 repro proofs (settlement watch / faithful replay / truthful approval card)

### 2a. P0-2 faithful idempotency replay — ✅ FIXED (`scripts/_eval_d_kernel_stress.py`, in-memory/deterministic)

```
===== 1. IDEMPOTENCY (replay must not double-effect) =====
FIRST  status=ok body_in_output=True output={"draft_id": "draft_idem_inst:run:draft_email", "to": "x@y.z", "subject": "S", "body": "B", "mode": "draft", "sent": false, "credential_ref": "vault://tenant_idem_inst/draft_email"}
SECOND status=ok attempted_event=None settled_event=None output={... IDENTICAL to FIRST ...}
SyscallSettled events for idem key = 1  (expect 1 = no double effect)
REPLAY_LOSSY = False  (True => replay drops the original output payload)
```
**Verdict:** replay returns the ORIGINAL full output (not `{}`), journals no second attempt/settled, and
exactly one `SyscallSettled` exists for the idempotency key. Session D's "replay returns `{}`" bug is fixed.
(Bonus from same script: L0/L1 park & L2 executes draft_email; unsupported intents → `human_task`
`queued_manual` tail, nothing "unimplemented".)

### 2b. P0-3 truthful approval card — ✅ FIXED (`scripts/_eval_d_dashboard.py`, sim/in-memory)

```
RUN_STATE=parked (expect parked)
JOURNAL_KINDS_AT_PARK=['run_created', 'run_hydrated', 'syscall_attempted', 'run_parked']
SyscallAttempted_in_journal_at_park=['draft_email']
...
DASHBOARD drafted_effect(events) = {"syscall": "draft_email", "args": {... full draft body ...}, "required_ring": "L2"}
  -> shows draft_email (CORRECT)
```
**Verdict:** the gateway now journals a `syscall_attempted(draft_email)` BEFORE `run_parked`, so the
dashboard's reverse-scan reconstruction (`api/state.py:_drafted_effect`) returns the real draft the manager
is approving — not the earlier research read. Session D's "card shows wrong/null effect" bug is fixed.
The approval inbox also carries the exact durable card (`syscall=draft_email`, args, idempotency_key).

### 2c. P0-1 settlement watch (live) — ✅ FIXED (`scripts/_eval_d_inspect.py`, default ICP, live MiniMax+Firecrawl+Mongo)

`INSTANCE_ID=agentx_evald_1781781401`, `RUN_ID=…:deadline:1781781401`. Full live park→approve→draft→verify→settle:

```
JOURNAL_EVENT_COUNT=16 SEQ_STRICTLY_INCREASING=True
JOURNAL_SEQ_KINDS=1:run_created, 2:run_hydrated, 3:syscall_attempted, 4:syscall_settled,
  5:syscall_attempted, 6:syscall_settled, 7:syscall_attempted, 8:syscall_settled,
  9:syscall_attempted, 10:run_parked, 11:manager_action, 12:approval_resolved,
  13:syscall_settled, 14:run_verified, 15:run_settled, 16:watch_registered
SETTLED_EVENT=…:settled seq=15 VERIFY_PASSED=True rungs=['rules']

----- WATCH docs (count=1) -----
[ { "id": "…:watch:reality", "run_id": "…", "instance_id": "agentx_evald_1781781401",
    "condition": "reality_outcome", "deadline": "2026-06-21T11:17:19+00:00", "status": "pending" } ]
```
**Verdict:** a live settle now appends `watch_registered` (seq 16, right after `run_settled` seq 15) and
**projects exactly one WATCH doc in Mongo (count=1)** — Session D had 0. The watch is a `reality_outcome`
condition with a 3-day deadline, `status=pending`. P0-1 fixed. (Maturation of that watch → probation→verified
→ eval_case is the remaining half of Step D, NOT in scope here.)

**P0 summary: all three Session-D correctness bugs (P0-1 watch, P0-2 replay, P0-3 card) are reproduced as FIXED.**

## Step 3 — P1-1 lead quality (2 live ICP runs + honest per-lead actionability verdict)

Run via `_eval_d_inspect.py` (the rich runner — same live lead-finder path as `run_lead_finder.py`, but it
also surfaces the trace, settled heap facts w/ provenance, and the rendered draft body). `run_lead_finder.py`
thin-runner also exercised (see end of Step 3).

### Run #1 — default ICP: "founders, agencies, and SMB operators buying an AI lead-finder", US+India, count 3

**Trace (live):**
```
1. thought (MiniMax): "<think> ICP = founders/agencies/SMB operators ... pain around manual lead
   generation ... budget $50-500/mo ..." — but prompted to "Think briefly about the ICP, then stop.
   Do not call tools and do not make commitments."   <-- LLM does NOT drive the loop
2. syscall_result: lead_research_batch  (ok, maturity 3)   <-- heuristic faculty issues the search
3. syscall_result: read_url             (ok)               <-- bounded enrichment (cap 3)
4. syscall_result: read_url             (ok)
5. parked: draft_email requires L2
```

**Settled heap facts (count=4, status=probation, all cite evidence):**
| subject | predicate | object | contact path cited | buying signal cited |
|---|---|---|---|---|
| firecrawl_1 | qualified_lead_score / actionable_lead | **Callbox** | sales@callboxinc.com, callboxinc.com | "B2B lead gen / appointment setting service" |
| firecrawl_3 | qualified_lead_score / actionable_lead | **Belkins** | sales@belkins.io, +1 302-803-5506, belkins.io | "100–400+ qualified appointments / appointment setting" |

**Drafted (highest-scoring = Belkins), kept in draft (sent=false), to internal review mailbox:**
> Subject: "Draft outreach to Belkins" — "Hi Founder or growth lead, I noticed this signal at Belkins:
> With personalized appointment setting and persistent follow-ups… Reference: https://belkins.io/. Draft only — not sent."

**Honest per-lead actionability verdict (vs rubric: real org + person/role + reachable URL + genuine buying signal + would a founder send it?):**
- ✅ **Machinery works.** The actionable-lead gate did its job: each settled lead has a real organization, a
  genuinely reachable contact path (real email/phone/URL), a cited buying-signal string, and evidence; it
  fails closed without them, scores on evidence fields, drafts only the top actionable lead, addresses a
  role, cites the signal+URL, and keeps the message in draft for approval. This is a real, verifiable
  improvement over Session D (where leads were content pages / no contact path).
- ❌ **Not a sendable draft — ICP-fit is wrong.** Callbox and Belkins are themselves **B2B lead-generation
  agencies** — i.e. competitors/vendors of the very product, NOT "founders/SMBs *buying* an AI lead-finder."
  The cited "buying signal" is actually each company's own **sales copy**. A founder would NOT send the
  Belkins draft: it's outreach to a competitor. "person/role" is a generic "Founder or growth lead", not a
  named decision-maker.
- **Root cause = G1.** The trace proves the LLM is deliberately side-lined ("think briefly… then stop, do
  not call tools"); query formulation, relevance/ICP-fit filtering, and competitor exclusion are all done by
  heuristic code that keyword-matches "lead generation / appointment setting" and cannot tell a *seller* of
  that service from a *buyer*. So the pipeline returns mechanically-actionable-but-semantically-mis-targeted
  leads. **Closing G4 (truly sendable leads) is blocked on G1 (make the LLM drive the loop).**

**Run #1 verdict: ≥1 lead passes the actionable gate with real contact + cited evidence (mechanically actionable: YES), but it is NOT a founder-sendable, ICP-correct draft (semantically actionable: NO — needs G1).**

### Run #2 — buyer-shaped ICP: "dental clinics looking to attract and retain new patients", Pune India, count 3

`INSTANCE_ID=agentx_evald_1781781560`. 14 journal events, strictly increasing, ending `13:run_settled,
14:watch_registered`; WATCH count=1; HEAP count=2 (one settled lead).

**Trace:** identical shape — `thought` (MiniMax again told to "think briefly… then stop, do not call tools"),
then heuristic `lead_research_batch` + 1× `read_url`, then park at L2.

**Settled lead — Smile Inn Dental Clinic (Kothrud, Pune):**
- organization: **real** — Smile Inn Dental Clinic, Kothrud, Pune.
- contact path: **real + reachable** — WhatsApp 9420065036, smileinn@gmail.com, phone 02025285508,
  https://smileinn.in/appointment-booking/.
- buying signal cited: "Smile-Inn… introduces teleconsulting facility for its patients" + appointment booking
  — a genuine patient-acquisition / tech-adoption signal (plausible buyer of a patient-finding tool).
- ICP-fit: ✅ **correct this time** — a Pune dental clinic IS a plausible buyer, not a competitor.

**Drafted (Smile Inn), sent=false, to internal review mailbox:**
> "Hi **Dr. Anjali Srinivasan**, I noticed this signal at Smile Inn Dental Clinic: …teleconsulting facility…
> Reference: https://api.whatsapp.com/send/?phone=919420065036. Draft only — not sent."

**Honest verdict Run #2:** ✅ **1 actionable, ICP-correct lead** with a real org, a genuinely reachable
contact (WhatsApp/email/phone), and a real signal — **close to founder-sendable**. ⚠️ But the salutation
"Dr. Anjali Srinivasan" is **NOT present in any cited evidence string** — the named decision-maker appears
fabricated/ungrounded (a founder would have to fix the name before sending), and one evidence string is junk
(a `demo.tico.chat refused to connect` failed-fetch leaked in). Both are evidence-grounding failures that an
LLM-in-the-loop (G1) would catch.

### Also ran the named thin shipping runner `scripts/run_lead_finder.py` (default ICP, live)

```
INSTANCE_ID=agentx_dogfood_1781781644   RUN_ID=…:deadline:1781781644
L1_STATE=parked → approve → DRAFT_STATUS=ok → SETTLED seq=15 → watch_registered
HEAP_FACT_COUNT=4   SYSCALL_TRACE_ROWS=8   LATENCY l1=41.44s approval_to_settle=0.86s
JOURNAL_KINDS=run_created,run_hydrated,(syscall_attempted,syscall_settled)x4-ish,run_parked,
  manager_action,approval_resolved,syscall_settled,run_verified,run_settled,watch_registered
FIRST_HEAP_FACT: Callbox (B2B lead-gen agency) — actionable gate passed, real contact sales@callboxinc.com
```
Confirms the actual shipping entrypoint runs green end-to-end live, persists a real MandateInstance
(`agentx_dogfood_1781781644`, used in Step 5), and **reproduces the Run-#1 competitor finding (Callbox)** —
so the ICP-fit gap is in the product path, not an artifact of the inspect script.

### Step 3 synthesis (honest, no overclaim)

| | Run #1 (lead-finder ICP) | Run #2 (dental ICP) |
|---|---|---|
| ≥1 lead passes actionable gate (real org + reachable contact + cited evidence) | ✅ 2 leads | ✅ 1 lead |
| Founder-**sendable** draft (right target, grounded personalization) | ❌ competitors (Callbox/Belkins) | ⚠️ right target, but ungrounded name |

**The P1-1 actionable-lead MACHINERY is real and working** — real organizations, genuinely reachable contact
paths, evidence-cited scoring, fail-closed actionable gate, draft-only-with-approval. This is a concrete,
verifiable improvement over Session D (content pages, no contact path). **But "reliably founder-sendable
leads" is NOT proven** — quality is ICP-dependent and the two systemic failures (returns competitors for a
vendor-shaped ICP; fabricates ungrounded personalization) both trace to the **same root cause: the LLM is
deliberately side-lined ("think briefly… then stop, do not call tools"), so query formulation, relevance/
competitor filtering, and evidence-grounded drafting are heuristic.** → **G4 cannot be closed; it is blocked
on G1 (make the LLM actually drive the run loop).** Recorded as next session's Step A.

## Step 4 — P1-2 real promptfoo judge (npx over OpenRouter, Node v24.13.1) — ✅ PROVEN

Switched node: `nvm use 24` → `NODE=v24.13.1`, `npx=…/v24.13.1/bin/npx` (default v20.18.0 / installed
v22.14.0 both fail promptfoo's `^20.20.0 || >=22.22.0` engine constraint; v24.13.1 satisfies it).

**Real Scorecard via `scripts/_eval_d_swarm_judge.py` (enabled=True → `npx promptfoo@latest eval` over OpenRouter):**
```
BRIDGED_ENV JUDGE_MODEL_ID_set=True OPENROUTER_set=True
SIM_RUN state=settled facts=2
===== REAL PROMPTFOO JUDGE (enabled=True -> npx promptfoo over OpenRouter) =====
REAL_JUDGE_OK scorecard: score=1.0 passed=True origin=synthetic
===== GATE behaviour =====
synthetic-only + human_approved -> allowed=False reasons=['synthetic-only evidence cannot promote customer-facing versions', ...]
real+human            -> allowed=True  live_ring=L0 reasons=[]
real+NO human         -> allowed=False reasons=['human approval is required']
```
The real `npx promptfoo` subprocess over OpenRouter returned a valid `Scorecard(score=1.0, passed=True,
origin=synthetic)` — not the offline fallback. The PromotionGate correctly bars synthetic-only evidence and
requires human approval before opening the live ring (L0).

**Required gate command (the prompt's exact invocation), Node v24.13.1:**
```
$ RUN_LIVE_PROMPTFOO=1 uv run pytest tests/integration/test_swarm_end_to_end.py -v
tests/integration/test_swarm_end_to_end.py::test_swarm_sim_run_judged_and_gate_bars_synthetic_only PASSED [ 50%]
tests/integration/test_swarm_end_to_end.py::test_real_promptfoo_judge_returns_scorecard PASSED [100%]
============================== 2 passed in 2.16s ===============================
EXIT_CODE=0
```
`test_real_promptfoo_judge_returns_scorecard` ran (PASSED, not SKIPPED) on the live path. The fast 2.16s is
promptfoo's own result-cache reuse from the eval seconds earlier — same real OpenRouter-backed judge.

**Verdict: P1-2 proven — the real promptfoo/OpenRouter judge returns a genuine Scorecard end-to-end.**

## Step 5 — P1-3 real MandateInstance (Mongo + dashboard /instances) — ✅ PROVEN

The live `run_lead_finder.py` (Step 3) persisted a canonical type + a full `MandateInstance` via
`KernelControl.register_mandate_type` + `instantiate_mandate`. Verified both in raw Mongo and through the
exact `/instances` code path (`api/state.py:instance_rows`, Mongo-backed, `seed_demo=False`):

```
MANDATE_INSTANCE total docs = 2
inst_demo present in DB? False                 <-- NOT the demo seed; these are REAL instances
non-demo agentx_dogfood_* instances found = 2

LATEST DOGFOOD MANDATE_INSTANCE DOC:
{ "id": "agentx_dogfood_1781781644", "type_ref": "lead-finder@0.1.0",
  "customer_id": "Agent-X dogfood", "ring": "L1",
  "heap_region_id": "tenant_agentx_dogfood_1781781644", "channel_binding": null, "overrides": [] }

/instances row count = 2
/instances contains inst_demo? False
/instances non-demo dogfood rows = 2
ONE /instances ROW (as the dashboard renders it):
{ "instance_id": "agentx_dogfood_1781781644", "type_ref": "lead-finder@0.1.0",
  "customer_id": "Agent-X dogfood", "ring": "L1", "approval_count": 0, "billing_total": 0,
  "latest_run": { "state": "settled", "event_count": 16,
      "settled": { "seq": 15, "trust_delta": 1,
                   "facts": [Callbox + Belkins actionable/score facts ...],
                   "watch_ids": ["…:watch:reality"] } } }
```
**Verdict:** a real (non-`inst_demo`) `MandateInstance` is persisted in Mongo and surfaced by `/instances`
with its settled run, facts, and registered watch. P1-3 proven. (The instance carries the customer-target
`ring=L1` copy; the canonical type is registered separately in `mandate_type`.)

## Step 6 — Live Hermes gate — ✅ GREEN

```
$ RUN_LIVE_HERMES=1 uv run pytest tests/kernel/test_hermes_client.py -v
tests/kernel/test_hermes_client.py::test_hermes_client_builds_openai_compatible_payload_and_endpoint PASSED [ 33%]
tests/kernel/test_hermes_client.py::test_hermes_client_from_settings_requires_key_base_url_and_model PASSED [ 66%]
tests/kernel/test_hermes_client.py::test_live_hermes_chat_completion PASSED [100%]
============================== 3 passed in 2.39s ===============================
EXIT=0
```
`test_live_hermes_chat_completion` ran live (PASSED, not SKIPPED) against MiniMax with the configured
`MINIMAX_API_KEY`/`FACULTY_MODEL_*`. The same client backed every `thought` step in the Step-3 live runs.

## Step 7 — Final ship gate + merge

_pending_
