"""P11 kernel-side lead-finder integration with the mandate library."""

from datetime import UTC, datetime

from agentx_contracts.mandate import InstanceBinding
from agentx_contracts.protocols import Adapter
from agentx_contracts.security import Credential
from agentx_contracts.syscall import GatewayContext, Health, SyscallRequest, SyscallResult, VerifyOutcome
from agentx_contracts.trigger import DeadlineTrigger
from agentx_kernel.bootstrap import build_phase1_runinvoker
from agentx_mandate.library.lead_finder import build_lead_finder_type

NOW = datetime(2026, 6, 17, tzinfo=UTC)


class DraftAdapter:
    name = "stub_draft"
    category = "draft_email"
    maturity_level = 1
    risk_class = "external_message"
    required_ring = "L2"
    tenant_auth = "manual"
    input_schema: dict[str, object] = {}
    output_schema: dict[str, object] = {}
    fixtures = []
    is_terminal_fallback = False

    def can_handle(self, req: SyscallRequest, ctx: GatewayContext) -> bool:
        return req.name == "draft_email"

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


class DraftRegistry:
    def __init__(self) -> None:
        self._adapter = DraftAdapter()

    def register(self, adapter: Adapter) -> None:
        self._adapter = adapter  # type: ignore[assignment]

    def adapters(self) -> list[Adapter]:
        return [self._adapter]  # type: ignore[list-item]

    def resolve(self, req: SyscallRequest, ctx: GatewayContext) -> Adapter:
        return self._adapter  # type: ignore[return-value]


def _instance(ring: str) -> InstanceBinding:
    return InstanceBinding(
        instance_id="inst_a",
        type_ref="lead-finder@0.1.0",
        ring=ring,
        heap_region_id="heap_a",
    )


async def test_library_lead_finder_parks_at_l1_with_no_registry() -> None:
    result = await build_phase1_runinvoker().invoke(
        mandate=build_lead_finder_type(),
        instance=_instance("L1"),
        trigger=DeadlineTrigger(ts=NOW, reason="sweep", entity_id="lead_1"),
        mode="sim",
    )

    assert result.state == "parked"
    assert result.park is not None
    assert result.park.awaiting == "human_approval"
    assert result.park.required_ring == "L2"


async def test_library_lead_finder_executes_and_settles_with_stub_registry() -> None:
    result = await build_phase1_runinvoker(registry=DraftRegistry()).invoke(
        mandate=build_lead_finder_type(),
        instance=_instance("L2"),
        trigger=DeadlineTrigger(ts=NOW, reason="sweep", entity_id="lead_1"),
        mode="sim",
    )

    assert result.state == "settled"
    assert result.settlement is not None
    assert all(fact.provenance.run_id == result.run_id for fact in result.settlement.facts)
