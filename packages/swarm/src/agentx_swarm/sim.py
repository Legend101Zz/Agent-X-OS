"""Deterministic simulated syscall adapter for swarm runs."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import cast

from agentx_contracts import (
    Adapter,
    GatewayContext,
    Health,
    JsonObject,
    JsonSchema,
    MaturityLevel,
    Ring,
    SyscallRegistry,
    SyscallRequest,
    SyscallResult,
    SyscallStatus,
    SyscallTestCase,
    TenantAuth,
    VerifyOutcome,
)
from agentx_contracts.security import Credential

from .scenarios import ScenarioPack


class SimAdapter:
    """A no-effect adapter that returns deterministic fixtures for Phase-1 syscalls."""

    name = "sim_adapter"
    category = "sim"
    maturity_level: MaturityLevel = 0
    risk_class = "read"
    required_ring: Ring = "L0"
    tenant_auth: TenantAuth = "manual"
    input_schema: JsonSchema = {"type": "object"}
    output_schema: JsonSchema = {"type": "object"}
    is_terminal_fallback = False

    def __init__(self, scenario_pack: ScenarioPack) -> None:
        self._scenario_pack = scenario_pack
        self.fixtures = [
            SyscallTestCase(name="lead_research_batch", input={"limit": 3}, expect_status="ok"),
            SyscallTestCase(name="read_url", input={"url": "https://example.invalid"}, expect_status="ok"),
            SyscallTestCase(name="draft_email", input={"to": "buyer@example.invalid"}, expect_status="ok"),
            SyscallTestCase(name="send_email", input={"to": "buyer@example.invalid"}, expect_status="ok"),
            SyscallTestCase(
                name="queue_manual_action",
                input={"action": "approve_draft"},
                expect_status="queued_manual",
            ),
            SyscallTestCase(name="mark_outcome", input={"outcome": "settled"}, expect_status="ok"),
        ]

    def can_handle(self, req: SyscallRequest, ctx: GatewayContext) -> bool:
        return req.name in {fixture.name for fixture in self.fixtures} and ctx.ring in {"L0", "L1", "L2"}

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        return await self.dry_run(req)

    async def dry_run(self, req: SyscallRequest) -> SyscallResult:
        output = self._output_for(req)
        status: SyscallStatus = "queued_manual" if req.name == "queue_manual_action" else "ok"
        return SyscallResult(
            status=status,
            output=output,
            idempotency_key=req.idempotency_key,
            fulfilled_by=self.name,
            maturity_used=self.maturity_level,
            raw={"simulated": True, "credential_used": False},
        )

    async def verify(self, result: SyscallResult) -> VerifyOutcome:
        ok = result.status in {"ok", "queued_manual"} and result.fulfilled_by == self.name
        return VerifyOutcome(ok=ok, reason="" if ok else "unexpected simulated result", checks=["deterministic_sim"])

    async def health_check(self) -> Health:
        return Health(status="ok", detail="deterministic simulation fixtures loaded", checked_at=datetime.now(UTC))

    def _output_for(self, req: SyscallRequest) -> JsonObject:
        fingerprint = _fingerprint(req)
        if req.name == "lead_research_batch":
            limit = _positive_int(req.args.get("limit", req.args.get("count")), default=5)
            leads: list[JsonObject] = []
            for case in self._scenario_pack.cases[:limit]:
                leads.append(
                    {
                        "case_id": case.id,
                        "origin": case.origin,
                        "company": case.company,
                        "lead": case.lead,
                        "expected_signals": list(case.expected_signals),
                    }
                )
            return cast(JsonObject, {"effect": "simulated", "fingerprint": fingerprint, "leads": leads})
        if req.name == "read_url":
            return {
                "effect": "simulated",
                "fingerprint": fingerprint,
                "url": str(req.args.get("url", "sim://missing-url")),
                "content": "Synthetic company page with hiring, market, and fit signals.",
            }
        if req.name == "draft_email":
            return {
                "effect": "simulated",
                "fingerprint": fingerprint,
                "draft_mode": True,
                "subject": "Potential fit for your growth workflow",
                "body": "Synthetic draft only. Requires human approval before any external send.",
            }
        if req.name == "send_email":
            # The wind-tunnel NEVER sends a real email: a send_email in sim is a simulated, gated
            # outreach (human approval still parks it before this rung in a live run).
            return {
                "effect": "simulated",
                "fingerprint": fingerprint,
                "simulated_send": True,
                "subject": "Potential fit for your growth workflow",
                "body": "Synthetic outreach — simulated send only; no real email left the wind-tunnel.",
            }
        if req.name == "queue_manual_action":
            return {
                "effect": "simulated",
                "fingerprint": fingerprint,
                "queued": True,
                "action": str(req.args.get("action", "review")),
            }
        if req.name == "mark_outcome":
            return {
                "effect": "simulated",
                "fingerprint": fingerprint,
                "recorded": True,
                "outcome": str(req.args.get("outcome", "unknown")),
            }
        return {"effect": "simulated", "fingerprint": fingerprint, "error": "unsupported syscall"}


class SimRegistry:
    """Registry that binds the deterministic SimAdapter in sim mode."""

    def __init__(self, adapter: Adapter) -> None:
        self._adapter = adapter

    def register(self, adapter: Adapter) -> None:
        self._adapter = adapter

    def adapters(self) -> list[Adapter]:
        return [self._adapter]

    def resolve(self, req: SyscallRequest, ctx: GatewayContext) -> Adapter:
        return self._adapter


def build_sim_registry(scenario_pack: ScenarioPack) -> SyscallRegistry:
    """Return a registry whose single rung is the deterministic SimAdapter."""

    return SimRegistry(SimAdapter(scenario_pack))


def _positive_int(value: object, *, default: int) -> int:
    if isinstance(value, int) and value > 0:
        return value
    return default


def _fingerprint(req: SyscallRequest) -> str:
    payload = req.model_dump(mode="json")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
