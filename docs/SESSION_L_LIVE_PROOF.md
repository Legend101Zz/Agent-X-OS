# Session L Live Proof

Date: 2026-06-19
Branch: `feat/dashboard-realtime-sse`

## Focused red-green proof

- API red: `api/tests/test_events_stream.py` failed because the old `/events` response stopped
  after its initial batch.
- Dashboard red: `dashboard/tests/events.test.ts` failed because `src/lib/events.ts` did not exist.
- API green: the bounded SSE test passed after the route began emitting individual journal frames,
  following a newly appended event with a strictly greater per-instance `seq`, and terminating on
  disconnect.
- Dashboard green: event parsing, settlement/parking invalidation, generic journal invalidation,
  and toast deduplication tests passed.

Focused verification:

```text
api:       ruff clean; mypy clean; 1 SSE test passed
dashboard: 9 tests passed; 0 failed
Next.js:   production build completed
```

## Full required gate

Commands run from the Session L worktree:

```bash
uv run ruff check .
uv run mypy --strict packages db tests
cd api && uv run mypy --strict src tests && cd ..
uv run pytest -q
cd api && uv run pytest -q && cd ..
uv run lint-imports
cd dashboard && PATH=/opt/homebrew/bin:$PATH npm test \
  && PATH=/opt/homebrew/bin:$PATH npm run build && cd ..
```

Result:

```text
ruff:             All checks passed
root mypy:        Success; 101 source files
API mypy:         Success; 8 source files
root pytest:      112 passed, 2 skipped
API pytest:       16 passed
import-linter:    3 kept, 0 broken
dashboard tests:  9 passed, 0 failed
dashboard build:  compiled, type-checked, and generated 4/4 static pages
```

The two expected live-gated tests remained skipped:

- `RUN_LIVE_PROMPTFOO=1`
- `RUN_LIVE_HERMES=1`

## Honest operational result

SSE now delivers new journal events to the dashboard without waiting for the next eight-second
poll. The poll remains intact as the floor when EventSource is unavailable or reconnecting.
Approve, reject, set-ring, instantiate, and trigger-run results now produce command toasts and
remain legible in the recent-command ledger instead of being lost when the next command overwrites
the shared receipt.

Browser proof against a live API and live Mongo deployment is deferred to the operator. This
session proves the streaming generator, disconnect behavior, dashboard parsing/invalidation,
feedback state, complete repository gate, and production build; it does not claim a live Mongo
browser run.
