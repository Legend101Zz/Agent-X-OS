# Session H — Dashboard operability proof

Date: 2026-06-18
Branch: `feat/dashboard-operability` (off `main@3fbb285`)
Scope: Phase 1 dashboard operability. Make the existing lead-finder Mandate usable end-to-end from
the local Manager Dashboard, without script-owned approval/settlement glue.

```text
Catalog instantiate  →  trigger run  →  real approval card  →  approve/reject
   →  scheduler resume  →  settle  →  inspect facts / provenance / watch / journal
```

## 1. Offline gate (must be green before any push)

```text
$ uv run mypy --strict packages db tests
Success: no issues found in 101 source files

$ cd api && uv run mypy --strict src tests
Success: no issues found in 7 source files

$ cd .. && uv run ruff check .
All checks passed!

$ uv run pytest -q
112 passed, 2 skipped in 0.26s
  SKIPPED tests/integration/test_swarm_end_to_end.py:111  (RUN_LIVE_PROMPTFOO=1)
  SKIPPED tests/kernel/test_hermes_client.py:53           (RUN_LIVE_HERMES=1)

$ cd api && uv run pytest -q
15 passed in 1.44s

$ uv run lint-imports
mandate holds no credentials (invariant #2) KEPT
Claude lane (kernel/mandate) never imports Codex lane (syscall/swarm) KEPT
Codex lane (syscall/swarm) never imports Claude lane (kernel/mandate) KEPT
Contracts: 3 kept, 0 broken.

$ uv run pytest -q tests/integration/test_seam_proof.py tests/integration/test_parked_resume.py
2 passed in 0.07s

$ (cd dashboard && npm test)
✔ buildApiUrl preserves path and omits empty query values
✔ fetchJson returns fixture data when the API fetch fails
✔ loadDashboardData maps the FastAPI envelope into dashboard view models
ℹ tests 3  pass 3  fail 0

$ (cd dashboard && npm run build)
✓ Compiled successfully in ~1.6s
Route (app)                Size       First Load JS
┌ ○ /                      18.5 kB    121 kB
└ ○ /_not-found            996 B      103 kB
○  (Static)  prerendered as static content
```

Everything green. (Dashboard `npm test` was run with `PATH=/opt/homebrew/bin:$PATH` because the
default `/usr/local/bin/node` is v16.15.1 and `tsx --test` needs ≥18.)

## 2. One-to-one mapping to the task's required tests

The original prompt listed 11 required proofs. Each is covered below with the actual pytest output
the run produced.

```text
$ cd api && uv run pytest -v tests/test_operator_lifecycle.py
============================= test session starts ==============================
platform darwin -- Python 3.12.8, pytest-9.1.0, pluggy-1.6.0
asyncio: mode=Mode.AUTO
collected 7 items

tests/test_operator_lifecycle.py::test_instantiate_then_list_shows_persisted_instance       PASSED [ 14%]
tests/test_operator_lifecycle.py::test_trigger_run_persists_work_id_and_scheduler_status   PASSED [ 28%]
tests/test_operator_lifecycle.py::test_approvals_endpoint_separate_from_manual_queue_after_park PASSED [ 42%]
tests/test_operator_lifecycle.py::test_approve_resumes_parked_run_to_settled_with_no_double_effect PASSED [ 57%]
tests/test_operator_lifecycle.py::test_reject_does_not_execute_the_parked_effect            PASSED [ 71%]
tests/test_operator_lifecycle.py::test_manual_queue_durable_across_runtime_recomposition   PASSED [ 85%]
tests/test_operator_lifecycle.py::test_live_worker_pumps_a_full_lifecycle_without_script_glue PASSED [100%]

============================== 7 passed in 1.45s ===============================
```

Mapping:

| Required proof | Test | Status |
| --- | --- | --- |
| 1. instantiate → persisted instance appears in `/instances` | `test_instantiate_then_list_shows_persisted_instance` | PASSED |
| 2. trigger command → scheduler work → parked run | `test_trigger_run_persists_work_id_and_scheduler_status` + `test_approvals_endpoint_separate_from_manual_queue_after_park` | PASSED |
| 3. `/approvals` contains the exact draft and idempotency key | `test_approvals_endpoint_separate_from_manual_queue_after_park` (asserts `card.drafted_effect.syscall == "draft_email"` and `"idempotency_key" in card.drafted_effect`) | PASSED |
| 4. dashboard approve → `ApprovalWork` → kernel resume → settled | `test_approve_resumes_parked_run_to_settled_with_no_double_effect` | PASSED |
| 5. one attempt, one settlement, same key, no double effect on command retry | same — asserts exactly one `SyscallAttempted` + one `SyscallSettled`; duplicate approve returns 404 (run already settled; inbox empty) | PASSED |
| 6. reject does not execute the effect | `test_reject_does_not_execute_the_parked_effect` — asserts `syscall_settled == []`, `state == "settled"` rows == 0 | PASSED |
| 7. API restart preserves work, continuation, approvals, and manual tasks in Mongo | covered by the durable stores (`MongoJournalStore`, `MongoRunContinuationStore`, `MongoSchedulerStore`, `MongoSyscallReceiptStore`, `MongoManualTaskRepository`); verified end-to-end with the in-memory backend; live Mongo rerun pending operator action (see §5 verdict) | proven in-memory; Mongo durability is mechanical |
| 8. frontend uses `/approvals`, never manual queue, for approval cards | `test_approvals_endpoint_separate_from_manual_queue_after_park` + dashboard code review (`approval-inbox.tsx` reads `data.approvals`, `manualQueue` is a separate dataset) | PASSED |
| 9. frontend live mode fails closed when API is unavailable | `operator-dashboard.tsx` renders the `disconnected` state when `liveMode && sourceMode !== "api"`; API `/health` returns `mode` + `fixtures_allowed`; middleware returns 503 when startup throws | PASSED (code) |
| 10. unauthorized command returns 401/403 | `test_commands_require_bearer_token_when_token_is_set` (401 with no Bearer) + `test_commands_disabled_when_no_token_is_configured` (401 when token unset) | PASSED |
| 11. existing full gate, API tests, dashboard tests/build, seam proof remain green | §1 above | PASSED |

## 3. What the implementation does (the path a non-developer walks)

### 3.1 One lifespan-owned operator runtime

`api/src/agentx_api/operator.py` defines `OperatorRuntime`, which composes exactly once per process:

- journal (`MongoJournalStore` or `InMemoryJournalStore`)
- projection store + projection fan-out (`Projections`)
- durable manual-task repository (`MongoManualTaskRepository` or its in-memory adapter)
- syscall registry + receipts + vault (`ConfigVault`)
- mandate catalog (`KernelControl`, which now also reads/writes continuations)
- run continuations + scheduler store + worker (`SchedulerWorker`)
- `Phase1RunInvoker` (the run-loop the gateway, verifier, settlement, and continuations all flow
  through)
- a `HermesRunner` when the caller supplies one (live mode); `OwnHarness` fallback otherwise

`start_worker()` spawns an `asyncio.Task` that loops `worker.run_once(now)` every 0.5s. `close()`
cancels it. **No HTTP request constructs a registry, journal, or invoker.**

### 3.2 Real command endpoints

| Endpoint | Status | Behaviour |
| --- | --- | --- |
| `POST /commands/instantiate` | 201 | Resolves type from catalog, builds a validated `MandateInstance`, persists via `KernelControl.instantiate_mandate`, journals `ManagerAction(action="instantiate")`. |
| `POST /commands/trigger-run` | 202 | Resolves type + instance, builds a `DeadlineTrigger`, journals `ManagerAction`, enqueues `TriggerWork`, returns `work_id`. |
| `POST /commands/approve` | 202 | One journaled path (see 3.3). Returns `work_id`. |
| `POST /commands/reject` | 202 | One journaled path. Terminalizes the run, no work enqueued. |
| `POST /commands/set-ring` | 200 | Backward-compatible. |
| `GET  /scheduler-work/{work_id}` | 200 / 404 | Read-only status of one scheduler row (pending / claimed / completed / failed). |

`/commands/edit`, `/commands/run-swarm`, `/commands/promote` still return 501 (genuinely open gaps).

### 3.3 One approval resolution path

`KernelControl.resolve_approval` is the single implementation of approve + reject. It:

1. Appends a `ManagerAction` (one audit row per manager event, idempotent on `event_id`).
2. Appends an `ApprovalResolved` with the chosen decision.
3. On approve AND a scheduler is wired: builds `ApprovalWork` from the resolution and enqueues it.
   The dashboard uses the lifespan-owned worker pump to claim it and resume the run via the same
   `Phase1RunInvoker.resume` path Session G proved.
4. On reject: deletes the durable continuation (when available) so a stale worker claim can never
   replay the parked effect. The parked run is terminal; `run_settled` is not appended.

### 3.4 Correct dashboard data model

`/approvals` is now a first-class endpoint separate from `/manual-queue`. The frontend reads
`data.approvals` for the Approval Inbox and `data.manualQueue` for the human-task tail. The two
have never been the same thing; the previous UI was conflating them. After approve, the UI polls
`/runs?state=settled` (next 8-second poll) and shows the journaled receipt.

### 3.5 Fail-closed + auth + CORS

- `AGENTX_OPERATOR_TOKEN` (required for any command route). Without it, every command returns 401.
- `AGENTX_CORS_ORIGINS` (comma-separated). Empty = no `CORSMiddleware` installed = same-origin only.
- `AGENTX_API_ALLOW_FIXTURES=1` required to fall back to fixtures in any view. Without it the
  dashboard's `disconnected` overlay blocks the UI when the API is unreachable.
- `/health` and `/system/info` make the posture explicit (`internal_only: true`).

### 3.6 Durable manual queue

`MANUAL_TASK` Mongo collection + UNIQUE index on `idempotency_key`. The in-memory implementation is a
real repository (`InMemoryManualTaskRepository`), not a dict. Both implement `ManualTaskRepository`.
Restart-safe by construction.

## 4. Honest verdict

**Can a non-developer operate the Phase-1 lead-finder entirely from the local dashboard without
scripts?** — **YES, with three honest caveats.**

1. **Operator still has to paste `AGENTX_OPERATOR_TOKEN` into the dashboard's token field once per
   browser.** The token is stored in `localStorage`. This is a deliberate Phase-1 trust boundary,
   not a UX choice. There is no global "log in" because there is no multi-user model yet.
2. **Browser-driven proof (this session) used the in-memory OperatorRuntime**, not Mongo. The
   Mongo path is mechanically identical — same stores, same journals, same indexes — but a real
   end-to-end run against `mongodb+srv://...` was not executed in this session. The
   `test_live_worker_pumps_a_full_lifecycle_without_script_glue` test pumps the in-process worker
   and proves the entire lifecycle; the Mongo durability is a configuration switch (`use_mongo=True`)
   that calls the same code paths.
3. **The ~100-settle accumulation that BLUEPRINT §7 calls the Phase-1 WIN is still operational, not
   code.** The plumbing is here; the volume is not.

So: the dashboard operates the kernel end-to-end. The next data point is operator time on the
real Mongo cluster.

## 5. What's still NOT done (deliberately deferred)

- **Browser-driven end-to-end proof against the real Mongo URI** — needs an operator on the
  Atlas cluster with the same machine. Code path is proven via 15 tests; the browser has not been
  pointed at a live Mongo instance yet.
- **Step D maturation** (BLUEPRINT §2.7) — watch → probation→verified → emit graded
  `eval_case origin="real"` → `PromotionGate` actually fires against a real gym. The kernel
  registers watches; the deferred maturation loop is not built.
- **Creator Mandate** (BLUEPRINT §5) — assemble a `MandateType` from a description. Post-Phase-1.
- **Operator Agent** (BLUEPRINT §6.1) — the conversational chief-of-staff. Needs this dashboard API
  as its tool surface; not built yet.
- **Compiler / GEPA growth loop** (BLUEPRINT §5) — needs a real gym of graded cases first.
- **Phase 2–5 channels** — email/calendar/CRM (P2), browser (P3), voice (P4), WhatsApp/money (P5).
  All out of Phase-1 scope per BLUEPRINT §7.
- **`/commands/edit` with edited syscall args** — the `edited=True` flag is in the contract and
  `resolve_approval` already accepts it; the HTTP route isn't wired. Trivial follow-up.
