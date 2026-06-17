"""THE SEAMS — ``typing.Protocol`` interfaces both lanes build against (BUILD-KIT §3).

Three boundaries, ownership noted on each:
- SEAM 1 — the syscall boundary: ``Adapter`` + ``SyscallRegistry``. Codex IMPLEMENTS; the kernel
  gateway CALLS. The human-task queue is the tail of every ladder (invariant #5), made structural by
  ``Adapter.is_terminal_fallback`` and the ``SyscallRegistry.resolve`` contract.
- SEAM 2 — the run boundary: ``RunInvoker`` with ``mode: "live" | "sim"``. The kernel IMPLEMENTS;
  the swarm CALLS — the swarm runs ON the kernel, not beside it.
- SEAM 3 — pluggable verification rungs: ``Judge`` (Codex, promptfoo subprocess) and ``RuleCheck``
  (kernel, deterministic).

Signatures follow BUILD-KIT §3 verbatim. Two additions beyond the kit's sketch are marked
``[SEAM EXTENSION]`` with rationale: ``Adapter.is_terminal_fallback`` and the ``SyscallRegistry``
protocol (the kit's split assigns "fulfillment ladder resolution" to Codex; the gateway calls it).
These are part of the frozen seam — changing them is a stop-and-coordinate event.
"""

from typing import Protocol, runtime_checkable

from .enums import MaturityLevel, Ring, RunMode, TenantAuth
from .jsontypes import JsonSchema
from .mandate import InstanceBinding, MandateType
from .run import RunResult
from .security import Credential
from .syscall import (
    GatewayContext,
    Health,
    RuleVerdict,
    SyscallRequest,
    SyscallResult,
    SyscallTestCase,
    VerifyOutcome,
)
from .trigger import Trigger
from .verification import Rubric, Scorecard, Trace


@runtime_checkable
class Adapter(Protocol):
    """SEAM 1 — a syscall fulfillment plugin. Codex implements; the kernel gateway selects and calls it.

    Each adapter is one rung of the fulfillment ladder for one (or more) syscall intents. The gateway
    owns ring/idempotency/channel-rules/credential-injection/journaling; the adapter is a pure
    actuator (invariant: adapters are actuators, not brains — no autonomous decision loop).
    """

    name: str
    category: str
    maturity_level: MaturityLevel
    risk_class: str
    required_ring: Ring
    tenant_auth: TenantAuth
    input_schema: JsonSchema
    output_schema: JsonSchema
    fixtures: list[SyscallTestCase]
    is_terminal_fallback: bool
    """[SEAM EXTENSION] True for EXACTLY the HumanTaskAdapter — the guaranteed tail of every ladder, so
    nothing is ever "unimplemented" (invariant #5). All real adapters leave this False."""

    def can_handle(self, req: SyscallRequest, ctx: GatewayContext) -> bool:
        """True if this adapter can fulfill the request now. The terminal fallback always returns True."""
        ...

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        """Perform the effect. ``cred`` is injected by the gateway (None for the manual/human path).

        This signature is the ONLY place a ``Credential`` crosses the seam — invariant #2: the pod
        never holds it; the gateway injects it here, at call time.
        """
        ...

    async def dry_run(self, req: SyscallRequest) -> SyscallResult:
        """Simulate the effect without touching reality (used by the swarm and pre-flight checks)."""
        ...

    async def verify(self, result: SyscallResult) -> VerifyOutcome:
        """The adapter's own check that the effect actually landed."""
        ...

    async def health_check(self) -> Health:
        """Liveness/quality probe surfaced in the capability registry (the automation roadmap)."""
        ...


@runtime_checkable
class SyscallRegistry(Protocol):
    """SEAM 1 (ladder resolution) — Codex implements; the kernel gateway calls. [SEAM EXTENSION]

    Owns "first capable adapter on the ladder" selection. The gateway delegates selection here, then
    applies its own policy (ring/idempotency/cred/journal) around the chosen adapter.
    """

    def register(self, adapter: Adapter) -> None:
        """Add an adapter to the ladder for its syscall category."""
        ...

    def adapters(self) -> list[Adapter]:
        """All registered adapters (for health dashboards / the capability registry)."""
        ...

    def resolve(self, req: SyscallRequest, ctx: GatewayContext) -> Adapter:
        """Return the highest-rung adapter whose ``can_handle`` is True for this request.

        MUST NOT raise for an unknown syscall and MUST NOT return None: every ladder terminates in a
        terminal-fallback adapter (the HumanTaskAdapter, ``is_terminal_fallback=True``), so a request
        is never "unimplemented". This is invariant #5 made structural.
        """
        ...


@runtime_checkable
class RunInvoker(Protocol):
    """SEAM 2 — the run boundary. The kernel implements; the swarm calls. The swarm runs ON the kernel."""

    async def invoke(
        self,
        *,
        mandate: MandateType,
        instance: InstanceBinding,
        trigger: Trigger,
        mode: RunMode,
    ) -> RunResult:
        """Run the mandate's full loop: hydrate → think → syscall → verify → settle.

        ``mode="sim"`` binds SimAdapters in place of live ones (a ``SimAdapter`` is just another rung
        on the ladder, sitting where the human-task queue would). The loop does NOT branch on mode
        beyond which adapter registry it resolves through — so the swarm tests EXACTLY what live runs,
        not a look-alike. ``mode="live"`` touches real customers/effects.
        """
        ...


@runtime_checkable
class Judge(Protocol):
    """SEAM 3 — the judge rung. Codex implements via a promptfoo subprocess."""

    async def grade(self, trace: Trace, rubric: Rubric) -> Scorecard:
        """Score a run's trace against a rubric. The returned ``Scorecard.origin`` gates promotion (#7)."""
        ...


@runtime_checkable
class RuleCheck(Protocol):
    """SEAM 3 — the rules rung. The kernel implements it deterministically (never an LLM — invariant #4)."""

    def check(self, req: SyscallRequest, ctx: GatewayContext) -> RuleVerdict:
        """Deterministically decide allow / park / deny for a syscall request at the gateway."""
        ...
