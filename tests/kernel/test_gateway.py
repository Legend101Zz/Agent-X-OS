"""P7 syscall gateway: ring checks, idempotency, credential injection, and journaling."""

from datetime import UTC, datetime

from agentx_contracts.protocols import Adapter
from agentx_contracts.security import Credential
from agentx_contracts.syscall import GatewayContext, Health, SyscallRequest, SyscallResult, VerifyOutcome
from agentx_kernel.gateway import Gateway
from agentx_kernel.stores.memory import InMemoryJournalStore, InMemoryVault

NOW = datetime(2026, 6, 17, tzinfo=UTC)


def _ctx(ring: str = "L1") -> GatewayContext:
    return GatewayContext(instance_id="inst_a", run_id="run_1", tenant_id="tenant_a", ring=ring, now=NOW)


def _req(name: str, idem: str = "idem-1") -> SyscallRequest:
    return SyscallRequest(name=name, instance_id="inst_a", run_id="run_1", idempotency_key=idem, ring="L0")


class StubAdapter:
    name = "stub_research"
    category = "lead_research_batch"
    maturity_level = 2
    risk_class = "read"
    required_ring = "L0"
    tenant_auth = "api_key"
    input_schema: dict[str, object] = {}
    output_schema: dict[str, object] = {}
    fixtures = []
    is_terminal_fallback = False

    def __init__(self) -> None:
        self.calls = 0
        self.last_credential: Credential | None = None
        self.last_request: SyscallRequest | None = None

    def can_handle(self, req: SyscallRequest, ctx: GatewayContext) -> bool:
        return req.name == self.category and ctx.instance_id == "inst_a"

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        self.calls += 1
        self.last_credential = cred
        self.last_request = req
        return SyscallResult(
            status="ok",
            output={"count": 2},
            idempotency_key=req.idempotency_key,
            fulfilled_by=self.name,
            maturity_used=self.maturity_level,
        )

    async def dry_run(self, req: SyscallRequest) -> SyscallResult:
        return SyscallResult(
            status="ok",
            idempotency_key=req.idempotency_key,
            fulfilled_by=self.name,
            maturity_used=self.maturity_level,
        )

    async def verify(self, result: SyscallResult) -> VerifyOutcome:
        return VerifyOutcome(ok=result.status == "ok")

    async def health_check(self) -> Health:
        return Health(status="ok", checked_at=NOW)


class StubRegistry:
    def __init__(self, adapter: Adapter) -> None:
        self._adapter = adapter
        self.resolve_calls = 0

    def register(self, adapter: Adapter) -> None:
        self._adapter = adapter

    def adapters(self) -> list[Adapter]:
        return [self._adapter]

    def resolve(self, req: SyscallRequest, ctx: GatewayContext) -> Adapter:
        self.resolve_calls += 1
        return self._adapter


async def test_ring_check_parks_before_registry_resolution() -> None:
    adapter = StubAdapter()
    registry = StubRegistry(adapter)
    journal = InMemoryJournalStore()

    outcome = await Gateway(journal=journal, vault=InMemoryVault(), registry=registry).invoke(
        _req("draft_email"),
        _ctx(ring="L1"),
    )

    assert outcome.result is None
    assert outcome.parked is not None
    assert outcome.parked.awaiting == "human_approval"
    assert outcome.parked.required_ring == "L2"
    assert registry.resolve_calls == 0
    assert adapter.calls == 0


async def test_allowed_syscall_executes_with_injected_credential_and_journals_attempt_and_settle() -> None:
    adapter = StubAdapter()
    registry = StubRegistry(adapter)
    journal = InMemoryJournalStore()

    outcome = await Gateway(journal=journal, vault=InMemoryVault(), registry=registry).invoke(
        _req("lead_research_batch"),
        _ctx(ring="L0"),
    )

    assert outcome.result is not None
    assert outcome.result.status == "ok"
    assert adapter.calls == 1
    assert adapter.last_credential is not None
    assert adapter.last_credential.ref == "vault://tenant_a/stub_research"
    assert adapter.last_request is not None
    assert adapter.last_request.risk_class == "read"

    events = await journal.read_run("run_1")
    assert [event.kind for event in events] == ["syscall_attempted", "syscall_settled"]


async def test_duplicate_idempotency_key_returns_prior_result_without_reexecuting_adapter() -> None:
    adapter = StubAdapter()
    registry = StubRegistry(adapter)
    gateway = Gateway(journal=InMemoryJournalStore(), vault=InMemoryVault(), registry=registry)

    first = await gateway.invoke(_req("lead_research_batch", idem="idem-repeat"), _ctx(ring="L0"))
    second = await gateway.invoke(_req("lead_research_batch", idem="idem-repeat"), _ctx(ring="L0"))

    assert first.result is not None and first.result.status == "ok"
    assert second.result is not None and second.result.status == "ok"
    assert second.result.fulfilled_by == "stub_research"
    assert adapter.calls == 1


async def test_missing_registry_parks_to_human_approval() -> None:
    outcome = await Gateway(journal=InMemoryJournalStore(), vault=InMemoryVault(), registry=None).invoke(
        _req("lead_research_batch"),
        _ctx(ring="L0"),
    )

    assert outcome.parked is not None
    assert outcome.parked.awaiting == "human_approval"
    assert outcome.parked.reason == "no syscall registry available"
    assert outcome.result is None
