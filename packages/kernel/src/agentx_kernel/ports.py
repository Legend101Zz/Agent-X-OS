"""Kernel storage PORTS — the seam between kernel logic and persistence.

The run-loop, gateway, projections, and settlement all depend on these Protocols, never on a concrete
driver. That is what lets the SAME kernel code run against:
  - ``stores.memory`` (in-memory) — fast, deterministic unit tests + ``mode="sim"`` runs, no Mongo;
  - ``stores.mongo`` (PyMongo ``AsyncMongoClient``) — the live kernel.

Keeping persistence behind a port also keeps ``agentx_mandate`` pure: mandate computes over data the
kernel reads through these ports and never touches a store itself (invariant #2).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agentx_contracts import JournalEvent
from agentx_contracts.security import Credential

from .receipts import SyscallReceipt


@runtime_checkable
class JournalStore(Protocol):
    """The append-only event store (the source of truth). Append assigns order + enforces idempotency."""

    async def append(self, event: JournalEvent) -> JournalEvent:
        """Append one event. Assigns a monotonic per-instance ``seq`` and returns the stamped event.

        Raises ``DuplicateIdempotencyKey`` if ``event.idempotency_key`` is set and already present
        (so a retried effect never double-appends).
        """
        ...

    async def read_instance(self, instance_id: str) -> list[JournalEvent]:
        """All events for an instance, ordered by ``seq`` (the ledger's total order)."""
        ...

    async def read_run(self, run_id: str) -> list[JournalEvent]:
        """All events for a single run, in ``seq`` order."""
        ...

    async def max_seq(self, instance_id: str) -> int:
        """The highest assigned ``seq`` for an instance (0 if none) — the head of the ledger."""
        ...


@runtime_checkable
class ProjectionStore(Protocol):
    """A key-addressed document store for the projections built from the journal.

    Projections are derived state (heap_fact / thread / resume / watch / billing_line / syscall_trace);
    every write is an idempotent upsert keyed by a deterministic id so replaying the journal converges.
    """

    async def upsert(self, collection: str, doc_id: str, document: dict[str, object]) -> None:
        """Insert or replace the document with id ``doc_id`` in ``collection`` (idempotent)."""
        ...

    async def get(self, collection: str, doc_id: str) -> dict[str, object] | None:
        """Fetch one document by id, or ``None``."""
        ...

    async def find(self, collection: str, query: dict[str, object]) -> list[dict[str, object]]:
        """All documents in ``collection`` matching an equality ``query`` (Phase-1: equality only)."""
        ...


@runtime_checkable
class SyscallReceiptStore(Protocol):
    """Durable result sidecar for payload-faithful syscall replay.

    The frozen Phase-1 ``SyscallSettled`` event records status and fulfillment metadata but not the
    provider payload. Receipts preserve that payload under the same globally unique idempotency key.
    """

    async def save(self, receipt: SyscallReceipt) -> None:
        """Persist a receipt idempotently; reject a conflicting request for the same key."""
        ...

    async def get(self, idempotency_key: str) -> SyscallReceipt | None:
        """Fetch the receipt for a globally unique idempotency key."""
        ...


@runtime_checkable
class Vault(Protocol):
    """The credential-injection POINT (invariant #2). The gateway asks the vault for a credential at
    call time and hands it ONLY to ``Adapter.execute`` — it never enters a pod, snapshot, or journal.

    Phase-1 is a stub: it returns a manual/empty ``Credential`` (or ``None`` for the human tail).
    """

    async def get(self, ref: str, tenant_id: str) -> Credential | None:
        """Resolve a non-secret vault ``ref`` for a tenant into an injectable ``Credential`` (or None)."""
        ...
