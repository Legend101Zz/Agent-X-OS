"""Declarative index specs for Phase-1 collections.

These are data, not logic: ``setup.ensure_indexes`` (Session B) walks them and calls
``create_index`` on an ``AsyncMongoClient`` database. Index choices encode the access patterns:
- ``journal``: total order per instance ``(instance_id, seq)`` + UNIQUE idempotency (retries never
  double-append) — the heart of the event-sourced design.
- ``heap_fact``: per-instance SPO lookup + status; ``decay_at`` for GC. Per-instance keys keep the
  heap isolated (invariant #3).
"""

from typing import Final

from agentx_contracts import AgentXModel

from . import collections as c


class IndexSpec(AgentXModel):
    """One MongoDB index: ordered keys (1 asc / -1 desc), a stable name, and uniqueness/sparsity."""

    keys: list[tuple[str, int]]
    name: str
    unique: bool = False
    sparse: bool = False


INDEXES: Final[dict[str, list[IndexSpec]]] = {
    c.JOURNAL: [
        IndexSpec(keys=[("instance_id", 1), ("seq", 1)], name="ix_journal_instance_seq", unique=True),
        IndexSpec(keys=[("idempotency_key", 1)], name="ix_journal_idem", unique=True, sparse=True),
        IndexSpec(keys=[("run_id", 1)], name="ix_journal_run"),
        IndexSpec(keys=[("kind", 1)], name="ix_journal_kind"),
    ],
    c.HEAP_FACT: [
        IndexSpec(keys=[("instance_id", 1), ("subject", 1), ("predicate", 1)], name="ix_heap_spo"),
        IndexSpec(keys=[("instance_id", 1), ("status", 1)], name="ix_heap_status"),
        IndexSpec(keys=[("decay_at", 1)], name="ix_heap_decay", sparse=True),
    ],
    c.THREAD: [
        IndexSpec(keys=[("instance_id", 1), ("entity_id", 1)], name="ix_thread_entity", unique=True),
        IndexSpec(keys=[("instance_id", 1), ("state", 1)], name="ix_thread_state"),
    ],
    c.RESUME: [
        IndexSpec(keys=[("instance_id", 1)], name="ix_resume_instance", unique=True),
    ],
    c.MANDATE_TYPE: [
        IndexSpec(keys=[("name", 1), ("version", 1)], name="ix_type_name_version", unique=True),
    ],
    c.MANDATE_INSTANCE: [
        IndexSpec(keys=[("customer_id", 1)], name="ix_instance_customer"),
        IndexSpec(keys=[("type_ref", 1)], name="ix_instance_type"),
    ],
    c.MANDATE_RUN: [
        IndexSpec(keys=[("instance_id", 1), ("state", 1)], name="ix_run_instance_state"),
        IndexSpec(keys=[("state", 1)], name="ix_run_state"),
    ],
    c.WATCH: [
        IndexSpec(keys=[("status", 1), ("deadline", 1)], name="ix_watch_due"),
        IndexSpec(keys=[("run_id", 1)], name="ix_watch_run"),
    ],
    c.SYSCALL_TRACE: [
        IndexSpec(keys=[("run_id", 1)], name="ix_trace_run"),
        IndexSpec(keys=[("instance_id", 1)], name="ix_trace_instance"),
    ],
    c.BILLING_LINE: [
        IndexSpec(keys=[("instance_id", 1)], name="ix_billing_instance"),
        IndexSpec(keys=[("run_id", 1)], name="ix_billing_run"),
    ],
    c.EVAL_CASE: [
        IndexSpec(keys=[("type_ref", 1), ("origin", 1)], name="ix_eval_type_origin"),
        IndexSpec(keys=[("origin", 1)], name="ix_eval_origin"),
    ],
}
