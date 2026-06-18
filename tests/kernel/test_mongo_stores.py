"""P12 PyMongo-async kernel stores, verified with fake async collections."""

from datetime import UTC, datetime, timedelta

import pytest
from agentx_contracts.journal import ApprovalResolved, RunCreated
from agentx_contracts.mandate import (
    Charter,
    DomainPackRef,
    HydrationSnapshot,
    InstanceBinding,
    MandateType,
    SettlementRules,
    VerificationSuite,
)
from agentx_contracts.syscall import SyscallRequest, SyscallResult
from agentx_contracts.trigger import DeadlineTrigger
from agentx_contracts.verification import Trace
from agentx_kernel.continuations import RunContinuation
from agentx_kernel.errors import DuplicateIdempotencyKey, IdempotencyRequestConflict, JournalSeqContention
from agentx_kernel.receipts import SyscallReceipt
from agentx_kernel.scheduler import ApprovalWork, TriggerWork
from agentx_kernel.stores.mongo import (
    MongoJournalStore,
    MongoProjectionStore,
    MongoRunContinuationStore,
    MongoSchedulerStore,
    MongoSyscallReceiptStore,
    MongoVault,
)
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
            if _matches(doc, query):
                return dict(doc)
        return None

    async def replace_one(self, query: dict[str, object], document: dict[str, object], *, upsert: bool) -> None:
        for index, doc in enumerate(self.docs):
            if all(doc.get(k) == v for k, v in query.items()):
                self.docs[index] = dict(document)
                return
        if upsert:
            self.docs.append(dict(document))

    async def delete_one(self, query: dict[str, object]) -> None:
        self.docs = [doc for doc in self.docs if not all(doc.get(k) == v for k, v in query.items())]

    async def update_one(
        self,
        query: dict[str, object],
        update: dict[str, object],
        *,
        upsert: bool = False,
    ) -> None:
        for doc in self.docs:
            if _matches(doc, query):
                _apply_update(doc, update, inserting=False)
                return
        if upsert:
            inserted = {key: value for key, value in query.items() if not isinstance(value, dict)}
            _apply_update(inserted, update, inserting=True)
            self.docs.append(inserted)

    async def find_one_and_update(
        self,
        query: dict[str, object],
        update: dict[str, object],
        *,
        sort: list[tuple[str, int]],
        return_document: object,
    ) -> dict[str, object] | None:
        del return_document
        matches = [doc for doc in self.docs if _matches(doc, query)]
        for key, direction in reversed(sort):
            matches.sort(key=lambda doc: str(doc[key]), reverse=direction < 0)
        if not matches:
            return None
        selected = matches[0]
        _apply_update(selected, update, inserting=False)
        return dict(selected)


class FakeDatabase:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())


def _matches(doc: dict[str, object], query: dict[str, object]) -> bool:
    for key, expected in query.items():
        actual = doc.get(key)
        if isinstance(expected, dict):
            if "$lte" in expected and not (actual is not None and actual <= expected["$lte"]):
                return False
        elif actual != expected:
            return False
    return True


def _apply_update(doc: dict[str, object], update: dict[str, object], *, inserting: bool) -> None:
    set_values = update.get("$set")
    if isinstance(set_values, dict):
        doc.update(set_values)
    set_on_insert = update.get("$setOnInsert")
    if inserting and isinstance(set_on_insert, dict):
        doc.update(set_on_insert)
    increments = update.get("$inc")
    if isinstance(increments, dict):
        for key, value in increments.items():
            current = doc.get(key, 0)
            assert isinstance(current, int)
            assert isinstance(value, int)
            doc[key] = current + value


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


def _continuation(*, cursor: int = 3) -> RunContinuation:
    return RunContinuation(
        run_id="run_1",
        instance=InstanceBinding(
            instance_id="inst_a",
            type_ref="lead-finder@0.1.0",
            ring="L1",
            heap_region_id="heap_a",
        ),
        mandate=MandateType(
            id="type_lead_finder_v0",
            name="lead-finder",
            version="0.1.0",
            charter=Charter(goal="Find qualified leads."),
            domain_pack=DomainPackRef(name="dental", version="0.1.0"),
            verification=VerificationSuite(),
            settlement=SettlementRules(),
        ),
        mode="live",
        snapshot=HydrationSnapshot(frozen_at=NOW),
        scratchpad={"lead_id": "lead_1"},
        trace=Trace(run_id="run_1"),
        claimed_facts=[],
        harness_cursor=cursor,
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


def _scheduled_trigger(instance_id: str, *, available_at: datetime = NOW) -> TriggerWork:
    return TriggerWork.schedule(
        mandate=_continuation().mandate,
        instance=_continuation().instance.model_copy(update={"instance_id": instance_id}),
        trigger=DeadlineTrigger(ts=NOW, reason=instance_id),
        mode="live",
        available_at=available_at,
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


async def test_mongo_syscall_receipt_round_trips_and_rejects_conflicts() -> None:
    store = MongoSyscallReceiptStore(FakeDatabase())
    receipt = _receipt()

    await store.save(receipt)
    await store.save(receipt)

    assert await store.get("idem-1") == receipt
    with pytest.raises(IdempotencyRequestConflict):
        await store.save(_receipt(syscall="read_url"))


async def test_mongo_run_continuation_upserts_by_run_id_round_trips_and_deletes() -> None:
    database = FakeDatabase()
    store = MongoRunContinuationStore(database)
    continuation = _continuation()

    await store.save(continuation)
    await store.save(continuation)
    await store.save(_continuation(cursor=4))

    assert await store.get("run_1") == _continuation(cursor=4)
    assert database.collections["run_continuation"].docs == [
        {
            **_continuation(cursor=4).model_dump(mode="json"),
            "_id": "run_1",
        }
    ]

    await store.delete("run_1")
    await store.delete("run_1")
    assert await store.get("run_1") is None


async def test_mongo_scheduler_claims_due_work_in_order_and_requeues_atomically() -> None:
    database = FakeDatabase()
    store = MongoSchedulerStore(database)
    future = _scheduled_trigger("inst_future", available_at=NOW + timedelta(minutes=2))
    due = sorted(
        (_scheduled_trigger("inst_b"), _scheduled_trigger("inst_a")),
        key=lambda work: work.work_id,
    )
    approval = ApprovalWork.schedule(
        ApprovalResolved(
            event_id="run_1:approval",
            seq=4,
            ts=NOW + timedelta(minutes=1),
            instance_id="inst_a",
            run_id="run_1",
            decision="approve",
        )
    )
    for work in (future, due[1], approval, due[0], due[0]):
        await store.enqueue(work)

    assert len(database.collections["scheduler_work"].docs) == 4
    assert await store.claim_next(NOW - timedelta(seconds=1)) is None
    assert await store.claim_next(NOW) == due[0]
    await store.complete(due[0].work_id)
    assert await store.claim_next(NOW) == due[1]
    await store.fail(due[1].work_id, retry_at=NOW + timedelta(minutes=3))
    assert await store.claim_next(NOW) is None
    assert await store.claim_next(NOW + timedelta(minutes=1)) == approval
    await store.complete(approval.work_id)
    assert await store.claim_next(NOW + timedelta(minutes=2)) == future


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
