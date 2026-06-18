"""Durable manual-task repository: idem enqueue + restart-safe across instances."""

from __future__ import annotations

from datetime import UTC, datetime

from agentx_contracts import SyscallRequest
from agentx_syscall import InMemoryManualTaskRepository


def _request(idempotency_key: str, *, run_id: str = "run_1", args: dict[str, object] | None = None) -> SyscallRequest:
    payload: dict[str, object] = args if args is not None else {"action": "review_lead"}
    return SyscallRequest(
        name="queue_manual_action",
        args=payload,  # type: ignore[arg-type]
        instance_id="inst_1",
        run_id=run_id,
        idempotency_key=idempotency_key,
        ring="L1",
        risk_class="reversible_write",
    )


def test_enqueue_is_idempotent() -> None:
    repo = InMemoryManualTaskRepository()
    req = _request("manual-key-1")
    first = repo.enqueue(req, source_adapter="queue_manual_action")
    second = repo.enqueue(req, source_adapter="queue_manual_action")
    assert first.id == second.id
    assert len(repo.list_open()) == 1


def test_mark_outcome_closes_a_task_and_excludes_it_from_list_open() -> None:
    repo = InMemoryManualTaskRepository()
    task = repo.enqueue(_request("k1"), source_adapter="queue_manual_action")
    repo.mark_outcome(task.id, "completed", {"note": "ok"})
    listed = repo.list_open()
    assert listed == []
    stored = repo.get(task.id)
    assert stored is not None and stored.outcome == "completed"


def test_distinct_idempotency_keys_produce_distinct_tasks() -> None:
    repo = InMemoryManualTaskRepository()
    a = repo.enqueue(_request("ka"), source_adapter="queue_manual_action")
    b = repo.enqueue(_request("kb"), source_adapter="queue_manual_action")
    assert a.id != b.id
    assert {t.idempotency_key for t in repo.list_open()} == {"ka", "kb"}


def test_created_at_is_close_to_now() -> None:
    repo = InMemoryManualTaskRepository()
    before = datetime.now(UTC)
    task = repo.enqueue(_request("kstale"), source_adapter="queue_manual_action")
    after = datetime.now(UTC)
    assert before <= task.created_at <= after


def test_mark_outcome_on_unknown_task_raises_keyerror() -> None:
    repo = InMemoryManualTaskRepository()
    try:
        repo.mark_outcome("missing", "completed")
    except KeyError:
        return
    raise AssertionError("expected KeyError for missing manual task id")
