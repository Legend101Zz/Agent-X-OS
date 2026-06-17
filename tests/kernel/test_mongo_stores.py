"""P12 PyMongo-async kernel stores, verified with fake async collections."""

from datetime import UTC, datetime

import pytest
from agentx_contracts.journal import RunCreated
from agentx_contracts.trigger import DeadlineTrigger
from agentx_kernel.errors import DuplicateIdempotencyKey
from agentx_kernel.stores.mongo import MongoJournalStore, MongoProjectionStore, MongoVault
from pymongo.errors import DuplicateKeyError

NOW = datetime(2026, 6, 17, tzinfo=UTC)


class FakeCursor:
    def __init__(self, docs: list[dict[str, object]]) -> None:
        self._docs = docs

    def sort(self, key: str, direction: int) -> "FakeCursor":
        reverse = direction < 0

        def sort_key(doc: dict[str, object]) -> int:
            value = doc.get(key, 0)
            assert isinstance(value, int)
            return value

        self._docs.sort(key=sort_key, reverse=reverse)
        return self

    async def to_list(self, length: int | None = None) -> list[dict[str, object]]:
        return list(self._docs)


class FakeCollection:
    def __init__(self) -> None:
        self.docs: list[dict[str, object]] = []

    async def insert_one(self, doc: dict[str, object]) -> None:
        if "idempotency_key" in doc and any(
            existing.get("idempotency_key") == doc["idempotency_key"]
            for existing in self.docs
            if "idempotency_key" in existing
        ):
            raise DuplicateKeyError("duplicate idempotency")
        self.docs.append(dict(doc))

    def find(self, query: dict[str, object]) -> FakeCursor:
        return FakeCursor([doc for doc in self.docs if all(doc.get(k) == v for k, v in query.items())])

    async def find_one(self, query: dict[str, object]) -> dict[str, object] | None:
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return dict(doc)
        return None

    async def replace_one(self, query: dict[str, object], document: dict[str, object], *, upsert: bool) -> None:
        for index, doc in enumerate(self.docs):
            if all(doc.get(k) == v for k, v in query.items()):
                self.docs[index] = dict(document)
                return
        if upsert:
            self.docs.append(dict(document))


class FakeDatabase:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())


def _run_created(instance_id: str = "inst_a", event_id: str = "rc1") -> RunCreated:
    return RunCreated(
        event_id=event_id,
        seq=0,
        ts=NOW,
        instance_id=instance_id,
        run_id="run_1",
        type_ref="lead-finder@0.1.0",
        trigger=DeadlineTrigger(ts=NOW, reason="sweep"),
    )


async def test_mongo_journal_assigns_seq_and_reads_ordered_events() -> None:
    store = MongoJournalStore(FakeDatabase())

    first = await store.append(_run_created(event_id="rc1"))
    second = await store.append(_run_created(event_id="rc2"))

    assert (first.seq, second.seq) == (1, 2)
    assert [event.event_id for event in await store.read_instance("inst_a")] == ["rc1", "rc2"]
    assert [event.event_id for event in await store.read_run("run_1")] == ["rc1", "rc2"]
    assert await store.max_seq("inst_a") == 2


async def test_mongo_journal_maps_duplicate_idempotency_to_kernel_error() -> None:
    store = MongoJournalStore(FakeDatabase())
    event = _run_created()
    event = event.model_copy(update={"idempotency_key": "idem-1"})

    await store.append(event)
    with pytest.raises(DuplicateIdempotencyKey):
        await store.append(event.model_copy(update={"event_id": "rc2"}))


async def test_mongo_projection_store_upsert_get_find_and_vault_stub() -> None:
    database = FakeDatabase()
    projections = MongoProjectionStore(database)
    await projections.upsert("heap_fact", "f1", {"id": "f1", "instance_id": "inst_a"})

    assert await projections.get("heap_fact", "f1") == {"id": "f1", "instance_id": "inst_a"}
    assert await projections.find("heap_fact", {"instance_id": "inst_a"}) == [
        {"id": "f1", "instance_id": "inst_a"}
    ]

    cred = await MongoVault(database).get(ref="vault://stub", tenant_id="tenant_a")
    assert cred is not None and cred.kind == "manual"
