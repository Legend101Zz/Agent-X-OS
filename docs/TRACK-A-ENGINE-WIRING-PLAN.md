# Track A — Engine wiring plan for the books-prep product app

**Audience:** a fresh Claude Code session working in the **engine** repo
`C:\Users\XZNON\Agent-X-OS` (the KERNEL + MANDATE lane — see `CLAUDE.md`).
**Goal of this track:** land the three engine-side changes the separate
`agentx-books-app` product needs (its "Open flags #2/#3/#4"), so the BFF can
(a) share storage dirs with the engine, (b) read the exported `.xlsx` path from a
GET, and (c) optionally drive a real model in `mode="live"`.

This doc is the spec. It was produced by a READ-ONLY verification pass on branch
`feat/books-prep-mandate` (2026-06-23). **Line numbers are accurate as of that
pass but may drift — always re-`grep`/`Read` to re-anchor before editing.**

> **Branch:** do this work on `feat/books-prep-mandate` (or a `wt/track-a-*`
> worktree off it), NOT `main`. The user runs their own `git commit`/`push` —
> prepare diffs, write `[claude]`-prefixed commit messages in your handoff, but do
> not commit/push unless asked.

---

## Orientation (read before coding)

- **The seam is sacred.** `packages/contracts` is frozen. Flag #4 and #2 do **not**
  touch a frozen contract. **Flag #3 DOES** — it edits
  `packages/contracts/src/agentx_contracts/journal.py` (`SyscallSettled`). Per
  `CLAUDE.md` "Stop-and-coordinate", a contract change must be blessed by Hermes
  *first*. **Sequence accordingly:** do #4 and #2 freely; for #3, emit
  `BLOCKED: contract change needed — add SyscallSettled.output` in your handoff and
  pause #3 until cleared. If the operator clears it inline, proceed.
- **Lane fence.** You may import `agentx_kernel`, `agentx_syscall`,
  `agentx_contracts` from `api/` (the api is the composition edge — allowed). You
  must NOT make `agentx_mandate` import a credential/config root. None of these
  changes put a cred import into mandate, so `uv run lint-imports` should stay
  `3 kept / 0 broken`. Verify it after each flag.
- **TDD.** For each flag: write the failing test(s) that encode the Done-when
  FIRST, watch them fail, implement the smallest change to green, then run the full
  gate.

### Gate (run after each flag; must stay green)

```bash
uv sync
uv run pytest -q
cd api && uv run pytest -q && cd ..
uv run ruff check .
uv run mypy --strict packages db tests
cd api && uv run mypy --strict src tests && cd ..
uv run lint-imports          # expect: 3 kept / 0 broken
```

---

## Flag #4 — Make `books_intake_dir` / `books_output_dir` env-configurable

**Why:** `build_phase1_registry(books_intake_dir=, books_output_dir=)` accepts the
params, but the running api never passes them. Today
`api/src/agentx_api/operator.py` `_compose` calls
`build_phase1_registry(send_email_adapters=...)` with **no** books dirs, so both
default to `None` →
- `ingest_document` can't resolve a bare `doc_id` (intake_dir is None);
- `export_ledger` writes the `.xlsx` to `Path.cwd()` (the dir uvicorn was launched
  from), with no way to redirect it.

**Goal (one sentence):** `BOOKS_INTAKE_DIR` / `BOOKS_OUTPUT_DIR` in the engine
`.env` flow through to the registry's books adapters on every api run.

### Changes

1. **`packages/contracts/src/agentx_contracts/config.py`** — add two fields to
   `Settings` (this is `config.py`, the env loader — NOT a frozen mandate/syscall
   contract; still keep it minimal). Place them near the other api-runtime fields:

   ```python
   # --- books-prep shared storage (product app shares these dirs with the engine) ---
   # Empty string → adapters fall back to their None default (cwd for output; no
   # intake resolution for bare doc_ids). Set both to absolute paths in production.
   books_intake_dir: str = ""
   books_output_dir: str = ""
   ```

   pydantic-settings maps these to `BOOKS_INTAKE_DIR` / `BOOKS_OUTPUT_DIR`
   (case-insensitive) automatically — no extra config.

2. **`api/src/agentx_api/operator.py`** — in `_compose` (the function that builds
   the registry; the `build_phase1_registry(...)` call is ~line 311), thread the
   settings through. `_compose` already receives `settings: Settings`, so read them
   directly:

   ```python
   registry = build_phase1_registry(
       send_email_adapters=send_email_adapters,
       books_intake_dir=settings.books_intake_dir or None,
       books_output_dir=settings.books_output_dir or None,
   )
   ```

   `or None` converts the empty-string default back to the adapter's `None`
   sentinel so behavior is unchanged when unset.

3. **`.env.example`** — document the two vars (append a new section):

   ```
   # --- books-prep product app: shared storage dirs (absolute paths) ------------------
   # The product app's BFF (agentx-books-app/api) must point BOOKS_INTAKE_DIR /
   # BOOKS_OUTPUT_DIR at THESE SAME paths. Empty = engine falls back to cwd for output
   # and cannot resolve bare doc_ids on ingest.
   BOOKS_INTAKE_DIR=
   BOOKS_OUTPUT_DIR=
   ```

### Tests first (TDD)

- **`api/tests/`** (new test, e.g. `test_books_dirs_wiring.py`): build a runtime
  with a `Settings` that sets `books_intake_dir`/`books_output_dir` to `tmp_path`
  subdirs, then assert the composed registry's `export_ledger` adapter writes there.
  Two viable approaches — pick the one that fits the existing test style:
  - **Composition assertion:** call `build_runtime(settings=<settings with dirs>)`,
    reach into the gateway's registry, find the `ExportLedgerAdapter`, and assert its
    `_output_dir == tmp_path/out`. (Private attr, but this is a white-box wiring
    test.)
  - **End-to-end:** mirror `tests/integration/test_books_prep_e2e.py` (which already
    drives `build_phase1_registry(books_output_dir=...)` directly) but go through
    `build_runtime` so it proves the *api composition* passes the dirs, not just the
    registry builder. This is the stronger test — prefer it.
- Confirm the **unset** path still works (empty string → `None` → cwd), so existing
  behavior is preserved.

### Done-when

- A run triggered through a runtime built from a `Settings` carrying
  `books_output_dir` writes its `.xlsx` into that dir (not cwd).
- `ingest_document` with a bare `doc_id` resolves against `books_intake_dir`.
- Unset (`""`) preserves today's behavior. Gate green; `lint-imports` 3/0.

---

## Flag #2 — Wire a live model transport (`mode="live"`) into the api

**Why:** the Gemini/MiniMax factory `build_faculty_transport()`
(`packages/kernel/src/agentx_kernel/hermes.py:173`) exists and is env-configurable,
but the api never builds a runner from it. `create_state → build_runtime` passes no
`runner_factory`, so `_compose` sets `runner=None`, and
`Phase1RunInvoker._runner()` returns `OwnHarness(playbook=...)` for **both** sim and
live. Result: a `mode="live"` run through the api silently uses the deterministic
playbook and calls **no model**.

**Goal:** when faculty-model env is configured, a `mode="live"` run through the api
is driven by the real `HermesRunner` (MiniMax or Gemini per the toggle); `mode="sim"`
stays deterministic and **needs no keys**; when env is absent, `live` degrades to
the deterministic harness (logged), never crashes.

### ⚠ Blast-radius finding — do NOT naively gate `_runner` on mode

`Phase1RunInvoker._runner(self, mandate)` today is:
```python
if self.runner is not None:
    return self.runner
return OwnHarness(playbook=sim_playbook_for(mandate))
```
A naive "use `self.runner` only when `mode=='live'`" change **breaks existing
tests** that inject a runner and run sim — confirmed:
- `tests/integration/test_parked_resume.py:170` injects `runner=OwnHarness(...)` and
  schedules `mode="sim"` (line 176) — relies on the injected runner in sim.
- `tests/integration/test_mandate_discovery_phase14.py:324/337` injects
  `runner=OwnHarness(...)` with `mode="live"` — works either way.

**So keep the `runner=` slot's "always used if set" semantics, and add a SEPARATE,
optional `live_runner` slot that is consulted only for live runs.** This makes the
new behavior purely additive: existing callers (which set `runner=`, never
`live_runner=`) are unaffected.

### Changes

1. **`packages/kernel/src/agentx_kernel/run_loop.py`** — on `Phase1RunInvoker`
   (the `@dataclass`, fields start ~line 79) add a new optional field next to
   `runner`:

   ```python
   runner: HarnessRunner | None = None
   live_runner: HarnessRunner | None = None   # model-driven harness, used ONLY for mode="live"
   ```

   Change `_runner` (~line 306) to take `mode` and apply 3-way precedence:

   ```python
   def _runner(self, mandate: MandateType, mode: RunMode) -> HarnessRunner:
       # mode="live" + a configured model runner → drive the real model.
       # Otherwise (sim, OR live with no model configured) fall back to the
       # explicitly-injected runner if present (tests/scripts), else the
       # deterministic OwnHarness playbook. Sim NEVER touches a model → no keys, reproducible.
       if mode == "live" and self.live_runner is not None:
           return self.live_runner
       if self.runner is not None:
           return self.runner
       return OwnHarness(playbook=sim_playbook_for(mandate))
   ```

   Update the **two** callsites:
   - `invoke` (~line 177): `runner = self._runner(mandate, mode)`
   - `resume` (~line 248): `self._runner(continuation.mandate, continuation.mode).start(...)`
     — `continuation.mode` exists (`continuations.py:21`), so resume recovers the
     original run's mode and keeps live/sim consistent across the park boundary.

   `RunMode` is already imported in `run_loop.py`. Confirm there are no other
   `_runner(` callsites (`grep`).

2. **`api/src/agentx_api/operator.py`** — build the live runner from settings and
   pass it into the invoker. Add a helper near `_resolve_live_email_transport`
   (~line 412), mirroring its env-driven, never-raises shape:

   ```python
   def _resolve_live_runner(settings: Settings) -> Any | None:
       """Build the model-driven HarnessRunner from faculty-model env, or None.

       Returns None (→ live degrades to the deterministic OwnHarness) when neither the
       Gemini toggle nor a MiniMax key is usable. Never raises: a missing-key ConfigError
       from build_faculty_transport is swallowed so the api boots without a model in dev/sim.
       """
       try:
           from agentx_kernel.hermes import build_faculty_transport
           from agentx_kernel.hermes_runner import HermesRunner

           transport = build_faculty_transport(settings)  # raises ConfigError if no usable keys
       except Exception:  # noqa: BLE001 — no model configured is a valid (sim-only) state
           return None
       return HermesRunner(transport=transport)
   ```

   In `_compose`, where the invoker is constructed (~line 321), set `live_runner`:

   ```python
   runner: HarnessRunner | None = runner_factory() if callable(runner_factory) else None
   live_runner = _resolve_live_runner(settings)
   invoker = Phase1RunInvoker(
       journal=journal,
       projections=projections,
       hydration=hydration,
       gateway=gateway,
       settlement=settlement,
       verifier=verifier,
       continuations=continuations,
       runner=runner,
       live_runner=live_runner,
   )
   ```

   Optional but recommended: `logger.info("live model runner: %s", "configured" if
   live_runner else "absent (live will use deterministic harness)")` so operators
   can see the state at boot. (Never log key values.)

**Reuse-safety (verified):** `HermesRunner.start()` is stateless — it rebuilds
tools/prompts from `context` and returns a fresh `HermesSession` each call; the only
instance state is `self.transport` (a stateless HTTP client). Building ONE
`HermesRunner` at compose and reusing it across runs is safe.

**Env that configures it** (already in `Settings`):
- MiniMax (default): `MINIMAX_API_KEY` + `FACULTY_MODEL_BASE_URL` + `FACULTY_MODEL_ID`.
- Gemini toggle: `USE_GEMINI=1` + `GEMINI_API_KEY` + `GEMINI_BASE_URL` + `GEMINI_MODEL_ID`.
  (`build_faculty_transport` prefers Gemini when all four are set, else MiniMax.)

### Tests first (TDD)

- **`packages/kernel/tests/` (run_loop):** construct a `Phase1RunInvoker` with a
  **fake** `live_runner` (a recording harness) and `runner=None`. Assert:
  - `invoke(..., mode="live")` uses the `live_runner`.
  - `invoke(..., mode="sim")` uses `OwnHarness` (NOT the live_runner) — prove sim
    needs no model.
  - With `runner=<fake>` set and `live_runner=None`, BOTH modes use the injected
    `runner` (pins the back-compat semantics that protect `test_parked_resume`).
  - `resume` honors `continuation.mode` (park a live run, resume, assert live_runner
    used). Reuse the `test_parked_resume.py` scaffolding.
- **`api/tests/`:** `_resolve_live_runner` returns `None` when no keys (don't hit the
  network); returns a `HermesRunner` when a fake/temp `Settings` provides MiniMax or
  Gemini fields. Do NOT make a real model call in tests — assert on the object type
  and the transport's `provider`, mirroring `tests/kernel/test_hermes_client.py`.
- **Regression:** run `test_parked_resume.py` + `test_mandate_discovery_phase14.py`
  unchanged — they must stay green (proves the additive design).

### Done-when

- `live_runner` set + `mode="live"` → real `HermesRunner` drives the run.
- `mode="sim"` → deterministic `OwnHarness`, zero key requirement.
- No env keys → `_resolve_live_runner` returns `None`, api boots, `live` degrades
  gracefully (deterministic), no crash.
- All pre-existing invoker/resume/discovery tests stay green. Gate green; 3/0.

---

## Flag #3 — Surface the `export_ledger` output path in a READ endpoint  ⚠ CONTRACT CHANGE

**Why:** `export_ledger` returns `output.path` (the absolute `.xlsx` path) in its
`SyscallResult` (`packages/syscall/src/agentx_syscall/books.py:494`), but it's
surfaced nowhere readable:
- `SyscallSettled` journal event (`contracts/journal.py:64`) carries only
  `syscall/status/fulfilled_by/maturity_used` — no `output`. So `/journal` and the
  `timeline` in `GET /runs/{id}` omit it.
- The `syscall_trace` projection (`kernel/projections.py:85`, surfaced as
  `run_detail.syscall_trace`) stores the same fields — no `output`.
- The run's `Finish` output is `{transactions, clean, queued}`
  (`books_prep_playbook.py:79`) — no path. Committed facts are `ledger_transaction`
  rows — no path.

The BFF needs the path to stream the `.xlsx` for the download button.

**Goal:** the `export_ledger` result's `output` (incl. `path`) is readable from
`GET /runs/{id}` (via `syscall_trace`) and `GET /journal` (via the `SyscallSettled`
event) after the run settles.

> **🟥 STOP-AND-COORDINATE.** Step 1 edits a frozen contract (`journal.py`). Emit
> `BLOCKED: contract change needed — add SyscallSettled.output (JsonObject)` in your
> handoff and get Hermes's go-ahead before landing it. Steps 2–3 (projection + api)
> are in your lane and follow once the contract lands.

### Design note — full `output` is consistent with existing journal sizing

`SyscallAttempted` already stores the full `args: JsonObject` (`journal.py:60`),
and for `export_ledger` those args carry **all ledger rows**. So the journal already
persists large per-syscall payloads; adding `output` is consistent with that
existing decision. Carry the full `result.output`. (If a future audit wants to bound
journal size, that's a separate, broader change — do not special-case it here.)

### Changes

1. **`packages/contracts/src/agentx_contracts/journal.py`** (FROZEN — coordinate
   first) — add an `output` field to `SyscallSettled` (~line 64), defaulted so it's
   backward-compatible with every existing journal row:

   ```python
   class SyscallSettled(_JournalBase):
       kind: Literal["syscall_settled"] = "syscall_settled"
       syscall: str
       status: SyscallStatus
       fulfilled_by: str
       maturity_used: MaturityLevel
       output: JsonObject = Field(default_factory=dict)
       """The adapter's SyscallResult.output (e.g. export_ledger's {path, filename, ...}).
       Default {} keeps old rows valid and write-free syscalls cheap."""
   ```

   Confirm `JsonObject` and `Field` are already imported in `journal.py` (they are
   used elsewhere in the module).

2. **`packages/kernel/src/agentx_kernel/gateway.py`** — populate `output` at the
   **two** `SyscallSettled(...)` construction sites:
   - ~line 160 (fresh execution): add `output=result.output,`
   - ~line 239 (idempotent replay from receipt): add `output=receipt.result.output,`

   Both have the result in scope. No other logic changes.

3. **`packages/kernel/src/agentx_kernel/projections.py`** — in `TraceProjector.apply`
   for the `SyscallSettled` branch (~line 85), add `output` to the upserted
   `syscall_trace` doc:

   ```python
   {
       "id": event.event_id, "run_id": event.run_id, "instance_id": event.instance_id,
       "kind": "settled", "syscall": event.syscall, "status": event.status,
       "fulfilled_by": event.fulfilled_by, "maturity_used": event.maturity_used,
       "output": event.output,
       "seq": event.seq, "ts": event.ts.isoformat(),
   },
   ```

   No api change is needed: `run_detail` already returns `syscall_trace` docs
   verbatim (`api/src/agentx_api/state.py:597`), and `/journal` already dumps the
   full event (`app.py:611`). Once the projection carries `output`, both reads expose
   the path automatically.

### How the path reaches the BFF (end to end, for the test)

`export_ledger` is `reversible_write` and parks at L1. At ring L0 the gateway parks
it (RunParked, no settle). After `POST /commands/approve` + resume, the gateway
**executes** it and emits `SyscallSettled` with `output.path`. So the path appears
on the resumed run's settle, under the same `run_id` → `GET /runs/{id}` shows it in
`syscall_trace`. The BFF reads `syscall_trace[].output.path` where
`syscall=="export_ledger"`.

### Tests first (TDD)

- **`packages/contracts/tests/`:** `SyscallSettled` round-trips with and without
  `output`; default is `{}`; `model_dump(mode="json")` includes `output`.
- **`tests/kernel/test_gateway.py`:** after a successful write-class syscall, the
  appended `SyscallSettled.output` equals the adapter's `result.output`. Add an
  idempotent-replay assertion (the line-239 path) so both sites are covered.
- **`packages/kernel/tests/` (projections):** a `SyscallSettled` with
  `output={"path": ...}` produces a `syscall_trace` doc whose `output.path` matches.
- **Integration (strongest):** extend `tests/integration/test_books_prep_e2e.py` —
  after the export settles, read the `syscall_trace` (or journal) and assert the
  `export_ledger` row's `output.path` equals the written `.xlsx` path (and that the
  file exists in `books_output_dir`). This simultaneously re-proves flag #4.

### Done-when

- `GET /runs/{id}` `syscall_trace` (and `/journal`) expose `export_ledger`'s
  `output.path` after settlement.
- Old journal rows without `output` still validate (`default_factory=dict`).
- The `.xlsx` exists at that path inside `books_output_dir`. Gate green; 3/0.

---

## Suggested order & handoff

1. **Flag #4** (no contract change, unblocks app step 3) — implement, gate, commit
   `[claude] flag-4: env-configurable books intake/output dirs`.
2. **Flag #2** (no contract change, additive `live_runner`) — implement, gate, commit
   `[claude] flag-2: wire live model runner into api (mode-aware)`.
3. **Flag #3** (frozen-contract edit) — emit `BLOCKED: contract change needed` and
   WAIT for Hermes. Once cleared: implement contract → gateway → projection → tests,
   gate, commit `[claude] flag-3: surface export_ledger output path on SyscallSettled`.

### Self-review before each commit (per `CLAUDE.md`)

- Re-read the diff against the **8 invariants** (esp. #2 no creds in user space — none
  of these add a cred import to `agentx_mandate`; the live runner/transport is built
  at the api edge only).
- `uv run lint-imports` → **3 kept / 0 broken**.
- Full gate green (workspace + api pytest, ruff, mypy --strict both trees).
- Update the Kanban card / handoff with `changed_files`, `tests_run`,
  `tests_passed`, and decisions. The **user runs their own git** — do not
  commit/push unless explicitly asked.

### After Track A lands

Tell the operator to set `BOOKS_INTAKE_DIR` / `BOOKS_OUTPUT_DIR` (and, for a live
demo, the MiniMax or Gemini env) in the engine `.env`, then point the
`agentx-books-app` BFF's `BOOKS_INTAKE_DIR` / `BOOKS_OUTPUT_DIR` at the SAME paths.
The product app's `docs/IMPLEMENTATION-HANDOFF.md` "Open flags" section should be
flipped from 🟥 BLOCKED to ✅ once these are merged.
