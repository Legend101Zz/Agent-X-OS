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
from agentx_contracts.journal import ApprovalResolved, ManagerAction, RunParked, SyscallAttempted
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.mandate import InstanceBinding, MandateInstance, MandateType

from .ports import JournalStore, ProjectionStore
from .projections import Projections
from .registry import MandateRegistry


class ApprovalItem(AgentXModel):
    run_id: str
    reason: str
    required_ring: Ring | None = None
    seq: int
    approval_card: JsonObject | None = None


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
        self._registry = MandateRegistry(projection_store)

    async def register_mandate_type(self, mandate: MandateType) -> MandateType:
        return await self._registry.register_type(mandate)

    async def list_mandate_types(self) -> list[MandateType]:
        return await self._registry.list_types()

    async def instantiate_mandate(self, instance: MandateInstance) -> MandateInstance:
        return await self._registry.instantiate(instance)

    async def list_mandate_instances(self, *, customer_id: str | None = None) -> list[MandateInstance]:
        return await self._registry.list_instances(customer_id=customer_id)

    async def instance_binding(self, instance_id: str) -> InstanceBinding:
        return await self._registry.binding(instance_id)

    async def approval_inbox(self, *, instance_id: str) -> ApprovalInbox:
        events = await self.journal.read_instance(instance_id)
        resolved = {event.run_id for event in events if isinstance(event, ApprovalResolved)}
        items: list[ApprovalItem] = []
        for index, event in enumerate(events):
            if (
                not isinstance(event, RunParked)
                or event.awaiting != "human_approval"
                or event.run_id is None
                or event.run_id in resolved
            ):
                continue
            attempted = next(
                (
                    prior
                    for prior in reversed(events[:index])
                    if isinstance(prior, SyscallAttempted) and prior.run_id == event.run_id
                ),
                None,
            )
            card: JsonObject | None = None
            if attempted is not None:
                idempotency_key = attempted.event_id.removesuffix(":attempt")
                card = {
                    "syscall": attempted.syscall,
                    "args": attempted.args,
                    "idempotency_key": idempotency_key,
                }
            items.append(
                ApprovalItem(
                    run_id=event.run_id,
                    reason=event.reason,
                    required_ring=event.required_ring,
                    seq=event.seq,
                    approval_card=card,
                )
            )
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
