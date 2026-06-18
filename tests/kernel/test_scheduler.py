"""Scheduler-min: deterministic work, ordered claiming, and invoke/resume dispatch."""

from datetime import UTC, datetime, timedelta

import pytest
from agentx_contracts.enums import RunMode
from agentx_contracts.journal import ApprovalResolved
from agentx_contracts.mandate import (
    Charter,
    DomainPackRef,
    InstanceBinding,
    MandateType,
    SettlementRules,
    VerificationSuite,
)
from agentx_contracts.run import RunResult
from agentx_contracts.trigger import DeadlineTrigger, Trigger
from agentx_contracts.verification import Trace
from agentx_kernel.scheduler import ApprovalWork, SchedulerWorker, TriggerWork
from agentx_kernel.stores.memory import InMemorySchedulerStore

NOW = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)


def _mandate() -> MandateType:
    return MandateType(
        id="type_lead_finder_v0",
        name="lead-finder",
        version="0.1.0",
        charter=Charter(goal="Find qualified leads."),
        domain_pack=DomainPackRef(name="dental", version="0.1.0"),
        verification=VerificationSuite(),
        settlement=SettlementRules(),
    )


def _instance(instance_id: str = "inst_a") -> InstanceBinding:
    return InstanceBinding(
        instance_id=instance_id,
        type_ref="lead-finder@0.1.0",
        ring="L1",
        heap_region_id=f"heap_{instance_id}",
    )


def _trigger(reason: str = "sweep") -> DeadlineTrigger:
    return DeadlineTrigger(ts=NOW, reason=reason)


def _approval(run_id: str = "run_1") -> ApprovalResolved:
    return ApprovalResolved(
        event_id=f"{run_id}:approval:resolved",
        seq=7,
        ts=NOW,
        instance_id="inst_a",
        run_id=run_id,
        actor="manager:test",
        decision="approve",
    )


def _result(run_id: str) -> RunResult:
    return RunResult(run_id=run_id, state="settled", trace=Trace(run_id=run_id))


class FakeInvoker:
    def __init__(self) -> None:
        self.invocations: list[tuple[MandateType, InstanceBinding, Trigger, RunMode]] = []
        self.resumptions: list[tuple[str, ApprovalResolved]] = []

    async def invoke(
        self,
        *,
        mandate: MandateType,
        instance: InstanceBinding,
        trigger: Trigger,
        mode: RunMode,
    ) -> RunResult:
        self.invocations.append((mandate, instance, trigger, mode))
        return _result("run_trigger")

    async def resume(self, *, run_id: str, approval: ApprovalResolved) -> RunResult:
        self.resumptions.append((run_id, approval))
        return _result(run_id)


def test_work_ids_are_deterministic_and_ignore_retry_time() -> None:
    first = TriggerWork.schedule(
        mandate=_mandate(),
        instance=_instance(),
        trigger=_trigger(),
        mode="live",
    )
    retry = TriggerWork.schedule(
        mandate=_mandate(),
        instance=_instance(),
        trigger=_trigger(),
        mode="live",
        available_at=NOW + timedelta(minutes=5),
    )
    approval = ApprovalWork.schedule(_approval())

    assert first.work_id == retry.work_id
    assert first.available_at == NOW
    assert approval.work_id == ApprovalWork.schedule(_approval()).work_id
    assert approval.available_at == NOW


async def test_in_memory_store_claims_only_due_work_in_deterministic_order() -> None:
    store = InMemorySchedulerStore()
    later = TriggerWork.schedule(
        mandate=_mandate(),
        instance=_instance("inst_later"),
        trigger=_trigger("later"),
        mode="sim",
        available_at=NOW + timedelta(minutes=1),
    )
    same_time_a = TriggerWork.schedule(
        mandate=_mandate(),
        instance=_instance("inst_a"),
        trigger=_trigger("a"),
        mode="sim",
        available_at=NOW,
    )
    same_time_b = TriggerWork.schedule(
        mandate=_mandate(),
        instance=_instance("inst_b"),
        trigger=_trigger("b"),
        mode="sim",
        available_at=NOW,
    )
    for work in (later, same_time_b, same_time_a):
        await store.enqueue(work)

    expected = sorted((same_time_a, same_time_b), key=lambda work: work.work_id)
    assert await store.claim_next(NOW - timedelta(seconds=1)) is None
    assert await store.claim_next(NOW) == expected[0]
    await store.complete(expected[0].work_id)
    assert await store.claim_next(NOW) == expected[1]
    await store.complete(expected[1].work_id)
    assert await store.claim_next(NOW) is None
    assert await store.claim_next(NOW + timedelta(minutes=1)) == later


async def test_worker_dispatches_trigger_then_approval_and_marks_each_complete() -> None:
    store = InMemorySchedulerStore()
    invoker = FakeInvoker()
    worker = SchedulerWorker(store=store, invoker=invoker)
    trigger_work = TriggerWork.schedule(
        mandate=_mandate(),
        instance=_instance(),
        trigger=_trigger(),
        mode="live",
    )
    approval_work = ApprovalWork.schedule(_approval(), available_at=NOW + timedelta(seconds=1))
    await store.enqueue(approval_work)
    await store.enqueue(trigger_work)

    assert await worker.run_once(NOW) == _result("run_trigger")
    assert invoker.invocations == [(_mandate(), _instance(), _trigger(), "live")]
    assert await worker.run_once(NOW) is None

    assert await worker.run_once(NOW + timedelta(seconds=1)) == _result("run_1")
    assert invoker.resumptions == [("run_1", _approval())]
    assert await worker.run_once(NOW + timedelta(seconds=1)) is None


async def test_worker_requeues_failed_work_at_the_supplied_now() -> None:
    class FailingInvoker(FakeInvoker):
        async def invoke(
            self,
            *,
            mandate: MandateType,
            instance: InstanceBinding,
            trigger: Trigger,
            mode: RunMode,
        ) -> RunResult:
            raise RuntimeError("transient")

    store = InMemorySchedulerStore()
    work = TriggerWork.schedule(
        mandate=_mandate(),
        instance=_instance(),
        trigger=_trigger(),
        mode="sim",
    )
    await store.enqueue(work)
    worker = SchedulerWorker(store=store, invoker=FailingInvoker())

    with pytest.raises(RuntimeError, match="transient"):
        await worker.run_once(NOW)

    assert await store.claim_next(NOW) == work
