"""P9 Phase-1 RunInvoker: hydrate -> faculty actions -> gateway -> verify -> settle."""

from datetime import UTC, datetime

from agentx_contracts.enums import MaturityLevel, Ring, TenantAuth
from agentx_contracts.faculty import FacultyBinding
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
from agentx_kernel.run_loop import _apply_read_result, _draft_args, _first_lead_id
from agentx_mandate.harness import FacultyContext

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

    assert _first_lead_id(ctx) == "clinic"
    draft = _draft_args(ctx, "clinic")
    assert "Hi Dr. Asha Kulkarni" in str(draft["body"])
    assert "accepting new patients" in str(draft["body"])
    assert "https://galaxy.example/contact" in str(draft["body"])
    assert "10 Best Clinics" not in str(draft["body"])
