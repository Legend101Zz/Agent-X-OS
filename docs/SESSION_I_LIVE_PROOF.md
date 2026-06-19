# Session I — Live Proof (Working Swarm from the Dashboard)

*Branch: `feat/swarm-from-dashboard`. Closes gap **G8** (Swarm REPL command surface).
Canon: [PROPOSAL_NICE_DASHBOARD_SWARM_CREATOR.md](./PROPOSAL_NICE_DASHBOARD_SWARM_CREATOR.md)
(Pillar 2, Session I) + [AUDIT_2026-06-19_POST_SESSION_H.md](./AUDIT_2026-06-19_POST_SESSION_H.md).*

## What shipped

One button on the Manager Dashboard's Foundry view now drives a scenario pack through the kernel in
**sim mode**, grades it with the promptfoo Judge, gates it with the `PromotionGate`, persists a
synthetic `EvalCase`, journals the action, and renders the BLUEPRINT §5 timeline — all on the
existing 8s poll (SSE is Session L).

| Task | Deliverable | Status |
|------|-------------|--------|
| I-1 | `api/src/agentx_api/swarm_runner.py` — `SwarmRunner` composes a **second, sim-bound** `Phase1RunInvoker` via `build_sim_registry(pack)` (mirrors `tests/integration/test_swarm_end_to_end.py`), grades + gates, returns `SwarmRunReport`. | ✅ |
| I-2 | `operator.py` — `OperatorRuntime` owns `swarm_runner: SwarmRunner`, composed in `_compose()`. | ✅ |
| I-3 | `app.py` — real `POST /commands/run-swarm` behind `Depends(_require_command_auth)` (200): resolve candidate `MandateType` → run → grade → gate → **direct write** one `EvalCase(origin="synthetic")` into `c.EVAL_CASE` (no projector) → journal one `ManagerAction(action="run_swarm")` → return the report JSON. | ✅ |
| I-4 | `gaps.py` — `command.run_swarm` removed from `CORE_GAPS`, added to `KNOWN_CLOSED`. | ✅ |
| I-5 | `foundry-view.tsx` rewritten into a two-pane Swarm REPL; new `swarm-timeline.tsx`; `runSwarm` POST helper + view models (`SwarmRunReport`, `ScorecardView`, `GateDecisionView`) in `lib/api.ts` + `lib/types.ts`. | ✅ |
| I-6 | `operator-dashboard.tsx` — Foundry nav always shown; empty state is a "run your first swarm" CTA; command props passed to `FoundryView`. | ✅ |

## Design notes (honest)

- **Isolation is structural, not tagged.** The `SwarmRunner` builds a fully self-contained sim invoker
  (`build_phase1_runinvoker(registry=build_sim_registry(pack))`) with its **own** in-memory journal,
  exactly like the proven integration test. The operator's live registry/journal are therefore never
  touched, and the swarm run's `RunCreated`/`Syscall*`/`RunSettled` events never reach the live Floor —
  so no "filter the sim instance out of the Floor" step is needed. Test `…never_touches_the_live_registry`
  asserts every fulfilled effect carries `fulfilled_by == "sim_adapter"`.
- **EvalCase hydration is real, not fabricated.** `RunResult` does not carry a hydration snapshot, so the
  runner captures one from the kernel's own `HydrationLoader` (the sim heap is empty, so the snapshot is
  honestly empty) rather than synthesising fake facts.
- **Uniform projection-store write.** Both `InMemoryProjectionStore` and `MongoProjectionStore` expose the
  same `upsert(collection, doc_id, doc)`, so the direct `EVAL_CASE` write is uniform (no `backend.name`
  branch needed). The persisted doc mirrors `score`/`passed` at the top level so the dashboard's
  `mapEvalCases` renders the bar (same shape the demo seed uses).
- **Gate evaluated with `human_approved=True`** so the *sole* operative reason is the synthetic bar —
  proving invariant #7 holds even when a human would otherwise approve (mirrors the integration test).
- **Judge stays deterministic** for the unit suite (env scrubbed by an autouse fixture); the live
  promptfoo path is opt-in via the `judge_live` toggle. The two `RUN_LIVE_*` tests stay skipped.

## Gate output (all green)

```text
### ruff
All checks passed!
### mypy strict packages db tests
Success: no issues found in 101 source files
### mypy strict api (from api/)
Success: no issues found in 10 source files
### root pytest
112 passed, 2 skipped in 0.26s        # 2 skipped = RUN_LIVE_PROMPTFOO / RUN_LIVE_HERMES (opt-in)
### api pytest
22 passed in 1.53s                     # was 16; +6 new run-swarm tests
### lint-imports
Contracts: 3 kept, 0 broken.           # agentx_api (composition edge) importing agentx_swarm is allowed
### dashboard
npm test  -> tests 10, pass 10, fail 0
npm run build -> ✓ Compiled successfully, types valid, 4/4 static pages
```

## New tests (red → green)

```text
api/tests/test_run_swarm.py::test_run_swarm_returns_scorecard_gate_and_trace          PASSED
api/tests/test_run_swarm.py::test_run_swarm_persists_exactly_one_synthetic_eval_case  PASSED
api/tests/test_run_swarm.py::test_run_swarm_gate_bars_synthetic_only                   PASSED
api/tests/test_run_swarm.py::test_run_swarm_never_touches_the_live_registry            PASSED
api/tests/test_run_swarm.py::test_run_swarm_requires_bearer_token                      PASSED
api/tests/test_run_swarm.py::test_run_swarm_eval_case_is_readable_with_top_level_score PASSED
dashboard/tests/api-client.test.ts: "runSwarm maps the swarm report into the timeline view model" PASSED
```

These cover the Session-I acceptance criteria verbatim: (a) returns scorecard + gate decision + trace
timeline payload; (b) persists **exactly one** `EvalCase(origin="synthetic")` (count delta = 1);
(c) `PromotionGate` **bars** the synthetic-only result with the documented reason string;
(d) unauthorized → **401**; (e) the sim run never touches the live registry (`fulfilled_by ==
"sim_adapter"` on every effect).

## Verdict

The synthetic `EvalCase` is persisted, the gate bars it, the route is journaled, and the dashboard
renders the §5 timeline — end-to-end **in-memory** (the same backend the 22-test api suite exercises).
**Live-Mongo browser proof is deferred to the operator**, the same caveat as Session H: the
projection-store write path is identical for memory and Mongo (`upsert`), and the api suite proves the
memory path, but an actual Mongo-backed click-through has not been run here. No real-engine
(Hermes/MiroFish) adapters, no `/patch` re-run loop, and no `/commands/promote` — those remain
Sessions J/K as scoped.
