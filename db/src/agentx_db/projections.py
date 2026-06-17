"""Projection-builder Protocols (kernel implements; Session B).

Event sourcing: the kernel applies each ``JournalEvent`` to the projection collections. These are
KERNEL-ONLY interfaces (Codex's lanes never build projections), so they live here in ``db/`` rather
than in the cross-lane ``agentx_contracts`` seam. Each projector is idempotent and replayable —
``rebuild`` reconstructs a projection for an instance from the journal alone.
"""

from typing import Protocol, runtime_checkable

from agentx_contracts import JournalEvent


@runtime_checkable
class Projector(Protocol):
    """Base projection builder: fold journal events into one projection collection."""

    target_collection: str

    async def apply(self, event: JournalEvent) -> None:
        """Apply a single event to the projection (idempotent — safe to replay)."""
        ...

    async def rebuild(self, instance_id: str) -> None:
        """Rebuild this projection for one instance by replaying its journal from seq 0."""
        ...


@runtime_checkable
class HeapProjector(Projector, Protocol):
    """journal (RunSettled/DeferredSettled) → ``heap_fact``. Commits facts with provenance (invariant #1)."""


@runtime_checkable
class ThreadProjector(Projector, Protocol):
    """journal → ``thread``. Advances per-entity relational state."""


@runtime_checkable
class ResumeProjector(Projector, Protocol):
    """journal (trust deltas) → ``resume``. Maintains ring + verified success rates."""


@runtime_checkable
class WatchProjector(Projector, Protocol):
    """journal (WatchRegistered/WatchFired) → ``watch``. Drives deferred (reality-rung) settlement."""


@runtime_checkable
class BillingProjector(Projector, Protocol):
    """journal (RunSettled) → ``billing_line``. The atom of every P&L query."""


@runtime_checkable
class TraceProjector(Projector, Protocol):
    """journal (Syscall* events) → ``syscall_trace``. The auditable effect ledger per run."""
