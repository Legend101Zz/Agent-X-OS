# BUILD-PLAN.md — Agent-X Phase 1

Phase 1 (BLUEPRINT §7): **one lead-finder mandate, manual projection, one operator, rings L0–L2.**
The whole game: get one instance to `settle()` against reality ~100 times. Two agents build in
parallel against the **frozen** `packages/contracts`:

- **CLAUDE LANE** → `packages/kernel` + `packages/mandate`
- **CODEX LANE** → `packages/syscall` + `packages/swarm`

> **`packages/contracts` is FROZEN as of the end of Session A.** It is the only cross-boundary
> dependency and the only reason two agents can build one system in parallel. Changing it is a
> **stop-and-coordinate** event (see bottom). Both lanes build ONLY against it; neither imports the
> other (enforced by `.importlinter`).

## Stack (web-confirmed 2026-06-17 — do not rely on memory)
Python 3.12 · uv workspace · Pydantic v2 (`>=2.13`) + pydantic-settings (`>=2.14`) · pytest 9 +
pytest-asyncio (`asyncio_mode="auto"`) · ruff 0.15 · mypy 2.1 (strict) · MCP SDK `mcp>=1.27,<2` ·
promptfoo (npm, subprocess) · Exa `exa-py>=2.14` · Firecrawl `firecrawl-py>=4.30`.

> **⚠️ Driver deviation from BUILD-KIT §2 (logged):** the kit says "Motor (async)". **Motor reached
> end-of-life 2026-05-14.** We use **PyMongo async (`AsyncMongoClient`, `pymongo>=4.17,<5`)** — same
> MongoDB ecosystem, still async, MongoDB's official successor. The event-sourced design is unchanged.

## Dependency DAG (what unblocks what)
```
contracts (FROZEN) ─┬─────────────── CLAUDE ───────────────┐   ┌──────────── CODEX ────────────┐
                    │  db(K0) → journal(K1) → projections(K2)│   │ adapters fw (S1) → adapters (S2)│
                    │                  │         hydration(K3)│   │            │       HumanTask(S3)│
                    │  verifier rules+human (K4)              │   │ scenario packs (S4)            │
                    │                  └→ gateway (K5) ───────┼──▶│ SimAdapter (S5)  [Adapter iface]│
                    │  run-loop live+sim = RunInvoker (K6) ◀──┼───│ promptfoo Judge (S6)           │
                    │  settlement (K7) → supervision (K8)     │   │ trace data + PromotionGate (S7)│
                    │  command/query API (K9)                 │   └────────────────────────────────┘
                    │  faculties fw (M1) → 4 faculties (M2)   │
                    │  lead-finder MandateType (M3)           │
                    └─────────────────────────────────────────┘
                                         └────────── seam proof: tests/integration (I1) ──────────┘
```

---

## CLAUDE LANE — kernel + mandate

### Kernel
| # | Task | Definition of done (one line) |
|---|---|---|
| K0 | Mongo connection + `db.setup.ensure_indexes` | `AsyncMongoClient` connects; all Phase-1 collections + `INDEXES` created (idempotent); journal idempotency index is UNIQUE. |
| K1 | Journal event store (append-only) | `append(event)` is a single-doc atomic insert; duplicate `idempotency_key` is rejected; events are totally ordered per instance by `seq`. |
| K2 | Projection builders (heap/thread/résumé/watch/billing/trace) | Applying a `RunSettled` event updates `heap_fact` with provenance; every projector is idempotent and `rebuild(instance_id)` replays from the journal. |
| K3 | Hydration | `hydrate(instance, trigger)` returns a frozen `HydrationSnapshot` (heap facts ranked relevance×conf×recency + open thread + recent journal + skill/domain refs). |
| K4 | Verifier — rules + human rungs | rules rung returns a `RuleVerdict` deterministically; human rung parks the run and resumes on `ApprovalResolved`. |
| K5 | Gateway policy | ring-check (L0–L2) + idempotency + channel-rule hook + adapter selection via `SyscallRegistry` + credential-injection POINT (vault stub) + journaling; a read executes at any ring, an L1 effectful syscall PARKS. |
| K6 | Run-loop = `RunInvoker` (live + sim) | `invoke(...,mode)` runs hydrate→think→syscall→verify→settle; `sim` swaps the adapter registry and the loop does NOT branch otherwise; returns a `RunResult`. |
| K7 | Settlement engine | `settle(run)` appends exactly ONE `RunSettled` event (facts w/ provenance, trust Δ, billing, watches, spawns) — no bypass path to the heap (invariant #1). |
| K8 | Supervision | a crashed run escalates upward with full context; the owner's resolution commits to memory (heap). |
| K9 | Command/query API over projections | typed reads (floor / approval inbox / instance file) + commands (approve / set-ring) that are themselves journaled `ManagerAction` events. |

### Mandate
| # | Task | Definition of done (one line) |
|---|---|---|
| M0 | MandateType/Instance/Run wired as data | load the lead-finder type from a doc; construct an L1 instance binding. |
| M1 | Faculties framework | a faculty's `harness_adapter` enables native skills, re-points effectful tools to the gateway, keeps harness memory as scratch; a faculty proposes a syscall via its `tool_manifest`; the pod holds no creds (guard test passes). |
| M2 | The four faculties: research, judgment, memory-craft, escalation | each runs in sim and emits the right syscall intents / proposes facts with provenance + confidence (`memory-craft`) / crashes upward (`escalation`). |
| M3 | lead-finder `MandateType` assembled | charter conditions are all checkable; the mandate runs end-to-end in sim through `RunInvoker`. |

**CLAUDE done-when:** kernel + mandate import clean (`uv run mypy`), unit tests pass, and the kernel side of `tests/integration` passes (hydrate → faculty proposes syscall → gateway parks at L1 → approval resumes → settlement commits atomically with provenance → run is invokable in sim mode). Report integration points awaiting Codex; confirm `contracts` unchanged.

---

## CODEX LANE — syscall + swarm

| # | Task | Definition of done (one line) |
|---|---|---|
| S1 | Adapter framework + `SyscallRegistry` + ladder resolution | `resolve(req, ctx)` returns the highest-rung capable adapter and NEVER returns None — the human-task adapter is the guaranteed tail (`is_terminal_fallback=True`). |
| S2 | Phase-1 adapters: `lead_research_batch`, `read_url`, `draft_email`, `queue_manual_action`, `mark_outcome` | each implements the `Adapter` Protocol with fixtures + a passing `health_check`; `draft_email` is draft-mode only (never sends); research uses Exa/Firecrawl (confirm APIs via `doc-researcher`). |
| S3 | `HumanTaskAdapter` (manual-projection queue) | `can_handle` always True; queues the intent to the manual queue and returns `status="queued_manual"`. |
| S4 | Scenario packs (10–30 synthetic lead/company cases) | loadable JSON/Mongo docs with actors, tasks, traps, expected signals. |
| S5 | `SimAdapter` (sim counterparties + sandboxed syscalls) | binds in `sim` mode in place of live adapters; produces deterministic results with NO real creds/effects. |
| S6 | promptfoo bridge = `Judge` | runs promptfoo as a subprocess with the kernel's `RunInvoker` wired as a Python custom provider; `grade(trace, rubric)` returns a `Scorecard`. |
| S7 | Trace viewer data + `PromotionGate` | the gate blocks promotion when the only passing cases are `origin="synthetic"` (invariant #7). |

**CODEX done-when:** syscall + swarm import clean (`uv run mypy`), unit tests pass, every adapter has fixtures + a passing health check, the HumanTaskAdapter resolves as the tail; the syscall+swarm side of `tests/integration` passes (gateway selects+calls a Phase-1 adapter; a candidate mandate runs in the SimAdapter world via `RunInvoker`; promptfoo grades the trace; `PromotionGate` blocks synthetic-only promotion). Confirm `contracts` unchanged.

---

## Integration (joint)
| # | Task | Definition of done |
|---|---|---|
| I1 | `tests/integration/test_seam_proof.py` passes | the full flow joins: candidate mandate → `RunInvoker` (sim) → gateway selects a syscall adapter → parks for approval → settles atomically with provenance → swarm Judge grades the trace. (Currently fails with a clear "not implemented" — that IS the target.) |

## Definition of done (every component, both lanes)
Builds · `uv run mypy` clean · unit tests pass **with shown output** · respects all 8 invariants ·
changed nothing in `contracts` unilaterally · no Phase 2–5 code · **verified by running, not asserted**
(use the `verification-before-completion` skill). The `contract-guardian` subagent reviews diffs that
touch the seam.

## Stop-and-coordinate protocol (the seam is sacred)
If either agent finds the seam is wrong: **STOP — do not work around it.**
1. Open it as a coordination event (note what's wrong + why).
2. Edit `packages/contracts`; run `uv run mypy packages/contracts` + the guard test + `lint-imports`.
3. Have `contract-guardian` review the contract diff against the 8 invariants.
4. Both lanes re-pull `contracts` (it merges FIRST), then resume. No agent edits the other's package.
Use separate branches/worktrees per agent; `contracts` changes always land before dependent work.
