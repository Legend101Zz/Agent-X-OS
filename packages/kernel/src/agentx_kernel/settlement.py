"""Kernel settlement commit path."""

from __future__ import annotations

from typing import cast

from agentx_contracts.journal import RunSettled, WatchRegistered
from agentx_contracts.settlement import SettlementEvent

from .ports import JournalStore
from .projections import Projections


class SettlementCommitter:
    """Append one ``RunSettled`` event and fan it out through projectors."""

    def __init__(self, *, journal: JournalStore, projections: Projections) -> None:
        self._journal = journal
        self._projections = projections

    async def commit(self, settlement: SettlementEvent) -> RunSettled:
        event = cast(
            RunSettled,
            await self._journal.append(
                RunSettled(
                    event_id=f"{settlement.run_id}:settled",
                    seq=0,
                    ts=settlement.settled_at,
                    instance_id=settlement.instance_id,
                    run_id=settlement.run_id,
                    facts=settlement.facts,
                    billing_amount=settlement.billing.amount if settlement.billing is not None else None,
                    trust_delta=settlement.trust.delta if settlement.trust is not None else 0,
                    watch_ids=[watch.id for watch in settlement.watches],
                    spawned=[spawn.child_type_ref for spawn in settlement.spawns],
                )
            ),
        )
        await self._projections.apply(event)
        for watch in settlement.watches:
            watch_event = await self._journal.append(
                WatchRegistered(
                    event_id=f"{watch.id}:registered",
                    seq=0,
                    ts=settlement.settled_at,
                    instance_id=watch.instance_id,
                    run_id=watch.run_id,
                    watch_id=watch.id,
                    condition=watch.condition,
                    deadline=watch.deadline,
                )
            )
            await self._projections.apply(watch_event)
        return event
