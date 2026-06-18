"""P7 syscall gateway: ring checks, idempotency, credential injection, and journaling."""

from datetime import UTC, datetime

import pytest
from agentx_contracts.enums import MaturityLevel, Ring, TenantAuth
from agentx_contracts.jsontypes import JsonSchema
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
from agentx_kernel.errors import IdempotencyRequestConflict
from agentx_kernel.gateway import Gateway
from agentx_kernel.stores.memory import InMemoryJournalStore, InMemoryVault

NOW = datetime(2026, 6, 17, tzinfo=UTC)


def _ctx(ring: Ring = "L1") -> GatewayContext:
    return GatewayContext(instance_id="inst_a", run_id="run_1", tenant_id="tenant_a", ring=ring, now=NOW)


def _req(name: str, idem: str = "idem-1") -> SyscallRequest:
    return SyscallRequest(name=name, instance_id="inst_a", run_id="run_1", idempotency_key=idem, ring="L0")


class StubAdapter:
    name: str = "stub_research"
    category: str = "lead_research_batch"
    maturity_level: MaturityLevel = 2
    risk_class: str = "read"
    required_ring: Ring = "L0"
    tenant_auth: TenantAuth = "api_key"
    input_schema: JsonSchema = {}
    output_schema: JsonSchema = {}
    fixtures: list[SyscallTestCase] = []
    is_terminal_fallback: bool = False

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


class RaisingAdapter(StubAdapter):
    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        raise ValueError("missing string arg: url")


async def test_adapter_exception_becomes_an_error_result_not_an_uncaught_crash() -> None:
    # An adapter that raises (e.g. bad LLM-supplied args) must NOT crash the kernel — the gateway turns it
    # into an error SyscallResult and still journals attempted + settled, so the run loop can feed it back.
    registry = StubRegistry(RaisingAdapter())
    journal = InMemoryJournalStore()

    outcome = await Gateway(journal=journal, vault=InMemoryVault(), registry=registry).invoke(
        _req("lead_research_batch"),
        _ctx(ring="L0"),
    )

    assert outcome.result is not None
    assert outcome.result.status == "error"
    assert "missing string arg: url" in (outcome.result.error or "")
    assert [event.kind for event in await journal.read_run("run_1")] == ["syscall_attempted", "syscall_settled"]


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
    assert outcome.attempted is not None
    assert outcome.attempted.syscall == "draft_email"
    assert registry.resolve_calls == 0
    assert adapter.calls == 0
    assert [event.kind for event in await journal.read_run("run_1")] == ["syscall_attempted", "run_parked"]


async def test_approved_retry_reuses_parked_attempt_instead_of_appending_another() -> None:
    adapter = StubAdapter()
    registry = StubRegistry(adapter)
    journal = InMemoryJournalStore()
    gateway = Gateway(journal=journal, vault=InMemoryVault(), registry=registry)
    request = _req("draft_email", idem="idem-draft")

    parked = await gateway.invoke(request, _ctx(ring="L1"))
    executed = await gateway.invoke(request, _ctx(ring="L2"))

    assert parked.parked is not None
    assert executed.result is not None and executed.result.status == "ok"
    events = await journal.read_run("run_1")
    assert [event.kind for event in events] == ["syscall_attempted", "run_parked", "syscall_settled"]
    assert sum(event.kind == "syscall_attempted" for event in events) == 1


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
    assert second.result.output == first.result.output == {"count": 2}
    assert second.result.fulfilled_by == "stub_research"
    assert adapter.calls == 1


async def test_duplicate_idempotency_key_rejects_a_different_request() -> None:
    adapter = StubAdapter()
    registry = StubRegistry(adapter)
    gateway = Gateway(journal=InMemoryJournalStore(), vault=InMemoryVault(), registry=registry)

    await gateway.invoke(_req("lead_research_batch", idem="idem-repeat"), _ctx(ring="L0"))
    conflicting = _req("read_url", idem="idem-repeat").model_copy(update={"args": {"url": "https://example.com"}})

    with pytest.raises(IdempotencyRequestConflict, match="idempotency key belongs to a different syscall request"):
        await gateway.invoke(conflicting, _ctx(ring="L0"))


async def test_missing_registry_parks_to_human_approval() -> None:
    outcome = await Gateway(journal=InMemoryJournalStore(), vault=InMemoryVault(), registry=None).invoke(
        _req("lead_research_batch"),
        _ctx(ring="L0"),
    )

    assert outcome.parked is not None
    assert outcome.parked.awaiting == "human_approval"
    assert outcome.parked.reason == "no syscall registry available"
    assert outcome.result is None
