"""The FACULTIES-FRAMEWORK harness seam (BLUEPRINT §1, §4.5) — "borrow the muscle, own the moat".

A faculty's reasoning runs on a *harness*. The harness is a swappable CPU below the adapter line
(Model D): the kernel run-loop drives it, feeds it the frozen hydration snapshot + skill_pack, lets
it use its native skills, but RE-POINTS every effectful proposal to the kernel gateway and keeps the
harness's own memory as per-run scratch only. The pod therefore holds no credentials and no durable
state — and this module imports only the pure ``agentx_contracts`` seam (invariant #2).

IMPORT DISCIPLINE (invariant #2, enforced by ``.importlinter``): ``agentx_mandate`` must import from
contracts SUBMODULES (``agentx_contracts.memory`` etc.), NEVER the ``agentx_contracts`` package root —
the root's ``__init__`` re-exports ``protocols``, which imports ``security`` (Credential), so a root
import would transitively reach a credential-bearing module in the import graph.

Two harnesses ship the contract:
  - ``OwnHarness`` (``HarnessKind="own"``) — a deterministic TEST DOUBLE with canned/recorded reasoning;
    powers ``mode="sim"`` + the seam proof, fast and reproducible, never spins up a live model.
  - the live ``hermes`` harness (driving Minimax) lives on the KERNEL side (it needs config/creds) and
    implements the same ``HarnessRunner`` Protocol.

Interaction model: the harness yields one ``HarnessAction`` per ``step``. READ intents are fulfilled
NATIVELY by the harness (in sim, canned) and never surface; only effectful proposals surface so the
run-loop can ring-check + journal them. A session is a durable continuation: deterministic, so it can
be rebuilt from the frozen snapshot and resumed at a saved ``cursor`` (Temporal-style replay).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from agentx_contracts.base import AgentXModel
from agentx_contracts.enums import HarnessKind, Ring
from agentx_contracts.faculty import Faculty
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.mandate import HydrationSnapshot
from agentx_contracts.memory import Fact
from agentx_contracts.syscall import SyscallRequest, SyscallResult
from pydantic import Field


# --- The actions a harness proposes each step ------------------------------------------
class Think(AgentXModel):
    """A reasoning step with no real-world effect — recorded onto the run trace."""

    summary: str
    detail: JsonObject = Field(default_factory=dict)


class Call(AgentXModel):
    """A proposal to touch the world: a syscall INTENT (WHAT, never HOW — invariant #5).

    Effectful calls surface to the run-loop, which routes them through the gateway. READ-class calls
    (``request.risk_class == "read"``) are fulfilled natively by the harness in sim and do not surface.
    """

    request: SyscallRequest


class Claim(AgentXModel):
    """A proposal of facts to commit (the ``memory-craft`` faculty). Verified before they reach the heap."""

    facts: list[Fact]


class Escalate(AgentXModel):
    """Crash upward (the ``escalation`` faculty / a supervised failure) with full context."""

    reason: str
    detail: JsonObject = Field(default_factory=dict)


class Finish(AgentXModel):
    """The harness is done reasoning; the run proceeds to verify + settle."""

    output: JsonObject = Field(default_factory=dict)


HarnessAction = Think | Call | Claim | Escalate | Finish


# --- What a faculty sees when it reasons -----------------------------------------------
@dataclass
class FacultyContext:
    """The mutable working context a faculty reasons over (its slice of the run).

    ``scratchpad`` is the harness's per-run scratch memory — faculties hand results to one another
    through it (research caches leads; judgment scores them; memory-craft turns them into facts). It is
    NEVER the system of record (that is the kernel's heap); it evaporates at settlement.
    """

    snapshot: HydrationSnapshot
    target: JsonObject
    scratchpad: dict[str, object]
    instance_id: str
    run_id: str
    ring: Ring
    now: datetime
    error: str | None = None


# --- The harness Protocols (the kernel run-loop depends on these) ----------------------
@runtime_checkable
class HarnessSession(Protocol):
    """One run's reasoning session. ``step`` returns the next action; the loop feeds back observations."""

    cursor: int

    async def step(self, observation: SyscallResult | None) -> HarnessAction: ...


@runtime_checkable
class HarnessRunner(Protocol):
    """A bound harness (Hermes / own). The run-loop builds the per-run ``context`` and calls ``start``.

    ``cursor`` resumes a parked run: a deterministic harness rebuilds its trajectory from the frozen
    snapshot in ``context`` and fast-forwards to ``cursor`` (the continuation pointer).
    """

    name: HarnessKind

    def start(
        self,
        *,
        context: FacultyContext,
        faculties: list[Faculty],
        cursor: int = 0,
    ) -> HarnessSession: ...


Playbook = Callable[[FacultyContext, list[Faculty]], Iterable[HarnessAction]]
"""Composes faculty proposals into the ordered trajectory for a mandate (e.g. the lead-finder).

A playbook may be a plain ``list`` or a GENERATOR. As a generator it is driven LAZILY (one ``yield`` per
``step``) over the shared-by-reference ``FacultyContext`` — so a read Call it yields suspends until the
run-loop fulfils it (mutating ``ctx.scratchpad``), and the next faculty's proposal sees the result.
"""


def _surface(actions: list[HarnessAction]) -> list[HarnessAction]:
    """Drop READ-class calls (fulfilled natively in sim); keep everything the run-loop must see."""
    return [a for a in actions if not (isinstance(a, Call) and a.request.risk_class == "read")]


@dataclass
class OwnHarnessSession:
    """A deterministic session over a precomputed action list. ``cursor`` is the continuation pointer.

    Used for ``recorded=`` trajectories: reads were already dropped by ``_surface`` (the canned double
    "fulfils" them by omission), so this session only ever replays surfaced actions.
    """

    actions: list[HarnessAction]
    cursor: int = 0

    async def step(self, observation: SyscallResult | None) -> HarnessAction:
        # The canned double is deterministic: it ignores the observation (a live harness would use it).
        if self.cursor >= len(self.actions):
            return Finish()
        action = self.actions[self.cursor]
        self.cursor += 1
        return action


@dataclass
class PlaybookHarnessSession:
    """A deterministic session that drives a playbook GENERATOR lazily (one ``yield`` per ``step``).

    Unlike ``OwnHarnessSession``, reads are NOT surfaced-away: a read Call the playbook yields reaches the
    run-loop, which fulfils it (sim-native / via the gateway) and mutates the shared ``ctx`` before the
    generator is resumed. ``cursor`` counts surfaced actions for Temporal-style resume (Step B).
    """

    _actions: Iterator[HarnessAction]
    cursor: int = 0

    async def step(self, observation: SyscallResult | None) -> HarnessAction:
        # Deterministic double: ignores the observation; the generator re-reads the shared ctx instead.
        action = next(self._actions, None)
        if action is None:
            return Finish()
        self.cursor += 1
        return action


class OwnHarness:
    """``HarnessKind="own"`` — the deterministic test double.

    Construct with ``recorded`` (an explicit action list) for unit tests, or with a ``playbook`` that
    composes the faculties' proposals for a real mandate trajectory.
    """

    name: HarnessKind = "own"

    def __init__(
        self,
        *,
        recorded: list[HarnessAction] | None = None,
        playbook: Playbook | None = None,
    ) -> None:
        if (recorded is None) == (playbook is None):
            raise ValueError("OwnHarness needs exactly one of `recorded` or `playbook`")
        self._recorded = recorded
        self._playbook = playbook

    def start(
        self,
        *,
        context: FacultyContext,
        faculties: list[Faculty],
        cursor: int = 0,
    ) -> HarnessSession:
        if self._recorded is not None:
            # recorded trajectory: reads are dropped (fulfilled by omission), replayed from a fixed list.
            return OwnHarnessSession(actions=_surface(self._recorded), cursor=cursor)
        assert self._playbook is not None
        # playbook trajectory: stepped lazily; reads surface to the run-loop for native/gateway fulfilment.
        actions = iter(self._playbook(context, faculties))
        for _ in range(cursor):
            next(actions, None)  # fast-forward for resume (Step B); deterministic replay re-fulfils reads
        return PlaybookHarnessSession(_actions=actions, cursor=cursor)
