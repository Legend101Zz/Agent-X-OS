"""Phase-1 run loop implementing the ``RunInvoker`` seam.

G1: the run's trajectory comes from a ``HarnessRunner`` — in ``live`` mode the Hermes runner driving
MiniMax (which emits Think/Call/Claim/Finish), in ``sim`` mode the deterministic ``OwnHarness`` following
the lead-finder PLAYBOOK. The kernel DISPOSES every step: it ring-checks + journals effectful Calls through
the gateway, fulfils read Calls (sim-native / via the gateway) and feeds the SyscallResult back, accumulates
Claims for verification, and settles on Finish. The LLM proposes; deterministic code disposes (invariant #4).
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, cast, runtime_checkable

from agentx_contracts.enums import Ring, RunMode
from agentx_contracts.journal import ApprovalResolved, RunCreated, RunHydrated, RunParked, RunSettled, RunVerified
from agentx_contracts.jsontypes import JsonObject, JsonValue
from agentx_contracts.mandate import InstanceBinding, MandateRun, MandateType
from agentx_contracts.memory import Fact
from agentx_contracts.run import ParkInfo, RunResult
from agentx_contracts.syscall import GatewayContext, SyscallRequest, SyscallResult
from agentx_contracts.trigger import Trigger
from agentx_contracts.verification import Trace, TraceEvent
from agentx_mandate.faculties import get_faculty
from agentx_mandate.harness import (
    Call,
    Claim,
    Escalate,
    FacultyContext,
    Finish,
    HarnessAction,
    HarnessRunner,
    HarnessSession,
    OwnHarness,
    Playbook,
    Think,
)
from agentx_mandate.lead_quality import enrich_lead
from agentx_mandate.library.books_prep_playbook import books_prep_playbook
from agentx_mandate.library.lead_finder_playbook import lead_finder_playbook
from agentx_mandate.settlement import build_settlement

from .continuations import RunContinuation
from .errors import RunNotResumable
from .gateway import Gateway
from .hydration import HydrationLoader
from .ports import JournalStore, RunContinuationStore
from .projections import Projections
from .run_log import NULL_RUN_LOG, RunLog
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


@runtime_checkable
class StatefulHarnessSession(Protocol):
    """Optional kernel-side extension for live harnesses with process-local continuation state."""

    def export_state(self) -> JsonObject: ...

    def restore_state(self, state: JsonObject) -> None: ...


@dataclass
class Phase1RunInvoker:
    journal: JournalStore
    projections: Projections
    hydration: HydrationLoader
    gateway: Gateway
    settlement: SettlementCommitter
    verifier: RulesVerifier
    continuations: RunContinuationStore
    runner: HarnessRunner | None = None
    max_steps: int = 24
    # Where per-run JSONL logs are written. None → enabled at the default dir
    # (AGENTX_RUN_LOG_DIR or ./run_logs). Set to "" to disable run logging.
    run_log_dir: str | None = None

    def _open_run_log(self, *, run_id: str, instance_id: str, type_ref: str) -> RunLog:
        if self.run_log_dir == "":
            return NULL_RUN_LOG
        try:
            return RunLog(
                run_id=run_id,
                instance_id=instance_id,
                type_ref=type_ref,
                base_dir=self.run_log_dir,
            )
        except Exception:  # noqa: BLE001 — logging must never break a run
            return NULL_RUN_LOG

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
        run_log = self._open_run_log(
            run_id=run_id, instance_id=instance.instance_id, type_ref=instance.type_ref
        )
        run_log.event(
            "thought",
            "run invoked",
            {
                "mode": mode,
                "trigger_kind": trigger.kind,
                "target": dict(mandate.charter.target) if isinstance(mandate.charter.target, dict) else {},
                "faculties": [b.faculty_name for b in mandate.faculties],
            },
        )
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

        runner = self._runner(mandate)
        run_log.event("thought", f"harness started: {type(runner).__name__}", {})
        session = runner.start(context=ctx, faculties=faculties, cursor=0, mandate=mandate)
        return await self._drive(
            mandate=mandate,
            instance=instance,
            trigger=trigger,
            mode=mode,
            ctx=ctx,
            trace=trace,
            claimed_facts=claimed_facts,
            session=session,
            now=trigger.ts,
            run_log=run_log,
        )

    async def resume(self, *, run_id: str, approval: ApprovalResolved) -> RunResult:
        """Resume one journaled parked run through the same harness/gateway/verify/settle loop."""
        events = await self.journal.read_run(run_id)
        if any(isinstance(event, RunSettled) for event in events):
            raise RunNotResumable(run_id, "run is already settled")
        created = next((event for event in events if isinstance(event, RunCreated)), None)
        parked = next((event for event in reversed(events) if isinstance(event, RunParked)), None)
        journaled_approval = next(
            (
                event
                for event in reversed(events)
                if isinstance(event, ApprovalResolved) and event.event_id == approval.event_id
            ),
            None,
        )
        if created is None:
            raise RunNotResumable(run_id, "RunCreated is missing")
        if parked is None or parked.awaiting != "human_approval":
            raise RunNotResumable(run_id, "human-approval park is missing")
        if (
            journaled_approval is None
            or journaled_approval.run_id != run_id
            or journaled_approval.decision != "approve"
        ):
            raise RunNotResumable(run_id, "matching approved ApprovalResolved is missing")
        approval = journaled_approval
        continuation = await self.continuations.get(run_id)
        if continuation is None:
            raise RunNotResumable(run_id, "durable continuation is missing")
        if (
            created.instance_id != continuation.instance.instance_id
            or created.type_ref != continuation.instance.type_ref
        ):
            raise RunNotResumable(run_id, "continuation does not match RunCreated")

        faculties = [get_faculty(binding.faculty_name) for binding in continuation.mandate.faculties]
        ctx = FacultyContext(
            snapshot=continuation.snapshot,
            target=continuation.mandate.charter.target,
            scratchpad=cast(dict[str, object], deepcopy(continuation.scratchpad)),
            instance_id=continuation.instance.instance_id,
            run_id=run_id,
            ring=continuation.instance.ring,
            now=created.trigger.ts,
        )
        trace = continuation.trace.model_copy(deep=True)
        run_log = self._open_run_log(
            run_id=run_id,
            instance_id=continuation.instance.instance_id,
            type_ref=continuation.instance.type_ref,
        )
        run_log.event(
            "resumed", "run resumed from continuation after approval",
            {"approval_event_id": approval.event_id},
        )
        claimed_facts = [fact.model_copy(deep=True) for fact in continuation.claimed_facts]
        session = self._runner(continuation.mandate).start(
                    context=ctx,
                    faculties=faculties,
                    cursor=continuation.harness_cursor,
                    mandate=continuation.mandate,
                )
        if continuation.harness_state:
            if not isinstance(session, StatefulHarnessSession):
                raise RunNotResumable(run_id, "harness cannot restore persisted state")
            session.restore_state(continuation.harness_state)

        _emit(
            run_log,
            trace,
            approval.ts,
            "resumed",
            "human approval resolved; replaying parked syscall",
            {"approval_event_id": approval.event_id},
        )
        terminal, observation = await self._dispose(
            action=Call(request=continuation.pending_call),
            mode=continuation.mode,
            instance=continuation.instance,
            now=approval.ts,
            ctx=ctx,
            trace=trace,
            claimed_facts=claimed_facts,
            run_log=run_log,
            gateway_ring=parked.required_ring,
        )
        if terminal is not None:
            if terminal.state == "parked":
                await self._save_continuation(
                mandate=continuation.mandate,
                instance=continuation.instance,
                mode=continuation.mode,
                ctx=ctx,
                trace=trace,
                claimed_facts=claimed_facts,
                session=session,
                pending_call=continuation.pending_call,
                )
            run_log.terminal(terminal.state, {"via": "resume"})
            return terminal
        return await self._drive(
            mandate=continuation.mandate,
            instance=continuation.instance,
            trigger=created.trigger,
            mode=continuation.mode,
            ctx=ctx,
            trace=trace,
            claimed_facts=claimed_facts,
            session=session,
            observation=observation,
            now=approval.ts,
            run_log=run_log,
        )

    def _runner(self, mandate: MandateType) -> HarnessRunner:
        # Live runs use the injected Hermes runner (mandate-driven tools/prompt). Sim runs use the
        # deterministic ``own`` double following the mandate's playbook (lead-finder by default).
        if self.runner is not None:
            return self.runner
        return OwnHarness(playbook=sim_playbook_for(mandate))

    async def _drive(
        self,
        *,
        mandate: MandateType,
        instance: InstanceBinding,
        trigger: Trigger,
        mode: RunMode,
        ctx: FacultyContext,
        trace: Trace,
        claimed_facts: list[Fact],
        session: HarnessSession,
        now: datetime,
        observation: SyscallResult | None = None,
        run_log: RunLog = NULL_RUN_LOG,
    ) -> RunResult:
        steps = 0
        while steps < self.max_steps:
            steps += 1
            try:
                action = await session.step(observation)
            except Exception as step_exc:  # noqa: BLE001
                # Surface the real exception the harness (OwnHarness or live
                # Hermes) raised — into the durable run log AND the trace, so
                # the failure is visible in view_run.py, not just on stderr.
                import traceback as _tb
                tb_text = _tb.format_exc()
                _emit(
                run_log,
                trace,
                now,
                "error",
                f"harness step {steps} raised {type(step_exc).__name__}: {step_exc}",
                cast(JsonObject, {"step": steps, "exception": repr(step_exc), "traceback": tb_text}),
                )
                run_log.terminal("crashed", {"reason": "harness_step_raised", "step": steps})
                return RunResult(
                run_id=ctx.run_id, state="crashed", trace=trace, claimed_facts=claimed_facts
                )
            action_kind, action_summary, action_detail = _describe_action(action)
            run_log.event(action_kind, f"step {steps}: {action_summary}", {"step": steps, **action_detail})
            observation = None
            if isinstance(action, Finish):
                break
            terminal, observation = await self._dispose(
                action=action,
                mode=mode,
                instance=instance,
                now=now,
                ctx=ctx,
                trace=trace,
                claimed_facts=claimed_facts,
                run_log=run_log,
            )
            if terminal is not None:
                if terminal.state == "parked" and isinstance(action, Call):
                    await self._save_continuation(
                        mandate=mandate,
                        instance=instance,
                        mode=mode,
                        ctx=ctx,
                        trace=trace,
                        claimed_facts=claimed_facts,
                        session=session,
                        pending_call=_bind_request(action.request, ctx),
                )
                run_log.terminal(terminal.state, {"park_reason": terminal.park.reason if terminal.park else None})
                return terminal
        else:
            _emit(run_log, trace, now, "error", "harness exceeded max steps", {"max_steps": self.max_steps})
            run_log.terminal("crashed", {"reason": "max_steps_exceeded", "max_steps": self.max_steps})
            return RunResult(run_id=ctx.run_id, state="crashed", trace=trace, claimed_facts=claimed_facts)

        result = await self._verify_and_settle(
            mandate=mandate,
            instance=instance,
            trigger=trigger,
            ctx=ctx,
            trace=trace,
            claimed_facts=claimed_facts,
            now=now,
            run_log=run_log,
        )
        if result.state == "settled":
            await self.continuations.delete(ctx.run_id)
        run_log.terminal(
            result.state,
            {"claimed_fact_count": len(claimed_facts), "fact_predicates": sorted({f.predicate for f in claimed_facts})},
        )
        return result

    async def _verify_and_settle(
        self,
        *,
        mandate: MandateType,
        instance: InstanceBinding,
        trigger: Trigger,
        ctx: FacultyContext,
        trace: Trace,
        claimed_facts: list[Fact],
        now: datetime,
        run_log: RunLog = NULL_RUN_LOG,
    ) -> RunResult:
        verify = self.verifier.verify_postconditions(mandate, claimed_facts=claimed_facts)
        if not verify.passed:
            _emit(
                run_log,
                trace,
                now,
                "error",
                "rules verification failed",
                cast(JsonObject, {"reasons": verify.reasons}),
            )
            return RunResult(run_id=ctx.run_id, state="crashed", trace=trace, claimed_facts=claimed_facts)
        run_log.event("verify", "postconditions passed", {"rungs_passed": list(verify.rungs_passed)})

        await self.journal.append(
            RunVerified(
                event_id=f"{ctx.run_id}:verified",
                seq=0,
                ts=now,
                instance_id=instance.instance_id,
                run_id=ctx.run_id,
                rungs_passed=verify.rungs_passed,
            )
        )
        run = MandateRun(
            id=ctx.run_id,
            instance_id=instance.instance_id,
            type_ref=instance.type_ref,
            trigger=trigger,
            state="verifying",
            hydration=ctx.snapshot,
            trace=trace,
            claimed_facts=claimed_facts,
            created_at=trigger.ts,
        )
        settlement = build_settlement(
            run=run,
            rules=mandate.settlement,
            verified_facts=claimed_facts,
            trigger_ctx={"success": True, "thread_state": "settled"},
            now=now,
        )
        await self.settlement.commit(settlement)
        _emit(run_log, trace, now, "verify", "settled", {"fact_count": len(settlement.facts)})
        return RunResult(
            run_id=ctx.run_id,
            state="settled",
            trace=trace,
            claimed_facts=claimed_facts,
            settlement=settlement,
        )

    async def _save_continuation(
        self,
        *,
        mandate: MandateType,
        instance: InstanceBinding,
        mode: RunMode,
        ctx: FacultyContext,
        trace: Trace,
        claimed_facts: list[Fact],
        session: HarnessSession,
        pending_call: SyscallRequest,
    ) -> None:
        harness_state: JsonObject = {}
        if isinstance(session, StatefulHarnessSession):
            harness_state = session.export_state()
        cursor = getattr(session, "cursor", 0)
        if not isinstance(cursor, int):
            raise TypeError("HarnessSession.cursor must be an int")
        await self.continuations.save(
            RunContinuation(
                run_id=ctx.run_id,
                instance=instance,
                mandate=mandate,
                mode=mode,
                snapshot=ctx.snapshot,
                scratchpad=cast(JsonObject, deepcopy(ctx.scratchpad)),
                trace=trace,
                claimed_facts=claimed_facts,
                harness_cursor=cursor,
                harness_state=harness_state,
                pending_call=pending_call,
            )
        )

    async def _dispose(
        self,
        *,
        action: HarnessAction,
        mode: RunMode,
        instance: InstanceBinding,
        now: datetime,
        ctx: FacultyContext,
        trace: Trace,
        claimed_facts: list[Fact],
        run_log: RunLog = NULL_RUN_LOG,
        gateway_ring: Ring | None = None,
    ) -> tuple[RunResult | None, SyscallResult | None]:
        """Dispose one harness action. Returns (terminal RunResult | None, observation to feed back | None)."""
        if isinstance(action, Think):
            _trace(trace, now, "thought", action.summary, action.detail)
            return None, None
        if isinstance(action, Claim):
            claimed_facts.extend(action.facts)
            return None, None
        if isinstance(action, Escalate):
            # _drive already logged this Escalate to the run_log as the harness
            # action; here we only need it in the Trace (for the verifier/judge).
            _trace(trace, now, "error", action.reason, action.detail)
            return (
                RunResult(run_id=ctx.run_id, state="crashed", trace=trace, claimed_facts=claimed_facts),
                None,
            )
        if not isinstance(action, Call):
            return None, None
        request = _bind_request(action.request, ctx)

        # Invariant #8 (per-instance sender of record): the kernel run-loop stamps the instance's own
        # ChannelBinding.sender_identity into the send_email request args (overriding any harness-supplied
        # value) so the adapter cannot be tricked into using a shared/global sender. If the instance has
        # no channel_binding yet, we leave the request alone — the adapter will refuse it with a clear
        # error (no shared/global sender, ever).
        if (
            request.name == "send_email"
            and instance.channel_binding is not None
            and instance.channel_binding.sender_identity
        ):
            sender = instance.channel_binding.sender_identity
            existing_args = dict(request.args)
            changed = False
            if existing_args.get("sender_identity") != sender:
                existing_args["sender_identity"] = sender
                changed = True
            # Phase-1 dogfood default: with no explicit recipient, the outreach goes to the instance's
            # own sender (review-in-your-own-inbox). A real send can then only ever reach the operator,
            # never an unverified address — and the founder reviews/forwards it from their own inbox.
            recipient = existing_args.get("to")
            if not (isinstance(recipient, str) and recipient.strip()):
                existing_args["to"] = sender
                changed = True
            if changed:
                request = request.model_copy(update={"args": existing_args})

        if request.risk_class == "read" and mode == "sim":
            # Read-class intents are fulfilled NATIVELY (off-gateway) and never reach a ring check.
            # In sim the kernel supplies deterministic, clearly-synthetic data (mirrors the live harness's
            # native web-search fulfilment, but unmistakably synthetic so it can't pose as real research).
            _fulfill_sim_native_read(ctx, request, trace, now)
            return None, None

        outcome = await self.gateway.invoke(
            request,
            GatewayContext(
                instance_id=instance.instance_id,
                run_id=ctx.run_id,
                tenant_id=instance.heap_region_id,
                ring=gateway_ring or instance.ring,
                now=now,
            ),
        )
        if outcome.attempted is not None:
            await self.projections.apply(outcome.attempted)
        if outcome.settled is not None:
            await self.projections.apply(outcome.settled)
        if outcome.parked is not None:
            _emit(
                run_log,
                trace,
                now,
                "parked",
                outcome.parked.reason,
                cast(JsonObject, {"required_ring": outcome.parked.required_ring, "syscall": request.name}),
            )
            return (
                RunResult(
                run_id=ctx.run_id,
                state="parked",
                trace=trace,
                claimed_facts=claimed_facts,
                park=ParkInfo(
                        reason=outcome.parked.reason,
                        awaiting=outcome.parked.awaiting,
                        required_ring=outcome.parked.required_ring,
                        approval_card={
                            "syscall": request.name,
                            "args": request.args,
                            "idempotency_key": request.idempotency_key,
                        },
                ),
                ),
                None,
            )
        if outcome.result is None:
            return None, None

        _trace(
            trace,
            now,
            "syscall_result",
            request.name,
            {
                "status": outcome.result.status,
                "fulfilled_by": outcome.result.fulfilled_by,
                "maturity_used": outcome.result.maturity_used,
            },
        )
        run_log.event(
            "syscall_result",
            f"{request.name} → {outcome.result.status}",
            {
                "syscall": request.name,
                "status": outcome.result.status,
                "fulfilled_by": outcome.result.fulfilled_by,
                "maturity_used": outcome.result.maturity_used,
                "output": _syscall_output_summary(request.name, outcome.result.output)
                if outcome.result.status == "ok"
                else {},
            },
        )
        if outcome.result.status == "error":
            # Agent-loop resilience: a failed syscall is FED BACK to the harness (an LLM can recover and
            # retry within max_steps), not crashed. Only Escalate + the max_steps bound terminate a run.
            _emit(
                run_log,
                trace,
                now,
                "error",
                f"{request.name} failed",
                {"error": outcome.result.error or "unknown", "status": outcome.result.status},
            )
            return None, outcome.result
        if request.risk_class == "read" and outcome.result.status == "ok":
            _apply_read_result(ctx, request, outcome.result.output)
            _apply_discovery_read_result(ctx, request, outcome.result.output)
        # Expose the most recent non-error SyscallResult on the scratchpad so playbooks (e.g. the
        # Creator's ``creator_playbook``) can react to a draft_candidate_type result without
        # the playbook needing to know the gateway's receipt-store shape. We only set this when
        # status == "ok" — error results are already surfaced through the Escalate faculty path.
        if outcome.result.status == "ok" and request.name != "lead_research_batch":
            ctx.scratchpad["last_receipt"] = {
                "syscall": request.name,
                "idempotency_key": request.idempotency_key,
                "args": dict(request.args),
                "output": dict(outcome.result.output),
                "fulfilled_by": outcome.result.fulfilled_by,
                "maturity_used": outcome.result.maturity_used,
            }
        return None, outcome.result


def _apply_read_result(ctx: FacultyContext, request: SyscallRequest, output: JsonObject) -> None:
    if request.name == "lead_research_batch":
        normalized = _normalize_leads(output.get("leads"))
        if normalized:
            ctx.scratchpad["leads"] = normalized
        return
    if request.name == "ingest_document":
        # Stash parsed transactions (accumulating across multiple ingested docs) for the categorizer.
        raw = output.get("transactions")
        if not isinstance(raw, list):
            return
        existing = ctx.scratchpad.get("transactions")
        transactions: list[object] = existing if isinstance(existing, list) else []
        transactions.extend(txn for txn in raw if isinstance(txn, dict))
        ctx.scratchpad["transactions"] = transactions
        return
    if request.name != "read_url":
        return
    lead_id = request.args.get("lead_id")
    leads = ctx.scratchpad.get("leads")
    if not isinstance(lead_id, str) or not isinstance(leads, list):
        return
    for index, lead in enumerate(leads):
        if isinstance(lead, dict) and lead.get("id") == lead_id:
            leads[index] = enrich_lead(lead, output, ctx.target)
            return


# Phase 14: mandate-discovery's three read syscalls each write a specific
# scratchpad key the playbook reads (community_posts / moat_assessments /
# buyer_channels). The kernel's _apply_read_result only handled
# lead_research_batch + read_url before — extend it for the META mandate
# without disturbing the lead-finder path.
_MANDATE_DISCOVERY_SCRATCHPAD_KEYS: dict[str, str] = {
    "community_source_sample": "community_posts",
    "competitor_search": "moat_assessments",
    "buyer_channel_discovery": "buyer_channels",
    # Shared in-OS deep research: the pack lands in scratchpad for the own-harness
    # path; the live Hermes path also gets it fed back as the tool result.
    "deep_research": "research_pack",
}


def _apply_discovery_read_result(
    ctx: FacultyContext, request: SyscallRequest, output: JsonObject
) -> None:
    """Inject the result of a mandate-discovery read syscall into the
    playbook's expected scratchpad key. The META-mandate F1/F4/F5 adapters
    return payloads shaped exactly the way the playbook reads them; this
    function does the side-effect for the kernel run-loop.

    This is the **Phase 14 wiring fix**: without it, the kernel run-loop
    stores the F1/F4/F5 results only in ``last_receipt`` (not in
    ``community_posts`` / ``moat_assessments`` / ``buyer_channels``), and
    the deterministic playbook sees an empty scratchpad and parks at the
    F1 minimum-sample check. The kernel-side handler in
    ``_drive._apply_read_result`` doesn't know about META-mandate syscall
    names; this helper is the targeted addition.
    """
    target_key = _MANDATE_DISCOVERY_SCRATCHPAD_KEYS.get(request.name)
    if target_key is None:
        return
    payload = output.get(target_key)
    if payload is None:
        return
    ctx.scratchpad[target_key] = payload


def _fulfill_sim_native_read(ctx: FacultyContext, request: SyscallRequest, trace: Trace, ts: datetime) -> None:
    """Fulfil a READ-class intent natively in sim (off-gateway), then trace it.

    Sim reads use clearly synthetic fixtures but preserve the live structured enrichment shape.
    """
    if request.name == "read_url":
        lead_id = request.args.get("lead_id")
        url = request.args.get("url")
        if isinstance(lead_id, str) and isinstance(url, str):
            page: JsonObject = {
                "lead_id": lead_id,
                "url": url,
                "title": f"[sim] {lead_id} Dental Clinic",
                "markdown": (
                f"# [sim] {lead_id} Dental Clinic\n"
                "Dr. Sim Owner and the clinic team are accepting new patients.\n"
                "[Book an appointment](/contact)\n"
                ),
                "evidence": ["Dr. Sim Owner and the clinic team are accepting new patients."],
            }
            _apply_read_result(ctx, request, page)
        _trace(trace, ts, "thought", "native read (sim): read_url", request.args)
        return
    if request.name != "lead_research_batch":
        # books-prep sim: synthesize clearly-marked bank transactions for ingest_document.
        if request.name == "ingest_document":
            output = _synthetic_sim_transactions(ctx, request.args)
            _apply_read_result(ctx, request, output)
            transactions = output.get("transactions")
            _trace(
                trace,
                ts,
                "thought",
                "native ingest (sim synthetic transactions)",
                {
                    "doc_id": output.get("doc_id"),
                    "txn_count": len(transactions) if isinstance(transactions, list) else 0,
                    "source": "sim_native_read",
                },
            )
            return
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
        signal = "accepting new patients"
        evidence: list[JsonValue] = [
            f"sim-native-read:lead_research_batch:{ctx.run_id}:{index}",
            signal,
        ]
        leads.append(
            {
                "id": f"sim_lead_{index}",
                "company": f"[sim] {icp} candidate {index}",
                "url": f"https://sim.invalid/lead/{index}",
                "contact_name": "Dr. Sim Owner",
                "contact_role": "Practice owner or clinic manager",
                "contact_url": f"https://sim.invalid/lead/{index}/contact",
                "buying_signal": signal,
                "buying_signal_evidence": signal,
                "evidence": evidence,
                "origin": "synthetic",
                "actionable": True,
            }
        )
    return leads


# --- sim-playbook resolver: type → deterministic playbook the ``own`` double follows in sim ---------
# Defaults to lead-finder. books-prep registers its playbook here in step 5 (kernel→mandate import is
# allowed; the reverse is forbidden, which is why the registry lives kernel-side).
_SIM_PLAYBOOKS: dict[str, Playbook] = {
    "lead-finder": lead_finder_playbook,
    "books-prep": books_prep_playbook,
}


def sim_playbook_for(mandate: MandateType) -> Playbook:
    """Resolve the deterministic sim playbook for a mandate (defaults to the lead-finder playbook)."""
    return _SIM_PLAYBOOKS.get(mandate.name, lead_finder_playbook)


def _synthetic_sim_transactions(ctx: FacultyContext, args: JsonObject) -> JsonObject:
    """Deterministic, unmistakably-synthetic bank transactions for a books-prep sim ingest.

    Mirrors the live ``IngestDocumentAdapter`` output shape (rows + per-row source citation + a
    deterministic ``extraction_confidence``) but everything is flagged ``[sim]`` / ``origin:synthetic``
    so it can never pose as a real statement. Running balance is continuous (so balance-continuity holds).
    """
    raw_doc = args.get("doc_id")
    doc_id = raw_doc if isinstance(raw_doc, str) and raw_doc else "sim_doc_1"
    account_id = "[sim] account XXXX1234"
    period = "2026-04"
    rows = [
        ("2026-04-02", "[sim] NEFT ACME TRADERS PVT LTD inward payment", 0.0, 25000.0),
        ("2026-04-05", "[sim] UPI/AMAZON/office stationery purchase", 1800.0, 0.0),
        ("2026-04-09", "[sim] NEFT GST PAYMENT challan CPIN", 12000.0, 0.0),
    ]
    balance = 100000.0
    transactions: list[JsonValue] = []
    for index, (date, narration, debit, credit) in enumerate(rows, start=1):
        balance = round(balance - debit + credit, 2)
        transactions.append(
            {
                "date": date,
                "narration": narration,
                "debit": debit,
                "credit": credit,
                "balance": balance,
                "ref": f"SIM{index:04d}",
                "source": {"doc_id": doc_id, "page": 1, "line": index},
                "account_id": account_id,
                "statement_period": period,
                "extraction_confidence": 1.0,
                "extraction_suspect": False,
                "origin": "synthetic",
            }
        )
    return {"doc_id": doc_id, "transactions": transactions}


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
                "metadata": cast(JsonValue, item.get("metadata")) if isinstance(item.get("metadata"), dict) else {},
            }
        )
    return leads


def _str_value(value: object, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _bind_request(request: SyscallRequest, ctx: FacultyContext) -> SyscallRequest:
    """Bind a harness-proposed intent to the current kernel-owned run identity."""
    return request.model_copy(update={"instance_id": ctx.instance_id, "run_id": ctx.run_id})


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


def _emit(
    run_log: RunLog,
    trace: Trace,
    ts: datetime,
    kind: TraceKind,
    summary: str,
    detail: JsonObject,
) -> None:
    """Record one event in BOTH the in-memory Trace and the durable per-run log.

    Single chokepoint so the durable log can never silently drift from the trace
    the verifier/judge see. ``run_log`` is a no-op sink when logging is disabled.
    """
    _trace(trace, ts, kind, summary, detail)
    run_log.event(kind, summary, dict(detail))


def _describe_action(action: HarnessAction) -> tuple[str, str, JsonObject]:
    """Render a harness action as (kind, summary, detail) for the run log.

    This is the "what did the harness decide this step" record — the single most
    useful thing when debugging why a run escalated or claimed the wrong facts.
    """
    if isinstance(action, Think):
        return "thought", action.summary, dict(action.detail)
    if isinstance(action, Call):
        return (
            "syscall_attempt",
            f"call {action.request.name}",
            cast(JsonObject, {"syscall": action.request.name, "args": dict(action.request.args)}),
        )
    if isinstance(action, Claim):
        facts = [
            {
                "subject": f.subject,
                "predicate": f.predicate,
                "object": f.object,
                "confidence": f.confidence,
                "evidence": list(f.provenance.evidence)[:3] if f.provenance else [],
            }
            for f in action.facts
        ]
        return "decision", f"claim {len(action.facts)} fact(s)", cast(JsonObject, {"facts": facts})
    if isinstance(action, Escalate):
        return "error", f"escalate: {action.reason}", dict(action.detail)
    if isinstance(action, Finish):
        output = getattr(action, "output", None)
        return "decision", "finish", cast(JsonObject, dict(output) if isinstance(output, dict) else {})
    return "decision", type(action).__name__, cast(JsonObject, {})


def _syscall_output_summary(name: str, output: JsonObject) -> JsonObject:
    """A compact, human-skimmable summary of a syscall's output for the run log.

    The full payload lives in the receipt store; here we surface the counts that
    explain a downstream gate decision (how many posts F1 returned, which
    candidates F4/F5 covered, how many leads research found).
    """
    summary: dict[str, object] = {}
    posts = output.get("community_posts")
    if isinstance(posts, list):
        summary["community_posts"] = len(posts)
        stats = output.get("sample_stats")
        if isinstance(stats, dict):
            summary["sample_stats"] = dict(stats)
        sources = sorted(
            {str(p.get("source")) for p in posts if isinstance(p, dict) and p.get("source")}
        )
        if sources:
            summary["distinct_sources"] = sources
        errors = [
            str(p.get("error"))
            for p in posts
            if isinstance(p, dict) and p.get("error")
        ]
        if errors:
            summary["post_errors"] = errors[:5]
    moat = output.get("moat_assessments")
    if isinstance(moat, dict):
        summary["moat_candidates"] = list(moat.keys())
    channels = output.get("buyer_channels")
    if isinstance(channels, dict):
        summary["buyer_channels_per_candidate"] = {
            str(k): (len(chans) if isinstance(chans := v.get("channels"), list) else 0)
            for k, v in channels.items()
            if isinstance(v, dict)
        }
    leads = output.get("leads")
    if isinstance(leads, list):
        summary["leads"] = len(leads)
    if not summary:
        summary["keys"] = list(output.keys())
    return cast(JsonObject, summary)
