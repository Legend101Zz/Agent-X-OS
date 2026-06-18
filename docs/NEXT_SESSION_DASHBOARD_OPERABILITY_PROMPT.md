# Next session prompt — make the Phase-1 mandate operable from the dashboard

Working directory: `/Volumes/Mrigesh SSD/Startup/Agent-X-OS`.

Integration model: create a new branch from main and do changes in that and commit

```bash
git fetch && git checkout main && git pull --ff-only
```

Read first:

- `docs/BLUEPRINT.md` §6 and §7
- `docs/flowwalk/mandate-dashboard-readiness.md`
- `docs/SESSION_G_LIVE_PROOF.md`
- `api/NEXT-SESSION-CORE-GAPS-PROMPT.md` only as historical context; several listed core gaps are now stale

## Goal

Make the existing lead-finder Mandate usable end-to-end from the local Manager Dashboard:

```text
Catalog instantiate -> trigger run -> real approval card -> approve/reject
-> scheduler resume -> settle -> inspect facts/provenance/watch/journal
```

No script-owned approval or settlement glue.

## Non-negotiable findings to fix

1. The frontend Approval view currently loads `/manual-queue`, not `/approvals`.
2. `/commands/approve` journals `ApprovalResolved` but does not enqueue `ApprovalWork`; the run does not resume.
3. `/commands/instantiate` and `/commands/trigger-run` still return `501`, although catalog and scheduler core
   capabilities now exist.
4. The live API state does not compose `Phase1RunInvoker`, continuation/receipt stores, `SchedulerStore`, or worker.
5. Fixture fallback can display fake operational state when the API is unavailable.
6. Manager commands have no authentication and CORS is unrestricted.

## Required implementation

### 1. One lifespan-owned operator runtime

Refactor API state/bootstrap so Mongo mode owns and reuses:

- journal + projection store/projections;
- catalog/`KernelControl`;
- live syscall registry + `ConfigVault`;
- syscall receipts;
- run continuations;
- scheduler store;
- Hermes runner + `Phase1RunInvoker`;
- `SchedulerWorker`.

Do not construct a disconnected registry/manual queue per HTTP request. Keep `agentx_kernel` lane-pure and do
not edit `packages/contracts` unless there is a genuine stop-and-coordinate issue.

### 2. Real command endpoints

TDD these API commands:

- `POST /commands/instantiate`
  - resolve a registered `MandateType`;
  - create a validated `MandateInstance`;
  - persist it through `KernelControl.instantiate_mandate`;
  - return the instance.
- `POST /commands/trigger-run`
  - resolve type + instance from the catalog;
  - allow a typed target override (`icp`, `location`, `count`);
  - enqueue deterministic `TriggerWork`;
  - return HTTP 202 with `work_id`.
- `POST /commands/approve`
  - journal approval exactly once;
  - fetch the resulting `ApprovalResolved`;
  - enqueue deterministic `ApprovalWork`;
  - return HTTP 202 with `work_id`;
  - retries must not duplicate manager events or effects.
- `POST /commands/reject`
  - journal rejection;
  - make the run visibly terminal/rejected without executing the parked effect;
  - clean up or terminalize its continuation safely.
- `GET /scheduler-work/{work_id}` or equivalent status query.

Run a background worker loop in API lifespan, or provide a deterministic worker pump suitable for local
single-operator use. Do not execute long paid runs inside the request handler.

### 3. Correct dashboard data model

- Add a first-class `approvals` collection to `DashboardData`.
- Fetch `/approvals` separately from `/manual-queue`.
- Approval Inbox must render real parked approval cards.
- Keep Manual Queue as a separate view/data type.
- After approve/reject, poll work/run state until settled/rejected and show the journaled receipt.

### 4. Enable core Phase-1 controls

- Activate Catalog “Create Instance”.
- Add “Run Mandate” on an instance with target fields and live/sim selection.
- Add Approve and Reject.
- Keep Edit disabled unless edited-call semantics are implemented correctly.
- Display scheduler work status, parked/resumed/settled transition, facts with provenance, and pending watch.
- Keep Foundry promote disabled until Step D produces real eval cases. Do not fake readiness.

### 5. Fail closed and secure local operation

- Fixture/demo mode must require an explicit env flag.
- In live mode, API failure must show a blocking disconnected state, not substitute fixture businesses/runs.
- Add a minimal operator bearer token (`AGENTX_OPERATOR_TOKEN`) for command routes.
- Restrict CORS to configured local dashboard origins.
- Document that the service is internal/local, not internet-ready.

### 6. Durable manual queue

Move `ManualTaskStore` behind a memory/Mongo protocol so manual tasks are visible across API/worker processes
and survive restart. Keep approval cards and manual tasks distinct.

## TDD and proof

Required tests:

1. instantiate -> persisted instance appears in `/instances`;
2. trigger command -> scheduler work -> parked run;
3. `/approvals` contains the exact draft and idempotency key;
4. dashboard approve -> `ApprovalWork` -> kernel resume -> settled;
5. one attempt, one settlement, same key, no double effect on command retry;
6. reject does not execute the effect;
7. API restart preserves work, continuation, approvals, and manual tasks in Mongo;
8. frontend uses `/approvals`, never manual queue, for approval cards;
9. frontend live mode fails closed when API is unavailable;
10. unauthorized command returns 401/403;
11. existing full gate, API tests, dashboard tests/build, and seam proof remain green.

Use the OwnHarness/fake transport first. For final proof, run API + dashboard on localhost against Mongo and
use browser automation to:

- instantiate one test instance;
- trigger a sim run;
- inspect the approval card;
- approve it;
- watch it settle;
- inspect facts/provenance/watch/journal.

Only run a paid live MiniMax/research proof after explicit user authorization in the main thread.

## Ship

- Create `docs/SESSION_DASHBOARD_OPERABILITY_PROOF.md` and append real output/screenshots as work proceeds.
- Update stale `api/gaps.py`, `api/README.md`, dashboard README, roadmap, and progress.
- Run before every push:

```bash
uv run mypy --strict packages db tests
uv run ruff check .
uv run pytest -q
uv run lint-imports
uv run pytest -q tests/integration/test_seam_proof.py tests/integration/test_parked_resume.py
(cd api && uv run pytest -q)
(cd dashboard && npm test && npm run build)
```

- Commit and push directly to `main`.
- Finish with an honest verdict: can a non-developer operate the Phase-1 lead-finder entirely from the local
  dashboard without scripts?
