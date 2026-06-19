# Session L — Real-time SSE + Command Feedback

*Paste this whole file into a fresh Codex session. Goal: replace the dashboard's 8-second polling
with a true Server-Sent-Events journal stream, and add a toast/feedback system so every manager
command is legible. This is **Pillar 1, items D1 + D2** of
[PROPOSAL_NICE_DASHBOARD_SWARM_CREATOR.md](./PROPOSAL_NICE_DASHBOARD_SWARM_CREATOR.md). It does NOT
build the swarm (that's the parallel Session I).*

## ⚠️ A PARALLEL SESSION IS RUNNING RIGHT NOW — coordinate

A second agent (**Claude Code**) is working **concurrently** on **Session I — Working Swarm from the
Dashboard**, on branch **`feat/swarm-from-dashboard`**. You are **Codex on
`feat/dashboard-realtime-sse`**. Both branches push to `origin`; the founder merges both to `main`
later (**the swarm branch merges FIRST**, then this branch rebases on the updated `main`). You cannot
talk to the other session live, so file discipline is the only way to avoid a painful merge:

**Two files are touched by BOTH sessions — shared territory:**
1. `api/src/agentx_api/app.py` — *you* rewrite **only** the `stream_events` function (line ~342).
   Claude edits the `run_swarm` route (line ~567) + adds a `RunSwarmCommand` model — a **different
   region**. Do **not** reorder/reformat/reorganise this file or its import block; keep your change
   inside `stream_events` so the 3-way merge stays clean.
2. `dashboard/src/components/operator-dashboard.tsx` — *you* edit **only**: (a) the polling effect
   (line ~141, add SSE alongside it), (b) the command/toast state (line ~92), (c) the bottom ledger
   (line ~468, recent-commands log). Claude edits the Foundry nav filter (~401) and the
   `case "foundry"` render (~383) — **do NOT touch those two regions.**

**You OWN (Claude will not touch):** `dashboard/src/components/shared.tsx` (add `ToastStack` +
`useToasts`), `dashboard/src/lib/events.ts` (NEW — the `EventSource` hook + any event view types),
`dashboard/tests/events.test.ts` (NEW), `api/tests/test_events_stream.py` (NEW), and the SSE/toast
wiring inside the shell.

**Claude OWNS (do NOT touch these):** `dashboard/src/components/foundry-view.tsx`,
`dashboard/src/components/swarm-timeline.tsx`, `dashboard/src/lib/api.ts` (Claude adds `runSwarm`
there — keep your SSE logic in `events.ts`; you may *import* from `api.ts` but not edit it),
`dashboard/src/lib/types.ts` (Claude adds swarm view-models — keep your toast/event types in
`shared.tsx`/`events.ts`, not here), `dashboard/tests/api-client.test.ts`, the Foundry nav un-hide,
and everything under `api/src/agentx_api/{swarm_runner,operator,gaps}.py`.

**Commit + push cadence:** commit small and often with a `[session-l]` prefix and
`git push -u origin feat/dashboard-realtime-sse` after each green step. Open a PR to `main`; do **not**
merge to `main` yourself.

## Context

`feat/dashboard-operability` (Sessions C–H) is merged to `main` at `6566ce4`. The dashboard refreshes
by `setInterval(refresh, 8000)` (`operator-dashboard.tsx:141`); the `/events` route
(`api/src/agentx_api/app.py:342`) is a **one-shot** (yields the recent 50 events then closes) and the
UI never consumes it. Commands surface through a single `commandResult` state that a second command
overwrites — so an operator can't tell whether a `trigger-run` from 5s ago actually parked. This
session fixes both: a real SSE stream and a toast/feedback system.

## First actions

```bash
cd "/Volumes/Mrigesh SSD/Startup/Agent-X-OS"
git checkout main && git pull
git checkout -b feat/dashboard-realtime-sse
git status                      # you will see 4 untracked docs (AUDIT_*, PROPOSAL_*, SESSION_I/L_PROMPT)
# DO NOT `git add -A` and DO NOT add those docs — they belong to the swarm branch. Stage only YOUR
# files, by name. They will arrive on main when the swarm branch merges; leave them untracked here.
git log --oneline -5
```

Run the gate once for a green baseline before touching anything (see **Gate** below).

## Read these first (canon — do not re-derive)

1. `docs/PROPOSAL_NICE_DASHBOARD_SWARM_CREATOR.md` → **Pillar 1** (the "nice dashboard" gaps + the
   `docs/dashboard-polish.md` backlog — you create that file as a deliverable).
2. `api/src/agentx_api/app.py:341` — the current one-shot `stream_events` you replace.
3. `dashboard/src/components/operator-dashboard.tsx` — the polling effect (~141), the `commandResult`
   thread (search `setCommandResult`), and the bottom ledger (~468).
4. `dashboard/src/components/shared.tsx` — where `ToastStack` + `useToasts` go.

## The tasks (TDD — write the tests in step 0 first)

### 0. Tests first (red)
- **New:** `api/tests/test_events_stream.py` — assert `/events` (a) emits the existing journal events
  on connect, (b) emits a **new** event (append one to the journal) identified by a strictly greater
  `seq`, (c) terminates cleanly (no hang) when the client disconnects. Use a bounded read so the test
  never blocks forever.
- **New:** `dashboard/tests/events.test.ts` — the `EventSource` hook parses an SSE `journal` frame and
  reports which dashboard slices should be invalidated for `run_settled` / `run_parked` / generic
  journal events.

### D1 — true SSE journal stream
- **Change:** `api/src/agentx_api/app.py` — rewrite **only** `stream_events` into a real SSE generator
  that: yields the current journal tail immediately, then loops, polling `state.journal_events(...)`
  for events with `seq` greater than the last sent (~1s server-side cadence), yielding each as an SSE
  `data:` frame. **It must be testable and must never block the worker** — guard the loop with a
  disconnect check (`await request.is_disconnected()`) and a sane max-idle/heartbeat so tests and idle
  clients terminate. Keep the route signature + `media_type="text/event-stream"`.
- **New:** `dashboard/src/lib/events.ts` — a `useJournalStream({ baseUrl })` hook that opens an
  `EventSource` to `/events`, parses frames, and exposes the latest events + a "connected" flag. It
  imports `DEFAULT_API_BASE_URL` from `lib/api.ts` (read-only import; do not edit `api.ts`).
- **Change:** `dashboard/src/components/operator-dashboard.tsx` — add a `useEffect` that consumes the
  hook and calls `refresh({ silent: true })` (or invalidates the affected slices) on
  `run_settled`/`run_parked`/new journal events. **Keep the 8s poll as a fallback** (do not delete the
  existing interval — SSE is best-effort, polling is the floor). Stay out of the nav filter (~401) and
  the `case "foundry"` render (~383) — those belong to the swarm session.

### D2 — toast / feedback system
- **Change:** `dashboard/src/components/shared.tsx` — add a `ToastStack` component + a `useToasts`
  hook (push, auto-dismiss, dedupe by key). Style with the existing CSS tokens (`--green`/`--amber`/
  `--red`, `command-receipt` look) — no new visual identity.
- **Change:** `dashboard/src/components/operator-dashboard.tsx` — on each command result
  (approve/reject/set-ring/instantiate/trigger-run), push a toast instead of (or in addition to)
  overwriting the single `commandResult`. Add a small **recent-commands log** to the bottom ledger
  (~468): last N commands with status + timestamp. Touch only the toast state (~92) and the bottom
  ledger (~468).
- **CSS:** add the toast styles to `dashboard/app/globals.css` (additive only). If you add a
  `@media (prefers-reduced-motion: reduce)` block while you're here, that's a welcome bonus (backlog
  D8) — but keep it additive.

### Backlog doc
- **New:** `docs/dashboard-polish.md` — copy the prioritized backlog from
  `PROPOSAL_NICE_DASHBOARD_SWARM_CREATOR.md` (Pillar 1) and mark D1, D2 as done-in-this-session, D3 as
  owned by the swarm session, D4–D9 as future.

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

- No swarm, no Creator, no `/commands/run-swarm` — that's the parallel Session I. Do **not** edit
  `foundry-view.tsx`, `swarm_runner.py`, `operator.py`, `gaps.py`, `lib/api.ts`, or `lib/types.ts`.
- No WebSockets — SSE only. Do not remove the 8s polling fallback.
- No state-management library, no Next.js version bump, no visual-identity redesign.
- No new `packages/contracts` types. No multi-user auth. No Mongo fixture fakes.

## Deliverables

1. The code above, gate green, on `feat/dashboard-realtime-sse`, pushed to `origin`.
2. `docs/SESSION_L_LIVE_PROOF.md` — the gate output + the new test output + an honest paragraph
   (SSE delivers new journal events without the 8s wait; toasts make commands legible; polling
   fallback intact; browser proof against live Mongo deferred to the operator).
3. `docs/dashboard-polish.md` (the backlog).
4. Open a PR to `main`; do **not** merge yourself. Keep pushing after each green step.

## Gotchas

- Dashboard `npm` needs Node ≥18: prefix with `PATH=/opt/homebrew/bin:$PATH` (system node is v16).
- The SSE generator runs inside the same event loop as the in-process scheduler worker — never block
  it; always `await` and always honour `request.is_disconnected()`.
- `lint-imports` must stay 3/3 — you are only editing the API composition edge + the dashboard, so no
  lane fence is at risk, but re-run it.
- The two skipped pytest items (`RUN_LIVE_PROMPTFOO=1`, `RUN_LIVE_HERMES=1`) stay skipped.
- Expect a small merge against `app.py` and `operator-dashboard.tsx` after the swarm branch lands on
  `main` first — that's why your edits to those two files must stay surgical and in your own regions.

Begin.
