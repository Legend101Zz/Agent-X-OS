"""The MANDATE models — the three layers and the seven organs (BLUEPRINT §1, ARCHITECTURE D1/D2).

``MandateType`` (the class, shared) → ``MandateInstance`` (the object, private = the moat) →
``MandateRun`` (the stack frame, born per trigger, dies at settlement). ``InstanceBinding`` is the
minimal binding ``RunInvoker`` needs to start a run (SEAM 2).
"""

from datetime import datetime

from pydantic import Field

from .base import AgentXModel
from .enums import HarnessKind, Ring, RunState, VerificationRung
from .faculty import FacultyBinding
from .journal import JournalEvent
from .jsontypes import JsonObject, JsonValue
from .memory import Fact, Thread
from .trigger import Trigger
from .verification import Rubric, Trace

_DEFAULT_VERIFICATION_LADDER: list[VerificationRung] = ["rules", "judge", "human", "reality"]


# --- Organ 1: Charter ------------------------------------------------------------------
class Condition(AgentXModel):
    """A charter clause. Discipline: if a clause can't be checked, it can't be in the charter.

    Every condition names the verification ``rung`` that checks it, so "done" is always mechanical.
    Unverifiable intent belongs in the domain pack as guidance, not here as a promise.
    """

    id: str
    description: str
    rung: VerificationRung
    expr: str | None = None
    """Optional machine-checkable expression for the deterministic rules rung."""


class Charter(AgentXModel):
    """What "done" means, in checkable terms — Design-by-Contract (pre/path/post conditions)."""

    goal: str
    preconditions: list[Condition] = Field(default_factory=list)
    pathconditions: list[Condition] = Field(default_factory=list)
    postconditions: list[Condition] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    target: JsonObject = Field(default_factory=dict)
    """Typed-JSON goal schema: quantity / window / budget / ICP, etc."""


# --- Organ 3: Domain pack --------------------------------------------------------------
class DomainPackRef(AgentXModel):
    """Reference to the versioned domain pack (vertical playbook + distilled cross-customer priors).

    Priors are the ONLY place cross-customer learning re-enters a mandate — as patterns, never as
    facts traceable to a business (invariant #3).
    """

    name: str
    version: str


# --- Organ 4: Verification -------------------------------------------------------------
class VerificationSuite(AgentXModel):
    """The commit-time type system: a ladder of checkers, cheapest rung first."""

    ladder: list[VerificationRung] = Field(
        default_factory=lambda: list(_DEFAULT_VERIFICATION_LADDER)
    )
    rules: list[str] = Field(default_factory=list)
    """Refs to deterministic rule checks (the rules rung)."""
    rubrics: list[Rubric] = Field(default_factory=list)


# --- Organ 5: Settlement ---------------------------------------------------------------
class SpawnRule(AgentXModel):
    """A declarative composition edge: on a settled condition, spawn a child run (the function call)."""

    on_condition: str
    child_type_ref: str
    params: JsonObject = Field(default_factory=dict)
    inherit_authority: bool = False


class SettlementRules(AgentXModel):
    """What happens at commit, declaratively (BLUEPRINT §2 step 6)."""

    fact_commit_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    """Probationary confidence for agent-inferred facts entering the heap."""
    trust_on_success: int = 1
    trust_on_failure: int = -1
    watch_window_hours: int = 72
    spawn_rules: list[SpawnRule] = Field(default_factory=list)
    billing_per_run: float | None = None


# --- Organ 7: Execution profile --------------------------------------------------------
class RoutingEntry(AgentXModel):
    """Per-faculty routing: harness adapter × model × budget (harness arbitrage made concrete)."""

    faculty_name: str
    harness: HarnessKind
    model: str
    budget: float | None = None


class ExecutionProfile(AgentXModel):
    routing: list[RoutingEntry] = Field(default_factory=list)


# --- The TYPE (the class) --------------------------------------------------------------
class MandateType(AgentXModel):
    """The class — shared by every customer, almost open-source. The seven organs (BLUEPRINT §1)."""

    id: str
    name: str
    version: str
    """Semver — versions ship like software releases (changelog, rollback)."""
    charter: Charter
    faculties: list[FacultyBinding] = Field(default_factory=list)
    domain_pack: DomainPackRef
    verification: VerificationSuite
    settlement: SettlementRules
    gym_ref: str | None = None
    execution: ExecutionProfile = Field(default_factory=ExecutionProfile)
    service_ports: list[str] = Field(default_factory=list)
    """What this type produces for the internal market (e.g. "qualified_leads"). Reserved post-Phase-1."""


# --- The INSTANCE (the object — the moat) ----------------------------------------------
class ChannelBinding(AgentXModel):
    """Per-instance sender of record (invariant #8): channel identity is never shared across instances.

    Reserved — relevant to Phase 5 channels; modelled now so we don't design it away.
    """

    channel: str
    sender_identity: str
    opt_in: bool = False


class Override(AgentXModel):
    """An instance-level learned delta (e.g. "this owner signs off casually; never use 'Dear'")."""

    key: str
    value: JsonValue


class MandateInstance(AgentXModel):
    """The object — private to one business. The moat lives here."""

    id: str
    type_ref: str
    """Which type+version this instance runs, e.g. "lead-finder@0.1.0"."""
    customer_id: str
    ring: Ring = "L0"
    heap_region_id: str
    channel_binding: ChannelBinding | None = None
    overrides: list[Override] = Field(default_factory=list)


class InstanceBinding(AgentXModel):
    """The minimal binding a run needs to start (SEAM 2: ``RunInvoker.invoke(instance=...)``).

    A projection of ``MandateInstance`` carrying only what hydration + the gateway require. The swarm
    constructs one of these to drive a sim run through the SAME kernel loop.
    """

    instance_id: str
    type_ref: str
    ring: Ring
    heap_region_id: str
    channel_binding: ChannelBinding | None = None
    overrides: list[Override] = Field(default_factory=list)


# --- The RUN (the stack frame) ---------------------------------------------------------
class HydrationSnapshot(AgentXModel):
    """The frozen working set the harness sees (BLUEPRINT §2 — the read side).

    Assembled at run start and frozen onto the run, so you can forever answer "what did the agent
    know when it said that?" The harness is stateless; this snapshot is how it "knows what to do."
    """

    facts: list[Fact] = Field(default_factory=list)
    """Relevant heap facts, ranked relevance × confidence × recency."""
    thread: Thread | None = None
    recent_journal: list[JournalEvent] = Field(default_factory=list)
    skill_pack_refs: list[str] = Field(default_factory=list)
    domain_pack: DomainPackRef | None = None
    frozen_at: datetime


class MandateRun(AgentXModel):
    """The stack frame — a durable continuation that can park for days, then dies at settlement.

    Holds nothing durable of its own: at settlement everything either commits to the Instance/Type
    layers or evaporates. The pod can be destroyed mid-run and resumed from this row (Temporal-style).
    """

    id: str
    instance_id: str
    type_ref: str
    trigger: Trigger
    state: RunState = "created"
    hydration: HydrationSnapshot | None = None
    trace: Trace | None = None
    claimed_facts: list[Fact] = Field(default_factory=list)
    scratchpad: JsonObject = Field(default_factory=dict)
    parked_reason: str | None = None
    created_at: datetime
    settled_at: datetime | None = None
