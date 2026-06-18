"""K5 syscall gateway.

The gateway is the security boundary around every effect: deterministic ring policy first, then
idempotency, channel rules, adapter resolution, credential injection, execution, and journaling.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from agentx_contracts.enums import Ring, RiskClass
from agentx_contracts.journal import RunParked, SyscallAttempted, SyscallSettled
from agentx_contracts.protocols import SyscallRegistry
from agentx_contracts.syscall import GatewayContext, RuleVerdict, SyscallRequest, SyscallResult

from .errors import IdempotencyRequestConflict, MissingSyscallReceipt
from .ports import JournalStore, SyscallReceiptStore, Vault
from .receipts import SyscallReceipt
from .stores.memory import InMemorySyscallReceiptStore
from .verifier import HumanApprovalGate


@dataclass(frozen=True)
class SyscallPolicy:
    required_ring: Ring
    risk_class: RiskClass


@dataclass(frozen=True)
class GatewayOutcome:
    result: SyscallResult | None = None
    parked: RunParked | None = None
    attempted: SyscallAttempted | None = None
    settled: SyscallSettled | None = None


ChannelRuleHook = Callable[[SyscallRequest, GatewayContext], RuleVerdict]

_POLICY: dict[str, SyscallPolicy] = {
    "lead_research_batch": SyscallPolicy(required_ring="L0", risk_class="read"),
    "read_url": SyscallPolicy(required_ring="L0", risk_class="read"),
    "score_lead": SyscallPolicy(required_ring="L0", risk_class="read"),
    "queue_manual_action": SyscallPolicy(required_ring="L0", risk_class="read"),
    "mark_outcome": SyscallPolicy(required_ring="L1", risk_class="reversible_write"),
    "draft_email": SyscallPolicy(required_ring="L2", risk_class="external_message"),
}
_RING_ORDER: dict[Ring, int] = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}


def policy_for(intent: str) -> SyscallPolicy:
    return _POLICY.get(intent, SyscallPolicy(required_ring="L0", risk_class="read"))


def _allow_channel(_req: SyscallRequest, _ctx: GatewayContext) -> RuleVerdict:
    return RuleVerdict(decision="allow")


class Gateway:
    """Executes syscall intents through deterministic kernel policy and injected adapters."""

    def __init__(
        self,
        *,
        journal: JournalStore,
        vault: Vault,
        registry: SyscallRegistry | None,
        receipts: SyscallReceiptStore | None = None,
        channel_rule: ChannelRuleHook | None = None,
    ) -> None:
        self._journal = journal
        self._vault = vault
        self._registry = registry
        self._receipts = receipts or InMemorySyscallReceiptStore()
        self._channel_rule = channel_rule or _allow_channel
        self._approval_gate = HumanApprovalGate(journal)

    async def invoke(self, req: SyscallRequest, ctx: GatewayContext) -> GatewayOutcome:
        policy = policy_for(req.name)
        stamped = req.model_copy(update={"ring": ctx.ring, "risk_class": policy.risk_class})

        prior = await self._prior_outcome(stamped, ctx)
        if prior is not None:
            return prior

        attempted = await self._ensure_attempt(stamped, policy, ctx)

        if _RING_ORDER[ctx.ring] < _RING_ORDER[policy.required_ring]:
            return await self._park(
                instance_id=ctx.instance_id,
                run_id=ctx.run_id,
                reason=f"{req.name} requires {policy.required_ring}",
                required_ring=policy.required_ring,
                ctx=ctx,
                attempted=attempted,
            )

        channel_verdict = self._channel_rule(stamped, ctx)
        if channel_verdict.decision == "park":
            return await self._park(
                instance_id=ctx.instance_id,
                run_id=ctx.run_id,
                reason=channel_verdict.reason or "channel rule parked syscall",
                required_ring=channel_verdict.required_ring,
                ctx=ctx,
                attempted=attempted,
            )
        if channel_verdict.decision == "deny":
            return GatewayOutcome(
                result=SyscallResult(
                    status="error",
                    output={},
                    idempotency_key=stamped.idempotency_key,
                    fulfilled_by="gateway_policy",
                    maturity_used=0,
                    error=channel_verdict.reason or "channel rule denied syscall",
                ),
                attempted=attempted,
            )

        if self._registry is None:
            return await self._park(
                instance_id=ctx.instance_id,
                run_id=ctx.run_id,
                reason="no syscall registry available",
                required_ring=None,
                ctx=ctx,
                attempted=attempted,
            )

        adapter = self._registry.resolve(stamped, ctx)
        try:
            credential = await self._vault.get(
                ref=f"vault://{ctx.tenant_id}/{adapter.name}", tenant_id=ctx.tenant_id
            )
            result = await adapter.execute(stamped, credential)
        except Exception as exc:  # noqa: BLE001 — the gateway is the boundary: an adapter/credential
            # failure (e.g. bad LLM-supplied args) must become an error result, never crash the kernel.
            result = SyscallResult(
                status="error",
                output={},
                idempotency_key=stamped.idempotency_key,
                fulfilled_by=adapter.name,
                maturity_used=0,
                error=f"{type(exc).__name__}: {exc}",
            )
        await self._receipts.save(SyscallReceipt.from_execution(stamped, result))
        settled = cast(
            SyscallSettled,
            await self._journal.append(
                SyscallSettled(
                    event_id=f"{stamped.idempotency_key}:settled",
                    seq=0,
                    ts=ctx.now,
                    instance_id=ctx.instance_id,
                    run_id=ctx.run_id,
                    idempotency_key=stamped.idempotency_key,
                    syscall=stamped.name,
                    status=result.status,
                    fulfilled_by=result.fulfilled_by,
                    maturity_used=result.maturity_used,
                )
            ),
        )
        return GatewayOutcome(result=result, attempted=attempted, settled=settled)

    async def _park(
        self,
        *,
        instance_id: str,
        run_id: str,
        reason: str,
        required_ring: Ring | None,
        ctx: GatewayContext,
        attempted: SyscallAttempted,
    ) -> GatewayOutcome:
        parked = await self._approval_gate.park_for_approval(
            instance_id=instance_id,
            run_id=run_id,
            reason=reason,
            required_ring=required_ring,
            now=ctx.now,
        )
        return GatewayOutcome(parked=parked, attempted=attempted)

    async def _ensure_attempt(
        self,
        req: SyscallRequest,
        policy: SyscallPolicy,
        ctx: GatewayContext,
    ) -> SyscallAttempted:
        event_id = f"{req.idempotency_key}:attempt"
        for event in reversed(await self._journal.read_instance(ctx.instance_id)):
            if isinstance(event, SyscallAttempted) and event.event_id == event_id:
                if event.run_id != ctx.run_id or event.syscall != req.name or event.args != req.args:
                    raise IdempotencyRequestConflict(req.idempotency_key)
                return event
        return cast(
            SyscallAttempted,
            await self._journal.append(
                SyscallAttempted(
                    event_id=event_id,
                    seq=0,
                    ts=ctx.now,
                    instance_id=ctx.instance_id,
                    run_id=ctx.run_id,
                    syscall=req.name,
                    args=req.args,
                    ring_required=policy.required_ring,
                )
            ),
        )

    async def _prior_outcome(self, req: SyscallRequest, ctx: GatewayContext) -> GatewayOutcome | None:
        receipt = await self._receipts.get(req.idempotency_key)
        if receipt is not None and not receipt.matches(req):
            raise IdempotencyRequestConflict(req.idempotency_key)

        events = await self._journal.read_instance(ctx.instance_id)
        for event in reversed(events):
            if isinstance(event, SyscallSettled) and event.idempotency_key == req.idempotency_key:
                if receipt is None:
                    raise MissingSyscallReceipt(req.idempotency_key)
                return GatewayOutcome(result=receipt.result)

        if receipt is not None:
            settled = cast(
                SyscallSettled,
                await self._journal.append(
                    SyscallSettled(
                        event_id=f"{req.idempotency_key}:settled",
                        seq=0,
                        ts=ctx.now,
                        instance_id=ctx.instance_id,
                        run_id=ctx.run_id,
                        idempotency_key=req.idempotency_key,
                        syscall=req.name,
                        status=receipt.result.status,
                        fulfilled_by=receipt.result.fulfilled_by,
                        maturity_used=receipt.result.maturity_used,
                    )
                )
            )
            return GatewayOutcome(result=receipt.result, settled=settled)
        return None
