"""P12 db.setup.ensure_indexes creates declared indexes idempotently."""

from agentx_db import collections as c
from agentx_db.indexes import INDEXES
from agentx_db.setup import ensure_indexes


class FakeCollection:
    def __init__(self) -> None:
        self.created: list[dict[str, object]] = []

    async def create_index(
        self,
        keys: list[tuple[str, int]],
        *,
        name: str,
        unique: bool = False,
        sparse: bool = False,
    ) -> str:
        self.created.append({"keys": keys, "name": name, "unique": unique, "sparse": sparse})
        return name


class FakeDatabase:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())


async def test_ensure_indexes_creates_every_declared_index() -> None:
    database = FakeDatabase()

    await ensure_indexes(database)

    created_count = sum(len(collection.created) for collection in database.collections.values())
    assert created_count == sum(len(specs) for specs in INDEXES.values())
    assert database.collections["journal"].created[0]["name"] == "ix_journal_instance_seq"
    assert [index["name"] for index in database.collections[c.RUN_CONTINUATION].created] == [
        "ix_continuation_instance",
        "ix_continuation_pending_idem",
    ]
    assert [index["name"] for index in database.collections[c.SCHEDULER_WORK].created] == [
        "ix_scheduler_due",
    ]
