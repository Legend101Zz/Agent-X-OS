"""agentx_db — MongoDB setup for Phase 1 (event-sourced).

The append-only ``journal`` collection is the SOURCE OF TRUTH (single-document atomic inserts);
``heap_fact`` / ``thread`` / ``resume`` / ``watch`` / ``billing_line`` / ``syscall_trace`` are
PROJECTIONS built from it. This package holds the collection names, declarative index specs, the
projection-builder Protocols (kernel implements), and the index-setup entry point.

Driver: PyMongo async (``AsyncMongoClient``) — NOT Motor (EOL 2026-05-14). Interfaces/schemas only;
no business logic. See db/README.md.
"""

from .collections import (
    ALL_COLLECTIONS,
    PROJECTIONS,
    SOURCE_OF_TRUTH,
)
from .indexes import INDEXES, IndexSpec
from .projections import (
    BillingProjector,
    HeapProjector,
    Projector,
    ResumeProjector,
    ThreadProjector,
    TraceProjector,
    WatchProjector,
)

__all__ = [
    "ALL_COLLECTIONS",
    "PROJECTIONS",
    "SOURCE_OF_TRUTH",
    "INDEXES",
    "IndexSpec",
    "Projector",
    "HeapProjector",
    "ThreadProjector",
    "ResumeProjector",
    "WatchProjector",
    "BillingProjector",
    "TraceProjector",
]
