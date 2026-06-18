# SESSION E — Fix the Session D punch-list (P0 correctness bugs + P1 lead quality)

*This is the in-depth, paste-ready prompt for the fix session that follows the Session D shakedown.
It restates the mechanics of every bug so you don't have to re-derive them, and points at exact
`file:line`s. Ground truth: `docs/EVAL_FINDINGS.md` (the punch-list) and `findings.md` (Session D
section — full traces, leads, drafts, root-causes). When this prompt and the code disagree, trust the
code and say so.*

---

```
SESSION E — Fix the P0/P1 punch-list from the Session D shakedown
working dir: /Volumes/Mrigesh SSD/Startup/Agent-X-OS
```

## 0. What you are inheriting (read this first)

Phase 1 has been integrated and run live (Session C), then **evaluated honestly (Session D)**. The kernel
mechanics are sound (rings, human-task tail, idempotency-no-double-effect, append-only journal with
monotonic seq, deterministic projections). The gate is green: `mypy --strict` (85 files), `ruff`,
`lint-imports` 3/3, `pytest` 65p+1skip, live Hermes↔Minimax 3p.

But the shakedown found the system behaves like a **deterministic pipeline that returns bad leads**, plus
three real correctness bugs. Your job is to fix them — **TDD, Phase-1 only, gate stays green at every step.**

The headline problems, in plain terms:
1. **Leads are not actionable** — across two live ICPs, 0 of 6 "leads" were real prospects; they were
   YouTube videos, listicles, an Instagram post, and a competitor SaaS page. The drafts are unsendable.
2. **The reality→growth loop is dead at the source** — settlement computes a 72h watch and then throws it
   away, so no `WatchRegistered` is ever journaled and deferred-settle can never fire.
3. **The approval surface lies** — on a real parked run the dashboard cannot show the draft the manager is
   approving (the card is never journaled).
4. **Idempotency replay is lossy** — a replayed syscall returns `output={}`, silently losing the payload.
5. **The real promptfoo judge has never actually run** (Node too old + an incomplete bridge).

## 1. Required reading (skim, then act)
- `docs/EVAL_FINDINGS.md` — the prioritized punch-list (P0/P1/P2), each with repro + `file:line` + G#.
- `findings.md` (Session D section) — the raw evidence: both live traces, all 6 leads, the drafts, the
  per-finding root-cause with code references.
- `docs/STATE_AND_ROADMAP.md` §2 (G-table; note G3 is now ❌, G9 🟡), §3 Steps C/D/E (the completion path).
- `docs/BLUEPRINT.md` §2 (the 7-step core loop — esp. step 6 "settle: register WATCH" and step 7 "deferred
  settle"), §4 (the 8 invariants), §7 (Phase-1 done-conditions / "~100 settles").
- `CLAUDE.md` (your lane + invariants), `AGENTS.md` (syscall/swarm lane).

## 2. Preconditions & environment setup
- `.env` is filled (verified in Session D): `MONGODB_URI`, `MINIMAX_API_KEY`, `FACULTY_MODEL_BASE_URL`,
  `FACULTY_MODEL_ID`, `FIRECRAWL_API_KEY`, `OPENROUTER_API_KEY`, `JUDGE_MODEL_ID`. Live runs make real
  Minimax/Firecrawl/Mongo/OpenRouter calls and cost money — **authorized for this session.**
- **Node:** for P1-2 (real promptfoo judge) you MUST upgrade Node to `^20.20.0 || >=22.22.0`
  (Session D had `v20.18.0`, which `promptfoo@latest` refuses to run on). Do this before attempting P1-2.
- Shell quirk: the working dir resets between commands — prefix each with
  `cd "/Volumes/Mrigesh SSD/Startup/Agent-X-OS"` and `export _ZO_DOCTOR=0` to silence zoxide noise.
- Reusable Session-D repro instruments (untracked scratch, pass ruff) live in `scripts/_eval_d_*.py`:
  `_eval_d_inspect.py` (live run → full trace + heap + draft + thread/resume/watch + journal seq, ICP via
  `AGENTX_EVAL_ICP_JSON`), `_eval_d_kernel_stress.py` (idempotency/rings/human-tail), `_eval_d_swarm_judge.py`
  (real judge + gate), `_eval_d_dashboard.py` (approval-card reconstruction). Use/extend them to prove fixes.

## 3. Global constraints & method (non-negotiable)
- **Phase 1 ONLY.** No money/WhatsApp/voice/browser; no compiler; `draft_email` stays draft-only (`sent:false`).
- **TDD** (`superpowers:test-driven-development`): write the failing test first, then the fix. Do not weaken
  or delete existing tests. The **seam proof must stay green on the OwnHarness double**
  (`tests/integration/test_seam_proof.py`).
- **`packages/contracts` is the frozen seam.** Some fixes below need a contract change — that is allowed but
  **deliberate**: change the contract, re-run the contract-guardian review, and re-run the FULL gate + seam
  proof. Each contract change is called out explicitly below. Prefer the no-contract-change option when one exists.
- **Keep invariants enforced:** lane isolation + `mandate` holds-no-credentials (`lint-imports` 3/3 +
  `tests/test_credential_boundary.py`); facts reach the heap only via the settlement engine with provenance.
- **`verification-before-completion`:** every "done" claim is backed by pasted command output / live traces /
  real leads. No assertions without evidence.
- After each item: run the gate (`uv run mypy --strict packages db tests && uv run ruff check && uv run pytest -q
  && uv run lint-imports`). At the very end also run `RUN_LIVE_HERMES=1 uv run pytest tests/kernel/test_hermes_client.py -v`.

---

## 4. THE FIXES (do P0 → P1; each: what / why / root cause / where / approach / done-when)

### P0-1 · Settlement must actually register the WATCH (and decide on thread advance) — unblocks G3
- **What's wrong:** Every settled run computes a 72h `Watch` and a `ThreadUpdate`, but they are silently
  dropped. `WATCH` projection docs = 0 after any settle; threads stay `state="engaged" history=[]` forever.
  Because no `WatchRegistered` is ever journaled, deferred-settle / probation→verified promotion / real
  graded eval-cases are impossible — the entire reality→growth loop (G3, BLUEPRINT §2 step 7) is dead.
- **Root cause / where:**
  - `packages/mandate/src/agentx_mandate/settlement.py:93-104` (`_watches`) and `:107-117` (`_thread_update`)
    DO build the rich `Watch` (condition + deadline) and `ThreadUpdate` into the `SettlementEvent`.
  - `packages/kernel/src/agentx_kernel/settlement.py:21-40` (`SettlementCommitter.commit`) appends ONLY a
    `RunSettled` carrying `watch_ids=[w.id for w in settlement.watches]` (just the ids) and `spawned=[...]`.
    It emits **no `WatchRegistered`** and ignores `settlement.thread_update` entirely.
  - `packages/kernel/src/agentx_kernel/projections.py:98-119` (`WatchProjector`) only projects from
    `WatchRegistered`/`WatchFired`, so the watch never materializes.
- **Approach (the watch part needs NO contract change — `WatchRegistered` already exists):**
  - `WatchRegistered` is already a frozen journal event (`packages/contracts/.../journal.py:117-122`:
    `watch_id`, `condition`, `deadline`). In `commit`, after appending `RunSettled`, append one
    `WatchRegistered` per `settlement.watches` (mapping `Watch.id/condition/deadline`) and project each via
    `self._projections.apply(...)`. Keep it atomic-in-spirit (RunSettled first, then the watches).
  - **Thread advance** has no journal event kind in the frozen Phase-1 set (`ThreadProjector` only fires on
    `RunCreated`). Two options — pick one and state it: (a) add a `ThreadUpdated` journal event kind +
    projector branch (a **deliberate frozen-contract change** → coordinate + full re-gate), or (b) leave
    threads inert for Phase-1 and document it in `projections.py` and STATE_AND_ROADMAP. Minimum bar for this
    session: the **watch must materialize.**
- **Done-when:** new TDD test asserts a settle appends `WatchRegistered` and the `WATCH` projection has a
  pending doc with the right `condition`/`deadline`. Live proof: `uv run python scripts/_eval_d_inspect.py`
  now shows `WATCH docs (count>=1)`. Maps to **G3**, BLUEPRINT §2 step 6/7.

### P0-2 · Make idempotency replay faithful (stop returning `output={}`)
- **What's wrong:** Re-invoking a syscall with the same `idempotency_key` correctly avoids a double effect,
  but the replayed `SyscallResult` has an **empty** `output` — the original draft body / research leads are
  gone. Any crash-resume or replay path silently loses the payload.
- **Root cause / where:** `packages/kernel/src/agentx_kernel/gateway.py:176-186` (`_prior_result`) rebuilds a
  `SyscallResult` from the `SyscallSettled` journal event, which has **no `output` field**
  (`packages/contracts/.../journal.py:64-72`). (Also note: `_prior_result` does an O(n) `read_instance` scan
  per call — fine for now, but don't make it worse.)
- **Approach (prefer the no-contract-change option):**
  - **Option A (no contract change, recommended):** persist each settled syscall's `output` in a small
    projection/store keyed by `(instance_id, idempotency_key)` at execute time, and have `_prior_result` read
    the output from there so replay returns the real payload. Keep the kernel lane-pure.
  - **Option B (contract change):** add `output: JsonObject` (or `output_ref`) to `SyscallSettled` and
    populate it in the gateway — a **deliberate frozen-contract change** → coordinate + full re-gate.
- **Done-when:** extend `scripts/_eval_d_kernel_stress.py` / add a unit test: second invoke with the same
  idem key returns `status=ok` AND the original `output` (body present), with still exactly ONE
  `SyscallSettled` for that key (no double effect). `REPLAY_LOSSY=False`.

### P0-3 · Make the approval card truthful — the manager must see the draft they approve
- **What's wrong:** On a **real** parked `draft_email` run, the dashboard cannot show the draft being
  approved. In sim the reconstructed effect is `null`; in live it's the earlier `lead_research_batch` read
  (wrong). The actual draft exists only in the in-memory `RunResult.park.approval_card` and is never
  journaled — so it's lost on process exit and invisible to any out-of-process dashboard. This breaks the
  trust ladder's bottom rung (BLUEPRINT §8 kill-condition: "if owners won't tap Approve…").
- **Root cause / where:**
  - `packages/kernel/src/agentx_kernel/gateway.py:74-85` — when the ring is too low the gateway calls
    `_park()` and returns **before** journaling any `SyscallAttempted` (that append is at `:122-136`, after
    the ring/idempotency/channel/registry checks). So at park time there is no draft `SyscallAttempted`.
  - `packages/kernel/src/agentx_kernel/run_loop.py:256-279` — the draft (`approval_card={syscall,args,
    idempotency_key}`) is attached to the in-memory `RunResult`, never journaled. `RunParked`
    (`journal.py:75-84`) carries only `reason`/`awaiting`/`required_ring`.
  - `packages/kernel/src/agentx_kernel/control.py:54-70` — `approval_inbox` returns `ApprovalItem{run_id,
    reason, required_ring, seq}` only; no card. Consumer: `api/src/agentx_api/state.py:563-567`
    (`_drafted_effect`) reverse-engineers from the last `SyscallAttempted` (which doesn't exist at park).
- **Approach:** make the parked effect durable and surface it. Two options — pick one:
  - **Option A:** journal a `SyscallAttempted` (the intent) BEFORE the ring-park in the gateway, so the
    journal records what was attempted even when parked. (Semantically true: an attempt that was gated.)
  - **Option B (contract change):** add the pending `syscall`/`args` to `RunParked` — a deliberate
    frozen-contract change → coordinate.
  - Then extend `KernelControl.approval_inbox` (`ApprovalItem`) to carry the card (`syscall`+`args`), so the
    dashboard reads it directly instead of reconstructing.
- **Done-when:** `uv run python scripts/_eval_d_dashboard.py` shows the reconstructed/served effect ==
  `draft_email` with the real body; a unit test asserts `approval_inbox` returns the draft card for a parked
  run. Coordinate with the `api/` owner if the `ApprovalItem` shape changes. Maps to **G9**, BLUEPRINT §6.

### P1-1 · Make leads ACTIONABLE (the main event) — real orgs/people/contact + usable drafts (G4)
- **What's wrong:** see `docs/EVAL_FINDINGS.md §1` — 0/6 actionable. The pipeline does ONE generic web
  search on the raw ICP string, never enriches, scores everything a flat 0.7, and emits a template draft to
  a hardcoded internal address. A founder would send none of them.
- **Root cause / where (multi-part):**
  - `packages/mandate/src/agentx_mandate/faculties/research.py:32-56` — emits one `lead_research_batch`
    with `criteria={icp,location}` verbatim. A topic query, not a prospect-finding query.
  - **No enrichment:** the `read_url` adapter exists (`packages/syscall/.../adapters.py`) but is never
    called; nothing visits a candidate page to extract `{company, decision-maker/role, buying signal,
    contact/URL}`. The run loop only applies `lead_research_batch` read output to scratchpad
    (`run_loop.py:355-360` `_apply_read_result`) — `read_url` output is currently ignored.
  - `packages/mandate/src/agentx_mandate/faculties/judgment.py:31-42` — flat `0.7` for every lead.
  - `packages/kernel/src/agentx_kernel/run_loop.py:338-352` (`_draft_args`) — fixed template, hardcoded `to`.
  - `packages/mandate/src/agentx_mandate/library/lead_finder.py:23-36` — postconditions only require
    `claimed_facts>=1` and `fact:qualified_lead_score exists`. Nothing bars a non-actionable lead.
- **Approach (deterministic multi-step pipeline — matches STATE_AND_ROADMAP §3 Step C):**
  1. **Better query:** in `research.py`, construct a prospect-finding query (e.g. directory/“contact”/site
     queries, exclude obvious content domains) and/or emit a multi-step plan. You will likely need to
     web-research Firecrawl search params — do that, don't guess.
  2. **Enrich:** after the search, call `read_url` on the top N candidates and **extract structured fields**
     `{company, decision_maker/role, buying_signal, contact_url}`. Teach the run loop (or a new enrichment
     faculty/step) to apply `read_url` output back into `ctx.scratchpad['leads']` (extend
     `_apply_read_result` to handle `read_url`, or add an enrichment pass).
  3. **Score for real:** replace the flat-0.7 stub in `judgment.py` with scoring tied to the extracted
     signal (org match, role present, signal present, contact reachable).
  4. **Draft per-lead:** rewrite `_draft_args` to produce a person-addressed outreach email citing the real
     signal (still `draft` mode, still goes to the founder-review path, but reads like real outreach).
  5. **Gate non-actionable leads:** add a postcondition (and/or have `memory-craft` only claim a lead when it
     is actionable) requiring a real URL + org-name + cited signal. `RulesVerifier` (`verifier.py`) supports
     `claimed_facts>=N` and `fact:PRED exists`; encode actionability as a predicate (e.g. only stamp
     `qualified_lead_score` / a new `actionable_lead` fact when the lead passes), or extend the verifier.
- **Scope honesty:** doing this *really well* eventually wants **G1** (the LLM driving the loop so research is
  genuinely multi-step and adaptive). For Session E, implement the **deterministic multi-step pipeline**; if
  you hit a wall that truly needs G1, scope it honestly, ship what improves quality, and leave G1 on the
  roadmap (STATE_AND_ROADMAP §3 Step A). Do NOT fake leads — real provenance only (invariant #1).
- **Done-when:** run **two live ICPs** (default dogfood + e.g. "independent dental clinics, Pune") via
  `scripts/run_lead_finder.py` / `_eval_d_inspect.py`; paste the leads + drafts; target **≥1 genuinely
  actionable lead per run** (real org + person/role + reachable URL + cited buying signal) that a founder
  would actually send, and the postcondition rejects article/video/competitor "leads". Maps to **G4**.

### P1-2 · Make the REAL promptfoo judge actually work (it has never run end-to-end)
- **What's wrong:** only the offline fallback and a **fake-runner** unit test exercise the judge. Driving the
  real path fails (Node version), and on inspection the bridge wouldn't produce a `Scorecard` even on a good
  runtime, and it isn't wired to `.env`.
- **Root cause / where:** `packages/swarm/src/agentx_swarm/judge.py` — `_promptfoo_env` reads raw `os.environ`
  not Settings (`:150-167`); generated config has **no `assert:` block** and the provider just echoes the
  trace (`:170-209`); base command uses `--output json` (promptfoo treats `--output` as a FILE path, not
  stdout) while `_extract_scorecard_payload` expects a `Scorecard`-shaped stdout (`:212-227`). The only
  enabled-path test uses a fake runner (`packages/swarm/tests/test_phase1_swarm.py:146-181`).
- **Approach:** (a) upgrade Node (see §2); (b) bridge `.env`→`os.environ` for the enabled path at the worker
  edge (the swarm package can't import config — do the export in the runner/script, like `run_lead_finder`
  does for Settings); (c) make the bridge actually grade: add a model-graded / `llm-rubric` assert so the
  judge model scores against the rubric, point `--output` at a real file, and parse promptfoo's results JSON
  into a `Scorecard`; (d) add an **opt-in** live integration test gated like `RUN_LIVE_HERMES` (e.g.
  `RUN_LIVE_PROMPTFOO=1`) that runs real `npx` and asserts a valid `Scorecard`.
- **Done-when:** `scripts/_eval_d_swarm_judge.py` (with supported Node) prints `REAL_JUDGE_OK` with a real
  score; the opt-in test passes when enabled and is skipped otherwise; the offline fallback + gate behavior
  remain green. Maps to swarm/grading quality (supports G3 real eval-cases, G12 later).

### P1-3 · Persist the mandate instance on run start (so the dashboard shows real data) — G5 (minimal)
- **What's wrong:** real runs never write `mandate_type`/`mandate_instance`/`mandate_run`, so the dashboard
  `/instances` (and its approvals enumeration, ring counts) is empty after real runs — only `seed_demo`
  populates it.
- **Root cause / where:** `scripts/run_lead_finder.py` + the run loop build the mandate/instance inline and
  never persist; collections exist (`db/src/agentx_db/collections.py:9-11`) but nothing reads/writes them.
- **Approach (minimal Step E):** on run start, persist a `MandateInstance` row (and ideally `MandateType` +
  a `MandateRun` summary) through a small `MandateRegistry` behind a Protocol (kernel-edge), exposed via
  `KernelControl` (`register_type`/`instantiate`/`list_catalog`). Keep the kernel lane-pure (wire at the edge).
- **Done-when:** after a live run, Mongo `mandate_instance` has the run's instance; the dashboard `/instances`
  returns it. Maps to **G5** (and makes **G9** usable on real data).

### P2 (do only if P0/P1 are solid; don't let these block)
- **P2-1** `resume.ring` stays `L0` for an L1 instance → `floor()` misreports (`projections.py:148-153`,
  `control.py:81-89`): seed/track ring from the binding or fall back to it in `floor()`. (G6)
- **P2-2** `score_lead` is in gateway `_POLICY` (`gateway.py:41`) with no adapter → silently `human_task`:
  implement it or drop it from policy. (G7)
- **P2-3** `DraftEmailAdapter.required_ring="L1"` (`adapters.py:374`) is dead metadata (gateway forces L2):
  align metadata with policy.
- **P2-4** `Fact.decay_at` always null / no decay-GC: set a decay horizon + GC pass.
- **P2-5** cost/usage not surfaced (`run_lead_finder.py:223`): capture token/credit usage into billing lines.
- (`projection.manual_queue_durable` and `projection.full_trace_snapshot` are already correctly tracked in
  `api/src/agentx_api/gaps.py` — coordinate with the api owner; not re-listed here.)

---

## 5. Order of work (low-risk correctness first, then the quality crux)
1. **P0-1** settlement watch (no contract change) + decide thread handling. *(isolated, TDD, fast)*
2. **P0-2** idempotency replay fidelity. *(isolated, TDD)*
3. **P0-3** truthful approval card. *(coordinate if `ApprovalItem`/`RunParked` shape changes)*
4. **P1-1** actionable leads — the main event; budget most of the session here; prove with 2 live ICPs.
5. **P1-2** real promptfoo judge (after Node upgrade).
6. **P1-3** persist mandate instance.
7. **P2** as time allows.

## 6. DONE WHEN
- P0-1, P0-2, P0-3 fixed with TDD tests + live proof (watch doc exists; replay returns the real output; the
  approval card shows the real draft).
- Leads are actionable on two live ICPs (paste the leads + drafts; ≥1 sendable lead per run); the postcondition
  rejects non-actionable "leads".
- Real promptfoo judge produces a valid `Scorecard` on supported Node (opt-in test); offline + gate stay green.
- `mandate_instance` is persisted on real runs and the dashboard shows it.
- FULL gate green and pasted: `uv run mypy --strict packages db tests` · `uv run ruff check` · `uv run pytest -q`
  · `uv run lint-imports` · `RUN_LIVE_HERMES=1 uv run pytest tests/kernel/test_hermes_client.py -v`. Seam proof
  green on the OwnHarness double.
- `docs/STATE_AND_ROADMAP.md` G-table updated to reflect what's now closed (esp. G3, G4, G9), and
  `docs/EVAL_FINDINGS.md` items checked off.
- Short report: what you fixed, with evidence; what you deliberately deferred (and why); the next 3 things
  (drive toward STATE_AND_ROADMAP §3 Steps A/B — the LLM-driven loop and repeatable runner — after this).

---

*Hand this whole file to the next session (or paste it). It is self-contained: the mechanics, the exact
`file:line`s, the contract-change call-outs, and the done-when bars are all here. When in doubt, trust the
code over this prompt and say so.*
