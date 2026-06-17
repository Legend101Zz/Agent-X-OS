"""The result of a run (SEAM 2 — ``RunInvoker.invoke`` returns ``RunResult``).

This is what the swarm (driving sim runs) and the kernel (driving live runs) both receive. A run can
end ``settled`` (committed), ``parked`` (awaiting a human/webhook/watch), or ``crashed`` (escalated).
"""

from pydantic import Field

from .base import AgentXModel
from .enums import RunState
from .jsontypes import JsonObject
from .memory import Fact
from .settlement import SettlementEvent
from .verification import Scorecard, Trace


class ParkInfo(AgentXModel):
    """Why a run parked and what it is waiting for — the L0/L1 approval card surface (BLUEPRINT §6)."""

    reason: str
    awaiting: str
    """"human_approval" | "webhook" | "watch"."""
    required_ring: str | None = None
    approval_card: JsonObject = Field(default_factory=dict)
    """The card shown to the owner (draft, options, context). Typed JSON, never an untyped dict."""


class RunResult(AgentXModel):
    """The terminal output of a run loop (SEAM 2).

    ``state`` is the terminal run state. ``settlement`` is present iff the run settled; ``park`` is
    present iff it parked; ``scorecard`` is present when a judge graded it (always in sim).
    """

    run_id: str
    state: RunState
    output: JsonObject = Field(default_factory=dict)
    trace: Trace
    claimed_facts: list[Fact] = Field(default_factory=list)
    settlement: SettlementEvent | None = None
    scorecard: Scorecard | None = None
    park: ParkInfo | None = None
