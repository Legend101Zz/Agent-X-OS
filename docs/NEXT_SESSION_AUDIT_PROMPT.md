# Resume prompt for a fresh agent session

Paste this verbatim into a new chat. Replace `<DATE>` and `<COMMIT>` with current values when you start.

---

## Context

Working in `/Volumes/Mrigesh SSD/Startup/Agent-X-OS` on branch `feat/dashboard-operability` (off `main@3fbb285`). Last commits: `f826fa5 feat: frontend dashboard changes` and `79395e4 Session H polish: docs + final mypy fixes`. Branch is pushed to `origin/feat/dashboard-operability`. Previous sessions (C through H) built and proved Phase-1 dashboard operability. You are picking up here to **assess where we are, how far we are from the blueprint, and what's left for a "nice dashboard + working swarm + mandate creator"**. Do NOT rebuild anything that exists; only audit, identify gaps, and propose the next sessions.

## First actions

```bash
cd "/Volumes/Mrigesh SSD/Startup/Agent-X-OS"
git status
git log --oneline -10
ls -la
```

Confirm you are on `feat/dashboard-operability` and the tree is clean.

## Read these (in order — they are the canon)

1. `docs/BLUEPRINT.md` — the source of truth for what "done" looks like (§1 mandates, §2 lifecycle, §3 syscalls, §4 kernel, §4.5 harnesses, §5 foundry + creator, §6 dashboard, §6.1 operator agent, §7 phase order, §8 lineage + kill conditions)
2. `docs/STATE_AND_ROADMAP.md` — verified snapshot of what is built today (G1-G13 gap table)
3. `docs/SESSION_DASHBOARD_OPERABILITY_PROOF.md` — Session H proof: 15 new tests, gate green, branch pushed
4. `docs/flowwalk/mandate-dashboard-readiness.md` — the pre-Session-H audit
5. `docs/SESSION_G_LIVE_PROOF.md` and `docs/SESSION_F_LIVE_PROOF.md` — what the live loop looks like
6. `progress.md` — chronological log, Session H block is at the top

## Inventory commands (run after reading)

```bash
# Source LOC + language breakdown
uv run ruff check . && uv run mypy --strict packages db tests && uv run mypy --strict api/src tests
uv run pytest -q
cd api && uv run pytest -q && cd ..
uv run lint-imports
cd dashboard && PATH=/opt/homebrew/bin:$PATH npm test && npm run build && cd ..
```

Then inspect the directory tree (skip caches):

```bash
find . -type d \( -name node_modules -o -name .venv -o -name .next -o -name __pycache__ \
  -o -name .mypy_cache -o -name .ruff_cache -o -name .pytest_cache -o -name .import_linter_cache \
  -o -name dist -o -name build \) -prune -o -type f \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.md" \) -print | sort
```

## What is BUILT and PROVEN (do not rebuild)

- **Kernel (online, deterministic, dumb)** — `packages/kernel/src/agentx_kernel/`:
  `run_loop.py` (Phase1RunInvoker.invoke + resume), `gateway.py` (ring + idempotency + channel + adapter + credential inject + journal), `verifier.py` (rules + human park), `scheduler.py` (TriggerWork/ApprovalWork + worker), `settlement.py` (atomic RunSettled + watch), `hydration.py`, `vault.py` (ConfigVault), `control.py` (catalog + approve + resolve_approval + enqueue_trigger + set_ring), `registry.py` (MandateRegistry), `bootstrap.py`, `ports.py`, `errors.py`, `receipts.py`, `continuations.py`, `projections.py`, `stores/` (memory + mongo).
- **Mandate (user-space pod)** — `packages/mandate/src/agentx_mandate/`: faculties
  (research, judgment, memory-craft, escalation, enrichment), `harness.py` (HarnessRunner,
  HarnessSession, OwnHarness, HermesRunner), `library/lead_finder.py`, `lead_quality.py`,
  `hydration.py`, `settlement.py`.
- **Syscall ladder** — `packages/syscall/src/agentx_syscall/`: adapters (lead_research_batch, read_url,
  draft_email, queue_manual_action, mark_outcome, human_task terminal fallback), `registry.py`
  (Phase1SyscallRegistry with maturity-ranked resolve), `manual_tasks.py` (InMemory + Mongo
  ManualTaskRepository).
- **Persistence** — `db/src/agentx_db/`: collections, indexes, setup. New `MANUAL_TASK` collection
  added in Session H.
- **Swarm / Foundry-min** — `packages/swarm/src/agentx_swarm/`: `judge.py` (PromptfooJudge subprocess
  bridge with deterministic fallback), `gate.py` (PromotionGate that bars synthetic-only
  promotion), `sim.py` (SimRegistry/SimAdapter), `scenarios.py`, `scenario_packs/indian_b2b_leads_v1.json`,
  `trace.py`.
- **API** — `api/src/agentx_api/`: `operator.py` (OperatorRuntime composing journal+projections+
  control+registry+vault+receipts+continuations+scheduler+invoker+worker; in-process worker pump in
  lifespan), `app.py` (FastAPI routes), `state.py`, `gaps.py` (updated — closed gaps removed),
  `__init__.py`.
- **Dashboard** — `dashboard/src/`: `app/page.tsx`, `components/{operator-dashboard,approval-inbox,
  catalog-create,instance-file,run-detail,floor-view,foundry-view,ledger-view,capability-registry,
  shared}.tsx`, `lib/{api,types,fixtures}.ts`. Operator-token input + fail-closed disconnected state.
- **Tests** — 112 in workspace + 15 in api + 3 in dashboard, all green. Key new ones:
  `api/tests/test_operator_lifecycle.py` (7 lifecycle tests proving full instantiate→trigger→
  parked→approve→settle round-trip), `packages/syscall/tests/test_manual_tasks.py` (5).

## Three jobs you must do

### Job 1 — Honest where-we-are assessment vs BLUEPRINT.md

For each BLUEPRINT section (§1-§8), state: built, partial, missing, deferred. Use percentages
the previous flowwalk used. Anchor each claim to a file/line or a test name. Distinguish
**kernel-only proven** from **browser-proven** vs **Mongo-atlas-proven**. End with the same
flowwalk-shape verdict table the previous sessions produced (Phase-1 engine %, dashboard read %,
dashboard command %, end-to-end operability, whole blueprint %, what's left).

### Job 2 — Gap analysis for "nice dashboard + working swarm + mandate creator"

The three pillars the user named:

- **Nice dashboard** — what makes a dashboard "nice" beyond "operable"? Read
  `docs/flowwalk/mandate-dashboard-readiness.md` and the current `dashboard/src/components/`.
  Identify: design polish (motion, density, hierarchy, accessibility), missing surfaces
  (real-time updates via SSE vs 8s polling, watch/timer UI, parked-run editing, eval-case drill-down),
  observability (gym status, trust-ladder motion, watch progress), empty-state handling,
  mobile/responsive. Open `dashboard/src/components/operator-dashboard.tsx` and the styles in
  `app/globals.css`. Propose a concrete `dashboard-polish.md` backlog with priority/order.
- **Working swarm** — currently the swarm pieces exist (`sim.py`, `judge.py`, `gate.py`, scenario
  packs) but **no HTTP command drives a swarm run from the dashboard**. The task brief from
  Session D's NEXT-SESSION-CORE-GAPS-PROMPT.md listed `/commands/run-swarm` as still 501. Read
  `packages/swarm/src/agentx_swarm/` and the existing `tests/integration/test_swarm_end_to_end.py`.
  Propose: a `/commands/run-swarm` HTTP route, the journal events needed, the persistence of
  scorecards into `EVAL_CASE` with `origin="synthetic"`, and a dashboard "Swarm REPL" UI that
  visualises the timeline (scenario → mandate decision → syscall attempt → parked → judge comment
  → score → patch). Note that BLUEPRINT §5 explicitly says do NOT depend on Hermes Swarm.
- **Mandate creator** — read BLUEPRINT §5 "The Creator Mandate" carefully. It is itself a
  Mandate (charter "produce a swarm-passing Type from a description"; faculties = conversation +
  scheduling + memory-craft + escalation; emits candidates only; gate is swarm pass + human
  approve). Propose: how to model it as a real MandateType in the catalog, which faculties it
  needs (probably conversation from Hermes + scheduling + escalation), what its draft_syscall
  candidates look like (a CandidateMandateType envelope?), how the gate chain runs
  (swarm-driven sim → scorecard → PromotionGate → human approve → register_type), what the
  dashboard's "Creator" view should look like.

For each pillar, list concrete files to add/change and an ordered task list sized in 1-session
chunks (like Sessions D-H).

### Job 3 — Proposed session plan

Lay out the next 3-5 sessions (Session I, J, K, ...) with:

- session ID + one-line goal
- the ordered sub-tasks (each ≤ 1 session chunk)
- which BLUEPRINT gaps each session closes
- which tests to add (TDD-style)
- the gate to run before push
- the explicit "no-go" call (what is intentionally out of scope)

End with a re-statement of the % delta if the proposed sessions ship on plan.

## Things you MUST NOT do

- Do NOT push directly to `main`. Session H is on `feat/dashboard-operability`. New sessions
  should branch off it (or merge to main first if the user asks).
- Do NOT add Mongo fixtures that fake the production schema. The dashboard already has
  fixtures in `dashboard/src/lib/fixtures.ts` for the no-API path; do not duplicate.
- Do NOT invent new contracts. `packages/contracts` is the frozen seam.
- Do NOT build promptfoo judge changes unless the user asks; the existing `PromptfooJudge`
  + deterministic fallback is enough for Phase-1.
- Do NOT touch the dashboard's visual identity (no full redesign) — propose additive polish.
- Do NOT add multi-user auth. The bearer token model is the Phase-1 trust boundary; do not
  expand it.

## Output format

End with **three artefacts on disk**:

1. `docs/AUDIT_<DATE>_POST_SESSION_H.md` — Job 1 verdict + where-we-are table.
2. `docs/PROPOSAL_NICE_DASHBOARD_SWARM_CREATOR.md` — Jobs 2 & 3, with the dashboard-polish
   backlog, the run-swarm HTTP + UI design, the creator mandate design, and the Session I-K
   plan. Embed file paths, not file contents. Be concrete; "investigate X" is not a task.
3. A short final chat message to the user with: the verdict %, the session plan in 5 bullets,
   and the two questions you need answered before Session I can start (e.g. "do we want
   SSE now or after swarm?", "should the Creator write to the catalog directly or only emit
   candidates for human review?").

Use `final_verdict` format from the previous flowwalk doc.

## Gotchas to remember

- The current branch `feat/dashboard-operability` has commits `f826fa5` (the bulk of Session H)
  and `79395e4` (doc polish + final mypy fixes). The previous session pushed it to
  `origin/feat/dashboard-operability`.
- `dashboard npm test` needs Node ≥18; the system `node` is v16.15.1 on this Mac. Use
  `PATH=/opt/homebrew/bin:$PATH` (which has node v25.2.1).
- The fixture in `dashboard/src/lib/fixtures.ts` exists and is fine; the dashboard falls back
  to it ONLY when `AGENTX_API_ALLOW_FIXTURES=1`. In live mode (default) the dashboard fails
  closed.
- The two skipped pytest items are intentional: `RUN_LIVE_PROMPTFOO=1` and `RUN_LIVE_HERMES=1`
  are opt-in for paid live runs.
- The Mongo URI in `/Volumes/Mrigesh SSD/Startup/Agent-X-OS/.env` is real but lives on the
  operator's machine. Do not commit secrets; `.env` is gitignored.

Begin.

---

That's the prompt. It tells the next agent what to read, what NOT to redo, and asks for three concrete outputs on disk plus a final verdict + clarifying questions. Drop it into a fresh session.
