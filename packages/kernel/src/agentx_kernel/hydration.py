"""Kernel hydration loader.

This is the I/O half of hydration: read projection state and journal events through kernel ports,
parse them back into contract models, then call the pure mandate assembler.
"""

from __future__ import annotations

from datetime import datetime

import agentx_db.collections as c
from agentx_contracts.mandate import DomainPackRef, HydrationSnapshot
from agentx_contracts.memory import Fact, Thread
from agentx_mandate.hydration import assemble

from .ports import JournalStore, ProjectionStore


class HydrationLoader:
    """Loads an instance's working set from projections, then freezes a mandate snapshot."""

    def __init__(self, projection_store: ProjectionStore, journal_store: JournalStore) -> None:
        self._projection_store = projection_store
        self._journal_store = journal_store

    async def hydrate(
        self,
        *,
        instance_id: str,
        entity_id: str | None,
        skill_pack_refs: list[str],
        domain_pack: DomainPackRef | None,
        now: datetime,
        recent_limit: int = 20,
    ) -> HydrationSnapshot:
        fact_docs = await self._projection_store.find(c.HEAP_FACT, {"instance_id": instance_id})
        facts = [Fact.model_validate(doc) for doc in fact_docs]

        thread = None
        if entity_id is not None:
            thread_doc = await self._projection_store.get(c.THREAD, f"{instance_id}:{entity_id}")
            if thread_doc is not None:
                thread = Thread.model_validate(thread_doc)

        events = await self._journal_store.read_instance(instance_id)
        recent_journal = events[-recent_limit:] if recent_limit > 0 else events
        return assemble(
            facts=facts,
            thread=thread,
            recent_journal=recent_journal,
            skill_pack_refs=skill_pack_refs,
            domain_pack=domain_pack,
            now=now,
        )
