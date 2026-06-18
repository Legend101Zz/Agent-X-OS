# Session E Prompt: Core Control Plane and Durable Operator Commands

Copy this prompt into the next Agent-X-OS coding session.

---

# SESSION E - Close the Operator Dashboard Core Gaps

Repository:

`/Volumes/Mrigesh SSD/Startup/Agent-X-OS`

Date context:

`2026-06-18`

## Goal

Turn the Session D operator dashboard from a mostly read-only lens into a real control plane by
implementing the missing capabilities in the correct owning layers.

The dashboard and thin FastAPI layer already exist on branch `feat/dashboard`. They expose the
current kernel state and deliberately return `501` for commands the core does not support.

This session is core-first:

1. Add the missing journaled command and durable-continuation behavior in the owning packages.
2. Preserve all eight invariants and package import boundaries.
3. Only after the core surfaces exist, replace the corresponding API `501` stubs and enable the
   existing dashboard controls.

Do not fake success in the API. A dashboard button is only complete when the underlying action is
journaled, projected, restart-safe where required, and covered by integration tests.

## Read First

Read these before editing:

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/BLUEPRINT.md` sections 1, 2, 4, 5, and 6
4. `docs/BUILD-KIT.md`
5. `packages/kernel/src/agentx_kernel/control.py`
6. `packages/kernel/src/agentx_kernel/run_loop.py`
7. `packages/kernel/src/agentx_kernel/gateway.py`
8. `packages/kernel/src/agentx_kernel/projections.py`
9. `packages/kernel/src/agentx_kernel/ports.py`
10. `packages/kernel/src/agentx_kernel/stores/`
11. `packages/contracts/src/agentx_contracts/journal.py`
12. `packages/contracts/src/agentx_contracts/mandate.py`
13. `packages/contracts/src/agentx_contracts/protocols.py`
14. `packages/syscall/src/agentx_syscall/adapters.py`
15. `packages/syscall/src/agentx_syscall/registry.py`
16. `packages/swarm/src/agentx_swarm/gate.py`
17. `tests/kernel/test_control_api.py`
18. `tests/integration/test_swarm_end_to_end.py`
19. `api/src/agentx_api/app.py`
20. `api/src/agentx_api/gaps.py`
21. `api/src/agentx_api/state.py`

If `HANDOFF-CODEX.md` exists on the branch used for this session, read it before `CLAUDE.md`.

## Current State From Session D

Session D added:

- `api/`: a standalone FastAPI application that composes the existing kernel control surface,
  projections, journal, syscall registry, and Mongo configuration.
- `dashboard/`: a Next.js 15 / React 19 operator dashboard with:
  - Floor
  - Approval inbox
  - Mandate catalog and create form
  - Instance file
  - Run detail and trace timeline
  - Capability registry
  - Ledger
  - Foundry/eval view
- Eight-second near-real-time polling of the API.
- Fixture fallback when the API or Mongo is unavailable.
- Production screenshots and browser verification.

Currently working command endpoints:

- `POST /commands/approve`
- `POST /commands/set-ring`

Currently unsupported endpoints, intentionally returning `501`:

- `POST /commands/edit`
- `POST /commands/reject`
- `POST /commands/instantiate`
- `POST /commands/trigger-run`
- `POST /commands/run-swarm`
- `POST /commands/promote`

Current read-side limitations:

- The exact in-memory `RunResult.trace` and hydration snapshot are not durably queryable after the
  process exits.
- The human/manual queue uses an in-process `ManualTaskStore`.

## Critical Finding: Approve Does Not Resume

Do not mistake the existing `KernelControl.approve()` for a complete approval workflow.

It currently:

1. Appends `ManagerAction(action="approve")`.
2. Appends `ApprovalResolved(decision="approve")`.
3. Returns the manager action.

It does not resume the parked syscall or finish verification and settlement.

The live dogfood script in `scripts/run_lead_finder.py` performs that missing work manually:

1. Reads the in-memory `RunResult.park.approval_card`.
2. Reconstructs a `SyscallRequest`.
3. Invokes the gateway at the required ring.
4. Applies syscall projections.
5. Runs verification.
6. Builds and commits settlement.

That manual script logic must become a restart-safe core continuation path. Do not copy it into the
FastAPI endpoint.

## Non-Negotiable Boundaries

Keep all eight invariants green, especially:

- Every manager action is journaled.
- No fact reaches the heap except through settlement.
- Credentials remain kernel-side and are only injected at `Adapter.execute(req, cred)`.
- Kernel and mandate must not import syscall or swarm.
- Syscall and swarm must not import kernel or mandate.
- Synthetic-only evidence must never promote a customer-facing version.
- The human-task adapter remains the terminal fallback.

`packages/contracts` is frozen. If exact implementation requires changing a contract:

1. Stop.
2. Write down the required additive contract change and why existing fields cannot encode it.
3. Treat it as a stop-and-coordinate event.
4. Merge the contract change first.
5. Rebase/re-pull both lanes.
6. Resume implementation.

Do not work around a missing contract with untyped dictionaries that silently become new domain
models.

## Recommended Architecture

### 1. Add Restart-Safe Run Continuations

Use the existing `MANDATE_RUN` collection and `MandateRun` model as the durable execution
checkpoint. Add a kernel-local storage port rather than putting Mongo calls in the run loop.

Recommended local interface:

```python
class RunCheckpointStore(Protocol):
    async def save(self, run: MandateRun) -> None: ...
    async def get(self, run_id: str) -> MandateRun | None: ...
```

Implement matching in-memory and Mongo stores.

Checkpoint at minimum:

- after run creation
- after hydration
- before returning a parked result
- after approval edit
- before verification
- after settlement or rejection

For a parked run, persist enough data to resume without the original Python process:

- trigger
- type reference
- hydration snapshot
- trace so far
- claimed facts
- parked reason
- pending syscall intent
- original arguments
- idempotency key
- required ring
- relevant scratchpad/faculty state

The pending syscall can be stored in `MandateRun.scratchpad` for Phase 1 if it is validated through a
small typed kernel-local model before serialization.

Important source-of-truth rule:

- The journal remains the audit and settlement source of truth.
- `MANDATE_RUN` is an operational continuation checkpoint.
- Heap facts still only come from `RunSettled`.
- If strict journal replay must reconstruct every private trace event and the full approval card,
  the current journal event models are insufficient. That is a contract coordination event, not an
  excuse to invent undocumented projection writes.

### 2. Build One Approval Resolution Path

Avoid three divergent implementations for approve, edit, and reject.

Recommended surface:

```python
async def resolve_approval(
    *,
    instance_id: str,
    run_id: str,
    decision: ApprovalDecision,
    actor: str,
    now: datetime,
    edited_args: JsonObject | None = None,
) -> ApprovalCommandResult:
    ...
```

Keep `approve()` as a backward-compatible wrapper if existing callers depend on it.

Required behavior:

1. Load and validate the parked checkpoint.
2. Confirm the run belongs to the requested instance.
3. Confirm it has an unresolved `RunParked(awaiting="human_approval")`.
4. Reject duplicate/conflicting resolutions deterministically.
5. Append a `ManagerAction`.
6. Append `ApprovalResolved` with:
   - `decision="approve"` or `"reject"`
   - `edited=True` only when edited arguments were accepted
7. For reject:
   - do not execute the syscall
   - mark the continuation terminal/rejected
   - preserve the audit trail
   - do not commit claimed facts
8. For approve/edit:
   - use the pending syscall from the checkpoint
   - apply edited arguments only after validation against the adapter/syscall input schema
   - re-enter the gateway with the same idempotency key
   - never bypass gateway ring policy, credential injection, channel rules, or journaling
   - apply attempted/settled projections
   - continue deterministic verification
   - settle through `SettlementCommitter`
9. Save the final checkpoint.
10. Return a typed result containing the manager action and terminal run state.

Do not treat approval as an automatic permanent ring elevation. Approval is permission for the
specific parked effect. `set_ring` remains a separate explicit manager command.

### 3. Instantiate a Mandate Instance

Add a journaled kernel command such as:

```python
async def instantiate(
    *,
    mandate_type_id: str,
    customer_id: str,
    heap_region_id: str,
    ring: Ring,
    actor: str,
    now: datetime,
    target_override: JsonObject | None = None,
) -> MandateInstance:
    ...
```

Required behavior:

- Resolve a real `MandateType` from the catalog.
- Generate or accept a deterministic instance ID.
- Set `type_ref` from the selected type and version.
- Keep the customer heap region isolated.
- Append `ManagerAction(action="instantiate")` with sufficient non-secret detail.
- Project the instance into `MANDATE_INSTANCE`.
- Initialize the resume/ring projection.
- Reject duplicate instance IDs and invalid type references.
- Never store credentials or provider keys in the instance.

Recommended projection approach:

- Add an instance projector that consumes `ManagerAction(action="instantiate")`.
- Extend `ResumeProjector` to initialize ring/trust from the same event.
- Ensure `Projections.rebuild(instance_id)` reproduces the instance and resume state.

### 4. Trigger a Live Run

Add a journaled command that resolves catalog state and calls the existing run invoker:

```python
async def trigger_run(
    *,
    instance_id: str,
    trigger: Trigger,
    actor: str,
    now: datetime,
    mode: RunMode = "live",
) -> RunResult:
    ...
```

Required behavior:

- Load `MandateInstance`.
- Load its referenced `MandateType`.
- Construct `InstanceBinding`.
- Append `ManagerAction(action="trigger_run")`.
- Invoke the already-wired `RunInvoker`; do not construct a second isolated in-memory kernel.
- Use the same journal, projections, gateway, vault, and registry as the API process.
- Save the run checkpoint throughout execution.
- Return the parked, settled, or crashed result.

Phase 1 can await the run in the request path because it is one operator and one lead-finder.
Do not introduce a distributed scheduler unless measurements show it is necessary.

### 5. Persist Complete Operator Run Views

The dashboard currently reconstructs a partial timeline from:

- journal events
- syscall trace projection
- heap facts
- settlement events

After adding checkpoints, make `MANDATE_RUN` the source for:

- frozen hydration snapshot
- trace events
- claimed facts
- parked approval card
- run state
- creation/settlement timestamps

Keep journal and syscall projections visible alongside the checkpoint so the operator can distinguish:

- harness trace
- effect ledger
- settlement commit

Do not write heap facts from the run checkpoint.

If private thought events must be permanently journal-replayable, flag the additive journal-contract
change separately. Do not claim the checkpoint alone provides full event replay.

### 6. Make the Manual Queue Durable

`ManualTaskStore` currently lives in process memory inside the syscall registry.

Refactor it behind a syscall-owned repository abstraction with:

- in-memory implementation for tests/sim
- Mongo implementation for live API/kernel wiring
- idempotent enqueue by `idempotency_key`
- open-task listing
- task lookup
- outcome recording
- stable timestamps and IDs

Add a `manual_task` Mongo collection and indexes if needed.

Preserve the human-task adapter as the terminal fallback. Do not move manual fulfillment into the
kernel and do not make the kernel import `agentx_syscall`.

The edge composition layer may inject the durable store when constructing the registry.

### 7. Expose Swarm Tests Without Breaking Lane Isolation

The kernel must not import `agentx_swarm`.

Use dependency inversion:

- Define a small orchestration port accepted by the control service, or keep the integration
  orchestrator at the API composition edge.
- The concrete implementation can use:
  - `load_builtin_scenario_pack`
  - `build_sim_registry`
  - the existing kernel `RunInvoker`
  - `build_promptfoo_judge`
- Journal `ManagerAction(action="run_swarm")` before execution.
- Persist resulting `EvalCase`/`Scorecard` records in `EVAL_CASE`.
- Preserve `origin="synthetic"` end to end.

Do not allow a synthetic test command to touch customer effects or use the live adapter registry.

### 8. Add Gated Promotion

Promotion must call the existing `PromotionGate`; do not reimplement its rules in FastAPI or React.

Recommended command input:

- target instance/canary
- type reference/version
- requested ring
- selected scorecard/eval-case IDs
- explicit human approval
- actor and timestamp

Required behavior:

1. Load evidence from durable eval-case records.
2. Evaluate `PromotionGate`.
3. If denied:
   - return the typed denial reasons
   - do not change ring or promotion state
   - journal the attempted manager action and decision
4. If allowed:
   - require at least one passing real-origin evidence item
   - require human approval
   - append `ManagerAction(action="promote")`
   - apply the approved canary ring through the existing ring projection path
5. Never allow synthetic-only evidence to promote.

Because the journal envelope requires `instance_id`, implement Phase-1 promotion as a canary-instance
promotion. Do not invent a global type-level event without a contract decision.

### 9. Preserve Package Boundaries

Suggested dependency direction:

```text
api composition
  -> agentx_kernel control/run services
  -> agentx_syscall registry implementation
  -> agentx_swarm judge/gate implementation

agentx_kernel
  -> agentx_contracts
  -> agentx_db
  -> agentx_mandate

agentx_syscall
  -> agentx_contracts

agentx_swarm
  -> agentx_contracts
```

Use injected protocols/callables at the edge when orchestration needs both lanes. Never fix a
dashboard command by adding `agentx_swarm` or `agentx_syscall` imports inside `agentx_kernel`.

## API Work After Core Is Green

Replace the `501` routes in `api/src/agentx_api/app.py` with typed request models:

- `POST /commands/edit`
- `POST /commands/reject`
- `POST /commands/instantiate`
- `POST /commands/trigger-run`
- `POST /commands/run-swarm`
- `POST /commands/promote`

Requirements:

- API remains a thin HTTP adapter.
- No duplicate business rules.
- No direct frontend access to Mongo.
- No credentials returned to clients.
- Core domain errors become clear `4xx` responses.
- Unsupported/coordination-required capabilities stay `501`; do not lie.
- Update `/core-gaps` as each capability is genuinely closed.

Update `api/src/agentx_api/state.py` so live Mongo composition shares one:

- journal
- projection store
- projections object
- vault
- syscall registry
- run invoker
- control service
- durable manual-task repository

Do not use `build_phase1_runinvoker()` for the live API if it creates isolated in-memory stores.

## Dashboard Work After API Is Green

Enable the existing controls:

- Approval inbox:
  - approve
  - edit arguments with a focused modal
  - reject with confirmation
- Catalog:
  - business/customer
  - mandate type
  - ICP/target override
  - ring
  - instantiate, then trigger
- Instance file:
  - set ring
  - trigger run
- Foundry:
  - run swarm pack
  - show synthetic versus real evidence
  - promote only when the gate allows it

Keep the current visual system. Do not redesign the dashboard during this core session.

## Tests to Write First

Use TDD. Add focused tests before implementation.

Kernel/control tests:

1. Approval of a parked run resumes and settles.
2. Approval survives reconstructing services around the same stores.
3. Edited approval executes edited validated args and sets `edited=True`.
4. Invalid edited args are rejected without executing an adapter.
5. Rejection journals the decision and never executes or settles.
6. Duplicate approval/rejection is idempotent or returns a deterministic conflict.
7. Instantiate journals and projects a valid isolated instance.
8. Projection rebuild recreates instance and initial resume ring.
9. Trigger resolves type/instance and invokes the shared run invoker.
10. Run checkpoints preserve hydration, trace, claimed facts, and parked intent.

Syscall tests:

1. Durable manual queue survives store reconstruction.
2. Duplicate idempotency key does not duplicate a task.
3. Human fallback still terminates every ladder.
4. Marking an outcome removes a task from the open queue.

Swarm/promotion tests:

1. Dashboard swarm command runs only in sim mode.
2. Scorecards/eval cases retain `origin`.
3. Synthetic-only promotion is denied.
4. Real passing evidence plus human approval can promote a canary.
5. Denied promotion does not change ring.

API tests:

1. Every supported command maps to the core service exactly once.
2. Approval round-trip changes run state and journal.
3. Instantiate then trigger works end to end in memory.
4. Mongo-gated test proves durable continuation/manual queue when Mongo is available.
5. Core errors return stable HTTP status and JSON shapes.

Browser test:

1. Create an instance.
2. Trigger a run.
3. Observe it park.
4. Edit or approve.
5. Observe settlement and new ledger entries without a full page reload.

## Required Verification

Run all of these before claiming completion:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run mypy --strict packages db tests
uv run lint-imports

cd api
uv run pytest
uv run ruff check .
uv run mypy src tests

cd ../dashboard
npm test
npm run build
npm audit --omit=dev
```

Also run the API and production dashboard locally and verify the complete approval and
instantiate-trigger flows in a browser.

## Deliverables

1. Journaled approve/edit/reject with real continuation resume.
2. Journaled mandate instantiation.
3. Journaled live run trigger using shared live wiring.
4. Durable run checkpoints and rich run detail.
5. Durable human/manual queue.
6. Swarm test orchestration with persisted synthetic eval evidence.
7. Promotion command guarded by real evidence and human approval.
8. API stubs replaced only where the core capability is real.
9. Dashboard controls enabled for completed commands.
10. Updated `/core-gaps` containing only genuine remaining limitations.
11. Tests, build output, API route list, screenshots, and any contract coordination decision.

## Done When

The session is complete only when:

- A parked run can be approved or edited after service reconstruction and then settle.
- Rejecting a parked run is durable and executes no effect.
- A new instance can be created through the dashboard and appears in Mongo/projections.
- The operator can trigger a live run through the control path.
- The manual queue survives process restart.
- A swarm test produces durable synthetic eval evidence.
- Synthetic-only promotion is still impossible.
- Real evidence plus human approval can promote only the selected canary ring.
- Every action appears in the append-only journal.
- No secret enters the frontend or mandate user space.
- Import-linter still reports all contracts kept.
- No frozen contract was changed without an explicit stop-and-coordinate event.

## Final Reporting Format

Report:

1. What changed by owning package.
2. Exact command and query surfaces added.
3. Journal events and projections involved in each command.
4. Any contract change requested or performed.
5. Full verification output summary.
6. Browser flow evidence.
7. Remaining core gaps, without hiding incomplete behavior behind API success responses.
