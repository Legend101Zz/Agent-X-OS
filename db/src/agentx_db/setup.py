"""Index-setup entry point for PyMongo async databases."""

from typing import Any

from .indexes import INDEXES


async def ensure_indexes(database: Any) -> None:
    """Create all Phase-1 indexes from ``INDEXES``. ``create_index`` is idempotent."""
    for collection_name, specs in INDEXES.items():
        collection = database[collection_name]
        for spec in specs:
            await collection.create_index(
                spec.keys,
                name=spec.name,
                unique=spec.unique,
                sparse=spec.sparse,
            )
