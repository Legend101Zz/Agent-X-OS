"""Phase-1 run loop implementing the ``RunInvoker`` seam."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, cast

from agentx_contracts.enums import RunMode
from agentx_contracts.journal import RunCreated, RunHydrated, RunVerified
from agentx_contracts.jsontypes import JsonObject, JsonValue
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


class Reasoner(Protocol):
    async def complete(self, prompt: str) -> str:
        """Return a bounded reasoning note from the live harness."""
        ...


@dataclass
class Phase1RunInvoker:
    journal: JournalStore
    projections: Projections
    hydration: HydrationLoader
    gateway: Gateway
    settlement: SettlementCommitter
    verifier: RulesVerifier
    reasoner: Reasoner | None = None

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

        if mode == "live" and self.reasoner is not None:
            note = await self.reasoner.complete(_reasoning_prompt(mandate, ctx))
            _trace(trace, trigger.ts, "thought", "Hermes/Minimax reasoning", {"note": _trim(note)})

        for binding in mandate.faculties:
            for action in propose(binding.faculty_name, ctx):
                terminal = await self._handle_action(
                    action=action,
                    mode=mode,
                    instance=instance,
                    trigger=trigger,
                    ctx=ctx,
                    trace=trace,
                    claimed_facts=claimed_facts,
                )
                if terminal is not None:
                    return terminal

        lead_id = _first_lead_id(ctx)
        if lead_id is not None:
            terminal = await self._handle_action(
                action=Call(
                    request=SyscallRequest(
                        name="draft_email",
                        args=_draft_args(ctx, lead_id),
                        instance_id=ctx.instance_id,
                        run_id=ctx.run_id,
                        idempotency_key=f"{ctx.run_id}:draft_email",
                        ring=ctx.ring,
                        risk_class="external_message",
                    )
                ),
                mode=mode,
                instance=instance,
                trigger=trigger,
                ctx=ctx,
                trace=trace,
                claimed_facts=claimed_facts,
            )
            if terminal is not None:
                return terminal

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

    async def _handle_action(
        self,
        *,
        action: HarnessAction,
        mode: RunMode,
        instance: InstanceBinding,
        trigger: Trigger,
        ctx: FacultyContext,
        trace: Trace,
        claimed_facts: list[Fact],
    ) -> RunResult | None:
        if isinstance(action, Think):
            _trace(trace, trigger.ts, "thought", action.summary, action.detail)
            return None
        if isinstance(action, Claim):
            claimed_facts.extend(action.facts)
            return None
        if isinstance(action, Escalate):
            _trace(trace, trigger.ts, "error", action.reason, action.detail)
            return RunResult(
                run_id=ctx.run_id,
                state="crashed",
                trace=trace,
                claimed_facts=claimed_facts,
            )
        if not isinstance(action, Call):
            return None

        if action.request.risk_class == "read" and mode == "sim":
            # Read-class intents are fulfilled NATIVELY (off-gateway) and never surface to a ring check.
            # In sim the kernel supplies deterministic, clearly-synthetic data (mirrors the live harness's
            # native web-search fulfilment, but unmistakably synthetic so it can't pose as real research).
            _fulfill_sim_native_read(ctx, action.request, trace, trigger.ts)
            return None

        outcome = await self.gateway.invoke(
            action.request,
            GatewayContext(
                instance_id=instance.instance_id,
                run_id=ctx.run_id,
                tenant_id=instance.heap_region_id,
                ring=instance.ring,
                now=trigger.ts,
            ),
        )
        if outcome.attempted is not None:
            await self.projections.apply(outcome.attempted)
        if outcome.settled is not None:
            await self.projections.apply(outcome.settled)
        if outcome.parked is not None:
            _trace(
                trace,
                trigger.ts,
                "parked",
                outcome.parked.reason,
                {"required_ring": outcome.parked.required_ring},
            )
            return RunResult(
                run_id=ctx.run_id,
                state="parked",
                trace=trace,
                claimed_facts=claimed_facts,
                park=ParkInfo(
                    reason=outcome.parked.reason,
                    awaiting=outcome.parked.awaiting,
                    required_ring=outcome.parked.required_ring,
                    approval_card={
                        "syscall": action.request.name,
                        "args": action.request.args,
                        "idempotency_key": action.request.idempotency_key,
                    },
                ),
            )
        if outcome.result is None:
            return None

        _trace(
            trace,
            trigger.ts,
            "syscall_result",
            action.request.name,
            {
                "status": outcome.result.status,
                "fulfilled_by": outcome.result.fulfilled_by,
                "maturity_used": outcome.result.maturity_used,
            },
        )
        if outcome.result.status == "error":
            _trace(
                trace,
                trigger.ts,
                "error",
                f"{action.request.name} failed",
                {"error": outcome.result.error or "unknown"},
            )
            return RunResult(
                run_id=ctx.run_id,
                state="crashed",
                trace=trace,
                claimed_facts=claimed_facts,
            )
        if action.request.risk_class == "read":
            if outcome.result.status != "ok":
                _trace(
                    trace,
                    trigger.ts,
                    "error",
                    f"{action.request.name} did not return live research",
                    {"status": outcome.result.status, "fulfilled_by": outcome.result.fulfilled_by},
                )
                return RunResult(
                    run_id=ctx.run_id,
                    state="crashed",
                    trace=trace,
                    claimed_facts=claimed_facts,
                )
            _apply_read_result(ctx, action.request.name, outcome.result.output)
        return None


def _first_lead_id(ctx: FacultyContext) -> str | None:
    leads = ctx.scratchpad.get("leads")
    if not isinstance(leads, list) or not leads:
        return None
    first = leads[0]
    if not isinstance(first, dict):
        return None
    lead_id = first.get("id")
    return lead_id if isinstance(lead_id, str) else None


def _draft_args(ctx: FacultyContext, lead_id: str) -> JsonObject:
    company = _lead_value(ctx, lead_id, "company", "name") or lead_id
    url = _lead_value(ctx, lead_id, "url") or "unknown source"
    evidence = _lead_evidence(ctx, lead_id)
    evidence_line = "; ".join(evidence[:3]) if evidence else "research evidence captured in the run trace"
    return {
        "lead_id": lead_id,
        "mode": "draft",
        "to": "founder-review@agent-x.local",
        "subject": f"Draft outreach: {company}",
        "body": (
            f"Draft only. Candidate: {company}. Source: {url}. "
            f"Why it may fit Agent-X lead-finder: {evidence_line}."
        ),
    }


def _apply_read_result(ctx: FacultyContext, request_name: str, output: JsonObject) -> None:
    if request_name != "lead_research_batch":
        return
    normalized = _normalize_leads(output.get("leads"))
    if normalized:
        ctx.scratchpad["leads"] = normalized


def _fulfill_sim_native_read(ctx: FacultyContext, request: SyscallRequest, trace: Trace, ts: datetime) -> None:
    """Fulfil a READ-class intent natively in sim (off-gateway), then trace it.

    Only ``lead_research_batch`` yields leads; other reads (e.g. ``read_url``) are traced no-ops in sim.
    """
    if request.name != "lead_research_batch":
        _trace(trace, ts, "thought", f"native read (sim): {request.name}", request.args)
        return
    leads = _synthetic_sim_leads(ctx, request.args)
    ctx.scratchpad["leads"] = leads
    _trace(
        trace,
        ts,
        "thought",
        "native research (sim synthetic leads)",
        {"lead_count": len(leads), "source": "sim_native_read"},
    )


def _synthetic_sim_leads(ctx: FacultyContext, args: JsonObject) -> list[JsonObject]:
    """Deterministic, unmistakably-synthetic leads for sim runs (ids/urls/evidence all flagged ``sim``)."""
    criteria = args.get("criteria")
    icp = "target ICP"
    if isinstance(criteria, dict):
        raw_icp = criteria.get("icp")
        if isinstance(raw_icp, str) and raw_icp:
            icp = raw_icp
    raw_count = args.get("count")
    count = raw_count if isinstance(raw_count, int) and 1 <= raw_count <= 10 else 3
    leads: list[JsonObject] = []
    for index in range(1, count + 1):
        evidence: list[JsonValue] = [f"sim-native-read:lead_research_batch:{ctx.run_id}:{index}"]
        leads.append(
            {
                "id": f"sim_lead_{index}",
                "company": f"[sim] {icp} candidate {index}",
                "url": f"sim://lead/{index}",
                "evidence": evidence,
            }
        )
    return leads


def _normalize_leads(value: object) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    leads: list[JsonObject] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        lead_id = _str_value(item.get("id"), f"lead_{index}")
        company = _str_value(item.get("company"), "") or _str_value(item.get("name"), lead_id)
        evidence = _str_list(item.get("evidence")) or _str_list(item.get("highlights"))
        evidence_json: list[JsonValue] = []
        for entry in evidence or [f"live_research:{lead_id}"]:
            evidence_json.append(entry)
        leads.append(
            {
                "id": lead_id,
                "company": company,
                "url": _str_value(item.get("url"), ""),
                "evidence": evidence_json,
            }
        )
    return leads


def _lead_value(ctx: FacultyContext, lead_id: str, *keys: str) -> str | None:
    leads = ctx.scratchpad.get("leads")
    if not isinstance(leads, list):
        return None
    for lead in leads:
        if not isinstance(lead, dict) or lead.get("id") != lead_id:
            continue
        for key in keys:
            value = lead.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _lead_evidence(ctx: FacultyContext, lead_id: str) -> list[str]:
    leads = ctx.scratchpad.get("leads")
    if not isinstance(leads, list):
        return []
    for lead in leads:
        if isinstance(lead, dict) and lead.get("id") == lead_id:
            return _str_list(lead.get("evidence"))
    return []


def _str_value(value: object, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _reasoning_prompt(mandate: MandateType, ctx: FacultyContext) -> str:
    return (
        "You are the Agent-X lead-finder faculty. Think briefly about the ICP, then stop. "
        "Do not call tools and do not make commitments. "
        f"Goal: {mandate.charter.goal}. Target: {ctx.target}."
    )


def _trim(value: str, limit: int = 1200) -> str:
    return value if len(value) <= limit else value[: limit - 3] + "..."


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
