# db/ — MongoDB setup (event-sourced)

Phase-1 MongoDB layer. **Interfaces + schemas only** in Session A; the kernel (Claude, Session B)
implements the index creation and the projection builders.

## The one idea: the Journal is the source of truth

```
            append-only, single-doc atomic INSERT
   kernel ───────────────────────────────────────▶  journal   (SOURCE OF TRUTH)
                                                        │
                       projection builders (idempotent, replayable)
                                                        ▼
        heap_fact · thread · resume · watch · billing_line · syscall_trace   (PROJECTIONS)
```

- **Appending an event is one document insert** — atomic in MongoDB, so settlement's fan-out
  (facts, trust, billing, watch, spawn) is committed as **one** `RunSettled` event. This sidesteps
  multi-document transactions: consistency comes from deriving everything else from the journal.
- **Projections** are rebuilt by folding journal events (`agentx_db.projections.*Projector`). They can
  be dropped and replayed from the journal at any time.

## Collections (Phase 1)

| Collection | Role |
|---|---|
| `mandate_type` | the class (seven organs) |
| `mandate_instance` | the object (private, per-customer — the moat) |
| `mandate_run` | the stack frame (durable continuation) |
| **`journal`** | **append-only event log — SOURCE OF TRUTH (WAL/ledger)** |
| `heap_fact` | projection: verified facts + provenance (per-instance, isolated) |
| `thread` | projection: per-entity relational state |
| `resume` | projection: trust/ring + verified success rates |
| `watch` | projection: deferred (reality-rung) verification timers |
| `syscall_trace` | projection: the auditable effect ledger per run |
| `billing_line` | projection: settlement P&L atoms |
| `eval_case` | gym corpus (synthetic + real; `origin` gates promotion — invariant #7) |

## Files

- `collections.py` — collection-name constants.
- `indexes.py` — declarative `IndexSpec`s (note: `journal` has a UNIQUE idempotency index — retries
  never double-append; per-instance keys keep `heap_fact` isolated, invariant #3).
- `projections.py` — projection-builder Protocols (kernel implements).
- `setup.py` — `ensure_indexes(database)` (kernel implements vs `AsyncMongoClient` in Session B).

## Driver

**PyMongo async (`AsyncMongoClient`)**, `pymongo>=4.17,<5`. **Not Motor** — Motor reached EOL
2026-05-14; PyMongo's native async is MongoDB's official successor.
