"""Phase-1 run loop implementing the ``RunInvoker`` seam."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from agentx_contracts.enums import RunMode
from agentx_contracts.journal import RunCreated, RunHydrated, RunVerified
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.mandate import InstanceBinding, MandateRun, MandateType
from agentx_contracts.memory import Fact
from agentx_contracts.run import ParkInfo, RunResult
from agentx_contracts.syscall import GatewayContext, SyscallRequest
from agentx_contracts.trigger import Trigger
from agentx_contracts.verification import Trace, TraceEvent
from agentx_mandate.faculties import get_faculty, propose
from agentx_mandate.harness import Call, Claim, Escalate, FacultyContext, HarnessAction, Think
from agentx_mandate.settlement import build_settlement

from .gateway import Gateway
from .hydration import HydrationLoader
from .ports import JournalStore
from .projections import Projections
from .settlement import SettlementCommitter
from .verifier import RulesVerifier

TraceKind = Literal[
    "thought",
    "syscall_attempt",
    "syscall_result",
    "parked",
    "resumed",
    "verify",
    "judge_comment",
    "decision",
    "error",
]


@dataclass
class Phase1RunInvoker:
    journal: JournalStore
    projections: Projections
    hydration: HydrationLoader
    gateway: Gateway
    settlement: SettlementCommitter
    verifier: RulesVerifier

    async def invoke(
        self,
        *,
        mandate: MandateType,
        instance: InstanceBinding,
        trigger: Trigger,
        mode: RunMode,
    ) -> RunResult:
        run_id = _run_id(instance, trigger)
        trace = Trace(run_id=run_id)
        created = cast(
            RunCreated,
            await self.journal.append(
                RunCreated(
                    event_id=f"{run_id}:created",
                    seq=0,
                    ts=trigger.ts,
                    instance_id=instance.instance_id,
                    run_id=run_id,
                    type_ref=instance.type_ref,
                    trigger=trigger,
                )
            ),
        )
        await self.projections.apply(created)

        faculties = [get_faculty(binding.faculty_name) for binding in mandate.faculties]
        snapshot = await self.hydration.hydrate(
            instance_id=instance.instance_id,
            entity_id=trigger.entity_id,
            skill_pack_refs=[faculty.skill_pack for faculty in faculties],
            domain_pack=mandate.domain_pack,
            now=trigger.ts,
        )
        hydrated = await self.journal.append(
            RunHydrated(
                event_id=f"{run_id}:hydrated",
                seq=0,
                ts=trigger.ts,
                instance_id=instance.instance_id,
                run_id=run_id,
                fact_count=len(snapshot.facts),
                thread_id=snapshot.thread.id if snapshot.thread is not None else None,
            )
        )
        await self.projections.apply(hydrated)

        ctx = FacultyContext(
            snapshot=snapshot,
            target=mandate.charter.target,
            scratchpad={},
            instance_id=instance.instance_id,
            run_id=run_id,
            ring=instance.ring,
            now=trigger.ts,
        )
        claimed_facts: list[Fact] = []
        for action in _phase1_actions(mandate, ctx):
            if isinstance(action, Think):
                _trace(trace, trigger.ts, "thought", action.summary, action.detail)
            elif isinstance(action, Claim):
                claimed_facts.extend(action.facts)
            elif isinstance(action, Escalate):
                _trace(trace, trigger.ts, "error", action.reason, action.detail)
                return RunResult(run_id=run_id, state="crashed", trace=trace, claimed_facts=claimed_facts)
            elif isinstance(action, Call):
                if action.request.risk_class == "read":
                    _trace(trace, trigger.ts, "thought", f"native read: {action.request.name}", action.request.args)
                    continue
                outcome = await self.gateway.invoke(
                    action.request,
                    GatewayContext(
                        instance_id=instance.instance_id,
                        run_id=run_id,
                        tenant_id=instance.heap_region_id,
                        ring=instance.ring,
                        now=trigger.ts,
                    ),
                )
                if outcome.parked is not None:
                    _trace(
                        trace,
                        trigger.ts,
                        "parked",
                        outcome.parked.reason,
                        {"required_ring": outcome.parked.required_ring},
                    )
                    return RunResult(
                        run_id=run_id,
                        state="parked",
                        trace=trace,
                        claimed_facts=claimed_facts,
                        park=ParkInfo(
                            reason=outcome.parked.reason,
                            awaiting=outcome.parked.awaiting,
                            required_ring=outcome.parked.required_ring,
                            approval_card={"syscall": action.request.name},
                        ),
                    )
                if outcome.result is not None:
                    _trace(
                        trace,
                        trigger.ts,
                        "syscall_result",
                        action.request.name,
                        {"status": outcome.result.status, "fulfilled_by": outcome.result.fulfilled_by},
                    )

        verify = self.verifier.verify_postconditions(mandate, claimed_facts=claimed_facts)
        if not verify.passed:
            _trace(
                trace,
                trigger.ts,
                "error",
                "rules verification failed",
                cast(JsonObject, {"reasons": verify.reasons}),
            )
            return RunResult(run_id=run_id, state="crashed", trace=trace, claimed_facts=claimed_facts)

        await self.journal.append(
            RunVerified(
                event_id=f"{run_id}:verified",
                seq=0,
                ts=trigger.ts,
                instance_id=instance.instance_id,
                run_id=run_id,
                rungs_passed=verify.rungs_passed,
            )
        )
        run = MandateRun(
            id=run_id,
            instance_id=instance.instance_id,
            type_ref=instance.type_ref,
            trigger=trigger,
            state="verifying",
            hydration=snapshot,
            trace=trace,
            claimed_facts=claimed_facts,
            created_at=trigger.ts,
        )
        settlement = build_settlement(
            run=run,
            rules=mandate.settlement,
            verified_facts=claimed_facts,
            trigger_ctx={"success": True, "thread_state": "settled"},
            now=trigger.ts,
        )
        await self.settlement.commit(settlement)
        _trace(trace, trigger.ts, "verify", "settled", {"fact_count": len(settlement.facts)})
        return RunResult(
            run_id=run_id,
            state="settled",
            trace=trace,
            claimed_facts=claimed_facts,
            settlement=settlement,
        )


def _phase1_actions(mandate: MandateType, ctx: FacultyContext) -> list[HarnessAction]:
    actions: list[HarnessAction] = []
    for binding in mandate.faculties:
        actions.extend(propose(binding.faculty_name, ctx))
    lead_id = _first_lead_id(ctx)
    if lead_id is not None:
        actions.append(
            Call(
                request=SyscallRequest(
                    name="draft_email",
                    args={"lead_id": lead_id, "mode": "draft"},
                    instance_id=ctx.instance_id,
                    run_id=ctx.run_id,
                    idempotency_key=f"{ctx.run_id}:draft_email",
                    ring=ctx.ring,
                    risk_class="external_message",
                )
            )
        )
    return actions


def _first_lead_id(ctx: FacultyContext) -> str | None:
    leads = ctx.scratchpad.get("leads")
    if not isinstance(leads, list) or not leads:
        return None
    first = leads[0]
    if not isinstance(first, dict):
        return None
    lead_id = first.get("id")
    return lead_id if isinstance(lead_id, str) else None


def _run_id(instance: InstanceBinding, trigger: Trigger) -> str:
    return f"{instance.instance_id}:{trigger.kind}:{int(trigger.ts.timestamp())}"


def _trace(trace: Trace, ts: datetime, kind: TraceKind, summary: str, detail: JsonObject) -> None:
    trace.events.append(
        TraceEvent(
            seq=len(trace.events) + 1,
            ts=ts,
            kind=kind,
            summary=summary,
            detail=detail,
        )
    )
