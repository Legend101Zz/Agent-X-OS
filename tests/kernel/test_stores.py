"""In-memory ProjectionStore + Vault — the derived-state store and the credential-injection stub."""

from datetime import UTC, datetime

import pytest
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.mandate import (
    Charter,
    DomainPackRef,
    HydrationSnapshot,
    InstanceBinding,
    MandateType,
    SettlementRules,
    VerificationSuite,
)
from agentx_contracts.security import Credential
from agentx_contracts.syscall import SyscallRequest, SyscallResult
from agentx_contracts.verification import Trace
from agentx_kernel.continuations import RunContinuation
from agentx_kernel.errors import IdempotencyRequestConflict
from agentx_kernel.ports import RunContinuationStore
from agentx_kernel.receipts import SyscallReceipt
from agentx_kernel.stores.memory import (
    InMemoryProjectionStore,
    InMemoryRunContinuationStore,
    InMemorySyscallReceiptStore,
    InMemoryVault,
)

NOW = datetime(2026, 6, 18, tzinfo=UTC)


def _receipt(*, syscall: str = "draft_email") -> SyscallReceipt:
    request = SyscallRequest(
        name=syscall,
        args={"body": "hello"},
        instance_id="inst_a",
        run_id="run_1",
        idempotency_key="idem-1",
        ring="L2",
    )
    result = SyscallResult(
        status="ok",
        output={"body": "hello", "sent": False},
        idempotency_key="idem-1",
        fulfilled_by="draft_email",
        maturity_used=1,
    )
    return SyscallReceipt.from_execution(request, result)


def _continuation(*, scratchpad: JsonObject | None = None) -> RunContinuation:
    mandate = MandateType(
        id="type_lead_finder_v0",
        name="lead-finder",
        version="0.1.0",
        charter=Charter(goal="Find qualified leads."),
        domain_pack=DomainPackRef(name="dental", version="0.1.0"),
        verification=VerificationSuite(),
        settlement=SettlementRules(),
    )
    return RunContinuation(
        run_id="run_1",
        instance=InstanceBinding(
            instance_id="inst_a",
            type_ref="lead-finder@0.1.0",
            ring="L1",
            heap_region_id="heap_a",
        ),
        mandate=mandate,
        mode="live",
        snapshot=HydrationSnapshot(frozen_at=NOW),
        scratchpad=scratchpad or {"lead_id": "lead_1"},
        trace=Trace(run_id="run_1"),
        claimed_facts=[],
        harness_cursor=3,
        harness_state={"messages": [{"role": "assistant", "content": "draft ready"}]},
        pending_call=SyscallRequest(
            name="draft_email",
            args={"lead_id": "lead_1"},
            instance_id="inst_a",
            run_id="run_1",
            idempotency_key="run_1:draft:1",
            ring="L1",
            risk_class="external_message",
        ),
    )


async def test_projection_upsert_is_idempotent_replace() -> None:
    store = InMemoryProjectionStore()
    await store.upsert("heap_fact", "f1", {"id": "f1", "object": "v1"})
    await store.upsert("heap_fact", "f1", {"id": "f1", "object": "v2"})  # replace, not duplicate
    got = await store.get("heap_fact", "f1")
    assert got == {"id": "f1", "object": "v2"}


async def test_projection_get_missing_returns_none() -> None:
    store = InMemoryProjectionStore()
    assert await store.get("heap_fact", "nope") is None


async def test_projection_find_by_equality_query() -> None:
    store = InMemoryProjectionStore()
    await store.upsert("heap_fact", "f1", {"id": "f1", "instance_id": "a", "status": "probation"})
    await store.upsert("heap_fact", "f2", {"id": "f2", "instance_id": "a", "status": "promoted"})
    await store.upsert("heap_fact", "f3", {"id": "f3", "instance_id": "b", "status": "probation"})
    found = await store.find("heap_fact", {"instance_id": "a"})
    assert {d["id"] for d in found} == {"f1", "f2"}
    probation_a = await store.find("heap_fact", {"instance_id": "a", "status": "probation"})
    assert [d["id"] for d in probation_a] == ["f1"]


async def test_in_memory_syscall_receipt_round_trips_and_rejects_conflicts() -> None:
    store = InMemorySyscallReceiptStore()
    receipt = _receipt()

    await store.save(receipt)
    await store.save(receipt)

    assert await store.get("idem-1") == receipt
    with pytest.raises(IdempotencyRequestConflict):
        await store.save(_receipt(syscall="read_url"))


async def test_in_memory_run_continuation_upserts_by_run_id_and_returns_defensive_copies() -> None:
    store = InMemoryRunContinuationStore()
    assert isinstance(store, RunContinuationStore)
    continuation = _continuation()

    await store.save(continuation)
    continuation.scratchpad["mutated_after_save"] = True
    continuation.snapshot.skill_pack_refs.append("mutated-after-save")

    saved = await store.get("run_1")
    assert saved == _continuation()
    assert saved is not None
    saved.scratchpad["mutated_after_get"] = True

    replacement = _continuation(scratchpad={"lead_id": "lead_2"})
    await store.save(replacement)
    assert await store.get("run_1") == replacement

    await store.delete("run_1")
    await store.delete("run_1")
    assert await store.get("run_1") is None


async def test_vault_stub_returns_injectable_manual_credential() -> None:
    vault = InMemoryVault()
    cred = await vault.get(ref="vault://stub", tenant_id="t1")
    assert cred is not None
    assert isinstance(cred, Credential)
    assert cred.ref == "vault://stub"
