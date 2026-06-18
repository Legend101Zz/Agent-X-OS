"""Bounded scheduler worker for trigger invocation and parked-run resumption."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal, Protocol, Self, runtime_checkable

from agentx_contracts.base import AgentXModel
from agentx_contracts.enums import RunMode
from agentx_contracts.journal import ApprovalResolved
from agentx_contracts.mandate import InstanceBinding, MandateType
from agentx_contracts.run import RunResult
from agentx_contracts.trigger import Trigger
from pydantic import Field, model_validator


class TriggerWork(AgentXModel):
    """One deterministic request to start a mandate run."""

    kind: Literal["trigger"] = "trigger"
    work_id: str
    available_at: datetime
    mandate: MandateType
    instance: InstanceBinding
    trigger: Trigger
    mode: RunMode

    @classmethod
    def schedule(
        cls,
        *,
        mandate: MandateType,
        instance: InstanceBinding,
        trigger: Trigger,
        mode: RunMode,
        available_at: datetime | None = None,
    ) -> Self:
        payload = {
            "mandate": mandate.model_dump(mode="json"),
            "instance": instance.model_dump(mode="json"),
            "trigger": trigger.model_dump(mode="json"),
            "mode": mode,
        }
        return cls(
            work_id=_work_id("trigger", payload),
            available_at=trigger.ts if available_at is None else available_at,
            mandate=mandate,
            instance=instance,
            trigger=trigger,
            mode=mode,
        )


class ApprovalWork(AgentXModel):
    """One deterministic request to resume a run after its approval was resolved."""

    kind: Literal["approval"] = "approval"
    work_id: str
    available_at: datetime
    approval: ApprovalResolved

    @model_validator(mode="after")
    def require_run_id(self) -> ApprovalWork:
        if self.approval.run_id is None:
            raise ValueError("approval work requires approval.run_id")
        return self

    @classmethod
    def schedule(cls, approval: ApprovalResolved, *, available_at: datetime | None = None) -> Self:
        return cls(
            work_id=_work_id("approval", approval.model_dump(mode="json")),
            available_at=approval.ts if available_at is None else available_at,
            approval=approval,
        )


ScheduledWork = Annotated[TriggerWork | ApprovalWork, Field(discriminator="kind")]


@runtime_checkable
class SchedulerStore(Protocol):
    """Durable queue semantics used by the scheduler worker."""

    async def enqueue(self, work: ScheduledWork) -> None:
        """Insert work idempotently by deterministic ``work_id``."""
        ...

    async def claim_next(self, now: datetime) -> ScheduledWork | None:
        """Atomically claim the earliest due pending item, ordered by time then id."""
        ...

    async def complete(self, work_id: str) -> None:
        """Mark claimed work complete."""
        ...

    async def fail(self, work_id: str, *, retry_at: datetime) -> None:
        """Release claimed work back to pending at ``retry_at``."""
        ...


@runtime_checkable
class ResumableRunInvoker(Protocol):
    """The run boundary needed by scheduler-min without changing frozen contracts."""

    async def invoke(
        self,
        *,
        mandate: MandateType,
        instance: InstanceBinding,
        trigger: Trigger,
        mode: RunMode,
    ) -> RunResult:
        ...

    async def resume(self, *, run_id: str, approval: ApprovalResolved) -> RunResult:
        ...


class SchedulerWorker:
    """Claim and process at most one due item per call."""

    def __init__(self, *, store: SchedulerStore, invoker: ResumableRunInvoker) -> None:
        self._store = store
        self._invoker = invoker

    async def run_once(self, now: datetime) -> RunResult | None:
        work = await self._store.claim_next(now)
        if work is None:
            return None
        try:
            if isinstance(work, TriggerWork):
                result = await self._invoker.invoke(
                    mandate=work.mandate,
                    instance=work.instance,
                    trigger=work.trigger,
                    mode=work.mode,
                )
            else:
                run_id = work.approval.run_id
                assert run_id is not None
                result = await self._invoker.resume(run_id=run_id, approval=work.approval)
        except Exception:
            await self._store.fail(work.work_id, retry_at=now)
            raise
        await self._store.complete(work.work_id)
        return result


def _work_id(kind: str, payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return f"{kind}:{digest}"
