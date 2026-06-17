"""K1 — the append-only journal store: total order per instance + idempotency.

The journal is the event-sourced source of truth (BLUEPRINT §2). Appending must assign a monotonic
per-instance ``seq`` (the ledger's total order) and reject a duplicate ``idempotency_key`` so an
LLM/gateway retry can never double-append the same effect.
"""

import uuid
from datetime import UTC, datetime

import pytest
from agentx_contracts import DeadlineTrigger, JournalEvent, RunCreated, SyscallSettled
from agentx_kernel.errors import DuplicateIdempotencyKey
from agentx_kernel.stores.memory import InMemoryJournalStore


def _run_created(instance_id: str) -> RunCreated:
    return RunCreated(
        event_id=str(uuid.uuid4()),
        seq=0,  # placeholder — the store assigns the real seq
        ts=datetime.now(UTC),
        instance_id=instance_id,
        run_id="run_1",
        type_ref="lead-finder@0.1.0",
        trigger=DeadlineTrigger(ts=datetime.now(UTC), reason="test"),
    )


def _syscall_settled(instance_id: str, idem: str) -> SyscallSettled:
    return SyscallSettled(
        event_id=str(uuid.uuid4()),
        seq=0,
        ts=datetime.now(UTC),
        instance_id=instance_id,
        run_id="run_1",
        idempotency_key=idem,
        syscall="draft_email",
        status="ok",
        fulfilled_by="stub",
        maturity_used=1,
    )


async def test_append_assigns_monotonic_seq_per_instance() -> None:
    store = InMemoryJournalStore()
    e1 = await store.append(_run_created("inst_a"))
    e2 = await store.append(_run_created("inst_a"))
    e3 = await store.append(_run_created("inst_b"))
    assert (e1.seq, e2.seq) == (1, 2)  # per-instance monotonic
    assert e3.seq == 1  # a different instance has its own counter


async def test_duplicate_idempotency_key_is_rejected() -> None:
    store = InMemoryJournalStore()
    await store.append(_syscall_settled("inst_a", idem="k1"))
    with pytest.raises(DuplicateIdempotencyKey):
        await store.append(_syscall_settled("inst_a", idem="k1"))


async def test_none_idempotency_keys_do_not_collide() -> None:
    store = InMemoryJournalStore()
    # Two non-effectful events both carry idempotency_key=None — must NOT be treated as duplicates.
    await store.append(_run_created("inst_a"))
    await store.append(_run_created("inst_a"))  # should not raise


async def test_read_instance_returns_events_ordered_by_seq() -> None:
    store = InMemoryJournalStore()
    await store.append(_run_created("inst_a"))
    await store.append(_syscall_settled("inst_a", idem="k1"))
    await store.append(_run_created("inst_b"))
    events: list[JournalEvent] = await store.read_instance("inst_a")
    assert [e.seq for e in events] == [1, 2]
    assert all(e.instance_id == "inst_a" for e in events)


async def test_read_run_filters_by_run_id() -> None:
    store = InMemoryJournalStore()
    await store.append(_run_created("inst_a"))
    got = await store.read_run("run_1")
    assert len(got) == 1 and got[0].run_id == "run_1"
    assert await store.read_run("missing") == []
