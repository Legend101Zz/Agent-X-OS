"""In-memory ProjectionStore + Vault — the derived-state store and the credential-injection stub."""

from agentx_contracts.security import Credential
from agentx_kernel.stores.memory import InMemoryProjectionStore, InMemoryVault


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


async def test_vault_stub_returns_injectable_manual_credential() -> None:
    vault = InMemoryVault()
    cred = await vault.get(ref="vault://stub", tenant_id="t1")
    assert cred is not None
    assert isinstance(cred, Credential)
    assert cred.ref == "vault://stub"
