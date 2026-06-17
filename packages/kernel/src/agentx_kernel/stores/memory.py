"""In-memory implementations of the storage ports — fast, deterministic, no Mongo.

Used by the default test suite and by ``mode="sim"`` runs. Semantics mirror the Mongo impl exactly
(per-instance ``seq`` total order, UNIQUE idempotency, idempotent projection upserts) so a sim run
exercises the same kernel behaviour a live run does.
"""

from __future__ import annotations

import copy

from agentx_contracts import JournalEvent
from agentx_contracts.security import Credential

from ..errors import DuplicateIdempotencyKey


class InMemoryJournalStore:
    """The append-only journal as a list, with a per-instance ``seq`` counter + a global idempotency set."""

    def __init__(self) -> None:
        self._events: list[JournalEvent] = []
        self._seq_by_instance: dict[str, int] = {}
        self._idem_keys: set[str] = set()

    async def append(self, event: JournalEvent) -> JournalEvent:
        key = event.idempotency_key
        if key is not None and key in self._idem_keys:
            raise DuplicateIdempotencyKey(key)
        seq = self._seq_by_instance.get(event.instance_id, 0) + 1
        stamped: JournalEvent = event.model_copy(update={"seq": seq})
        self._seq_by_instance[event.instance_id] = seq
        if key is not None:
            self._idem_keys.add(key)
        self._events.append(stamped)
        return stamped

    async def read_instance(self, instance_id: str) -> list[JournalEvent]:
        return sorted(
            (e for e in self._events if e.instance_id == instance_id),
            key=lambda e: e.seq,
        )

    async def read_run(self, run_id: str) -> list[JournalEvent]:
        return sorted(
            (e for e in self._events if e.run_id == run_id),
            key=lambda e: e.seq,
        )

    async def max_seq(self, instance_id: str) -> int:
        return self._seq_by_instance.get(instance_id, 0)


class InMemoryProjectionStore:
    """Nested ``{collection: {doc_id: document}}`` maps. Upsert replaces; find does equality matching."""

    def __init__(self) -> None:
        self._collections: dict[str, dict[str, dict[str, object]]] = {}

    async def upsert(self, collection: str, doc_id: str, document: dict[str, object]) -> None:
        self._collections.setdefault(collection, {})[doc_id] = copy.deepcopy(document)

    async def get(self, collection: str, doc_id: str) -> dict[str, object] | None:
        doc = self._collections.get(collection, {}).get(doc_id)
        return copy.deepcopy(doc) if doc is not None else None

    async def find(self, collection: str, query: dict[str, object]) -> list[dict[str, object]]:
        return [
            copy.deepcopy(doc)
            for doc in self._collections.get(collection, {}).values()
            if all(doc.get(k) == v for k, v in query.items())
        ]


class InMemoryVault:
    """Phase-1 credential stub. Returns a ``manual``-kind ``Credential`` handle carrying no secret.

    Real adapters that need a secret receive ``material`` here once a real vault is wired; for Phase 1
    every effect either drafts (no secret) or lands in the human-task queue (``manual``), so an empty
    handle is correct — and it keeps the credential-injection POINT exercised end-to-end.
    """

    async def get(self, ref: str, tenant_id: str) -> Credential | None:
        return Credential(ref=ref, kind="manual", material=None)
