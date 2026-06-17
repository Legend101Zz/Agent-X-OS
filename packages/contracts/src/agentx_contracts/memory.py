"""The MEMORY layer types (BLUEPRINT §1/§2).

The harness remembers nothing across runs; continuity is the kernel's job. Memory is four
per-instance stores — three of them modelled here (Heap=semantic ``Fact``, relational ``Thread``,
performance ``Resume``); the fourth, the episodic Journal, is the append-only source of truth in
``journal.py``. Heap/Threads/Résumé are *projections* built from the Journal (see ``db/``).

Invariants encoded here:
- **#1 No fact without a commit:** a ``Fact`` cannot exist without ``provenance`` + ``source``;
  committed facts are only ever produced by settlement (projected from a ``RunSettled`` journal event).
- **#3 No raw fact crosses customers:** every ``Fact``/``Thread``/``Resume`` is stamped with
  ``instance_id`` — the heap region owner. Facts never travel between instances.
"""

from datetime import datetime

from pydantic import Field

from .base import AgentXModel
from .enums import FactSource, FactStatus, Ring
from .jsontypes import JsonObject


class Provenance(AgentXModel):
    """Where a fact came from — the audit trail that makes "no fact without a commit" real."""

    run_id: str
    """The run that claimed or observed this fact."""
    evidence: list[str] = Field(default_factory=list)
    """Refs that justify the fact: syscall-trace ids, source URLs, owner-message ids."""
    note: str | None = None
    """Optional human-readable note (e.g. "owner correction at 14:05")."""


class Fact(AgentXModel):
    """A HEAP fact — semantic memory, private to one instance (BLUEPRINT §2).

    A subject–predicate–object triple with confidence, provenance, source, and decay. Facts enter
    the heap on ``probation`` (typically ``agent-inferred`` at low confidence) and are promoted or
    retired by reality via the deferred-settlement watch.
    """

    id: str
    instance_id: str
    """The heap region owner. Facts NEVER cross instances (invariant #3)."""
    subject: str
    predicate: str
    object: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: FactSource
    provenance: Provenance
    status: FactStatus = "probation"
    decay_at: datetime | None = None
    """GC horizon: episodic facts expire; tenured policy facts set ``None``."""
    created_at: datetime
    updated_at: datetime | None = None


class Thread(AgentXModel):
    """Relational memory — per-entity/conversation state ("where we are with THIS lead").

    Inter-mandate communication is the heap, not a message channel; the Thread tracks the live
    state of a single counterparty (lead, patient, conversation).
    """

    id: str
    instance_id: str
    entity_id: str
    """The counterparty this thread is about (lead/patient/conversation id)."""
    state: str
    """Where the relationship stands, e.g. "messaged twice, asked price, awaiting reply"."""
    history: list[JsonObject] = Field(default_factory=list)
    """Ordered, typed turns/events for this entity (typed JSON, never an untyped dict)."""
    updated_at: datetime


class Resume(AgentXModel):
    """Performance memory — the verified track record this instance has EARNED.

    Drives the trust ladder (ring promotion/demotion) and, later, market awards. Non-portable
    earned state: "your agent runs at L2 here, earned over 14 months" is a row here.
    """

    instance_id: str
    ring: Ring = "L0"
    success_rates: dict[str, float] = Field(default_factory=dict)
    """Verified success rate per effect/outcome class (e.g. {"send_message": 0.97})."""
    counts: dict[str, int] = Field(default_factory=dict)
    """Volume per outcome class (e.g. {"delivered": 430, "accepted": 306})."""
    streak: int = 0
    """Consecutive clean actions toward the next promotion proposal."""
    updated_at: datetime
