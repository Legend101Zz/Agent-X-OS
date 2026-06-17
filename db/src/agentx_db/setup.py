"""Index-setup entry point (STUB — kernel implements against AsyncMongoClient in Session B).

Interfaces/schemas only in Session A. The real body (Session B, kernel) is a few lines:

    from pymongo import AsyncMongoClient
    from agentx_db.indexes import INDEXES

    async def ensure_indexes(database) -> None:
        for coll, specs in INDEXES.items():
            for spec in specs:
                await database[coll].create_index(
                    spec.keys, name=spec.name, unique=spec.unique, sparse=spec.sparse,
                )

``create_index`` is idempotent, so this is safe to run on every boot.
"""

from .indexes import INDEXES


async def ensure_indexes(database: object) -> None:
    """Create all Phase-1 indexes from ``INDEXES`` (idempotent). ``database`` is an ``AsyncMongoClient``
    database handle. Session B implements; Session A raises so the boundary is explicit."""
    raise NotImplementedError(
        f"agentx_db.setup.ensure_indexes: kernel applies {sum(len(v) for v in INDEXES.values())} "
        "index specs across "
        f"{len(INDEXES)} collections via AsyncMongoClient (Session B)."
    )
