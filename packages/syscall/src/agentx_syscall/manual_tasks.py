"""Durable manual-task storage.

Phase-1 ``ManualTaskStore`` lived in ``adapters.py`` and was a process-local dict. The dashboard's
durable queue requirement (§6, BLUEPRINT) makes that insufficient: tasks queued by the kernel must
survive an API restart and be visible across the API process and the scheduler worker process when
they are split. The two implementations below share a ``ManualTaskRepository`` Protocol so callers
and tests can swap them without touching adapter code.

LANE NOTE: this is the Codex lane (syscall). The kernel-side manual-task read endpoints go through
``agentx_api.state`` which composes both lanes at the edge.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

import agentx_db.collections as c
from agentx_contracts import JsonObject, SyscallRequest

from .adapters import ManualTask


def _copy_task(task: ManualTask) -> ManualTask:
    """Deep-copy a ManualTask (dataclass, not Pydantic) for safe cross-call returns."""
    return replace(task, args=dict(task.args), outcome_detail=dict(task.outcome_detail))


@runtime_checkable
class ManualTaskRepository(Protocol):
    """The durable contract for the manual-task tail. Two implementations:

    - :class:`InMemoryManualTaskRepository` — tests + transient API boot.
    - :class:`MongoManualTaskRepository` — the production API and worker.
    """

    async def enqueue(self, req: SyscallRequest, *, source_adapter: str) -> ManualTask: ...

    async def mark_outcome(self, task_id: str, outcome: str, detail: JsonObject | None = None) -> ManualTask: ...

    async def get(self, task_id: str) -> ManualTask | None: ...

    async def list_open(self) -> list[ManualTask]: ...

    async def aclose(self) -> None: ...


class InMemoryManualTaskRepository:
    """Process-local manual-task queue (fast, deterministic). Phase-1 default for tests + sim API."""

    def __init__(self) -> None:
        self._tasks: dict[str, ManualTask] = {}
        self._order: list[str] = []

    async def enqueue(self, req: SyscallRequest, *, source_adapter: str) -> ManualTask:
        existing = self._find_by_idempotency(req.idempotency_key)
        if existing is not None:
            return _copy_task(existing)
        task_id = f"manual_{len(self._order) + 1}"
        task = ManualTask(
            id=task_id,
            request_name=req.name,
            args=dict(req.args),
            instance_id=req.instance_id,
            run_id=req.run_id,
            idempotency_key=req.idempotency_key,
            source_adapter=source_adapter,
            created_at=datetime.now(UTC),
        )
        self._tasks[task.id] = task
        self._order.append(task.id)
        return _copy_task(task)

    async def mark_outcome(self, task_id: str, outcome: str, detail: JsonObject | None = None) -> ManualTask:
        task = self._tasks[task_id]
        task.outcome = outcome
        task.outcome_detail = dict(detail or {})
        return _copy_task(task)

    async def get(self, task_id: str) -> ManualTask | None:
        task = self._tasks.get(task_id)
        return _copy_task(task) if task is not None else None

    async def list_open(self) -> list[ManualTask]:
        return [_copy_task(self._tasks[task_id]) for task_id in self._order if self._tasks[task_id].outcome is None]

    async def aclose(self) -> None:
        return None

    def _find_by_idempotency(self, idempotency_key: str) -> ManualTask | None:
        for task in self._tasks.values():
            if task.idempotency_key == idempotency_key:
                return task
        return None


class MongoManualTaskRepository:
    """Mongo-backed durable manual-task tail.

    Idempotency is enforced by a UNIQUE index on ``idempotency_key``; outcome updates are atomic
    ``$set`` against the existing document. Restart-safe: queued tasks survive API restarts.
    """

    def __init__(self, database: Any) -> None:
        self._collection = database[c.MANUAL_TASK]

    @staticmethod
    def _doc_to_task(doc: dict[str, object]) -> ManualTask:
        clean: dict[str, object] = {str(key): value for key, value in doc.items() if key != "_id"}
        outcome_value = clean.get("outcome")
        outcome: str | None = outcome_value if isinstance(outcome_value, str) else None
        outcome_detail_value = clean.get("outcome_detail")
        outcome_detail: JsonObject = (
            dict(outcome_detail_value)
            if isinstance(outcome_detail_value, dict)
            else {}
        )
        created_at_value = clean.get("created_at")
        created_at: datetime = (
            created_at_value
            if isinstance(created_at_value, datetime)
            else datetime.fromisoformat(str(created_at_value))
        )
        args_value = clean.get("args")
        args: JsonObject = dict(args_value) if isinstance(args_value, dict) else {}
        return ManualTask(
            id=str(clean["id"]),
            request_name=str(clean["request_name"]),
            args=args,
            instance_id=str(clean["instance_id"]),
            run_id=str(clean["run_id"]),
            idempotency_key=str(clean["idempotency_key"]),
            source_adapter=str(clean["source_adapter"]),
            created_at=created_at,
            outcome=outcome,
            outcome_detail=outcome_detail,
        )

    def _task_to_doc(self, task: ManualTask) -> dict[str, object]:
        doc: dict[str, object] = {
            "id": task.id,
            "request_name": task.request_name,
            "args": dict(task.args),
            "instance_id": task.instance_id,
            "run_id": task.run_id,
            "idempotency_key": task.idempotency_key,
            "source_adapter": task.source_adapter,
            "created_at": task.created_at,
            "outcome": task.outcome,
            "outcome_detail": dict(task.outcome_detail),
        }
        doc["_id"] = task.idempotency_key
        return doc

    async def enqueue(self, req: SyscallRequest, *, source_adapter: str) -> ManualTask:
        existing_doc = await self._collection.find_one({"idempotency_key": req.idempotency_key})
        if existing_doc is not None:
            return self._doc_to_task(existing_doc)
        task = ManualTask(
            id=f"manual:{req.idempotency_key}",
            request_name=req.name,
            args=dict(req.args),
            instance_id=req.instance_id,
            run_id=req.run_id,
            idempotency_key=req.idempotency_key,
            source_adapter=source_adapter,
            created_at=datetime.now(UTC),
        )
        await self._collection.insert_one(self._task_to_doc(task))
        return task

    async def mark_outcome(self, task_id: str, outcome: str, detail: JsonObject | None = None) -> ManualTask:
        # Callers look tasks up by ``task.id`` (e.g. "manual:<idem>"), which is the ``id`` field; the
        # document ``_id`` is the idempotency_key, so we must NOT query by ``_id`` here.
        await self._collection.update_one(
            {"id": task_id},
            {"$set": {"outcome": outcome, "outcome_detail": dict(detail or {})}},
        )
        doc = await self._collection.find_one({"id": task_id})
        if doc is None:
            raise KeyError(task_id)
        return self._doc_to_task(doc)

    async def get(self, task_id: str) -> ManualTask | None:
        doc = await self._collection.find_one({"id": task_id})
        return self._doc_to_task(doc) if doc is not None else None

    async def list_open(self) -> list[ManualTask]:
        docs = await self._collection.find({"outcome": None}).to_list(length=None)
        return [self._doc_to_task(doc) for doc in docs]

    async def aclose(self) -> None:
        return None


def make_in_memory_manual_task_repository() -> InMemoryManualTaskRepository:
    """Public constructor so callers don't have to reach for the concrete class.

    The API composition layer picks one of the two factories based on backend.
    """
    return InMemoryManualTaskRepository()


def make_mongo_manual_task_repository(database: Any) -> MongoManualTaskRepository:
    """Public Mongo-backed factory; the ``database`` is a PyMongo ``AsyncMongoDatabase``."""
    return MongoManualTaskRepository(database)


__all__ = [
    "InMemoryManualTaskRepository",
    "ManualTaskRepository",
    "MongoManualTaskRepository",
    "make_in_memory_manual_task_repository",
    "make_mongo_manual_task_repository",
]  # noqa: E501
