# Session I — Working Swarm from the Dashboard

*Paste this whole file into a fresh session. Goal: one button on the Manager Dashboard runs a
scenario pack through the kernel in sim mode, grades it with the Judge, gates it, persists a
synthetic `EvalCase`, and shows the BLUEPRINT §5 timeline. This closes gap **G8** (Swarm REPL
command surface). Canon for this session: [PROPOSAL_NICE_DASHBOARD_SWARM_CREATOR.md](./PROPOSAL_NICE_DASHBOARD_SWARM_CREATOR.md)
(Pillar 2 + Session I task list) and [AUDIT_2026-06-19_POST_SESSION_H.md](./AUDIT_2026-06-19_POST_SESSION_H.md).*

## ⚠️ A PARALLEL SESSION IS RUNNING RIGHT NOW — coordinate

A second agent (**Codex**) is working **concurrently** on **Session L — Real-time SSE + feedback**,
on branch **`feat/dashboard-realtime-sse`**. You are **Claude Code on `feat/swarm-from-dashboard`**.
Both branches push to `origin`; the founder merges both to `main` later (**swarm merges FIRST**, then
SSE rebases on top). You cannot talk to the other session live, so the only way to avoid a painful
merge is file discipline:

**Two files are touched by BOTH sessions — shared territory:**
1. `api/src/agentx_api/app.py` — *you* edit the `run_swarm` route (line ~567) + add the
   `RunSwarmCommand` model. Codex rewrites `stream_events` (line ~342, a **different function**).
   Do **not** reorder/reformat/reorganise this file or its import block; keep your change inside your
   route + model so the 3-way merge stays clean.
2. `dashboard/src/components/operator-dashboard.tsx` — *you* edit **only** (a) the Foundry nav filter
   (line ~401, un-hide) and (b) the `case "foundry"` render (line ~383, pass command props). Codex
   edits the polling effect (~141), the toast/`commandResult` wiring (~92), and the bottom ledger
   (~468) — **different regions**. Do not touch the polling effect, the toast state, or the bottom
   ledger.

**You OWN (Codex will not touch):** `foundry-view.tsx`, `swarm-timeline.tsx`, the Foundry nav un-hide,
`runSwarm` in `lib/api.ts`, swarm view-models in `lib/types.ts`, `dashboard/tests/api-client.test.ts`,
all of `api/src/agentx_api/swarm_runner.py` + `operator.py` + `gaps.py` + `api/tests/test_run_swarm.py`.

**Codex OWNS (do NOT touch these):** `dashboard/src/components/shared.tsx`,
`dashboard/src/lib/events.ts` (new), `dashboard/tests/events.test.ts` (new),
`api/tests/test_events_stream.py` (new), and the SSE/toast/polling wiring inside the shell + ledger.

**Commit + push cadence:** commit small and often with a `[session-i]` prefix and
`git push -u origin feat/swarm-from-dashboard` after each green step. Open a PR to `main`; do **not**
merge to `main` yourself.

## Context

`feat/dashboard-operability` (Sessions C–H + the post-H audit) is **merged to `main`** at
`6566ce4 Feat/dashboard operability (#4)`. The dashboard is operable end-to-end in-memory (15 tests).
The swarm grading machinery already exists and joins up **in sim** — but no HTTP command drives it
and `POST /commands/run-swarm` is a **501 stub**. This session makes the swarm runnable from the
dashboard. The founder confirmed two decisions: **swarm first** (this session), and the Creator must
use the **human-gated chain** (Sessions J/K, not this one).

> Note: `docs/AUDIT_2026-06-19_POST_SESSION_H.md` and `docs/PROPOSAL_NICE_DASHBOARD_SWARM_CREATOR.md`
> are currently **untracked** in the working tree (written during the audit, never committed). Commit
> them as part of this session's first commit so the canon is on `main`.

## First actions

```bash
cd "/Volumes/Mrigesh SSD/Startup/Agent-X-OS"
git checkout main && git pull
git status                      # expect 4 untracked docs: AUDIT_*, PROPOSAL_*, SESSION_I_PROMPT, SESSION_L_PROMPT
git checkout -b feat/swarm-from-dashboard
# YOU own the canon docs — commit them first so they land on this branch (Codex is told NOT to add them):
git add docs/AUDIT_2026-06-19_POST_SESSION_H.md docs/PROPOSAL_NICE_DASHBOARD_SWARM_CREATOR.md docs/SESSION_I_PROMPT.md docs/SESSION_L_PROMPT.md
git commit -m "[session-i] docs: land audit + proposal + session I/L prompts"
git push -u origin feat/swarm-from-dashboard
git log --oneline -5
```

Then run the gate once to confirm a green baseline before touching anything (see the **Gate** section
for the full command set).

## Read these first (canon — do not re-derive)

1. `docs/PROPOSAL_NICE_DASHBOARD_SWARM_CREATOR.md` → **Pillar 2** + the **Session I** task list (I-1…I-6).
2. `tests/integration/test_swarm_end_to_end.py` — the exact, already-proven composition this session
   wraps in HTTP. **Copy its sequence; don't reinvent it.**
3. `packages/swarm/src/agentx_swarm/{sim,judge,gate,scenarios,trace}.py` — the pieces you compose.
4. `api/src/agentx_api/{app,operator,gaps}.py` — where the route, the runtime, and the gap entry live.
5. `dashboard/src/components/foundry-view.tsx` + `dashboard/src/lib/{api,types}.ts` — the UI you rewrite.

## What is BUILT and PROVEN — DO NOT rebuild

- The full swarm loop, proven in `tests/integration/test_swarm_end_to_end.py`:
  `load_builtin_scenario_pack("indian_b2b_leads_v1")` → `build_sim_registry(pack)` →
  `build_phase1_runinvoker(registry=...)` → `invoker.invoke(mandate, instance, trigger, mode="sim")`
  → `build_promptfoo_judge(enabled=?, case_origin="synthetic").grade(trace, rubric)` →
  `PromotionGate.evaluate(PromotionGateInput(...))`.
- `trace_to_viewer_payload(trace, scorecard=...)` (`packages/swarm/.../trace.py`) **already** shapes a
  timeline JSON for the UI — reuse it.
- `PromotionGate` (`gate.py`) already enforces invariant #7 (synthetic-only is barred). Do not change it.
- The `PromptfooJudge` + deterministic fallback is enough — **no promptfoo changes** this session.
- The dashboard command path (auth, `OperatorRuntime`, worker pump) from Session H — reuse it.

## The tasks (TDD — write the tests in step 0 first)

### 0. Tests first (red)
- **New:** `api/tests/test_run_swarm.py` —
  (a) `POST /commands/run-swarm` returns a scorecard + gate decision + a `trace` timeline payload;
  (b) it persists **exactly one** `EvalCase(origin="synthetic")` (assert count delta = 1);
  (c) `PromotionGate` **bars** the synthetic-only result (`allowed == False`, the synthetic reason
      string present);
  (d) unauthorized call (no Bearer) → **401**;
  (e) the sim run **never touches the live registry** — assert the real `lead_research_batch`/
      `draft_email` adapters were not invoked (use the sim registry only; e.g. spy the live registry
      `resolve` is never called, or assert `fulfilled_by == "sim_adapter"` on every effect).
- **Change:** `dashboard/tests/api-client.test.ts` — `runSwarm(...)` maps the report into the
  timeline view model.

### I-1 — `SwarmRunner` (api layer; composition edge MAY import `agentx_swarm`)
- **New:** `api/src/agentx_api/swarm_runner.py` → `SwarmRunner` that builds a **second, sim-bound**
  `Phase1RunInvoker` via `build_sim_registry(pack)` so the **live invoker (real adapters) is never
  touched**. Method: `async run(*, type_ref, pack_id, ring="L2", judge_enabled=None) -> SwarmRunReport`
  returning `{run_id, trace_payload, scorecard, gate_decision}`.

### I-2 — own it on the runtime
- **Change:** `api/src/agentx_api/operator.py` — add `swarm_runner: SwarmRunner` to `OperatorRuntime`
  and compose it in `_compose(...)` (it needs the journal + projection_store + a sim invoker;
  reuse the existing hydration/settlement/verifier wiring).

### I-3 — the real route
- **Change:** `api/src/agentx_api/app.py` — replace `run_swarm_unavailable` (currently 501, ~line 566)
  with a real `run_swarm` behind `Depends(_require_command_auth)`, status 200. Request model
  `RunSwarmCommand{type_ref, pack_id, ring="L2", actor}`. It must:
  1. resolve the candidate `MandateType` from the catalog (fallback `build_lead_finder_type()`),
  2. call `runtime.swarm_runner.run(...)`,
  3. **persist** the graded run as `EvalCase(origin="synthetic", scorecard=..., tags=[pack_id,"swarm"],
     type_ref=...)` **directly** into `c.EVAL_CASE` (EVAL_CASE has **no projector** — direct write;
     branch on `runtime.backend.name` for memory vs Mongo),
  4. journal **one** `ManagerAction(action="run_swarm", detail={pack_id, score, passed, gate_allowed})`,
  5. return the `SwarmRunReport` JSON.

### I-4 — retire the gap
- **Change:** `api/src/agentx_api/gaps.py` — remove `command.run_swarm` from `CORE_GAPS`, add it to
  `KNOWN_CLOSED`.

### I-5 — Swarm REPL UI
- **Rewrite:** `dashboard/src/components/foundry-view.tsx` into a two-pane Swarm REPL: left = a
  "Run a swarm" form (candidate `type_ref`, `pack_id`, ring, judge-live toggle — mirror
  `catalog-create.tsx`'s form + POST pattern); right = the §5 timeline.
- **New:** `dashboard/src/components/swarm-timeline.tsx` — renders the
  `scenario → mandate decision → syscall attempt → parked/manual → judge comment → score → patch`
  shape from the returned `trace_payload` + `scorecard` + `gate_decision`.
- **Change:** `dashboard/src/lib/types.ts` — add **view-only** models `SwarmRunReport`,
  `ScorecardView`, `GateDecisionView` (these are dashboard view models, **not** contracts — the
  `packages/contracts` seam stays frozen). Add a `runSwarm` POST helper in `dashboard/src/lib/api.ts`.

### I-6 — un-hide Foundry
- **Change:** `dashboard/src/components/operator-dashboard.tsx` — stop filtering out the Foundry nav
  when `evalCases.length === 0` (~line 401); empty state becomes a "Run your first swarm" CTA.

## Gate (must be green before push)

```bash
cd "/Volumes/Mrigesh SSD/Startup/Agent-X-OS"
uv run ruff check .
uv run mypy --strict packages db tests
cd api && uv run mypy --strict src tests && cd ..      # NOTE: from api/, not root (fastapi lives there)
uv run pytest -q
cd api && uv run pytest -q && cd ..
uv run lint-imports                                     # expect 3/3 kept
cd dashboard && PATH=/opt/homebrew/bin:$PATH npm test && PATH=/opt/homebrew/bin:$PATH npm run build && cd ..
```

## Explicit no-go (out of scope this session)

- No real-engine swarm adapters (no Hermes Swarm, no MiroFish) — sim only, on **our** gateway.
- No `/patch` re-run loop and no `/commands/promote` (those are Sessions J/K).
- No Creator (Session J). No SSE/real-time (Session L) — `run-swarm` ships on the existing 8s poll.
- No new `packages/contracts` types. No promptfoo judge changes. No Mongo fixture fakes.
- No multi-user auth — the bearer token stays the trust boundary.

## Deliverables

1. The code above, gate green, on `feat/swarm-from-dashboard`.
2. `docs/SESSION_I_LIVE_PROOF.md` — the gate output + the new test output + a one-paragraph honest
   verdict (synthetic `EvalCase` persisted; gate bars it; UI shows the timeline; live-Mongo browser
   proof deferred to the operator, same caveat as Session H).
3. The canon docs were committed in your first commit (see First actions). Open a PR from
   `feat/swarm-from-dashboard` to `main`; do **not** merge to `main` yourself. Keep pushing after each
   green step.

## Gotchas

- Dashboard `npm` needs Node ≥18: prefix with `PATH=/opt/homebrew/bin:$PATH` (system node is v16).
- The lane fence (`lint-imports`) bars kernel/mandate ↔ syscall/swarm. `agentx_api` is **neither
  lane** (it's the composition edge), so importing `agentx_swarm` there is allowed — verify
  `lint-imports` stays 3/3 after the import.
- `EVAL_CASE` has **no projector** — the write is deliberately direct; do not add a projector.
- `EvalCase` requires a `HydrationSnapshot` — it's on the `RunResult` the sim invoke returns; pass it
  through, don't synthesize a fake one.
- The two skipped pytest items (`RUN_LIVE_PROMPTFOO=1`, `RUN_LIVE_HERMES=1`) stay skipped — keep the
  Judge in deterministic fallback for the unit tests; the live promptfoo path is opt-in.

Begin.
