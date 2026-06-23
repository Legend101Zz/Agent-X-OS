"""The JOURNAL — the append-only episodic source of truth (BLUEPRINT §2, BUILD-KIT §2).

The Journal is the WAL/ledger: every run, effect, outcome, and *manager action* is an event.
Heap / Threads / Résumé are projections built from it (see ``db/``). Appending an event is a single
*document insert* — atomic in MongoDB — which sidesteps multi-document transactions: settlement
writes ONE ``RunSettled`` event carrying the whole fan-out, and the projection builders apply it
idempotently (and can be replayed).

Modelled as a discriminated union on ``kind`` so consumers match exhaustively and mypy checks it.
This is the Phase-1 event set; new kinds are additive (a stop-and-coordinate event for the seam).
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from .base import AgentXModel
from .enums import ApprovalDecision, MaturityLevel, Ring, SyscallStatus, VerificationRung
from .jsontypes import JsonObject
from .memory import Fact
from .trigger import Trigger


class _JournalBase(AgentXModel):
    """Common envelope for every journal event."""

    event_id: str
    seq: int
    """Per-instance monotonic sequence number — the total order of the ledger."""
    ts: datetime
    instance_id: str
    run_id: str | None = None
    """None for type-level / instance-level events that are not tied to a single run."""
    actor: str = "kernel"
    """Who caused the event: "kernel" | "owner:<id>" | "faculty:<name>" | "manager:<id>" | "watch"."""
    idempotency_key: str | None = None
    """Set on effectful events; the journal enforces uniqueness so retries never double-append."""


class RunCreated(_JournalBase):
    kind: Literal["run_created"] = "run_created"
    type_ref: str
    trigger: Trigger


class RunHydrated(_JournalBase):
    """The frozen hydration snapshot was assembled — records WHAT the agent knew, for forever-auditability."""

    kind: Literal["run_hydrated"] = "run_hydrated"
    fact_count: int
    thread_id: str | None = None


class SyscallAttempted(_JournalBase):
    """A faculty requested a syscall (intent). Names WHAT, never HOW (invariant #5)."""

    kind: Literal["syscall_attempted"] = "syscall_attempted"
    syscall: str
    args: JsonObject = Field(default_factory=dict)
    ring_required: Ring


class SyscallSettled(_JournalBase):
    """A syscall completed (or queued to the human-task tail). The audit row for the effect."""

    kind: Literal["syscall_settled"] = "syscall_settled"
    syscall: str
    status: SyscallStatus
    fulfilled_by: str
    """Adapter name, or "human_task" when it landed in the manual queue."""
    maturity_used: MaturityLevel
    output: JsonObject = Field(default_factory=dict)
    """The adapter's SyscallResult.output (e.g. export_ledger's {path, filename, ...}).
    Default {} keeps old rows valid and write-free syscalls cheap."""


class RunParked(_JournalBase):
    """The run became a durable continuation, awaiting a human approval, a webhook, or a watch.

    A human approval is mechanically identical to waiting on a webhook — both are just a parked state.
    """

    kind: Literal["run_parked"] = "run_parked"
    reason: str
    awaiting: Literal["human_approval", "webhook", "watch"]
    required_ring: Ring | None = None


class ApprovalResolved(_JournalBase):
    """An owner/manager resolved a parked approval card (BLUEPRINT §6 — a journaled command)."""

    kind: Literal["approval_resolved"] = "approval_resolved"
    decision: ApprovalDecision
    edited: bool = False
    """True when the human edited the effect — the before/after diff becomes a gold-tier gym case."""


class RunVerified(_JournalBase):
    kind: Literal["run_verified"] = "run_verified"
    rungs_passed: list[VerificationRung] = Field(default_factory=list)


class RunSettled(_JournalBase):
    """The atomic settlement commit (BLUEPRINT §2 step 6) — ONE append = the whole fan-out.

    Carries the claimed facts (each with provenance — invariant #1), the trust delta, the billing
    line, the watches to register, and any spawns. Heap/Résumé/Watch/Billing projections are built
    from this single event, so they can never disagree about what happened.
    """

    kind: Literal["run_settled"] = "run_settled"
    facts: list[Fact] = Field(default_factory=list)
    billing_amount: float | None = None
    trust_delta: int = 0
    watch_ids: list[str] = Field(default_factory=list)
    spawned: list[str] = Field(default_factory=list)


class WatchRegistered(_JournalBase):
    kind: Literal["watch_registered"] = "watch_registered"
    watch_id: str
    condition: str
    deadline: datetime


class WatchFired(_JournalBase):
    """Reality answered (the booking happened / the reply came / silence). The only ungameable rung."""

    kind: Literal["watch_fired"] = "watch_fired"
    watch_id: str
    outcome: str


class DeferredSettled(_JournalBase):
    """The deferred commit when a watch fires: probation facts promote, trust confirms, run becomes a case."""

    kind: Literal["deferred_settled"] = "deferred_settled"
    promoted_fact_ids: list[str] = Field(default_factory=list)
    trust_confirmed: bool = False
    eval_case_id: str | None = None


class ManagerAction(_JournalBase):
    """A control-surface command (approve / set-ring / instantiate / promote / run-swarm).

    Every manager action is itself a journaled event (BLUEPRINT §6): one source of truth, consistent
    by construction. The Operator Agent (§6.1) emits these same events as a gated, privileged user.
    """

    kind: Literal["manager_action"] = "manager_action"
    action: str
    detail: JsonObject = Field(default_factory=dict)


# The append-only event — the SOURCE OF TRUTH. Discriminated on ``kind``.
JournalEvent = Annotated[
    (
        RunCreated
        | RunHydrated
        | SyscallAttempted
        | SyscallSettled
        | RunParked
        | ApprovalResolved
        | RunVerified
        | RunSettled
        | WatchRegistered
        | WatchFired
        | DeferredSettled
        | ManagerAction
    ),
    Field(discriminator="kind"),
]
