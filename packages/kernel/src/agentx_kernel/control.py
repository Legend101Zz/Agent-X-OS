"""Typed command/query surface over kernel projections.

This is the dashboard/API layer in miniature: reads are projection/journal views, and commands append
manager actions to the journal.
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

import agentx_db.collections as c
from agentx_contracts.base import AgentXModel
from agentx_contracts.enums import Ring
from agentx_contracts.journal import ApprovalResolved, ManagerAction, RunParked
from agentx_contracts.jsontypes import JsonObject

from .ports import JournalStore, ProjectionStore
from .projections import Projections


class ApprovalItem(AgentXModel):
    run_id: str
    reason: str
    required_ring: Ring | None = None
    seq: int


class ApprovalInbox(AgentXModel):
    instance_id: str
    items: list[ApprovalItem]


class InstanceFile(AgentXModel):
    instance_id: str
    facts: list[JsonObject]
    resume: JsonObject | None = None


class KernelFloor(AgentXModel):
    instance_id: str
    ring: Ring
    approval_count: int


class KernelControl:
    """Phase-1 internal command/query API."""

    def __init__(self, *, journal: JournalStore, projections: Projections, projection_store: ProjectionStore) -> None:
        self.journal = journal
        self._projections = projections
        self._projection_store = projection_store

    async def approval_inbox(self, *, instance_id: str) -> ApprovalInbox:
        events = await self.journal.read_instance(instance_id)
        resolved = {event.run_id for event in events if isinstance(event, ApprovalResolved)}
        items = [
            ApprovalItem(
                run_id=event.run_id or "",
                reason=event.reason,
                required_ring=event.required_ring,
                seq=event.seq,
            )
            for event in events
            if isinstance(event, RunParked)
            and event.awaiting == "human_approval"
            and event.run_id is not None
            and event.run_id not in resolved
        ]
        return ApprovalInbox(instance_id=instance_id, items=items)

    async def instance_file(self, *, instance_id: str) -> InstanceFile:
        fact_docs = await self._projection_store.find(c.HEAP_FACT, {"instance_id": instance_id})
        resume_doc = await self._projection_store.get(c.RESUME, instance_id)
        return InstanceFile(
            instance_id=instance_id,
            facts=[cast(JsonObject, doc) for doc in fact_docs],
            resume=cast(JsonObject, resume_doc) if resume_doc is not None else None,
        )

    async def floor(self, *, instance_id: str) -> KernelFloor:
        inbox = await self.approval_inbox(instance_id=instance_id)
        instance_file = await self.instance_file(instance_id=instance_id)
        ring: Ring = "L0"
        if instance_file.resume is not None:
            raw_ring = instance_file.resume.get("ring")
            if raw_ring in {"L0", "L1", "L2", "L3", "L4"}:
                ring = cast(Ring, raw_ring)
        return KernelFloor(instance_id=instance_id, ring=ring, approval_count=len(inbox.items))

    async def approve(self, *, instance_id: str, run_id: str, actor: str, now: datetime) -> ManagerAction:
        action = cast(
            ManagerAction,
            await self.journal.append(
                ManagerAction(
                    event_id=f"{run_id}:manager:approve",
                    seq=0,
                    ts=now,
                    instance_id=instance_id,
                    run_id=run_id,
                    actor=actor,
                    action="approve",
                    detail={"decision": "approve"},
                )
            ),
        )
        await self.journal.append(
            ApprovalResolved(
                event_id=f"{run_id}:approval:resolved",
                seq=0,
                ts=now,
                instance_id=instance_id,
                run_id=run_id,
                actor=actor,
                decision="approve",
            )
        )
        return action

    async def set_ring(self, *, instance_id: str, ring: Ring, actor: str, now: datetime) -> ManagerAction:
        action = cast(
            ManagerAction,
            await self.journal.append(
                ManagerAction(
                    event_id=f"{instance_id}:manager:set_ring:{ring}",
                    seq=0,
                    ts=now,
                    instance_id=instance_id,
                    actor=actor,
                    action="set_ring",
                    detail={"ring": ring},
                )
            ),
        )
        await self._projections.apply(action)
        return action
