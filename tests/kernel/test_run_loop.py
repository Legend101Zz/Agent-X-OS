"""P9 Phase-1 RunInvoker: hydrate -> faculty actions -> gateway -> verify -> settle."""

from datetime import UTC, datetime

from agentx_contracts.enums import MaturityLevel, Ring, TenantAuth
from agentx_contracts.faculty import FacultyBinding
from agentx_contracts.journal import ApprovalResolved, SyscallAttempted, SyscallSettled
from agentx_contracts.jsontypes import JsonSchema
from agentx_contracts.mandate import (
    Charter,
    Condition,
    DomainPackRef,
    HydrationSnapshot,
    InstanceBinding,
    MandateType,
    SettlementRules,
    VerificationSuite,
)
from agentx_contracts.memory import Fact, Provenance
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
from agentx_kernel.run_loop import _apply_read_result, _run_id
from agentx_mandate.harness import Call, Claim, FacultyContext, Finish, OwnHarness, Think
from agentx_mandate.library.lead_finder_playbook import build_outreach_call, first_actionable_lead_id

NOW = datetime(2026, 6, 17, tzinfo=UTC)


def _mandate() -> MandateType:
    return MandateType(
        id="type_lead_finder_v0",
        name="lead-finder",
        version="0.1.0",
        charter=Charter(
            goal="Find and score qualified leads.",
            postconditions=[
                Condition(
                    id="has_claimed_facts",
                    description="At least one fact was claimed.",
                    rung="rules",
                    expr="claimed_facts >= 1",
                ),
                Condition(
                    id="has_lead_score",
                    description="A lead score fact exists.",
                    rung="rules",
                    expr="fact:qualified_lead_score exists",
                ),
            ],
            target={"icp": "independent dental clinics", "location": "Pune", "count": 1},
        ),
        faculties=[
            FacultyBinding(faculty_name="research"),
            FacultyBinding(faculty_name="judgment"),
            FacultyBinding(faculty_name="memory-craft"),
            FacultyBinding(faculty_name="escalation"),
        ],
        domain_pack=DomainPackRef(name="indian-smb-leads", version="0.1.0"),
        verification=VerificationSuite(),
        settlement=SettlementRules(watch_window_hours=72),
    )


def _instance(ring: Ring) -> InstanceBinding:
    return InstanceBinding(instance_id="inst_a", type_ref="lead-finder@0.1.0", ring=ring, heap_region_id="heap_a")


class DraftAdapter:
    name: str = "stub_draft"
    category: str = "draft_email"
    maturity_level: MaturityLevel = 1
    risk_class: str = "external_message"
    required_ring: Ring = "L2"
    tenant_auth: TenantAuth = "manual"
    input_schema: JsonSchema = {}
    output_schema: JsonSchema = {}
    fixtures: list[SyscallTestCase] = []
    is_terminal_fallback: bool = False

    def can_handle(self, req: SyscallRequest, ctx: GatewayContext) -> bool:
        return req.name == "draft_email" and ctx.instance_id == "inst_a"

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        return SyscallResult(
            status="ok",
            output={"draft_id": "draft_1"},
            idempotency_key=req.idempotency_key,
            fulfilled_by=self.name,
            maturity_used=1,
        )

    async def dry_run(self, req: SyscallRequest) -> SyscallResult:
        return SyscallResult(
            status="ok",
            idempotency_key=req.idempotency_key,
            fulfilled_by=self.name,
            maturity_used=1,
        )

    async def verify(self, result: SyscallResult) -> VerifyOutcome:
        return VerifyOutcome(ok=result.status == "ok")

    async def health_check(self) -> Health:
        return Health(status="ok", checked_at=NOW)


class ErroringDraftAdapter(DraftAdapter):
    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        return SyscallResult(
            status="error",
            output={},
            idempotency_key=req.idempotency_key,
            fulfilled_by=self.name,
            maturity_used=1,
            error="provider down",
        )


class CountingDraftAdapter(DraftAdapter):
    def __init__(self) -> None:
        self.execute_count = 0
        self.idempotency_keys: list[str] = []

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        self.execute_count += 1
        self.idempotency_keys.append(req.idempotency_key)
        return await super().execute(req, cred)


class SingleAdapterRegistry:
    def __init__(self) -> None:
        self._adapter: Adapter = DraftAdapter()

    def register(self, adapter: Adapter) -> None:
        self._adapter = adapter

    def adapters(self) -> list[Adapter]:
        return [self._adapter]

    def resolve(self, req: SyscallRequest, ctx: GatewayContext) -> Adapter:
        return self._adapter


async def test_phase1_runinvoker_parks_l1_draft_email_before_registry_resolution() -> None:
    result = await build_phase1_runinvoker().invoke(
        mandate=_mandate(),
        instance=_instance("L1"),
        trigger=DeadlineTrigger(ts=NOW, reason="sweep", entity_id="lead_1"),
        mode="sim",
    )

    assert result.state == "parked"
    assert result.park is not None
    assert result.park.awaiting == "human_approval"
    assert result.park.required_ring == "L2"
    assert result.trace.run_id == result.run_id


async def test_phase1_runinvoker_executes_and_settles_at_l2_with_injected_registry() -> None:
    result = await build_phase1_runinvoker(registry=SingleAdapterRegistry()).invoke(
        mandate=_mandate(),
        instance=_instance("L2"),
        trigger=DeadlineTrigger(ts=NOW, reason="sweep", entity_id="lead_1"),
        mode="sim",
    )

    assert result.state == "settled"
    assert result.settlement is not None
    assert result.settlement.facts
    assert all(fact.provenance.run_id == result.run_id for fact in result.settlement.facts)
    assert any(event.kind == "syscall_result" for event in result.trace.events)


def test_read_url_enrichment_merges_by_lead_id_and_draft_uses_actionable_signal() -> None:
    ctx = FacultyContext(
        snapshot=HydrationSnapshot(frozen_at=NOW),
        target={"icp": "independent dental clinics", "location": "Pune"},
        scratchpad={
            "leads": [
                {"id": "article", "company": "10 Best Clinics", "url": "https://youtube.com/watch/1"},
                {
                    "id": "clinic",
                    "company": "Contact | Galaxy Dental Clinic",
                    "url": "https://galaxy.example",
                    "evidence": ["Pune clinic"],
                },
            ]
        },
        instance_id="inst_a",
        run_id="run_1",
        ring="L1",
        now=NOW,
    )
    request = SyscallRequest(
        name="read_url",
        args={"lead_id": "clinic", "url": "https://galaxy.example"},
        instance_id="inst_a",
        run_id="run_1",
        idempotency_key="run_1:read:clinic",
        ring="L1",
        risk_class="read",
    )

    _apply_read_result(
        ctx,
        request,
        {
            "url": "https://galaxy.example",
            "title": "Contact | Galaxy Dental Clinic",
            "markdown": (
                "# Galaxy Dental Clinic\n"
                "Dr. Asha Kulkarni and the team are accepting new patients.\n"
                "[Book an appointment](/contact)"
            ),
            "evidence": ["Dr. Asha Kulkarni and the team are accepting new patients."],
        },
    )
    ctx.scratchpad["scores"] = {"clinic": {"score": 1.0, "reason": "actionable"}}

    assert first_actionable_lead_id(ctx) == "clinic"
    call = build_outreach_call(ctx)
    assert call is not None
    body = str(call.request.args["body"])
    assert "Hi Dr. Asha Kulkarni" in body
    assert "accepting new patients" in body
    assert "https://galaxy.example/contact" in body
    assert "10 Best Clinics" not in body


async def test_runinvoker_disposes_an_injected_runner_trajectory_not_a_hardcoded_order() -> None:
    # G1: the trajectory comes from the HarnessRunner (here a recorded `own` double), not a hardcoded
    # faculty order. The kernel DISPOSES each step: Think -> trace, Claim -> facts, Call -> gateway, Finish.
    # The harness stamps the CURRENT run's provenance onto claimed facts (invariant #1, enforced at settle).
    instance = _instance("L2")
    trigger = DeadlineTrigger(ts=NOW, reason="sweep", entity_id="lead_1")
    run_id = _run_id(instance, trigger)
    score_fact = Fact(
        id=f"{run_id}:lead_1:score",
        instance_id="inst_a",
        subject="lead_1",
        predicate="qualified_lead_score",
        object="0.9",
        confidence=0.9,
        source="agent-inferred",
        provenance=Provenance(run_id=run_id, evidence=["accepting new patients"]),
        status="probation",
        created_at=NOW,
    )
    runner = OwnHarness(
        recorded=[
            Think(summary="LLM is deciding the trajectory"),
            Claim(facts=[score_fact]),
            Call(
                request=SyscallRequest(
                    name="draft_email",
                    args={"lead_id": "lead_1", "mode": "draft", "to": "x", "subject": "s", "body": "b"},
                    instance_id="inst_a",
                    run_id="seed",
                    idempotency_key="seed:draft_email",
                    ring="L2",
                    risk_class="external_message",
                )
            ),
            Finish(),
        ]
    )
    result = await build_phase1_runinvoker(registry=SingleAdapterRegistry(), runner=runner).invoke(
        mandate=_mandate(),
        instance=instance,
        trigger=trigger,
        mode="sim",
    )

    assert result.state == "settled"
    assert any(e.kind == "thought" and "deciding the trajectory" in e.summary for e in result.trace.events)
    assert result.settlement is not None
    assert any(f.predicate == "qualified_lead_score" for f in result.settlement.facts)


async def test_syscall_error_is_fed_back_to_the_harness_not_crashed() -> None:
    # An agent loop must not crash on a failed syscall — the kernel traces it and feeds the error result
    # back so the harness (an LLM) can recover. Here a recorded double simply proceeds to claim + finish.
    instance = _instance("L2")
    trigger = DeadlineTrigger(ts=NOW, reason="sweep", entity_id="lead_1")
    run_id = _run_id(instance, trigger)
    fact = Fact(
        id=f"{run_id}:lead_1:score",
        instance_id="inst_a",
        subject="lead_1",
        predicate="qualified_lead_score",
        object="0.9",
        confidence=0.9,
        source="agent-inferred",
        provenance=Provenance(run_id=run_id, evidence=["signal"]),
        status="probation",
        created_at=NOW,
    )
    runner = OwnHarness(
        recorded=[
            Call(
                request=SyscallRequest(
                    name="draft_email",
                    args={"lead_id": "lead_1", "body": "b"},
                    instance_id="inst_a",
                    run_id="seed",
                    idempotency_key="seed:draft_email",
                    ring="L2",
                    risk_class="external_message",
                )
            ),
            Claim(facts=[fact]),
            Finish(),
        ]
    )
    registry = SingleAdapterRegistry()
    registry.register(ErroringDraftAdapter())
    result = await build_phase1_runinvoker(registry=registry, runner=runner).invoke(
        mandate=_mandate(), instance=instance, trigger=trigger, mode="sim"
    )

    assert result.state == "settled"  # the syscall error did NOT crash the run
    assert any(e.kind == "error" and "draft_email" in e.summary for e in result.trace.events)
    assert result.settlement is not None and any(f.predicate == "qualified_lead_score" for f in result.settlement.facts)


async def test_kernel_resume_replays_approved_parked_call_once_then_continues_to_settle() -> None:
    instance = _instance("L1")
    trigger = DeadlineTrigger(ts=NOW, reason="sweep", entity_id="lead_1")
    run_id = _run_id(instance, trigger)
    score_fact = Fact(
        id=f"{run_id}:lead_1:score",
        instance_id=instance.instance_id,
        subject="lead_1",
        predicate="qualified_lead_score",
        object="0.9",
        confidence=0.9,
        source="agent-inferred",
        provenance=Provenance(run_id=run_id, evidence=["accepting new patients"]),
        status="probation",
        created_at=NOW,
    )
    pending_key = f"{run_id}:draft_email:1"
    runner = OwnHarness(
        recorded=[
            Claim(facts=[score_fact]),
            Call(
                request=SyscallRequest(
                    name="draft_email",
                    args={"lead_id": "lead_1", "mode": "draft", "subject": "s", "body": "b"},
                    instance_id=instance.instance_id,
                    run_id=run_id,
                    idempotency_key=pending_key,
                    ring="L1",
                    risk_class="external_message",
                )
            ),
            Finish(),
        ]
    )
    adapter = CountingDraftAdapter()
    registry = SingleAdapterRegistry()
    registry.register(adapter)
    invoker = build_phase1_runinvoker(registry=registry, runner=runner)

    parked = await invoker.invoke(mandate=_mandate(), instance=instance, trigger=trigger, mode="sim")
    assert parked.state == "parked"
    assert adapter.execute_count == 0

    approval = ApprovalResolved(
        event_id=f"{run_id}:approval:resolved",
        seq=0,
        ts=NOW,
        instance_id=instance.instance_id,
        run_id=run_id,
        actor="manager:test",
        decision="approve",
    )
    journaled = await invoker.journal.append(approval)
    assert isinstance(journaled, ApprovalResolved)

    resumed = await invoker.resume(run_id=run_id, approval=journaled)

    assert resumed.state == "settled"
    assert resumed.settlement is not None
    assert adapter.execute_count == 1
    assert adapter.idempotency_keys == [pending_key]
    events = await invoker.journal.read_run(run_id)
    attempts = [event for event in events if isinstance(event, SyscallAttempted)]
    settled = [event for event in events if isinstance(event, SyscallSettled)]
    assert len(attempts) == 1
    assert len(settled) == 1
    assert attempts[0].event_id == f"{pending_key}:attempt"
    assert settled[0].idempotency_key == pending_key
