# Proposal — Nice Dashboard + Working Swarm + Mandate Creator

*Date: 2026-06-19. Companion to [AUDIT_2026-06-19_POST_SESSION_H.md](./AUDIT_2026-06-19_POST_SESSION_H.md).
Branch base: `feat/dashboard-operability` @ `ef483c8`. This doc is Jobs 2 & 3 of the post-Session-H
audit: a concrete, file-anchored gap analysis for the three pillars the founder named, plus an
ordered Session I–K plan. Every task is sized to ≤ 1 session and names the files to add/change.
Embeds file paths, never file contents. "Investigate X" is not a task; each line is a deliverable.*

**Hard constraints honoured throughout (from BLUEPRINT + the audit prompt):**
- `packages/contracts` is the **frozen seam** — no new contracts; new envelopes are composed from
  existing models (`MandateType`, `EvalCase`, `Scorecard`, `Trace`).
- New work branches off `feat/dashboard-operability` (or merge to `main` first if the user asks).
  Never push to `main`.
- No fake Mongo fixtures (the `dashboard/src/lib/fixtures.ts` no-API path already exists).
- No promptfoo judge changes — the existing `PromptfooJudge` + deterministic fallback is enough.
- No dashboard visual-identity redesign — additive polish only.
- No multi-user auth — the bearer token stays the Phase-1 trust boundary.
- BLUEPRINT §5: do **not** depend on Hermes Swarm or build MiroFish. The swarm runs on **our**
  gateway via the existing `SimAdapter`.
- BLUEPRINT invariant #4 + #7: the Creator/Operator Agent are gated *users* of the control surface,
  never code inside the live kernel; synthetic cases never promote.

---

## Pillar 1 — "Nice Dashboard"

### What "nice" means beyond "operable"

The audit found the visual identity is already strong (`dashboard/app/globals.css`: dark
control-room theme, display/mono fonts, `floor-in`/`approval-breathe`/`scan` animations, responsive
breakpoints at 1100px/760px). So **"nice" is not a redesign** — it is *missing surfaces, real-time
truth, and feedback quality*. Concretely, the gaps are:

1. **Real-time, not 8s polling.** `operator-dashboard.tsx` uses `setInterval(refresh, 8000)`. The
   `/events` route in `api/src/agentx_api/app.py:341` is a one-shot (yields 50 events then closes),
   so even SSE isn't really wired. Approvals appearing 0–8s late is the single biggest "feels dead"
   issue.
2. **No command-feedback system.** A single `commandResult` state is threaded through every view; a
   second command overwrites the first, and there is no toast/history. Operators can't tell whether a
   `trigger-run` from 5s ago actually parked.
3. **Foundry is read-only + hidden when empty.** `foundry-view.tsx` shows eval-case score bars only;
   the nav item is filtered out when `evalCases.length === 0` (`operator-dashboard.tsx:401`) — a
   chicken-and-egg that blocks reaching the swarm UI (fixed by Pillar 2).
4. **No watch/timer surface.** Watches register (`WatchRegistered`) but the dashboard never shows
   "settles in 72h" countdowns — the deferred-settle story is invisible.
5. **No trust-ladder motion.** `instance-file.tsx` shows the current ring; there is no visualization
   of L0→L4 progress or "N clean actions → eligible for promotion".
6. **Thin empty/loading states.** Some views have `EmptyState`; loading is a single spinner. No
   skeletons, no per-panel staleness.
7. **Accessibility + reduced-motion.** `aria-label`s exist on the nav and drafted-effect; missing:
   `prefers-reduced-motion` opt-out for the infinite animations, focus-visible rings, and a documented
   contrast pass.

### Concrete files to add/change (Pillar 1)

- **Real-time:** rewrite `api/src/agentx_api/app.py` `stream_events` into a true SSE generator that
  tails the journal (poll the journal store every ~1s server-side, yield new events keyed by `seq`);
  add `dashboard/src/lib/events.ts` (an `EventSource` hook) and consume it in
  `dashboard/src/components/operator-dashboard.tsx` to invalidate the relevant slices on
  `journal`/`run_settled`/`run_parked` events, keeping the 8s poll as a fallback.
- **Feedback:** add `dashboard/src/components/shared.tsx` → a `ToastStack` + `useToasts` hook;
  replace the single `commandResult` thread with a toast per command + a small "recent commands"
  log in the bottom ledger (`operator-dashboard.tsx:468`).
- **Watch/trust motion:** add `dashboard/src/components/watch-strip.tsx` (countdown chips from
  `/instances/{id}` watch ids) and a `TrustLadder` component in `instance-file.tsx` driven by the
  résumé projection + ring history already in `InstanceSummary`.
- **Empty/loading/a11y:** add skeleton variants to `shared.tsx` (`Panel` loading state); add a
  `@media (prefers-reduced-motion: reduce)` block to `globals.css` that disables the infinite
  `scan`/`approval-breathe`; add `:focus-visible` styling.
- **Backlog doc:** write `docs/dashboard-polish.md` (the prioritized backlog below) so this work is
  trackable independent of the session plan.

### `docs/dashboard-polish.md` backlog (priority order)

```text
P0 (operability-completing — do alongside the swarm/creator sessions)
  D1  True SSE journal stream + EventSource hook (kills the 8s-late feel)        [api + dashboard]
  D2  Toast/feedback system + recent-commands log                                [dashboard only]
  D3  Always-show Foundry nav (un-hide when empty) + empty-state CTA "Run a swarm" [dashboard only]
P1 (truthfulness of the live system)
  D4  Watch/timer strip (72h countdowns) on Floor + Instance File                [dashboard only]
  D5  Trust-ladder motion component (L0->L4 + "N clean -> eligible")             [dashboard; needs G6 data]
  D6  Eval-case drill-down (scorecard criteria + judge comments + trace timeline) [dashboard; needs Pillar 2]
P2 (polish)
  D7  Skeleton loaders + per-panel staleness badges                              [dashboard only]
  D8  prefers-reduced-motion + focus-visible + contrast pass                     [globals.css]
  D9  Parked-run arg editing UI (drives /commands/edit once it lands)            [dashboard; needs edit route]
```

> No-go for Pillar 1: no component library swap, no theme change, no router/Next-version bump.

---

## Pillar 2 — "Working Swarm" (drive a swarm run from the dashboard)

### The gap

All swarm pieces exist and join up **in sim** (`tests/integration/test_swarm_end_to_end.py`), but
no HTTP command drives them and no UI shows the run. `POST /commands/run-swarm` is a 501 stub
(`api/src/agentx_api/app.py:566`). The full loop the route must wrap is already proven:

```text
load_builtin_scenario_pack("indian_b2b_leads_v1")
  -> build_sim_registry(pack)                      (packages/swarm/.../sim.py)
  -> build_phase1_runinvoker(registry=...)         (packages/kernel/.../bootstrap.py)
  -> invoker.invoke(mandate, instance, trigger, mode="sim")   -> RunResult + Trace
  -> build_promptfoo_judge(enabled=?, case_origin="synthetic").grade(trace, rubric) -> Scorecard
  -> PromotionGate.evaluate(PromotionGateInput(scorecards=[...], ...))               -> PromotionDecision
```

Two design facts from the audit drive the implementation:
- The API is the **composition edge** — it may import `agentx_swarm` (the lane fence only bars
  kernel/mandate ↔ syscall/swarm; `api` is neither lane, and `test_swarm_end_to_end.py` already
  imports both). So a swarm runner lives in the API layer, not the kernel.
- `EVAL_CASE` has **no projector** (`db/src/agentx_db/projections.py`); `/eval-cases` reads the
  collection directly. So the route persists `EvalCase` docs **directly** (origin="synthetic") and
  separately journals a `ManagerAction(action="run_swarm")` for the audit trail. `EvalCase` requires
  a `HydrationSnapshot`, which `RunResult` already carries.

### HTTP design — `POST /commands/run-swarm`

- **New file:** `api/src/agentx_api/swarm_runner.py` — a `SwarmRunner` that the `OperatorRuntime`
  owns (composed once in `operator.py`, like the live invoker). It builds a **second, sim-bound**
  `Phase1RunInvoker` via `build_sim_registry(pack)` so the live invoker (real adapters) is never
  touched. Method: `async run(type_ref, pack_id, ring="L2", judge_enabled=None) -> SwarmRunReport`.
- **Change:** `api/src/agentx_api/operator.py` — add a `swarm_runner: SwarmRunner` field to
  `OperatorRuntime` and compose it in `_compose(...)`.
- **Change:** `api/src/agentx_api/app.py` — replace `run_swarm_unavailable` (line 566) with a real
  `run_swarm` route behind `Depends(_require_command_auth)`, status 200. Request model
  `RunSwarmCommand{type_ref, pack_id, ring="L2", actor}`. It:
  1. resolves the candidate `MandateType` from the catalog (or `build_lead_finder_type()` default),
  2. calls `runtime.swarm_runner.run(...)` (which invokes on the kernel in sim mode + grades +
     gates),
  3. **persists** each graded run as an `EvalCase(origin="synthetic", scorecard=..., tags=[pack_id])`
     directly into `c.EVAL_CASE`,
  4. journals one `ManagerAction(action="run_swarm", detail={pack_id, score, passed, gate_allowed})`,
  5. returns a `SwarmRunReport` JSON: `{run_id, trace (via trace_to_viewer_payload), scorecard,
     gate_decision, eval_case_id}`.
- **Remove** the `command.run_swarm` entry from `api/src/agentx_api/gaps.py` `CORE_GAPS` and add it to
  `KNOWN_CLOSED`.

### Journal events needed

- `ManagerAction(action="run_swarm", ...)` — already a valid `ManagerAction` shape; no new contract.
- The swarm run itself emits the normal `RunCreated`/`Syscall*`/`RunSettled` journal events through
  the kernel (in sim mode) — these are already journaled; tag them with the sim instance id so the
  dashboard can filter them out of the live Floor.
- (Optional, deferred) a `projection.full_trace_snapshot` if the operator needs exact in-memory
  trace events after process exit — already tracked as a gap in `gaps.py`; not required for Phase-1
  because `trace_to_viewer_payload` is returned synchronously in the response.

### Persistence into `EVAL_CASE`

- Write via `runtime.projection_store`/the Mongo collection directly with `origin="synthetic"`,
  `scorecard=<graded>`, `tags=[pack_id, "swarm"]`, `type_ref=<candidate>`. Because there's no
  projector, this is a deliberate direct write — gate it on `runtime.backend.name` so the in-memory
  backend writes to its dict store and Mongo writes to the collection.
- `PromotionGate` already enforces invariant #7 (synthetic-only is barred). The `/eval-cases` reader
  + `mapEvalCases` in `dashboard/src/lib/api.ts` already render `origin="synthetic"` as
  `promotion="blocked"`, so persisted swarm scorecards show up in Foundry automatically.

### Swarm REPL UI

- **Rewrite** `dashboard/src/components/foundry-view.tsx` into a two-pane Swarm REPL:
  - left: a "Run a swarm" form (candidate `type_ref` select, `pack_id` select, ring select,
    judge-live toggle) — mirror the `catalog-create.tsx` form pattern; POST to `/commands/run-swarm`.
  - right: a **timeline** rendering the BLUEPRINT §5 shape from the returned `trace` +
    `scorecard` + `gate_decision`:
    `scenario → mandate decision → syscall attempt → parked/manual step → judge comment → score → patch`.
- **New file:** `dashboard/src/components/swarm-timeline.tsx` — consumes the `trace_to_viewer_payload`
  shape (`{run_id, events[], scorecard?}`) plus the gate decision.
- **Change:** `dashboard/src/lib/types.ts` — add UI-only view types `SwarmRunReport`, `ScorecardView`,
  `GateDecisionView` (these are *view models*, not contracts — they live in the dashboard, the seam
  stays frozen). Add a `runSwarm` POST helper in `dashboard/src/lib/api.ts`.
- **Change:** `operator-dashboard.tsx` — stop hiding the Foundry nav when empty (Pillar 1 D3); the
  empty state becomes "Run your first swarm".
- The `/patch` half of the REPL (edit rubric/charter then re-run) is **deferred to the Creator
  session** (Pillar 3) — Phase-1 run-swarm is `/run` + `/watch` + score; iterating the candidate is
  the Creator's job.

### Ordered task list (Pillar 2 — fits one session, "Session I")

```text
I-1  swarm_runner.py: SwarmRunner composing a sim-bound Phase1RunInvoker + judge + gate   [api]
I-2  operator.py: own SwarmRunner on OperatorRuntime                                       [api]
I-3  app.py: real POST /commands/run-swarm (run -> grade -> gate -> persist EvalCase -> journal) [api]
I-4  gaps.py: retire command.run_swarm                                                     [api]
I-5  foundry-view.tsx rewrite + swarm-timeline.tsx + api.ts runSwarm helper + types view models [dashboard]
I-6  un-hide Foundry nav + empty-state CTA                                                  [dashboard]
```

---

## Pillar 3 — "Mandate Creator" (the mandate that makes mandates, BLUEPRINT §5)

### What the Blueprint actually says (re-read of §5 "The Creator Mandate")

The Creator **is itself a Mandate** (not a script): charter = "produce a swarm-passing Type from a
description"; faculties = **conversation + scheduling + memory-craft + escalation**; verification =
"passes swarm smoke tests + human approval"; settlement = "learn which faculty combinations survive
reality". Guardrail: it emits **candidates only** — the gate (swarm pass + human approve) is the
bridge to live, and it can never spawn an unverified mandate onto a real customer (invariants #4, #7).
It lives in the Foundry / Operator-Agent surface (§6.1), never in the live kernel.

### How to model it as a real `MandateType` in the catalog

- **New file:** `packages/mandate/src/agentx_mandate/library/creator.py` → `build_creator_type()`
  returning a `MandateType` (same machinery as `build_lead_finder_type()`):
  - `charter.goal` = "produce a swarm-passing candidate MandateType from a description";
    `charter.target` = `{description, vertical, channel_hint}` (the founder's brief).
  - `postconditions` = checkable: "candidate has ≥1 faculty", "candidate has a charter goal",
    "candidate names a scenario pack" — all on the `rules` rung.
  - faculties (as `FacultyBinding`s into the library): `conversation` (NEW — see below),
    `scheduling` (NEW — thin), `memory-craft` (exists), `escalation` (exists).
  - `verification` = a rubric whose pass condition is "candidate ran in the swarm and scored ≥
    threshold" (graded by the existing Judge); `settlement` = record which faculty combos passed.
- **New faculties (library data, not new contracts):** add `conversation` and `scheduling` faculties
  in `packages/mandate/src/agentx_mandate/faculties/` — `conversation` binds to the Hermes harness
  (`HarnessAdapterSpec(harness="hermes", ...)`) to turn the founder's free-text brief into a
  structured candidate; `scheduling` is a thin faculty that proposes the watch/cadence. These reuse
  the existing `Faculty` contract — the seam stays frozen.

### What the candidate looks like — the `CandidateMandateType` envelope

- The candidate **is a `MandateType`** (the frozen contract) — there is no new contract. The
  "envelope" is just the Creator run's **claimed fact / output**: a draft `MandateType` carried as
  JSON in the run's `output`/scratchpad, plus the chosen `scenario_pack_id` and `rubric`. The Creator
  emits it via the same `draft_*` mechanism the lead-finder uses for `draft_email`: a
  `draft_candidate_type` **syscall** (maturity 1, draft-only, **no live effect**) added in
  `packages/syscall/src/agentx_syscall/adapters.py` + registered in `registry.py`. Its "effect" is to
  stage the candidate for human review — never to register it live. This keeps the Creator inside the
  gateway/ring discipline (invariant #5) exactly like every other faculty.

### How the gate chain runs

```text
founder brief (description)
  -> Creator run (Hermes conversation faculty) drafts a candidate MandateType  [draft_candidate_type, parked]
  -> human reviews the draft in the Creator view, approves the draft           [/commands/approve]
  -> POST /commands/run-swarm with the candidate type_ref                      [Pillar 2, reused as-is]
       -> sim run on the kernel -> Judge scorecard (origin="synthetic") -> PromotionGate
  -> PromotionGate BARS synthetic-only; a human "promote to L0/L1" is required [/commands/promote, Session K]
  -> on promote: register_type into the catalog at L0/L1                       [KernelControl.register_mandate_type]
  -> real runs settle -> real eval_cases -> (later) compiler improves it
```

The **promote** step is the still-501 `/commands/promote` (`app.py:577`) — wiring it is its own
session (Session K), because it must call `PromotionGate.evaluate` with real evidence + human
approval before `register_mandate_type` flips a candidate live at a canary ring.

### Dashboard "Creator" view

- **New nav item** `creator` in `operator-dashboard.tsx` `navItems` + a new component
  `dashboard/src/components/creator-view.tsx`:
  - a brief box ("describe the job") + "Draft candidate" button → POSTs a `trigger-run` against the
    Creator instance;
  - renders the drafted candidate `MandateType` (charter, chosen faculties, scenario pack) for human
    review with Approve/Edit;
  - a "Run in swarm" button that reuses the Pillar-2 `/commands/run-swarm` against the candidate, and
    shows the same `swarm-timeline.tsx`;
  - a "Promote to L0/L1" button (enabled only after a real/human gate) wired to `/commands/promote`.
- This is the §6.1 Operator-Agent's future home, but Phase-1 ships the **GUI** version first (the
  conversational Operator Agent stays gap G11, deferred).

### Ordered task list (Pillar 3 — two sessions, "Session J" + "Session K")

```text
Session J (Creator as a MandateType + draft path)
  J-1  faculties/conversation.py + faculties/scheduling.py (library data, frozen contract)   [mandate]
  J-2  library/creator.py: build_creator_type()                                              [mandate]
  J-3  adapters.py + registry.py: draft_candidate_type syscall (draft-only, no live effect)  [syscall]
  J-4  app.py startup: register the Creator type in the catalog (like the canonical lead-finder) [api]
  J-5  creator-view.tsx + nav item + types view models + api.ts helper                       [dashboard]

Session K (promote gate + canary)
  K-1  KernelControl.promote(): PromotionGate.evaluate(real+human) -> register_type@canary ring [kernel]
  K-2  app.py: real POST /commands/promote behind auth + retire command.promote gap          [api]
  K-3  Creator/Foundry "Promote to L0/L1" button wired + trust-ladder motion (Pillar 1 D5)   [dashboard]
```

> No-go for Pillar 3: no Operator *Agent* (conversational G11), no compiler/GEPA (G12), no
> auto-promotion (human stays in the loop), no Creator writing to the catalog without the swarm+human
> gate.

---

## Job 3 — Proposed session plan (I → M)

Each session is ≤ 1 chunk, TDD-first, branched off `feat/dashboard-operability`, gate-green before
push. The gate for every session is the audit gate: `ruff` · `mypy --strict packages db tests` ·
`cd api && mypy --strict src tests` · `pytest` · `cd api && pytest` · `lint-imports` 3/3 ·
`cd dashboard && PATH=/opt/homebrew/bin:$PATH npm test && npm run build`.

### Session I — Working swarm from the dashboard  *(closes G8, Pillar 2)*
- **Goal:** one button on the dashboard runs `indian_b2b_leads_v1` through the kernel in sim, grades
  it, gates it, persists a synthetic `EvalCase`, and shows the §5 timeline.
- **Sub-tasks:** I-1…I-6 above.
- **Tests (write first):** `api/tests/test_run_swarm.py` — (a) `/commands/run-swarm` returns a
  scorecard + gate decision; (b) it persists exactly one `EvalCase(origin="synthetic")`; (c)
  `PromotionGate` bars the synthetic result; (d) unauthorized call → 401; (e) the sim run never
  touches the live registry (assert real adapters not invoked). `dashboard/tests/api-client.test.ts`
  — `runSwarm` maps the report into the timeline view model.
- **No-go:** no real-engine (Hermes/MiroFish) adapters; no `/patch` re-run loop; no promote.

### Session J — Creator mandate (draft path)  *(starts G10)*
- **Goal:** the founder types a job description and the Creator drafts a candidate `MandateType` that
  is reviewable in a Creator view and runnable in the Session-I swarm.
- **Sub-tasks:** J-1…J-5 above.
- **Tests (write first):** `tests/mandate/test_creator_library.py` — `build_creator_type()` has the
  four §5 faculties + checkable postconditions; `packages/syscall/tests/test_adapters.py` — the
  `draft_candidate_type` syscall is draft-only (no live effect, `sent`-style flag false);
  `api/tests/test_creator_flow.py` — trigger Creator → parked draft candidate appears in `/approvals`.
- **No-go:** no auto-registration; the candidate is a draft only.

### Session K — Promote gate + canary  *(closes the candidate→live bridge; G6 partial)*
- **Goal:** a gated `/commands/promote` registers an approved, swarm-tested candidate into the
  catalog at a canary ring (L0/L1), enforcing real-evidence + human approval via `PromotionGate`.
- **Sub-tasks:** K-1…K-3 above.
- **Tests (write first):** `tests/kernel/test_promote.py` — promote is **rejected** with
  synthetic-only evidence, **allowed** with real+human, and registers the type at the requested
  canary ring; `api/tests/test_promote_route.py` — auth + gate wired end-to-end.
- **No-go:** no auto-promotion; L2+ still gates to a human; money untouched.

### Session L — Dashboard real-time + feedback  *(Pillar 1 P0; closes the "feels dead" gap)*
- **Goal:** SSE journal stream replaces the 8s-late feel; a toast system makes every command legible.
- **Sub-tasks:** D1, D2, D3 from the polish backlog.
- **Tests (write first):** `api/tests/test_events_stream.py` — `/events` yields new journal events by
  `seq` and terminates cleanly on disconnect; `dashboard/tests/api-client.test.ts` — the EventSource
  hook invalidates the right slices.
- **No-go:** no websockets (SSE only); no state-management library swap.

### Session M — Step D maturation (reality grades runs)  *(closes G3 — the last Phase-1 engine gap)*
- **Goal:** a fired/`mark_outcome` watch promotes probation→verified facts, updates trust/résumé, and
  emits a graded `eval_case(origin="real")` — finally giving the `PromotionGate` a real corpus and
  making the Session-K promote meaningful, plus Pillar 1 D4/D5 (watch + trust motion) real data.
- **Sub-tasks:** deferred-settle worker in `settlement.py`/`scheduler.py`; `EvalCase(origin="real")`
  write; résumé/trust delta projection; dashboard watch-strip + trust-ladder consume real data.
- **Tests (write first):** `tests/kernel/test_deferred_settle.py` — watch matures → fact
  probation→verified + trust delta + one `eval_case(origin="real")`.
- **No-go:** no compiler/GEPA (G12); no Phase 2–5 channels.

### % delta if Sessions I–M ship on plan

```text
dashboard_command:   ~72%  ->  ~95%   (run-swarm, promote, edit-adjacent all live; only economy left)
dashboard_read/nice: ~88%  ->  ~95%   (SSE real-time, swarm timeline, watch/trust motion, feedback)
phase_1_engine:      ~82%  ->  ~95%   (Step-D maturation closes G3; only the ~100-settle VOLUME remains)
foundry / §5:        ~30%  ->  ~70%   (swarm REPL + Creator draft + promote gate live; compiler still ahead)
whole_blueprint_1-5: ~33%  ->  ~45%   (Phase 1 effectively complete; Operator Agent + compiler + Phases 2-5 ahead)
```

The honest cap: even after I–M, the BLUEPRINT §7 Phase-1 WIN ("~100 settles vs reality") is an
**operating** milestone (cost discipline + outcome capture), not a code one — and the conversational
Operator Agent (G11) + compiler (G12) + Phases 2–5 channels remain deliberately ahead.

## Two questions to answer before Session I starts

1. **SSE now or after the swarm?** Session I (swarm) and Session L (SSE) are independent. Doing SSE
   first makes every later session feel alive but delays the swarm; doing swarm first ships the
   headline feature on 8s polling. Recommendation: **swarm first (I), SSE next (L)** — the swarm is
   the higher-value, more-visible win and the polling is tolerable for a single operator.
2. **Should the Creator write to the catalog directly, or only emit candidates for human review?**
   The Blueprint says candidates-only (invariants #4/#7), which this plan follows (Creator drafts →
   human approves → swarm → human promote). Confirm you want the full human-gated chain (recommended)
   rather than a faster "Creator auto-registers at L0" shortcut.
