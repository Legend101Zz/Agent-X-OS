"""In-memory ProjectionStore + Vault — the derived-state store and the credential-injection stub."""

import pytest
from agentx_contracts.security import Credential
from agentx_contracts.syscall import SyscallRequest, SyscallResult
from agentx_kernel.errors import IdempotencyRequestConflict
from agentx_kernel.receipts import SyscallReceipt
from agentx_kernel.stores.memory import InMemoryProjectionStore, InMemorySyscallReceiptStore, InMemoryVault


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


async def test_vault_stub_returns_injectable_manual_credential() -> None:
    vault = InMemoryVault()
    cred = await vault.get(ref="vault://stub", tenant_id="t1")
    assert cred is not None
    assert isinstance(cred, Credential)
    assert cred.ref == "vault://stub"
