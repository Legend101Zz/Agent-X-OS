"""The syscall boundary types (BLUEPRINT §3) — shared because the gateway (kernel) calls adapters (Codex).

Carefully shaped to encode invariant #5: a ``SyscallRequest`` is an INTENT — it names WHAT (a syscall
name + args) and never HOW (no adapter, url, method, or credential field). The gateway decides
fulfillment and injects the credential; the pod/faculty never sees either.
"""

from datetime import datetime

from pydantic import Field

from .base import AgentXModel
from .enums import HealthStatus, MaturityLevel, Ring, RiskClass, RuleDecision, SyscallStatus
from .jsontypes import JsonObject


class SyscallRequest(AgentXModel):
    """A faculty's intent to touch the world. WHAT, never HOW (invariant #5).

    Deliberately has no ``adapter``/``url``/``method``/``credential`` field — fulfillment is the
    gateway's job. ``ring`` is the instance's CURRENT authority, stamped by the gateway; adapters
    must not trust a pod-supplied ring.
    """

    name: str
    """The syscall / intent name, e.g. "draft_email", "lead_research_batch"."""
    args: JsonObject = Field(default_factory=dict)
    instance_id: str
    run_id: str
    idempotency_key: str
    """LLMs retry; the gateway uses this to guarantee an effect happens at most once."""
    ring: Ring
    risk_class: RiskClass | None = None


class ChannelRule(AgentXModel):
    """A per-channel policy the gateway enforces (e.g. WhatsApp 24h window, opt-in required).

    Reserved hook for Phase 5 channels; present so the gateway shape is stable now.
    """

    rule: str
    detail: JsonObject = Field(default_factory=dict)


class GatewayContext(AgentXModel):
    """What the gateway hands to adapters and rule-checks so they can decide — but cannot widen authority."""

    instance_id: str
    run_id: str
    tenant_id: str
    ring: Ring
    now: datetime
    channel_rules: list[ChannelRule] = Field(default_factory=list)


class SyscallResult(AgentXModel):
    """The outcome of a syscall, from whichever rung of the ladder fulfilled it."""

    status: SyscallStatus
    output: JsonObject = Field(default_factory=dict)
    idempotency_key: str
    fulfilled_by: str
    """Adapter name, or "human_task" when the human-task tail handled it."""
    maturity_used: MaturityLevel
    error: str | None = None
    raw: JsonObject | None = None


class VerifyOutcome(AgentXModel):
    """An adapter's self-check that its effect actually landed (the adapter's own ``verify`` rung)."""

    ok: bool
    reason: str = ""
    checks: list[str] = Field(default_factory=list)


class Health(AgentXModel):
    """Adapter health — surfaces the capability registry's "automation roadmap" view (BLUEPRINT §6)."""

    status: HealthStatus
    detail: str = ""
    checked_at: datetime


class SyscallTestCase(AgentXModel):
    """A fixture every adapter ships — feeds health checks and the gym (BLUEPRINT §3 plugin contract)."""

    name: str
    input: JsonObject = Field(default_factory=dict)
    expect_status: SyscallStatus = "ok"
    expect_output_contains: JsonObject = Field(default_factory=dict)


class RuleVerdict(AgentXModel):
    """The deterministic rules-rung decision at the gateway (output of ``RuleCheck``, SEAM 3).

    ``park`` is not a failure — it is the normal path when the instance's ring is below the syscall's
    required ring (the effect waits for a human approval card).
    """

    decision: RuleDecision
    reason: str = ""
    required_ring: Ring | None = None
