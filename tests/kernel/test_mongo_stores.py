"""P12 PyMongo-async kernel stores, verified with fake async collections."""

from datetime import UTC, datetime

import pytest
from agentx_contracts.journal import RunCreated
from agentx_contracts.syscall import SyscallRequest, SyscallResult
from agentx_contracts.trigger import DeadlineTrigger
from agentx_kernel.errors import DuplicateIdempotencyKey, IdempotencyRequestConflict, JournalSeqContention
from agentx_kernel.receipts import SyscallReceipt
from agentx_kernel.stores.mongo import MongoJournalStore, MongoProjectionStore, MongoSyscallReceiptStore, MongoVault
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


async def test_mongo_syscall_receipt_round_trips_and_rejects_conflicts() -> None:
    store = MongoSyscallReceiptStore(FakeDatabase())
    receipt = _receipt()

    await store.save(receipt)
    await store.save(receipt)

    assert await store.get("idem-1") == receipt
    with pytest.raises(IdempotencyRequestConflict):
        await store.save(_receipt(syscall="read_url"))


def _seq_dup_key_error(instance_id: str, seq: int) -> DuplicateKeyError:
    """A DuplicateKeyError shaped like a real (instance_id, seq) unique-index violation."""
    return DuplicateKeyError(
        f"E11000 duplicate key error collection: agentx.journal index: ix_journal_instance_seq dup key: "
        f"{{ instance_id: '{instance_id}', seq: {seq} }}",
        11000,
        {"keyPattern": {"instance_id": 1, "seq": 1}, "keyValue": {"instance_id": instance_id, "seq": seq}},
    )


class SeqRaceOnceCollection(FakeCollection):
    """Simulates ONE concurrent writer stealing our seq between max_seq() and insert_one()."""

    def __init__(self) -> None:
        super().__init__()
        self._raced = False

    async def insert_one(self, doc: dict[str, object]) -> None:
        instance_id = str(doc.get("instance_id"))
        seq = doc.get("seq")
        assert isinstance(seq, int)
        if not self._raced:
            self._raced = True
            # A concurrent writer already committed our seq; record it, then reject our insert.
            self.docs.append({"event_id": "competitor", "instance_id": instance_id, "seq": seq})
            raise _seq_dup_key_error(instance_id, seq)
        if any(d.get("instance_id") == instance_id and d.get("seq") == seq for d in self.docs):
            raise _seq_dup_key_error(instance_id, seq)
        self.docs.append(dict(doc))


class SeqRaceForeverCollection(FakeCollection):
    """Every insert collides on (instance_id, seq) — exhausts the retry budget."""

    async def insert_one(self, doc: dict[str, object]) -> None:
        instance_id = str(doc.get("instance_id"))
        seq = doc.get("seq")
        assert isinstance(seq, int)
        raise _seq_dup_key_error(instance_id, seq)


class SeqRaceDatabase(FakeDatabase):
    def __init__(self, collection: FakeCollection) -> None:
        super().__init__()
        self._journal = collection

    def __getitem__(self, name: str) -> FakeCollection:
        if name == "journal":
            return self._journal
        return super().__getitem__(name)


async def test_seq_collision_is_retried_and_seq_advances_not_idempotency_error() -> None:
    store = MongoJournalStore(SeqRaceDatabase(SeqRaceOnceCollection()))

    # RunCreated carries no idempotency_key, so the only possible collision is on (instance_id, seq).
    stamped = await store.append(_run_created(event_id="rc1"))

    # After the simulated race (competitor took seq=1) the store recomputes max_seq and lands on seq=2.
    assert stamped.seq == 2
    assert stamped.event_id == "rc1"


async def test_seq_collision_with_idempotency_key_event_still_retries() -> None:
    store = MongoJournalStore(SeqRaceDatabase(SeqRaceOnceCollection()))
    event = _run_created(event_id="rc1").model_copy(update={"idempotency_key": "idem-real"})

    # The collision is on seq (not idempotency_key), so it must retry, not raise DuplicateIdempotencyKey.
    stamped = await store.append(event)
    assert stamped.seq == 2


async def test_seq_contention_exhausted_raises_typed_error() -> None:
    store = MongoJournalStore(SeqRaceDatabase(SeqRaceForeverCollection()))
    with pytest.raises(JournalSeqContention):
        await store.append(_run_created(event_id="rc1"))
