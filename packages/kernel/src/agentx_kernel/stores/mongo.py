"""PyMongo async implementations of kernel storage ports."""

from __future__ import annotations

from typing import Any

import agentx_db.collections as c
from agentx_contracts.journal import JournalEvent
from agentx_contracts.security import Credential
from pydantic import TypeAdapter
from pymongo.errors import DuplicateKeyError

from ..errors import DuplicateIdempotencyKey

_JOURNAL_EVENT: TypeAdapter[JournalEvent] = TypeAdapter(JournalEvent)


class MongoJournalStore:
    """Append-only journal backed by a PyMongo async database."""

    def __init__(self, database: Any) -> None:
        self._collection = database[c.JOURNAL]

    async def append(self, event: JournalEvent) -> JournalEvent:
        key = event.idempotency_key
        seq = await self.max_seq(event.instance_id) + 1
        stamped = event.model_copy(update={"seq": seq})
        try:
            await self._collection.insert_one(stamped.model_dump(mode="json", exclude_none=True))
        except DuplicateKeyError as exc:
            if key is not None:
                raise DuplicateIdempotencyKey(key) from exc
            raise
        return stamped

    async def read_instance(self, instance_id: str) -> list[JournalEvent]:
        docs = await self._collection.find({"instance_id": instance_id}).sort("seq", 1).to_list(length=None)
        return [_parse_event(doc) for doc in docs]

    async def read_run(self, run_id: str) -> list[JournalEvent]:
        docs = await self._collection.find({"run_id": run_id}).sort("seq", 1).to_list(length=None)
        return [_parse_event(doc) for doc in docs]

    async def max_seq(self, instance_id: str) -> int:
        docs = await self._collection.find({"instance_id": instance_id}).sort("seq", -1).to_list(length=1)
        if not docs:
            return 0
        value = docs[0].get("seq")
        return value if isinstance(value, int) else 0


class MongoProjectionStore:
    """Projection document store backed by PyMongo async collections."""

    def __init__(self, database: Any) -> None:
        self._database = database

    async def upsert(self, collection: str, doc_id: str, document: dict[str, object]) -> None:
        doc = dict(document)
        doc["_id"] = doc_id
        await self._database[collection].replace_one({"_id": doc_id}, doc, upsert=True)

    async def get(self, collection: str, doc_id: str) -> dict[str, object] | None:
        doc = await self._database[collection].find_one({"_id": doc_id})
        return _strip_mongo_id(doc) if doc is not None else None

    async def find(self, collection: str, query: dict[str, object]) -> list[dict[str, object]]:
        docs = await self._database[collection].find(query).to_list(length=None)
        return [_strip_mongo_id(doc) for doc in docs]


class MongoVault:
    """Phase-1 vault stub for live DB wiring; real secret lookup is an additive replacement."""

    def __init__(self, database: Any) -> None:
        self._database = database

    async def get(self, ref: str, tenant_id: str) -> Credential | None:
        return Credential(ref=ref, kind="manual", material=None)


def _parse_event(doc: dict[str, object]) -> JournalEvent:
    return _JOURNAL_EVENT.validate_python(_strip_mongo_id(doc))


def _strip_mongo_id(doc: dict[str, object]) -> dict[str, object]:
    clean = dict(doc)
    clean.pop("_id", None)
    return clean
