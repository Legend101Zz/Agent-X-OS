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

Pending.

## Scheduler-min worker proof

Pending.

## Honest verdict

Pending.
