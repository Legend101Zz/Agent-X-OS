# Task Plan — Session G · STEP B (G2): repeatable runner + kernel resume + scheduler-min

## Goal
Resume a parked run first-class through the kernel and make trigger/approval work repeatable through a
protocol-driven worker, with no script-owned reconstruction or settlement glue.

## Constraints
- TDD; keep the full offline gate and `tests/integration/test_seam_proof.py` green.
- Do not edit `packages/contracts`.
- Keep `agentx_kernel` lane-pure and `lint-imports` at 3/3.
- Journal is authoritative for run identity, trigger, parking, and approval. A kernel-owned durable
  continuation sidecar preserves payload the frozen journal event set cannot carry.
- Live runs spend real money; execute and judge them in the main thread.
- Integrate directly to `main`, no PR. Verify before every push.

## Architecture decisions
- Persist a `RunContinuation` at park: frozen hydration snapshot, JSON scratchpad, trace, claimed facts,
  harness cursor/state, and exact pending `SyscallRequest`.
- `resume(run_id, approval)` validates `RunCreated` + `RunParked` + matching `ApprovalResolved`, restores
  the continuation, re-disposes the pending call through the receipt-backed gateway, then feeds the
  result back into `HarnessSession.step` and continues to verify/settle.
- OwnHarness resumes from its cursor. Hermes persists/restores complete message history and pending tool
  call metadata so no paid reasoning turn is regenerated.
- Scheduler-min is behind kernel Protocols: durable work items represent triggers and approval-resolved
  resumes; deterministic in-memory and Mongo implementations share the same worker.

## Phases
- [x] G0 — sync `main`; baseline mypy/Ruff/pytest/import-fences/seam proof green.
- [x] G1 — continuation model/store (memory + Mongo), TDD.
- [x] G2 — OwnHarness parked→approve→kernel resume→settle; prove one effect / same key.
- [x] G3 — Hermes history persistence/replay and fake-transport live-path resume proof.
- [x] G4 — scheduler-min Protocol/store/worker; trigger→run and approval→resume→settle.
- [x] G5 — replace bespoke resume in `run_lead_finder.py` and `_eval_d_inspect.py`.
- [ ] G6 — parked→resume→settle integration test; full offline gate; commit/push. (gate green; push pending)
- [ ] G7 — real parked dental/vendor resume through kernel API; worker proof; honest verdict.
- [ ] G8 — reconcile roadmap/progress/proof; final gate; commit/push; next-session handoff.

## Baseline
- `uv run mypy --strict packages db tests` → success, 95 source files.
- `uv run ruff check .` → all checks passed.
- `uv run pytest -q` → 100 passed, 2 skipped.
- `uv run lint-imports` → 3 kept, 0 broken.
- `uv run pytest -q tests/integration/test_seam_proof.py` → 1 passed.

## Errors encountered
| Error | Attempt | Resolution |
|---|---:|---|
| none | | |
