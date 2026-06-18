"""G2 integration: approval card -> kernel resume -> idempotent effect -> verify -> settle."""

from datetime import UTC, datetime

from agentx_contracts.enums import MaturityLevel, Ring, TenantAuth
from agentx_contracts.faculty import FacultyBinding
from agentx_contracts.journal import ApprovalResolved, SyscallAttempted, SyscallSettled
from agentx_contracts.jsontypes import JsonSchema
from agentx_contracts.mandate import (
    Charter,
    Condition,
    DomainPackRef,
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
from agentx_kernel.control import KernelControl
from agentx_kernel.gateway import Gateway
from agentx_kernel.hydration import HydrationLoader
from agentx_kernel.projections import Projections
from agentx_kernel.run_loop import Phase1RunInvoker, _run_id
from agentx_kernel.scheduler import ApprovalWork, SchedulerWorker, TriggerWork
from agentx_kernel.settlement import SettlementCommitter
from agentx_kernel.stores.memory import (
    InMemoryJournalStore,
    InMemoryProjectionStore,
    InMemoryRunContinuationStore,
    InMemorySchedulerStore,
    InMemorySyscallReceiptStore,
    InMemoryVault,
)
from agentx_kernel.verifier import RulesVerifier
from agentx_mandate.harness import Call, Claim, Finish, OwnHarness

NOW = datetime(2026, 6, 18, tzinfo=UTC)


class CountingDraftAdapter:
    name = "counting_draft"
    category = "draft_email"
    maturity_level: MaturityLevel = 1
    risk_class = "external_message"
    required_ring: Ring = "L2"
    tenant_auth: TenantAuth = "manual"
    input_schema: JsonSchema = {}
    output_schema: JsonSchema = {}
    fixtures: list[SyscallTestCase] = []
    is_terminal_fallback = False

    def __init__(self) -> None:
        self.execute_count = 0

    def can_handle(self, req: SyscallRequest, ctx: GatewayContext) -> bool:
        return req.name == "draft_email"

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        self.execute_count += 1
        return SyscallResult(
            status="ok",
            output={"draft_id": "draft_1", "sent": False},
            idempotency_key=req.idempotency_key,
            fulfilled_by=self.name,
            maturity_used=1,
        )

    async def dry_run(self, req: SyscallRequest) -> SyscallResult:
        return await self.execute(req, None)

    async def verify(self, result: SyscallResult) -> VerifyOutcome:
        return VerifyOutcome(ok=result.status == "ok")

    async def health_check(self) -> Health:
        return Health(status="ok", checked_at=NOW)


class Registry:
    def __init__(self, adapter: Adapter) -> None:
        self.adapter = adapter

    def register(self, adapter: Adapter) -> None:
        self.adapter = adapter

    def adapters(self) -> list[Adapter]:
        return [self.adapter]

    def resolve(self, req: SyscallRequest, ctx: GatewayContext) -> Adapter:
        return self.adapter


async def test_approval_card_resumes_through_kernel_and_settles_without_double_effect() -> None:
    journal = InMemoryJournalStore()
    store = InMemoryProjectionStore()
    projections = Projections(store, journal)
    adapter = CountingDraftAdapter()
    instance = InstanceBinding(
        instance_id="inst_resume",
        type_ref="lead-finder@0.1.0",
        ring="L1",
        heap_region_id="tenant_resume",
    )
    trigger = DeadlineTrigger(ts=NOW, reason="integration", entity_id="lead_1")
    run_id = _run_id(instance, trigger)
    fact = Fact(
        id=f"{run_id}:lead_1:score",
        instance_id=instance.instance_id,
        subject="lead_1",
        predicate="qualified_lead_score",
        object="0.9",
        confidence=0.9,
        source="agent-inferred",
        provenance=Provenance(run_id=run_id, evidence=["real signal"]),
        status="probation",
        created_at=NOW,
    )
    request = SyscallRequest(
        name="draft_email",
        args={"lead_id": "lead_1", "subject": "Hello", "body": "Grounded draft", "mode": "draft"},
        instance_id=instance.instance_id,
        run_id=run_id,
        idempotency_key=f"{run_id}:draft_email:1",
        ring="L1",
        risk_class="external_message",
    )
    mandate = MandateType(
        id="lead-finder-v0",
        name="lead-finder",
        version="0.1.0",
        charter=Charter(
            goal="Find a lead and draft outreach.",
            postconditions=[
                Condition(
                    id="score",
                    description="score exists",
                    rung="rules",
                    expr="fact:qualified_lead_score exists",
                )
            ],
        ),
        faculties=[FacultyBinding(faculty_name="memory-craft")],
        domain_pack=DomainPackRef(name="test", version="0.1.0"),
        verification=VerificationSuite(),
        settlement=SettlementRules(),
    )
    invoker = Phase1RunInvoker(
        journal=journal,
        projections=projections,
        hydration=HydrationLoader(store, journal),
        gateway=Gateway(
            journal=journal,
            vault=InMemoryVault(),
            registry=Registry(adapter),
            receipts=InMemorySyscallReceiptStore(),
        ),
        settlement=SettlementCommitter(journal=journal, projections=projections),
        verifier=RulesVerifier(),
        continuations=InMemoryRunContinuationStore(),
        runner=OwnHarness(recorded=[Claim(facts=[fact]), Call(request=request), Finish()]),
    )
    control = KernelControl(journal=journal, projections=projections, projection_store=store)
    scheduler_store = InMemorySchedulerStore()
    worker = SchedulerWorker(store=scheduler_store, invoker=invoker)

    trigger_work = TriggerWork.schedule(mandate=mandate, instance=instance, trigger=trigger, mode="sim")
    await scheduler_store.enqueue(trigger_work)
    parked = await worker.run_once(NOW)
    assert parked is not None
    inbox = await control.approval_inbox(instance_id=instance.instance_id)
    assert parked.state == "parked"
    assert parked.park is not None
    assert inbox.items[0].approval_card == parked.park.approval_card

    await control.approve(
        instance_id=instance.instance_id,
        run_id=run_id,
        actor="manager:integration",
        now=NOW,
    )
    approval = next(
        event for event in reversed(await journal.read_run(run_id)) if isinstance(event, ApprovalResolved)
    )
    await scheduler_store.enqueue(ApprovalWork.schedule(approval))
    result = await worker.run_once(NOW)

    assert result is not None
    assert result.state == "settled"
    assert adapter.execute_count == 1
    events = await journal.read_run(run_id)
    assert len([event for event in events if isinstance(event, SyscallAttempted)]) == 1
    assert len([event for event in events if isinstance(event, SyscallSettled)]) == 1
