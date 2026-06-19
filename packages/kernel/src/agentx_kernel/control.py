"""Typed command/query surface over kernel projections.

This is the dashboard/API layer in miniature: reads are projection/journal views, and commands append
manager actions to the journal.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, cast

import agentx_db.collections as c
from agentx_contracts.base import AgentXModel
from agentx_contracts.enums import ApprovalDecision, Ring, RunMode
from agentx_contracts.journal import (
    ApprovalResolved,
    ManagerAction,
    RunParked,
    SyscallAttempted,
)
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.mandate import InstanceBinding, MandateInstance, MandateType
from agentx_contracts.trigger import Trigger

from .ports import JournalStore, ProjectionStore, RunContinuationStore
from .projections import Projections
from .registry import MandateRegistry
from .scheduler import ApprovalWork, TriggerWork


class ApprovalEnqueuer(Protocol):
    """Structural type the API uses to enqueue ApprovalWork without coupling KernelControl to scheduler."""

    def build_approval_work(self, approval: ApprovalResolved) -> ApprovalWork: ...

    async def enqueue(self, work: ApprovalWork) -> None: ...


class TriggerEnqueuer(Protocol):
    """Structural type the API uses to enqueue TriggerWork without coupling KernelControl to scheduler."""

    def build_trigger_work(
        self, *, mandate: MandateType, instance: InstanceBinding, trigger: Trigger, mode: RunMode
    ) -> TriggerWork: ...

    async def enqueue(self, work: TriggerWork) -> None: ...


class ApprovalItem(AgentXModel):
    run_id: str
    reason: str
    required_ring: Ring | None = None
    seq: int
    approval_card: JsonObject | None = None


class ApprovalInbox(AgentXModel):
    instance_id: str
    items: list[ApprovalItem]


class ApprovalResolution(AgentXModel):
    """The typed return value of ``resolve_approval`` — every manager action returns one."""

    action: ManagerAction
    resolution: ApprovalResolved
    work_enqueued: bool
    """True when the API/worker should run the scheduler to advance the run."""
    work_id: str | None = None
    """The ``ApprovalWork.work_id`` to claim for resume (when decision=approve and the run was parked)."""
    run_id: str


class InstanceFile(AgentXModel):
    instance_id: str
    facts: list[JsonObject]
    resume: JsonObject | None = None


class KernelFloor(AgentXModel):
    instance_id: str
    ring: Ring
    approval_count: int


class KernelControl:
    """Phase-1 internal command/query API.

    Lane-pure: this module does NOT import the syscall or swarm packages. The run-loop machinery
    (resumable invoker, scheduler worker) is accepted as an optional ``driver`` so command endpoints
    can enqueue durable work without crossing lanes; when no driver is provided the resolution only
    journals (legacy behaviour).
    """

    def __init__(
        self,
        *,
        journal: JournalStore,
        projections: Projections,
        projection_store: ProjectionStore,
        continuations: RunContinuationStore | None = None,
    ) -> None:
        self.journal = journal
        self._projections = projections
        self._projection_store = projection_store
        self._continuations = continuations
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
        """Backward-compatible wrapper: journals ``ManagerAction`` + ``ApprovalResolved(approve)``.

        Does NOT enqueue resume work. Use ``resolve_approval`` at the API edge so the run actually
        resumes through the worker; this remains for legacy callers (scripts/tests) that drive the
        kernel resume path themselves.
        """
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

    async def resolve_approval(
        self,
        *,
        instance_id: str,
        run_id: str,
        decision: ApprovalDecision,
        actor: str,
        now: datetime,
        edited: bool = False,
        scheduler: ApprovalEnqueuer | None = None,
    ) -> ApprovalResolution:
        """One journaled approval path: approve / reject share one implementation.

        Behaviour:

        - Append a ``ManagerAction`` (one audit row per manager event).
        - Append ``ApprovalResolved`` (one per resolution; replays of the same call hit the journal's
          idempotency-key guard on the ManagerAction event_id, which makes retries a no-op).
        - For ``decision="approve"`` AND the run was parked awaiting human approval AND a scheduler
          is wired: enqueue ``ApprovalWork`` so the worker resumes through the same gateway.
        - For ``decision="reject"``: terminalize the parked continuation so a stale resumption can
          never replay the parked effect; do NOT execute the syscall; the audit trail is preserved.
        """
        manager_event_id = f"{run_id}:manager:{decision}:{actor}"
        action = cast(
            ManagerAction,
            await self.journal.append(
                ManagerAction(
                    event_id=manager_event_id,
                    seq=0,
                    ts=now,
                    instance_id=instance_id,
                    run_id=run_id,
                    actor=actor,
                    action=decision,
                    detail={"decision": decision},
                )
            ),
        )
        resolution_event_id = f"{run_id}:approval:resolved:{actor}"
        resolution = cast(
            ApprovalResolved,
            await self.journal.append(
                ApprovalResolved(
                    event_id=resolution_event_id,
                    seq=0,
                    ts=now,
                    instance_id=instance_id,
                    run_id=run_id,
                    actor=actor,
                    decision=decision,
                    edited=edited,
                )
            ),
        )
        work_id: str | None = None
        work_enqueued = False
        if decision == "approve" and scheduler is not None:
            work = scheduler.build_approval_work(resolution)
            await scheduler.enqueue(work)
            work_id = work.work_id
            work_enqueued = True
        elif decision == "approve":
            # Default fallback: if no scheduler was passed but KernelControl was bound to one,
            # enqueue there. Lets the API composition wire a single scheduler driver.
            enqueuer = getattr(self, "_approval_enqueuer", None)
            if enqueuer is not None:
                work = enqueuer.build_approval_work(resolution)
                await enqueuer.enqueue(work)
                work_id = work.work_id
                work_enqueued = True
        elif decision == "reject" and self._continuations is not None:
            # Drop any durable continuation so a stale worker claim cannot replay the parked effect.
            await self._continuations.delete(run_id)
        return ApprovalResolution(
            action=action,
            resolution=resolution,
            work_enqueued=work_enqueued,
            work_id=work_id,
            run_id=run_id,
        )

    async def enqueue_trigger(
        self,
        *,
        instance_id: str,
        mandate: MandateType,
        trigger: Trigger,
        mode: RunMode,
        actor: str,
        now: datetime,
        scheduler: TriggerEnqueuer | None = None,
    ) -> ManagerAction:
        """Journal a ``ManagerAction(action='trigger_run')`` and enqueue ``TriggerWork``.

        The run itself is driven by the worker via the existing ``Phase1RunInvoker.invoke`` path —
        we do not invoke here. Returns the manager action so callers can surface the journal row.
        """
        from .scheduler import TriggerWork  # local import keeps the surface tight

        action = cast(
            ManagerAction,
            await self.journal.append(
                ManagerAction(
                    event_id=f"{instance_id}:manager:trigger_run:{actor}:{int(now.timestamp())}",
                    seq=0,
                    ts=now,
                    instance_id=instance_id,
                    actor=actor,
                    action="trigger_run",
                    detail={
                        "type_ref": mandate.id,
                        "trigger": trigger.model_dump(mode="json"),
                        "mode": mode,
                    },
                )
            ),
        )
        if scheduler is not None:
            binding = await self._registry.binding(instance_id)
            work = TriggerWork.schedule(
                mandate=mandate,
                instance=binding,
                trigger=trigger,
                mode=mode,
            )
            await scheduler.enqueue(work)
        else:
            enqueuer = getattr(self, "_trigger_enqueuer", None)
            if enqueuer is not None:
                binding = await self._registry.binding(instance_id)
                mode_str: str = mode if isinstance(mode, str) else mode.value
                work = enqueuer.build_trigger_work(
                    mandate=mandate,
                    instance=binding,
                    trigger=trigger,
                    mode=mode_str,
                )
                await enqueuer.enqueue(work)
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
