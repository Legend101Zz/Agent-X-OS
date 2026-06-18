"""G1 — the live Hermes runner: MiniMax (OpenAI tool-calling) drives the run trajectory.

These tests use a FAKE chat transport (no network) returning canned MiniMax-shaped responses, so they
verify the PARSING + history discipline faithfully and run in the offline gate. The actual money-spending
live run is proven separately (SESSION_F_LIVE_PROOF.md).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from agentx_contracts import HydrationSnapshot
from agentx_contracts.enums import MaturityLevel, Ring, TenantAuth
from agentx_contracts.faculty import FacultyBinding
from agentx_contracts.journal import ApprovalResolved, SyscallAttempted, SyscallSettled
from agentx_contracts.jsontypes import JsonObject, JsonSchema
from agentx_contracts.mandate import (
    Charter,
    Condition,
    DomainPackRef,
    InstanceBinding,
    MandateType,
    SettlementRules,
    VerificationSuite,
)
from agentx_contracts.protocols import Adapter
from agentx_contracts.security import Credential
from agentx_contracts.syscall import (
    GatewayContext,
    Health,
    SyscallRequest,
    SyscallResult,
    SyscallTestCase,
    VerifyOutcome,
)
from agentx_contracts.trigger import DeadlineTrigger
from agentx_kernel.bootstrap import build_phase1_runinvoker
from agentx_kernel.hermes_runner import HermesRunner
from agentx_mandate.harness import Call, Claim, FacultyContext, Finish, Think

NOW = datetime(2026, 6, 17, tzinfo=UTC)


def _ctx() -> FacultyContext:
    return FacultyContext(
        snapshot=HydrationSnapshot(frozen_at=NOW),
        target={"icp": "independent dental clinics", "location": "Pune", "count": 1},
        scratchpad={},
        instance_id="inst_a",
        run_id="run_1",
        ring="L1",
        now=NOW,
    )


def _tool_response(name: str, arguments: dict[str, object], reasoning: str = "thinking...") -> JsonObject:
    """A MiniMax/OpenAI-shaped chat response carrying a single tool call (with preserved reasoning)."""
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": f"<think>{reasoning}</think>",
                    "tool_calls": [
                        {
                            "id": f"call_{name}",
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(arguments)},
                        }
                    ],
                }
            }
        ]
    }


def _text_response(content: str) -> JsonObject:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


class FakeTransport:
    """Records the messages it is sent and replays canned responses in order."""

    def __init__(self, responses: list[JsonObject]) -> None:
        self._responses = responses
        self.sent: list[list[JsonObject]] = []
        self._i = 0

    async def complete_chat(self, *, messages: list[JsonObject], tools: list[JsonObject]) -> JsonObject:
        self.sent.append([dict(m) for m in messages])
        response = self._responses[self._i]
        self._i += 1
        return response


def _runner(responses: list[JsonObject]) -> tuple[HermesRunner, FakeTransport]:
    transport = FakeTransport(responses)
    return HermesRunner(transport=transport), transport


async def test_runner_is_a_hermes_harness() -> None:
    runner, _ = _runner([])
    assert runner.name == "hermes"


async def test_think_tool_call_becomes_a_think_action() -> None:
    runner, _ = _runner([_tool_response("think", {"summary": "the ICP is dental clinics in Pune"})])
    session = runner.start(context=_ctx(), faculties=[])
    action = await session.step(None)
    assert isinstance(action, Think)
    assert "dental clinics" in action.summary


async def test_search_leads_tool_becomes_a_lead_research_batch_call_with_built_criteria() -> None:
    # Concrete per-syscall tools (real param schemas) so MiniMax reliably fills args (vs a free-form blob).
    runner, _ = _runner(
        [
            _tool_response(
                "search_leads",
                {"query": "dental clinic Pune", "icp": "dental clinics", "location": "Pune", "count": 5},
            )
        ]
    )
    session = runner.start(context=_ctx(), faculties=[])
    action = await session.step(None)
    assert isinstance(action, Call)
    assert action.request.name == "lead_research_batch"  # mapped to the syscall name for the gateway
    assert action.request.risk_class == "read"
    assert action.request.ring == "L1"
    assert action.request.instance_id == "inst_a"
    assert action.request.idempotency_key
    criteria = action.request.args["criteria"]
    assert isinstance(criteria, dict)
    assert criteria["query"] == "dental clinic Pune"
    assert action.request.args["count"] == 5


async def test_read_url_tool_becomes_a_read_url_call() -> None:
    runner, _ = _runner([_tool_response("read_url", {"lead_id": "galaxy", "url": "https://galaxy.example"})])
    session = runner.start(context=_ctx(), faculties=[])
    action = await session.step(None)
    assert isinstance(action, Call)
    assert action.request.name == "read_url"
    assert action.request.risk_class == "read"
    assert action.request.args == {"lead_id": "galaxy", "url": "https://galaxy.example"}


async def test_draft_email_tool_is_classified_external_message_and_forces_draft_mode() -> None:
    runner, _ = _runner(
        [_tool_response("draft_email", {"to": "x", "subject": "s", "body": "b", "lead_id": "galaxy"})]
    )
    session = runner.start(context=_ctx(), faculties=[])
    action = await session.step(None)
    assert isinstance(action, Call)
    assert action.request.name == "draft_email"
    assert action.request.risk_class == "external_message"
    assert action.request.args["mode"] == "draft"


async def test_claim_facts_become_a_claim_with_kernel_stamped_provenance() -> None:
    runner, _ = _runner(
        [
            _tool_response(
                "claim_facts",
                {
                    "facts": [
                        {
                            "subject": "galaxy_dental",
                            "predicate": "actionable_lead",
                            "object": "Galaxy Dental Clinic",
                            "confidence": 0.8,
                            "evidence": ["accepting new patients", "https://galaxy.example/contact"],
                        }
                    ]
                },
            )
        ]
    )
    session = runner.start(context=_ctx(), faculties=[])
    action = await session.step(None)
    assert isinstance(action, Claim)
    assert len(action.facts) == 1
    fact = action.facts[0]
    assert fact.predicate == "actionable_lead"
    assert fact.subject == "galaxy_dental"
    # the kernel STAMPS provenance — the LLM proposes content, the kernel disposes run-identity:
    assert fact.provenance.run_id == "run_1"
    assert fact.instance_id == "inst_a"
    assert fact.status == "probation"
    assert "https://galaxy.example/contact" in fact.provenance.evidence


async def test_finish_tool_call_becomes_a_finish_action() -> None:
    runner, _ = _runner([_tool_response("finish", {"summary": "done"})])
    session = runner.start(context=_ctx(), faculties=[])
    action = await session.step(None)
    assert isinstance(action, Finish)


async def test_a_response_with_no_tool_call_is_treated_as_an_implicit_think() -> None:
    runner, _ = _runner([_text_response("I should search for dental clinics first.")])
    session = runner.start(context=_ctx(), faculties=[])
    action = await session.step(None)
    assert isinstance(action, Think)
    assert "search for dental clinics" in action.summary


async def test_observation_is_fed_back_as_a_tool_message_and_reasoning_is_preserved() -> None:
    runner, transport = _runner(
        [
            _tool_response("search_leads", {"query": "dental clinic Pune", "count": 1}, "step1"),
            _tool_response("finish", {"summary": "done"}, "step2"),
        ]
    )
    session = runner.start(context=_ctx(), faculties=[])
    call = await session.step(None)
    assert isinstance(call, Call)
    observation = SyscallResult(
        status="ok",
        output={"leads": [{"id": "galaxy", "company": "Galaxy Dental"}]},
        idempotency_key=call.request.idempotency_key,
        fulfilled_by="firecrawl",
        maturity_used=3,
    )
    finish = await session.step(observation)
    assert isinstance(finish, Finish)

    # The SECOND request must contain: the preserved assistant reasoning + a tool message echoing the result.
    second_request = transport.sent[1]
    roles = [m.get("role") for m in second_request]
    assert "tool" in roles
    tool_msg = next(m for m in second_request if m.get("role") == "tool")
    assert "Galaxy Dental" in str(tool_msg.get("content"))
    assert tool_msg.get("tool_call_id") == call.request.idempotency_key or tool_msg.get("tool_call_id")
    # the prior assistant turn (with <think>) is preserved in history (interleaved-thinking requirement):
    assert any(m.get("role") == "assistant" and "step1" in str(m.get("content")) for m in second_request)


async def test_session_state_round_trips_message_history_for_process_safe_resume() -> None:
    before_runner, _ = _runner(
        [_tool_response("search_leads", {"query": "dental clinic Pune", "count": 1}, "persist me")]
    )
    before = before_runner.start(context=_ctx(), faculties=[])
    call = await before.step(None)
    assert isinstance(call, Call)
    state = before.export_state()

    after_runner, after_transport = _runner([_tool_response("finish", {"summary": "done"}, "continued")])
    after = after_runner.start(context=_ctx(), faculties=[], cursor=before.cursor)
    after.restore_state(state)
    result = await after.step(
        SyscallResult(
            status="ok",
            output={"leads": [{"id": "galaxy", "company": "Galaxy Dental"}]},
            idempotency_key=call.request.idempotency_key,
            fulfilled_by="firecrawl",
            maturity_used=3,
        )
    )

    assert isinstance(result, Finish)
    sent = after_transport.sent[0]
    assert any(message.get("role") == "assistant" and "persist me" in str(message.get("content")) for message in sent)
    assert any(message.get("role") == "tool" and "Galaxy Dental" in str(message.get("content")) for message in sent)


class ScriptedAdapter:
    """A single adapter that fulfils research/read_url/draft_email with canned output (live-mode test)."""

    name: str = "scripted"
    category: str = "multi"
    maturity_level: MaturityLevel = 3
    risk_class: str = "read"
    required_ring: Ring = "L0"
    tenant_auth: TenantAuth = "manual"
    input_schema: JsonSchema = {}
    output_schema: JsonSchema = {}
    fixtures: list[SyscallTestCase] = []
    is_terminal_fallback: bool = False

    def can_handle(self, req: SyscallRequest, ctx: GatewayContext) -> bool:
        return True

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        if req.name == "lead_research_batch":
            output: JsonObject = {"leads": [{"id": "galaxy", "company": "Galaxy Dental Clinic", "url": "https://galaxy.example"}]}
        elif req.name == "read_url":
            output = {
                "lead_id": req.args.get("lead_id"),
                "url": req.args.get("url"),
                "title": "Galaxy Dental Clinic",
                "markdown": "Dr. Asha Kulkarni is accepting new patients. [Book an appointment](/contact)",
            }
        else:
            output = {"draft_id": "d1"}
        return SyscallResult(
            status="ok", output=output, idempotency_key=req.idempotency_key, fulfilled_by=self.name, maturity_used=3
        )

    async def dry_run(self, req: SyscallRequest) -> SyscallResult:
        return SyscallResult(status="ok", idempotency_key=req.idempotency_key, fulfilled_by=self.name, maturity_used=3)

    async def verify(self, result: SyscallResult) -> VerifyOutcome:
        return VerifyOutcome(ok=result.status == "ok")

    async def health_check(self) -> Health:
        return Health(status="ok", checked_at=NOW)


class AllAdapterRegistry:
    def __init__(self) -> None:
        self._adapter: Adapter = ScriptedAdapter()

    def register(self, adapter: Adapter) -> None:
        self._adapter = adapter

    def adapters(self) -> list[Adapter]:
        return [self._adapter]

    def resolve(self, req: SyscallRequest, ctx: GatewayContext) -> Adapter:
        return self._adapter


def _live_mandate() -> MandateType:
    return MandateType(
        id="type_lead_finder_v0",
        name="lead-finder",
        version="0.1.0",
        charter=Charter(
            goal="Find and score qualified leads for an ICP, with evidence for each.",
            postconditions=[
                Condition(id="has_claimed_facts", description="x", rung="rules", expr="claimed_facts >= 1"),
                Condition(id="has_actionable", description="x", rung="rules", expr="fact:actionable_lead exists"),
            ],
            target={"icp": "independent dental clinics", "location": "Pune", "count": 1},
        ),
        faculties=[FacultyBinding(faculty_name="research"), FacultyBinding(faculty_name="memory-craft")],
        domain_pack=DomainPackRef(name="indian-smb-leads", version="0.1.0"),
        verification=VerificationSuite(),
        settlement=SettlementRules(watch_window_hours=72),
    )


async def test_run_loop_drives_hermes_through_a_live_trajectory_to_an_approval_park() -> None:
    # End-to-end OFFLINE: live mode routes reads through the gateway, feeds each SyscallResult back to the
    # next step, accumulates the LLM's claims, and parks the LLM-authored draft for human approval (L1<L2).
    score = {
        "subject": "galaxy",
        "predicate": "qualified_lead_score",
        "object": "0.9",
        "confidence": 0.9,
        "evidence": ["accepting new patients"],
    }
    actionable = {
        "subject": "galaxy",
        "predicate": "actionable_lead",
        "object": "Galaxy Dental Clinic",
        "confidence": 0.9,
        "evidence": ["accepting new patients", "https://galaxy.example/contact"],
    }
    draft_args: dict[str, object] = {
        "to": "x",
        "subject": "Outreach to Galaxy Dental",
        "body": "Hi Dr. Asha Kulkarni, I noticed you are accepting new patients...",
        "lead_id": "galaxy",
        "mode": "draft",
    }
    responses = [
        _tool_response("think", {"summary": "plan: search Pune dental clinics"}),
        _tool_response("search_leads", {"query": "dental clinic Pune", "icp": "dental"}),
        _tool_response("read_url", {"lead_id": "galaxy", "url": "https://galaxy.example"}),
        _tool_response("claim_facts", {"facts": [score, actionable]}),
        _tool_response("draft_email", draft_args),
    ]
    runner, _ = _runner(responses)
    instance = InstanceBinding(instance_id="inst_a", type_ref="lead-finder@0.1.0", ring="L1", heap_region_id="heap_a")
    result = await build_phase1_runinvoker(registry=AllAdapterRegistry(), runner=runner).invoke(
        mandate=_live_mandate(),
        instance=instance,
        trigger=DeadlineTrigger(ts=NOW, reason="sweep", entity_id="galaxy"),
        mode="live",
    )

    assert result.state == "parked"
    assert result.park is not None
    assert result.park.approval_card["syscall"] == "draft_email"
    card_args = result.park.approval_card["args"]
    assert isinstance(card_args, dict)
    assert "Asha Kulkarni" in str(card_args["body"])  # the LLM-authored, grounded draft body
    assert any(f.predicate == "actionable_lead" for f in result.claimed_facts)  # the LLM's claim, disposed
    assert any(e.kind == "syscall_result" for e in result.trace.events)  # reads went through the gateway


async def test_live_style_hermes_park_resumes_from_persisted_history_and_settles() -> None:
    facts = [
        {
            "subject": "galaxy",
            "predicate": "qualified_lead_score",
            "object": "0.9",
            "confidence": 0.9,
            "evidence": ["accepting new patients"],
        },
        {
            "subject": "galaxy",
            "predicate": "actionable_lead",
            "object": "Galaxy Dental Clinic",
            "confidence": 0.9,
            "evidence": ["accepting new patients"],
        },
    ]
    responses = [
        _tool_response("think", {"summary": "plan"}),
        _tool_response("search_leads", {"query": "dental clinic Pune", "count": 1}),
        _tool_response("read_url", {"lead_id": "galaxy", "url": "https://galaxy.example"}),
        _tool_response("claim_facts", {"facts": facts}),
        _tool_response(
            "draft_email",
            {"to": "x", "subject": "s", "body": "accepting new patients", "lead_id": "galaxy"},
            "draft is ready",
        ),
        _tool_response("finish", {"summary": "approved draft completed"}, "continue after approval"),
    ]
    runner, transport = _runner(responses)
    instance = InstanceBinding(
        instance_id="inst_a",
        type_ref="lead-finder@0.1.0",
        ring="L1",
        heap_region_id="heap_a",
    )
    invoker = build_phase1_runinvoker(registry=AllAdapterRegistry(), runner=runner)
    parked = await invoker.invoke(
        mandate=_live_mandate(),
        instance=instance,
        trigger=DeadlineTrigger(ts=NOW, reason="sweep", entity_id="galaxy"),
        mode="live",
    )
    approval = await invoker.journal.append(
        ApprovalResolved(
            event_id=f"{parked.run_id}:approval:resolved",
            seq=0,
            ts=NOW,
            instance_id=instance.instance_id,
            run_id=parked.run_id,
            actor="manager:test",
            decision="approve",
        )
    )
    assert isinstance(approval, ApprovalResolved)

    resumed = await invoker.resume(run_id=parked.run_id, approval=approval)

    assert resumed.state == "settled"
    assert len(transport.sent) == 6
    final_messages = transport.sent[-1]
    assert any(
        message.get("role") == "assistant" and "draft is ready" in str(message.get("content"))
        for message in final_messages
    )
    assert any(
        message.get("role") == "tool" and "draft_id" in str(message.get("content"))
        for message in final_messages
    )
    events = await invoker.journal.read_run(parked.run_id)
    attempts = [event for event in events if isinstance(event, SyscallAttempted) and event.syscall == "draft_email"]
    settled = [event for event in events if isinstance(event, SyscallSettled) and event.syscall == "draft_email"]
    assert len(attempts) == 1
    assert len(settled) == 1
