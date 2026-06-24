"""Durable manual-task repository: idem enqueue + restart-safe across instances."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agentx_contracts import SyscallRequest
from agentx_syscall import InMemoryManualTaskRepository, MongoManualTaskRepository


def _request(idempotency_key: str, *, run_id: str = "run_1", args: dict[str, object] | None = None) -> SyscallRequest:
    payload: dict[str, object] = args if args is not None else {"action": "review_lead"}
    return SyscallRequest(
        name="queue_manual_action",
        args=payload,  # type: ignore[arg-type]
        instance_id="inst_1",
        run_id=run_id,
        idempotency_key=idempotency_key,
        ring="L1",
        risk_class="reversible_write",
    )


async def test_enqueue_is_idempotent() -> None:
    repo = InMemoryManualTaskRepository()
    req = _request("manual-key-1")
    first = await repo.enqueue(req, source_adapter="queue_manual_action")
    second = await repo.enqueue(req, source_adapter="queue_manual_action")
    assert first.id == second.id
    assert len(await repo.list_open()) == 1


async def test_mark_outcome_closes_a_task_and_excludes_it_from_list_open() -> None:
    repo = InMemoryManualTaskRepository()
    task = await repo.enqueue(_request("k1"), source_adapter="queue_manual_action")
    await repo.mark_outcome(task.id, "completed", {"note": "ok"})
    listed = await repo.list_open()
    assert listed == []
    stored = await repo.get(task.id)
    assert stored is not None and stored.outcome == "completed"


async def test_distinct_idempotency_keys_produce_distinct_tasks() -> None:
    repo = InMemoryManualTaskRepository()
    a = await repo.enqueue(_request("ka"), source_adapter="queue_manual_action")
    b = await repo.enqueue(_request("kb"), source_adapter="queue_manual_action")
    assert a.id != b.id
    assert {t.idempotency_key for t in await repo.list_open()} == {"ka", "kb"}


async def test_created_at_is_close_to_now() -> None:
    repo = InMemoryManualTaskRepository()
    before = datetime.now(UTC)
    task = await repo.enqueue(_request("kstale"), source_adapter="queue_manual_action")
    after = datetime.now(UTC)
    assert before <= task.created_at <= after


async def test_mark_outcome_on_unknown_task_raises_keyerror() -> None:
    repo = InMemoryManualTaskRepository()
    try:
        await repo.mark_outcome("missing", "completed")
    except KeyError:
        return
    raise AssertionError("expected KeyError for missing manual task id")


# --- Mongo-backed repo over the async PyMongo driver -----------------------------------------


class _FakeAsyncCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        return list(self._docs)


class _FakeAsyncCollection:
    """Minimal stand-in for a PyMongo AsyncMongoClient collection (find_one/insert_one/etc. are
    coroutines; find() returns a cursor with an awaitable to_list)."""

    def __init__(self) -> None:
        self._docs: dict[str, dict[str, Any]] = {}

    async def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        for doc in self._docs.values():
            if all(doc.get(k) == v for k, v in query.items()):
                return dict(doc)
        return None

    async def insert_one(self, doc: dict[str, Any]) -> None:
        self._docs[str(doc["_id"])] = dict(doc)

    async def update_one(self, query: dict[str, Any], update: dict[str, Any]) -> None:
        for doc in self._docs.values():
            if all(doc.get(k) == v for k, v in query.items()):
                doc.update(update["$set"])
                return

    def find(self, query: dict[str, Any]) -> _FakeAsyncCursor:
        matched = [dict(d) for d in self._docs.values() if all(d.get(k) == v for k, v in query.items())]
        return _FakeAsyncCursor(matched)


class _FakeAsyncDatabase:
    def __init__(self) -> None:
        self._collections: dict[str, _FakeAsyncCollection] = {}

    def __getitem__(self, name: str) -> _FakeAsyncCollection:
        return self._collections.setdefault(name, _FakeAsyncCollection())


async def test_mongo_repo_full_lifecycle_over_async_driver() -> None:
    # Regression for the books-prep queue bug: the sync repo over the async driver never awaited, so
    # enqueue crashed (un-awaited coroutine) and queued rows never reached the review queue.
    repo = MongoManualTaskRepository(_FakeAsyncDatabase())
    req = _request("idem-async-1", args={"action": "review_transaction", "reason": "low conf"})

    first = await repo.enqueue(req, source_adapter="queue_manual_action")
    second = await repo.enqueue(req, source_adapter="queue_manual_action")
    assert first.id == second.id  # idempotent via find_one on idempotency_key

    open_tasks = await repo.list_open()
    assert [task.idempotency_key for task in open_tasks] == ["idem-async-1"]

    # Callers look up by task.id ("manual:<idem>"), NOT the stored _id (the idempotency_key).
    fetched = await repo.get(first.id)
    assert fetched is not None and fetched.id == first.id

    await repo.mark_outcome(first.id, "approve", {"note": "ok"})
    assert await repo.list_open() == []
    closed = await repo.get(first.id)
    assert closed is not None and closed.outcome == "approve"
