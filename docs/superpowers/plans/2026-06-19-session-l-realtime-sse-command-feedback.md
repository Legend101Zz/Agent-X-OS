# Session L Realtime SSE and Command Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dashboard's delayed-only refresh behavior with a real journal SSE stream while retaining polling, and make every manager command visible through toasts plus a recent-command ledger.

**Architecture:** The API `/events` route remains the composition edge and asynchronously tails `DashboardState.journal_events`, emitting one `journal` SSE frame per event after an immediate current tail. The dashboard owns transport parsing and invalidation policy in `src/lib/events.ts`; the shell uses the hook to trigger silent refreshes. Command results remain compatible with existing child-view props, while the shell records each result in a toast stack and bounded command history.

**Tech Stack:** FastAPI/Starlette streaming responses, asyncio, React 19 hooks, browser `EventSource`, Node test runner, pytest/httpx.

---

### Task 1: Establish the red SSE contracts

**Files:**
- Create: `api/tests/test_events_stream.py`
- Create: `dashboard/tests/events.test.ts`

- [ ] Write an API test that consumes the `/events` body with a bounded async iterator, proves the seeded tail arrives, appends a higher-sequence `ManagerAction`, proves the new frame arrives, then closes the iterator/client without hanging.
- [ ] Run `cd api && uv run pytest -q tests/test_events_stream.py` and confirm failure because `/events` closes after the initial batch.
- [ ] Write dashboard tests for parsing a `journal` SSE payload and mapping `run_settled`, `run_parked`, and a generic event to dashboard invalidation slices.
- [ ] Run `cd dashboard && PATH=/opt/homebrew/bin:$PATH npm test -- tests/events.test.ts` and confirm failure because `src/lib/events.ts` does not exist.

### Task 2: Implement the journal stream

**Files:**
- Modify: `api/src/agentx_api/app.py` only inside `stream_events`
- Create: `dashboard/src/lib/events.ts`
- Modify: `dashboard/src/components/operator-dashboard.tsx` only around hook state and refresh effects

- [ ] Change `stream_events` to emit the current journal tail as individual `event: journal` frames, track the greatest sent `seq`, await between reads, stop on disconnect, emit a heartbeat during idle periods, and end after a bounded idle window.
- [ ] Implement `parseJournalFrame`, `invalidationsForJournalEvent`, and `useJournalStream({baseUrl})`, importing `DEFAULT_API_BASE_URL` read-only from `lib/api.ts`.
- [ ] Consume the hook in `OperatorDashboard` and call `refresh({silent: true})` when a new event arrives; preserve the existing eight-second interval unchanged.
- [ ] Run the two focused test files, API mypy, dashboard tests, and dashboard build.
- [ ] Commit only the SSE tests/implementation and push `feat/dashboard-realtime-sse`.

### Task 3: Implement command feedback

**Files:**
- Modify: `dashboard/src/components/shared.tsx`
- Modify: `dashboard/src/components/operator-dashboard.tsx` only around command state/callbacks and the bottom ledger
- Modify: `dashboard/app/globals.css` additively

- [ ] Add `useToasts` with keyed deduplication, bounded state, auto-dismiss, and `ToastStack` with good/warn/hot tones.
- [ ] Add a single command-result recorder in the shell that preserves `commandResult`, pushes a toast, and prepends a timestamped bounded history row.
- [ ] Route approve, reject, set-ring, instantiate, and trigger-run callback results through the recorder without editing child components.
- [ ] Render `ToastStack` and recent commands near the bottom ledger.
- [ ] Add additive toast/history styling and reduced-motion rules.
- [ ] Run dashboard tests and build, then commit and push.

### Task 4: Documentation and final verification

**Files:**
- Create: `docs/dashboard-polish.md`
- Create: `docs/SESSION_L_LIVE_PROOF.md`

- [ ] Copy the Pillar 1 D1-D9 backlog, marking D1/D2 complete here, D3 owned by Session I, and D4-D9 future.
- [ ] Run the complete required gate:
  `uv run ruff check .`;
  `uv run mypy --strict packages db tests`;
  `(cd api && uv run mypy --strict src tests)`;
  `uv run pytest -q`;
  `(cd api && uv run pytest -q)`;
  `uv run lint-imports`;
  `(cd dashboard && PATH=/opt/homebrew/bin:$PATH npm test && PATH=/opt/homebrew/bin:$PATH npm run build)`.
- [ ] Record exact gate/test output and the honest browser/Mongo deferral in `docs/SESSION_L_LIVE_PROOF.md`.
- [ ] Re-run focused tests after the proof doc, review `git diff` for shared-file boundary compliance, commit by explicit filename, and push.
- [ ] Open a PR from `feat/dashboard-realtime-sse` to `main` and do not merge it.
