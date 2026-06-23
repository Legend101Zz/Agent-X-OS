"""Flag #3 — ``SyscallSettled.output`` surfaces an adapter's result payload to the readable trace.

`export_ledger` returns its `.xlsx` path in `SyscallResult.output`, but `SyscallSettled` carried only
syscall/status/fulfilled_by/maturity_used, so `/journal` and `syscall_trace` dropped it. These tests
pin: (1) the contract round-trips with/without `output` (default `{}` keeps old rows valid); (2) the
gateway populates `output` at BOTH settle sites (fresh execution AND idempotent receipt-replay);
(3) the trace projection carries `output` through to the `syscall_trace` doc.
"""

from __future__ import annotations

from datetime import UTC, datetime

from agentx_contracts.enums import MaturityLevel, Ring, TenantAuth
from agentx_contracts.journal import SyscallSettled
from agentx_contracts.jsontypes import JsonObject, JsonSchema
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
from agentx_kernel.gateway import Gateway
from agentx_kernel.projections import Projections
from agentx_kernel.receipts import SyscallReceipt
from agentx_kernel.stores.memory import (
    InMemoryJournalStore,
    InMemoryProjectionStore,
    InMemorySyscallReceiptStore,
    InMemoryVault,
)

NOW = datetime(2026, 6, 23, tzinfo=UTC)

_OUTPUT: JsonObject = {"path": "/books/out/ledger_run_1.xlsx", "filename": "ledger_run_1.xlsx"}


# --- contract round-trip ----------------------------------------------------------------


def test_syscall_settled_defaults_output_to_empty_dict() -> None:
    """Old rows that never set output stay valid: default is an empty dict."""
    event = SyscallSettled(
        event_id="s1", seq=0, ts=NOW, instance_id="inst_a", run_id="run_1",
        syscall="draft_email", status="ok", fulfilled_by="stub", maturity_used=1,
    )
    assert event.output == {}


def test_syscall_settled_round_trips_with_output() -> None:
    event = SyscallSettled(
        event_id="s1", seq=0, ts=NOW, instance_id="inst_a", run_id="run_1",
        syscall="export_ledger", status="ok", fulfilled_by="export_ledger", maturity_used=0,
        output=_OUTPUT,
    )
    dumped = event.model_dump(mode="json")
    assert dumped["output"] == _OUTPUT
    assert SyscallSettled.model_validate(dumped).output == _OUTPUT


# --- gateway populates output at both settle sites --------------------------------------


class _StubAdapter:
    name: str = "stub_writer"
    category: str = "mark_outcome"
    maturity_level: MaturityLevel = 0
    risk_class: str = "reversible_write"
    required_ring: Ring = "L1"
    tenant_auth: TenantAuth = "manual"
    input_schema: JsonSchema = {}
    output_schema: JsonSchema = {}
    fixtures: list[SyscallTestCase] = []
    is_terminal_fallback: bool = False

    def can_handle(self, req: SyscallRequest, ctx: GatewayContext) -> bool:
        return req.name == self.category

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        return SyscallResult(
            status="ok", output=dict(_OUTPUT), idempotency_key=req.idempotency_key,
            fulfilled_by=self.name, maturity_used=self.maturity_level,
        )

    async def dry_run(self, req: SyscallRequest) -> SyscallResult:
        return SyscallResult(
            status="ok", idempotency_key=req.idempotency_key, fulfilled_by=self.name,
            maturity_used=self.maturity_level,
        )

    async def verify(self, result: SyscallResult) -> VerifyOutcome:
        return VerifyOutcome(ok=True)

    async def health_check(self) -> Health:
        return Health(status="ok", checked_at=NOW)


class _StubRegistry:
    def __init__(self, adapter: Adapter) -> None:
        self._adapter = adapter

    def register(self, adapter: Adapter) -> None:
        self._adapter = adapter

    def adapters(self) -> list[Adapter]:
        return [self._adapter]

    def resolve(self, req: SyscallRequest, ctx: GatewayContext) -> Adapter:
        return self._adapter


def _ctx() -> GatewayContext:
    return GatewayContext(instance_id="inst_a", run_id="run_1", tenant_id="tenant_a", ring="L1", now=NOW)


def _req(idem: str = "idem-1") -> SyscallRequest:
    return SyscallRequest(name="mark_outcome", instance_id="inst_a", run_id="run_1", idempotency_key=idem, ring="L1")


async def test_fresh_execution_settles_with_adapter_output() -> None:
    """Line-160 path: a freshly executed write-class syscall carries result.output onto SyscallSettled."""
    journal = InMemoryJournalStore()
    gateway = Gateway(
        journal=journal, vault=InMemoryVault(), registry=_StubRegistry(_StubAdapter()),
        receipts=InMemorySyscallReceiptStore(),
    )
    outcome = await gateway.invoke(_req(), _ctx())
    assert outcome.result is not None and outcome.result.output == _OUTPUT
    assert outcome.settled is not None
    assert outcome.settled.output == _OUTPUT


async def test_idempotent_receipt_replay_settles_with_receipt_output() -> None:
    """Line-239 path: a receipt with no prior SyscallSettled re-emits the settle, carrying receipt output."""
    journal = InMemoryJournalStore()
    receipts = InMemorySyscallReceiptStore()
    req = _req(idem="idem-replay")
    prior_result = SyscallResult(
        status="ok", output=dict(_OUTPUT), idempotency_key=req.idempotency_key,
        fulfilled_by="export_ledger", maturity_used=0,
    )
    await receipts.save(SyscallReceipt.from_execution(req, prior_result))
    gateway = Gateway(
        journal=journal, vault=InMemoryVault(), registry=_StubRegistry(_StubAdapter()), receipts=receipts,
    )
    outcome = await gateway.invoke(req, _ctx())
    assert outcome.settled is not None
    assert outcome.settled.output == _OUTPUT


# --- projection carries output through ---------------------------------------------------


async def test_trace_projection_carries_output() -> None:
    journal = InMemoryJournalStore()
    store = InMemoryProjectionStore()
    proj = Projections(store, journal)
    event = await journal.append(
        SyscallSettled(
            event_id="s1", seq=0, ts=NOW, instance_id="inst_a", run_id="run_1", idempotency_key="idem-1",
            syscall="export_ledger", status="ok", fulfilled_by="export_ledger", maturity_used=0,
            output=_OUTPUT,
        )
    )
    await proj.apply(event)
    rows = await store.find("syscall_trace", {"run_id": "run_1"})
    settled = next(r for r in rows if r["kind"] == "settled")
    assert settled["output"] == _OUTPUT
    assert settled["output"]["path"] == _OUTPUT["path"]
