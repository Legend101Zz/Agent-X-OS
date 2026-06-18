# Session G live proof — G2 repeatable runner + kernel resume + scheduler-min

Date: 2026-06-18

## Scope

Step B (G2): a parked run resumes through the kernel from its journaled approval, re-executes the exact
approved syscall idempotently, continues the harness, verifies, and settles. A protocol-driven worker
turns triggers into runs and `ApprovalResolved` into resume work.

## Baseline before product-code changes

Repository state:

```text
main == origin/main == a67e07a
pre-existing local edit: task_plan.md (Session F completion record; preserved into this Session G plan)
```

Offline gate:

```text
$ uv run mypy --strict packages db tests
Success: no issues found in 95 source files

$ uv run ruff check .
All checks passed!

$ uv run pytest -q
100 passed, 2 skipped in 0.44s

$ uv run lint-imports
Contracts: 3 kept, 0 broken.

$ uv run pytest -q tests/integration/test_seam_proof.py
1 passed in 0.17s
```

## Architecture decision

The frozen `packages/contracts` journal events record that hydration happened, but do not carry the
hydration payload, scratchpad, claims, trace, harness cursor, or Hermes message history. Session G keeps
the journal authoritative for run identity, trigger, park, and approval, and adds a kernel-owned durable
continuation sidecar for those continuation payloads. This is the same boundary pattern as syscall
receipts: journaled control state plus durable payload-faithful replay data, without changing the seam.

## TDD/offline proof

Implemented:

- Kernel-owned `RunContinuation` sidecar with in-memory and Mongo stores.
- `Phase1RunInvoker.resume(run_id, approval)` validates journal state, restores the frozen continuation,
  re-disposes the exact parked call through the receipt-backed gateway, and continues the harness.
- Hermes exports/restores full message history, pending tool-call id, call index, and cursor.
- Scheduler-min `TriggerWork` / `ApprovalWork`, protocol-backed stores, deterministic in-memory queue,
  and atomic Mongo due-work claiming.
- `run_lead_finder.py` and `_eval_d_inspect.py` now use scheduler→kernel invoke/resume; bespoke gateway,
  verify, and settlement reconstruction was removed.

Focused proof:

```text
OwnHarness kernel resume:
1 passed
- same pending idempotency key
- one SyscallAttempted
- one SyscallSettled
- adapter execute_count == 1
- final state settled

Hermes persisted-history resume:
1 passed
- five pre-park model turns
- one post-approval continuation turn
- prior assistant/tool history restored
- final state settled

Worker-backed integration + unchanged seam proof:
2 passed
- TriggerWork -> parked run
- ApprovalWork -> kernel resume -> settled
- one effect
```

Full offline gate after implementation:

```text
$ uv run mypy --strict packages db tests
Success: no issues found in 99 source files

$ uv run ruff check .
All checks passed!

$ uv run pytest -q
111 passed, 2 skipped in 0.45s

$ uv run lint-imports
Contracts: 3 kept, 0 broken.

$ uv run pytest -q tests/integration/test_seam_proof.py tests/integration/test_parked_resume.py
2 passed in 0.18s
```

## Live kernel resume proof

Two real paid runs used the committed Mongo-backed worker and `Phase1RunInvoker.resume()` path.

### Dental run — requested domain proof

```text
INSTANCE_ID=agentx_evald_1781802680
RUN_ID=agentx_evald_1781802680:deadline:1781782880
L1_STATE=parked reason=draft_email requires L2
SETTLED_EVENT=...:settled seq=17 VERIFY_PASSED=True
APPROVAL_TO_SETTLE_S=7.13
HEAP_FACT_COUNT=2
WATCH_COUNT=1
JOURNAL_EVENT_COUNT=18 SEQ_STRICTLY_INCREASING=True
```

The approval card was Dental Sphere, Pune: real organisation and own-site URLs; Dr. Shrenik Parmar;
`care@dentalsphere.in`, phone, and contact page; cited multi-branch, service, blog, and marketing evidence;
and two settled probation facts with `run_id` provenance.

The continuation path was:

```text
draft_email SyscallAttempted -> RunParked -> ManagerAction -> ApprovalResolved
-> same draft_email SyscallSettled -> RunVerified -> RunSettled -> WatchRegistered
```

An additional dogfood run (`agentx_dogfood_1781802375:deadline:1781782575`) also parked, restored Hermes
history, executed the approved draft, took one post-approval turn, and settled at sequence 19.

Exact-key replay for the dental run:

```text
IDEMPOTENCY_KEY=agentx_evald_1781802680:deadline:1781782880:draft_email:5
DRAFT_ATTEMPT_COUNT=1 DRAFT_SETTLED_COUNT=1
REPLAY_STATUS=ok JOURNAL_EVENT_DELTA=0
REPLAY_EVENTS_ATTEMPTED=None SETTLED=None
RECEIPT_RESULT_EQUAL=True
```

## Scheduler-min worker proof

Offline, the integration test drives the real invoker:

```text
TriggerWork -> invoke -> parked
ApprovalWork -> resume -> settled
```

Live Mongo rows for the dental run:

```text
WORK_ID=trigger:9f8995... STATUS=completed ATTEMPTS=1
WORK_ID=approval:57ca60... STATUS=completed ATTEMPTS=1
CONTINUATION_PRESENT_AFTER_SETTLE=False
```

Both scripts now enqueue work and call `SchedulerWorker.run_once`; they contain no manual gateway replay,
postcondition verification, or settlement construction.

## Honest verdict

**G2 is proven:** the tested lead-finder flow is repeatable without bespoke resume wiring. A trigger becomes
a run, approval becomes resume work, the exact parked effect executes once, Hermes continues from persisted
history, and the run verifies and settles. This starts the path toward ~100 settles; it is not evidence that
100 runs have happened.

**The dental output is not founder-sendable without editing.** Its research/provenance is useful, but the
draft invented a “20–40 additional booked consultations per month” result and overstated Agent-X as
identifying people actively comparing treatment options. Replace `[Your name]`, remove the fabricated result,
and narrow the capability claim before sending. This is a G1/G4 quality guardrail issue, not a G2 failure.
