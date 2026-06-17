"""Settlement types — the atomic commit fan-out (BLUEPRINT §2 step 6, ARCHITECTURE D4).

``SettlementEvent`` is the in-memory shape the settlement engine produces; it mirrors the
``RunSettled`` journal event (which is the persisted, append-only commit). Memory, trust, billing,
watches, and spawns can never disagree because they all derive from this one event.
"""

from datetime import datetime
from typing import Literal

from pydantic import Field

from .base import AgentXModel
from .enums import Ring
from .jsontypes import JsonObject
from .memory import Fact


class TrustDelta(AgentXModel):
    """A change to an instance's earned authority (drives ring promotion/demotion)."""

    instance_id: str
    delta: int
    new_ring: Ring | None = None
    reason: str


class Watch(AgentXModel):
    """A deferred-verification timer: did it really work within the window? (the reality rung)."""

    id: str
    run_id: str
    instance_id: str
    condition: str
    deadline: datetime
    status: Literal["pending", "fired", "expired"] = "pending"


class BillingLine(AgentXModel):
    """One settlement-written billing line — the atom of every P&L query (BLUEPRINT §6 ECONOMY)."""

    id: str
    run_id: str
    instance_id: str
    amount: float
    currency: str = "INR"
    description: str
    ts: datetime


class SpawnInstruction(AgentXModel):
    """A child run to create at settlement (the composition call; the heap is its return path)."""

    child_type_ref: str
    params: JsonObject = Field(default_factory=dict)
    inherit_authority: bool = False


class ThreadUpdate(AgentXModel):
    """How settlement advances the relational thread for the entity this run touched."""

    entity_id: str
    new_state: str
    appended_history: list[JsonObject] = Field(default_factory=list)


class SettlementEvent(AgentXModel):
    """The one atomic commit — facts (with provenance), trust, billing, watches, spawns, thread.

    INVARIANT #1: claimed ``facts`` are the ONLY way facts reach the heap, and each carries
    provenance — there is no bypass path. The settlement engine appends exactly one ``RunSettled``
    journal event from this; projections are built from that event.
    """

    run_id: str
    instance_id: str
    facts: list[Fact] = Field(default_factory=list)
    trust: TrustDelta | None = None
    billing: BillingLine | None = None
    watches: list[Watch] = Field(default_factory=list)
    spawns: list[SpawnInstruction] = Field(default_factory=list)
    thread_update: ThreadUpdate | None = None
    settled_at: datetime
