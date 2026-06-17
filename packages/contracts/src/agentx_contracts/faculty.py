"""The FACULTY contract (BLUEPRINT §1 and §4.5) — the SDK brick.

A faculty is a harness-agnostic *capability contract*; the harness *realizes* it. The contract
stays swappable (Model D) while each harness is used to its full native capability, governed by one
line: **borrow the muscle, own the moat.**

The ``harness_adapter`` binds a faculty to a specific harness by ENABLING that harness's native
skills (not reimplementing them), then re-points every *effectful* tool to our gateway and treats
the harness's native memory as per-run scratch only. The ``fulfillment_pref`` mirrors the syscall
ladder: prefer the harness's strong native skill → fall back to our own → hybrid.
"""

from typing import Literal

from pydantic import Field

from .base import AgentXModel
from .enums import FulfillmentPreference, HarnessKind
from .verification import Rubric


class RoutingHint(AgentXModel):
    """What execution a faculty wants — consumed by the Type's ExecutionProfile (harness arbitrage)."""

    model: str | None = None
    """Preferred model id, or None to let the ExecutionProfile decide."""
    strong_model: bool = False
    """True when the faculty needs a frontier model (e.g. judgment), False when a cheap one suffices."""
    latency_tolerance: Literal["low", "tolerant"] = "tolerant"
    budget_hint: float | None = None


class HarnessAdapterSpec(AgentXModel):
    """How a faculty binds to a harness (BLUEPRINT §4.5).

    Encodes "borrow the muscle, own the moat": turn on the harness's strong NATIVE skills, but force
    every effectful tool through OUR gateway and keep the harness's memory as scratch only — so the
    pod still holds no credentials and no durable state lives below the adapter line.
    """

    harness: HarnessKind
    native_skills_enabled: list[str] = Field(default_factory=list)
    """Which of the harness's native skills this faculty switches on (e.g. OpenClaw web/MCP skills)."""
    effectful_tools_to_gateway: bool = True
    """ALWAYS true: every tool with a real-world effect is re-pointed to the kernel gateway."""
    memory_mode: Literal["per_run_scratch"] = "per_run_scratch"
    """The harness's native memory is per-run scratch ONLY — never the system of record."""


class Faculty(AgentXModel):
    """A composable capability module — the reusable, compounding brick of a MandateType.

    Faculties are shared: fix ``research`` once and every mandate that links it improves.
    ``memory-craft`` and ``escalation`` are faculties too — writing good memory and failing safely
    are engineered once, reused everywhere. The Phase-1 set is research, judgment, memory-craft,
    escalation (instantiated as data in ``packages/mandate`` — this is just the type).
    """

    name: str
    skill_pack: str
    """Ref to the compiled-prompts artifact (compiler-owned, versioned). Not raw prompt text."""
    tool_manifest: list[str] = Field(default_factory=list)
    """The syscall INTENT names this faculty may request (WHAT it wants — never adapters/HOW).
    Invariant #5: the manifest names intents; fulfillment is the gateway's, not the faculty's."""
    rubrics: list[Rubric] = Field(default_factory=list)
    eval_slice: str
    """Ref to this faculty's slice of the gym (its graded cases)."""
    routing_hint: RoutingHint = Field(default_factory=RoutingHint)
    harness_adapter: HarnessAdapterSpec
    fulfillment_pref: FulfillmentPreference = "prefer_harness_native"


class FacultyBinding(AgentXModel):
    """How a MandateType links a library faculty (by name + version), keeping the library shared."""

    faculty_name: str
    faculty_version: str = "latest"
