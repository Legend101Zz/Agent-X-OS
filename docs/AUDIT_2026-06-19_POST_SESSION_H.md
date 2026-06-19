# Audit — Where Agent-X Is vs BLUEPRINT.md (post-Session-H)

*Date: 2026-06-19. Branch: `feat/dashboard-operability` @ `ef483c8` (clean, pushed). Companion to
[BLUEPRINT.md](./BLUEPRINT.md) (canonical intent) and [STATE_AND_ROADMAP.md](./STATE_AND_ROADMAP.md)
(verified code snapshot). This audit is an honest where-we-are reading after Session H wired the
dashboard end-to-end. It does not rebuild anything; it grades, anchors each claim to a file/line or
test, and ends with a flowwalk-shape verdict table. Percentages are engineering judgment in the
same scale the [pre-H flowwalk](./flowwalk/mandate-dashboard-readiness.md) used, not Blueprint-defined
measurements.*

## 0. Method + proof-level legend

Every claim below is anchored. The proof level matters as much as the percentage:

- **kernel-only proven** — exercised by `uv run pytest` against in-memory stores (deterministic).
- **live-proven** — run against real MiniMax/Exa/Firecrawl and (for some) a real Mongo, per the
  `SESSION_*_LIVE_PROOF.md` docs.
- **browser-proven** — a human clicked through the Next.js UI against a running API. **Status: not
  yet done end-to-end.**
- **mongo-atlas-proven** — the full lifecycle ran against the operator's real Atlas cluster.
  **Status: deferred to the operator** (Session H §4 caveat 2).

Gate at audit time (all green): `ruff` clean · `mypy --strict packages db tests` = 101 files ·
`cd api && mypy --strict src tests` = 7 files · `pytest` = 112 passed / 2 intentional skips ·
`cd api && pytest` = 15 passed · `lint-imports` = 3/3 kept · dashboard `npm test` = 3 pass ·
`npm run build` = OK.

> **One inventory caveat to retire:** running `uv run mypy --strict api/src tests` *from the repo
> root* (as the audit prompt's inventory block literally says) reports 28 errors — but they are all
> "cannot find fastapi" + "untyped decorator", because `fastapi` lives in the `api/` subproject's own
> venv. The canonical command is `cd api && uv run mypy --strict src tests`, which is **clean**. This
> is not a regression; it is a wrong-working-directory artifact.

---

## 1. §-by-§ reading of the Blueprint

### §1 — How a MANDATE looks (Type → Instance → Run; the 7 organs) — **BUILT ~88%**

- **Built:** All three layers are real Pydantic models — `MandateType`, `MandateInstance`,
  `InstanceBinding`, `MandateRun` in `packages/contracts/src/agentx_contracts/mandate.py`. The seven
  organs are modelled: charter (`Charter`), faculties (`FacultyBinding` + `Faculty` in `faculty.py`),
  domain pack (`DomainPackRef`), verification (`VerificationSuite`), settlement (`SettlementRules`),
  gym (`gym_ref`), execution (`ExecutionProfile`). The Phase-1 type exists in code:
  `build_lead_finder_type()` (`packages/mandate/src/agentx_mandate/library/lead_finder.py`). Five
  faculties are realized as data + behaviour: research, judgment, memory-craft, escalation,
  enrichment (`packages/mandate/src/agentx_mandate/faculties/`). Proven by
  `tests/mandate/test_lead_finder_library.py`, `tests/mandate/test_faculties.py`.
- **Partial:** the **domain pack** is a bare ref (no distilled priors), and the **eval-gym** organ
  is a pointer to an empty corpus. The "faculty is a contract; harness realizes it" binding
  (`HarnessAdapterSpec`) exists but only Hermes/Own bindings are exercised.
- **Missing/Deferred:** cross-customer domain-pack priors (post-Phase-1).
- **Proof:** kernel-only proven; the type+faculties also live-proven via Session F lead runs.

### §2 — How a mandate RUNS (the core loop) — **online BUILT ~90%, deferred-settle ~30%**

- **Built (online loop):** trigger → create-run + freeze hydration → think (faculties) → act
  (gateway) → verify → settle, all in `packages/kernel/src/agentx_kernel/run_loop.py`
  (`Phase1RunInvoker.invoke`) + `hydration.py` + `gateway.py` + `verifier.py` + `settlement.py`.
  "Human approval = a parked state" is mechanically true: park → `ApprovalResolved` →
  `Phase1RunInvoker.resume` (`continuations.py`). Proven by `tests/integration/test_parked_resume.py`,
  `tests/kernel/test_run_loop.py`, and live-proven end-to-end in `SESSION_G_LIVE_PROOF.md`.
- **Partial:** the **deferred-settle / WATCH** half. `SettlementCommitter.commit` journals + projects
  a `WatchRegistered` (Session E P0-1, live-proven: one WATCH doc in Mongo), but the maturation loop
  (watch fires → probation→verified facts → trust/résumé update → emit a graded `eval_case
  origin="real"`) is **not built**. This is gap **G3 / Step D** — the single largest Phase-1 engine
  gap.
- **Missing/Deferred:** inter-mandate spawn (`SpawnRule` modelled, never fired in Phase 1 — correct).
- **Proof:** online loop live-proven; deferred-settle is kernel-only at the registration step,
  maturation absent.

### §3 — The SYSCALL / INTEGRATION layer — **BUILT ~88% (for Phase-1 scope)**

- **Built:** the gateway does ring check → idempotency (journal replay) → channel rule → adapter
  resolve → **credential injection from the vault** → execute → journal
  (`packages/kernel/src/agentx_kernel/gateway.py`, proven `tests/kernel/test_gateway.py`). The
  fulfillment ladder + `SyscallPlugin`-shaped adapter contract are real
  (`packages/syscall/src/agentx_syscall/adapters.py`, `registry.py`), with the **human-task tail** as
  the guaranteed bottom rung and a durable `MANUAL_TASK` repository (`manual_tasks.py`, proven
  `packages/syscall/tests/test_manual_tasks.py`). Real adapters: `lead_research_batch`, `read_url`
  (Exa/Firecrawl, live-proven), `draft_email` (**draft-only, `sent:false`**), `queue_manual_action`,
  `mark_outcome`. Credential boundary enforced by `tests/test_credential_boundary.py` + `lint-imports`.
- **Partial:** `score_lead` is declared in gateway policy but has no adapter (judgment scores in-pod)
  — gap **G7**, harmless.
- **Deferred (correct):** Phases 2–5 channels (real email send, calendar, CRM, browser, voice,
  WhatsApp, money). Money-as-API-only invariant is documented, not yet reachable.
- **Proof:** gateway + ladder + human tail kernel-only proven; the read/draft adapters live-proven.

### §4 — The KERNEL (two clocks; trust ladder; 8 invariants) — **online BUILT ~90%, offline Foundry ~40%, trust automation ~30%**

- **Built (online, dumb, deterministic):** scheduler/worker (`scheduler.py`), journal+heap as
  event-sourced projections (`projections.py`, `db/src/agentx_db/projections.py`), verifier, gateway,
  rings L0–L4, settlement. The **master invariants** are enforced structurally: #2 "no credential in
  user space" + the Claude/Codex lane fences are machine-checked (`lint-imports` 3/3,
  `test_credential_boundary.py`); #4 "no brain in the live kernel" holds (the LLM only proposes via
  `HarnessRunner.step`, kernel disposes); #7 "no synthetic case promotes" is enforced by
  `PromotionGate` (`packages/swarm/src/agentx_swarm/gate.py`).
- **Partial (offline Foundry):** the swarm grading machinery exists (SimAdapter, PromptfooJudge,
  PromotionGate, scenario packs, trace payload) and joins up end-to-end **in sim**
  (`tests/integration/test_swarm_end_to_end.py`) — but there is **no operator-facing REPL/command
  surface** to drive it (gap **G8**), no compiler (G12), no creator (G10).
- **Partial (trust ladder):** rings are enforced and `set_ring` is a journaled manager command
  (`control.py`), but the "N clean → propose promote / verified failure → demote" automation is
  **not built** (gap **G6**).
- **Proof:** online kernel live-proven; offline Foundry kernel-only proven in sim; trust automation
  absent.

### §4.5 — Using harnesses to full capability, safely — **BUILT ~70%**

- **Built:** `HermesRunner` (`packages/kernel/.../hermes_runner.py`) + `HermesClient`
  (`hermes.py`) drive MiniMax via OpenAI tool-calling; `OwnHarness` is the deterministic sim/test
  double (`packages/mandate/.../harness.py`). Every effectful tool is re-pointed to the gateway; the
  pod holds no creds. Live-proven (Session F).
- **Partial/Deferred:** multi-harness routing (OpenClaw/CheetahClaws), per-faculty harness arbitrage,
  native-skill enablement — modelled in `HarnessAdapterSpec` but only the Hermes/Own path runs.

### §5 — The FOUNDRY, CREATOR, and SWARM REPL — **PARTIAL ~30%**

- **Built:** the grading substrate — `build_sim_registry`, `build_promptfoo_judge` (promptfoo
  adopted, deterministic offline fallback), `PromotionGate`, `ScenarioPack` + bundled
  `indian_b2b_leads_v1`, `trace_to_viewer_payload` (`packages/swarm/`). The candidate runs through
  the **same production run-loop** with only adapters swapped (the §5 honesty principle), proven by
  `tests/integration/test_swarm_end_to_end.py`.
- **Missing:** the **Swarm REPL command surface** (`/create /run /watch /patch /promote`) — gap
  **G8**; the **Creator Mandate** — gap **G10**; the **compiler / GEPA growth loop** — gap **G12**.
  `POST /commands/run-swarm` and `/commands/promote` are **501 stubs**
  (`api/src/agentx_api/app.py:566`, `:577`).
- **Proof:** grading loop kernel-only proven in sim (+ live promptfoo behind `RUN_LIVE_PROMPTFOO=1`);
  the REPL/creator do not exist.

### §6 — The MANAGER DASHBOARD — **BUILT ~75% (operable, not yet "nice")**

- **Built:** dashboard = projections over the ledger + journaled command buttons, exactly as §6
  prescribes. Surfaces present: Floor (`floor-view.tsx`), Approval Inbox (`approval-inbox.tsx`,
  reads first-class `/approvals`), Manual Queue + Capability Registry (`capability-registry.tsx`),
  Catalog + Create-Instance (`catalog-create.tsx`, **now enabled**), Instance File
  (`instance-file.tsx`), Run Detail (`run-detail.tsx`), Ledger (`ledger-view.tsx`), Foundry
  (`foundry-view.tsx`, read-only). Command routes instantiate/trigger-run/approve/reject/set-ring are
  journaled + projected and resume parked runs through the lifespan-owned worker. Fail-closed
  disconnected state + bearer-token auth + CORS lockdown. Proven by **15 tests** (`api/tests/
  test_operator_lifecycle.py` ×7 + `test_dashboard_api.py` ×8).
- **Partial:** Foundry is **read-only** (no run-swarm, no creator, no trace drill-down); updates are
  **8s polling**, not SSE (the `/events` route is a one-shot, not a stream); no watch/timer surfacing,
  no parked-run arg editing, no trust-ladder motion; the Foundry nav item is hidden when there are no
  eval cases (chicken-and-egg).
- **Missing:** the **Economy** surface (later) and the **Operator Agent §6.1** (only an empty
  documented placeholder package `packages/operator/`).
- **Proof:** **kernel-only + in-memory proven** via the 15 tests. **NOT browser-proven and NOT
  mongo-atlas-proven** — Session H ran the lifecycle against the in-memory `OperatorRuntime`; the
  same code paths against Atlas + a real browser click-through are deferred to the operator.

### §7 — Build order (Phase 1) — **~85%**

- **Built:** one lead-finder mandate + manual projection + one operator (you), with auto syscalls
  (`lead_research_batch`, `read_url`), `draft_email` in draft mode, the human queue, `mark_outcome`.
  Kernel-min (scheduler, heap+journal, verifier rules+human, gateway L0–L2, parked-run state machine)
  on MongoDB + worker loop. Foundry-min grading loop. Dashboard-min (approval inbox + manual queue +
  instance file).
- **Missing:** the Phase-1 WIN itself — "get one instance to `settle()` against reality ~100 times."
  The plumbing is here; the **volume is not** (Session H §4 caveat 3). Step D maturation (G3) is the
  remaining code gap before that volume is meaningful.
- **Deferred (correct):** Phases 2–5.

### §8 — Lineage + kill conditions — **N/A (rationale, not buildable)**

- The kill conditions (churn vs heap depth; compiler beats hand-tuning by ~customer 5; owners tap
  Approve; demand posted between mandates) **cannot be evaluated yet** — they need real settled
  volume. Worth re-reading at the start of every post-Phase-1 session.

---

## 2. Final verdict (flowwalk-shape)

```text
final_verdict:
  phase_1_engine:            ~82%   (online loop + resume + scheduler + actionable leads live-proven;
                                      the missing ~18% is G3/Step-D deferred-settle maturation +
                                      the un-run ~100-settle volume)
  dashboard_read:            ~88%   (every read surface works against the API; the missing ~12% is
                                      real-time SSE, watch/timer surfacing, eval-case drill-down,
                                      trust-ladder motion)
  dashboard_command:         ~72%   (5/8 command routes live + journaled: instantiate, trigger-run,
                                      approve, reject, set-ring; still 501: edit, run-swarm, promote)
  end_to_end_operability:    OPERABLE IN-MEMORY (15 tests), NOT YET browser-/mongo-atlas-proven
  whole_blueprint_1_to_5:    ~33%   (Phase 1 nearly closed; Foundry-REPL, Creator, Operator Agent,
                                      compiler, and Phases 2-5 channels are all still ahead)
  delta_since_pre_H_flowwalk: dashboard_command 25-35% -> ~72%; operability "not ready" -> "operable
                                      in-memory"; engine/read/whole-blueprint roughly flat (Session H
                                      wired the UI to the existing engine, it did not extend the engine)
  whats_left_for_phase_1:
    - G3/Step-D: WATCH matures -> promote probation->verified -> trust/resume -> eval_case origin=real
    - the ~100-settle reality volume (operating discipline + cost/outcome capture, not just code)
    - browser-/mongo-atlas-proof of the dashboard lifecycle on the real cluster
  whats_left_for_the_three_pillars (see PROPOSAL doc):
    - nice dashboard:  SSE, swarm REPL surface, creator view, watch/trust motion, polish backlog
    - working swarm:   POST /commands/run-swarm + EVAL_CASE persistence + Swarm REPL timeline UI
    - mandate creator: model Creator as a real MandateType, candidate envelope, gate chain, Creator view
```

**Bottom line.** The Phase-1 *engine* is real and largely live-proven; Session H made it *operable
from the dashboard* (in-memory). The three things the founder named next — a **nice dashboard**, a
**working swarm**, and a **mandate creator** — are the natural §5/§6 frontier and are specced
concretely in `PROPOSAL_NICE_DASHBOARD_SWARM_CREATOR.md`. Nothing in this audit needs a rebuild; the
work ahead is additive.
