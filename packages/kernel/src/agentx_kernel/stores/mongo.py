"""PyMongo async implementations of kernel storage ports."""

from __future__ import annotations

from typing import Any

import agentx_db.collections as c
from agentx_contracts.journal import JournalEvent
from agentx_contracts.security import Credential
from pydantic import TypeAdapter
from pymongo.errors import DuplicateKeyError

from ..errors import DuplicateIdempotencyKey, IdempotencyRequestConflict, JournalSeqContention
from ..receipts import SyscallReceipt

_JOURNAL_EVENT: TypeAdapter[JournalEvent] = TypeAdapter(JournalEvent)

# How many times to recompute seq and retry when a concurrent appender wins the (instance_id, seq)
# race. Contention is per-instance and brief, so a small budget is ample; exhausting it is pathological.
_MAX_SEQ_RETRIES = 8


class MongoJournalStore:
    """Append-only journal backed by a PyMongo async database."""

    def __init__(self, database: Any) -> None:
        self._collection = database[c.JOURNAL]

    async def append(self, event: JournalEvent) -> JournalEvent:
        """Assign a per-instance ``seq`` and insert under the UNIQUE ``(instance_id, seq)`` +
        UNIQUE ``idempotency_key`` indexes.

        ``seq = max_seq + 1`` is read-then-write, so a concurrent appender can take our seq between the
        read and the insert. The unique index turns that race into a ``DuplicateKeyError`` on
        ``ix_journal_instance_seq``; we recompute and retry. A collision on ``ix_journal_idem`` instead
        means the same effect was already journaled → raise ``DuplicateIdempotencyKey`` (at-most-once).
        """
        key = event.idempotency_key
        for _attempt in range(_MAX_SEQ_RETRIES):
            seq = await self.max_seq(event.instance_id) + 1
            stamped = event.model_copy(update={"seq": seq})
            try:
                await self._collection.insert_one(stamped.model_dump(mode="json", exclude_none=True))
            except DuplicateKeyError as exc:
                if _is_idempotency_violation(exc, has_key=key is not None):
                    assert key is not None  # idempotency index only matches events that set the key
                    raise DuplicateIdempotencyKey(key) from exc
                # Otherwise the (instance_id, seq) unique index rejected us: a concurrent writer won
                # this seq. Recompute against the now-higher max and retry.
                continue
            return stamped
        raise JournalSeqContention(event.instance_id)

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


class MongoSyscallReceiptStore:
    """Mongo-backed durable syscall output receipts."""

    def __init__(self, database: Any) -> None:
        self._collection = database[c.SYSCALL_RECEIPT]

    async def save(self, receipt: SyscallReceipt) -> None:
        prior = await self.get(receipt.idempotency_key)
        if prior is not None and prior != receipt:
            raise IdempotencyRequestConflict(receipt.idempotency_key)
        document = receipt.model_dump(mode="json")
        document["_id"] = receipt.idempotency_key
        await self._collection.replace_one({"_id": receipt.idempotency_key}, document, upsert=True)

    async def get(self, idempotency_key: str) -> SyscallReceipt | None:
        doc = await self._collection.find_one({"_id": idempotency_key})
        if doc is None:
            return None
        return SyscallReceipt.model_validate(_strip_mongo_id(doc))


class MongoVault:
    """Phase-1 vault stub for live DB wiring; real secret lookup is an additive replacement."""

    def __init__(self, database: Any) -> None:
        self._database = database

    async def get(self, ref: str, tenant_id: str) -> Credential | None:
        return Credential(ref=ref, kind="manual", material=None)


def _is_idempotency_violation(exc: DuplicateKeyError, *, has_key: bool) -> bool:
    """Decide whether a DuplicateKeyError came from the idempotency index vs the (instance_id, seq) index.

    Prefers the structured ``details`` (``keyPattern``/``keyValue`` — always present from a real server),
    then falls back to the index name in the error message. When neither is conclusive we default to a
    seq collision UNLESS the event carries an idempotency_key (in which case we conservatively treat it
    as an idempotency violation so a retried effect can never double-execute).
    """
    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        for field in ("keyPattern", "keyValue"):
            pattern = details.get(field)
            if isinstance(pattern, dict):
                if "idempotency_key" in pattern:
                    return True
                if "seq" in pattern or "instance_id" in pattern:
                    return False
    message = str(exc)
    if "ix_journal_idem" in message or "idempotency_key" in message:
        return True
    if "ix_journal_instance_seq" in message or "seq" in message:
        return False
    return has_key


def _parse_event(doc: dict[str, object]) -> JournalEvent:
    return _JOURNAL_EVENT.validate_python(_strip_mongo_id(doc))


def _strip_mongo_id(doc: dict[str, object]) -> dict[str, object]:
    clean = dict(doc)
    clean.pop("_id", None)
    return clean
