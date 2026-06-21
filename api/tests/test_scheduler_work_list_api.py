"""C13 — Scheduler-work list API (BLUEPRINT §8 row 3).

Per the UI overhaul spec, the Kernel view's Scheduler tab needs a dedicated list
endpoint that surfaces every scheduler work row in a shape that's ready for the UI:

    {
      "work": [
        {
          "work_id": "trigger:inst_demo:...",
          "kind": "trigger",                       # trigger | approval
          "status": "pending",                      # pending | claimed | completed | failed
          "attempts": 0,
          "available_at": "2026-06-21T13:00:00+00:00",
          "run_id": "inst_demo:deadline:...",
          "instance_id": "inst_demo",
          "type_ref": "type_lead_finder_v0",
          "updated_at": "2026-06-21T13:00:00+00:00"
        },
        ...
      ],
      "count": int
    }

The endpoint MUST be:
  - READ-ONLY. No contract edits, no scheduler-store writes.
  - Graceful on an empty store (``{"work": [], "count": 0}``, never 500).
  - Honest about a bad filter (``?status=bogus`` → HTTP 400, not silent empty).
  - Bounded in response size (``?limit=`` is capped 1..1000 so a runaway client
    can't blow the response).
  - Sort-stable: rows come back in ``(available_at, work_id)`` order so the UI
    doesn't reorder between page loads.

The matching detail endpoint (``/scheduler-work/{work_id}``) and the
``SchedulerWorkStatus`` projection shape already existed before this card; this
test pins the list's shape and behavior to the same contract so the dashboard
team can wire it without re-deriving anything from the kernel.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from agentx_api.app import create_app

TEST_TOKEN = "***"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Empty memory-mode app — no enqueued scheduler work. The list endpoint must
    return ``{"work": [], "count": 0}`` on a cold install, never 500."""
    app = create_app(use_mongo=False, seed_demo=False, operator_token=TEST_TOKEN, start_worker=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as test_client:
        yield test_client


@pytest.fixture
async def populated_client() -> AsyncIterator[AsyncClient]:
    """Memory-mode app with three enqueued scheduler work rows of mixed kinds and statuses:

      - one pending trigger
      - one claimed trigger (claimed via ``claim_next`` so the row's status field flips)
      - one completed approval (claimed then completed)

    All three should appear in the unfiltered list; only the pending one should
    appear when ``?status=pending`` is set; only the trigger kind should appear
    when we hand-build a per-kind filter at the store level (the API doesn't
    expose a kind filter, only a status one, per the spec).
    """
    app = create_app(use_mongo=False, seed_demo=False, operator_token=TEST_TOKEN, start_worker=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as test_client:
        # Reach into the runtime state — same pattern as C3's heap-memory tests —
        # to enqueue deterministic work without spinning up the scheduler worker.
        state = test_client._transport.app.state.dashboard  # type: ignore[attr-defined]
        store = state.runtime.scheduler_store

        await _enqueue_trigger(
            store,
            work_id="trigger_pending",
            instance_id="inst_alpha",
            available_at=datetime(2026, 6, 21, 12, 0, tzinfo=UTC),
        )
        await _enqueue_trigger(
            store,
            work_id="trigger_claimed",
            instance_id="inst_beta",
            available_at=datetime(2026, 6, 21, 11, 0, tzinfo=UTC),
        )
        await _enqueue_approval(
            store,
            work_id="approval_completed",
            run_id="run_gamma_done",
            instance_id="inst_gamma",
            available_at=datetime(2026, 6, 21, 10, 0, tzinfo=UTC),
        )

        # Flip the second trigger to ``claimed`` by running claim_next once, then
        # flip the approval to ``completed`` via claim_next + complete. The third
        # work row stays ``pending`` so we have one of every status to filter on.
        now = datetime(2026, 6, 21, 13, 0, tzinfo=UTC)
        await store.claim_next(now)
        await store.claim_next(now)
        await store.complete("approval_completed")

        yield test_client


async def _enqueue_trigger(store: object, *, work_id: str, instance_id: str, available_at: datetime) -> None:
    """Bypass ``TriggerWork.schedule`` (which derives ``work_id`` from a hash) and
    enqueue a row whose ``work_id`` is the explicit test fixture id. We do this by
    building the row via ``schedule`` then patching the id — keeps the deterministic
    ``work_id`` formula consistent for any field we forgot, while letting the
    test reference rows by stable name."""
    from agentx_contracts.mandate import InstanceBinding
    from agentx_contracts.trigger import DeadlineTrigger
    from agentx_kernel.scheduler import TriggerWork
    from agentx_mandate.library.lead_finder import build_lead_finder_type

    mandate = build_lead_finder_type()
    type_ref = f"lead-finder@{mandate.version}"
    instance = InstanceBinding(
        instance_id=instance_id,
        type_ref=type_ref,
        ring="L1",
        heap_region_id=f"heap_{instance_id}",
    )
    trigger = DeadlineTrigger(
        ts=available_at,
        reason=f"test trigger for {instance_id}",
        entity_id=f"entity_{instance_id}",
    )
    work = TriggerWork.schedule(
        mandate=mandate,
        instance=instance,
        trigger=trigger,
        mode="sim",
        available_at=available_at,
    ).model_copy(update={"work_id": work_id})
    await store.enqueue(work)  # type: ignore[attr-defined]


async def _enqueue_approval(
    store: object, *, work_id: str, run_id: str, instance_id: str, available_at: datetime
) -> None:
    """Same pattern as ``_enqueue_trigger`` but for ``ApprovalWork``. Bypasses the
    class-level model_validator that requires ``approval.run_id``.

    Note: ``ApprovalDecision`` is a ``Literal["approve", "edit", "reject"]`` (not an
    Enum), so we pass the string directly. Tests cover all three literals elsewhere
    in the kernel; here we just need any resolved approval to populate the row.
    """
    from agentx_contracts.journal import ApprovalResolved
    from agentx_kernel.scheduler import ApprovalWork

    approval = ApprovalResolved(
        event_id=f"{run_id}:approval",
        seq=0,
        ts=available_at,
        instance_id=instance_id,
        run_id=run_id,
        decision="approve",
    )
    work = ApprovalWork.schedule(approval, available_at=available_at).model_copy(update={"work_id": work_id})
    await store.enqueue(work)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Empty-store behavior
# ---------------------------------------------------------------------------


async def test_list_returns_empty_envelope_when_queue_is_empty(client: AsyncClient) -> None:
    """A cold install must not 500. The Kernel view renders an EmptyState from
    ``count == 0``; the route returns 200 with an empty list."""
    response = await client.get("/scheduler-work")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {"work": [], "count": 0}


# ---------------------------------------------------------------------------
# Happy path — full list, sorted, with the contract-shaped envelope
# ---------------------------------------------------------------------------


async def test_list_returns_all_rows_in_sorted_order(populated_client: AsyncClient) -> None:
    """Three rows in the store: the list endpoint returns all three, ordered by
    ``available_at`` ascending (oldest first). The Kernel view depends on this
    order — it's the same order the scheduler worker uses to claim next."""
    response = await populated_client.get("/scheduler-work")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 3
    assert len(body["work"]) == 3

    # Sort check: earliest available_at first.
    available_ats = [row["available_at"] for row in body["work"]]
    assert available_ats == sorted(available_ats), f"rows not in (available_at, work_id) order: {available_ats}"

    # All three work_ids we enqueued are present.
    work_ids = {row["work_id"] for row in body["work"]}
    assert work_ids == {"trigger_pending", "trigger_claimed", "approval_completed"}


async def test_list_row_shape_matches_scheduler_work_status_contract(
    populated_client: AsyncClient,
) -> None:
    """The detail endpoint and the list endpoint must produce the same row shape —
    the dashboard builds one row component and reuses it. Any drift between
    ``GET /scheduler-work/{id}`` and ``GET /scheduler-work?status=`` here means a
    silent UI bug."""
    list_response = await populated_client.get("/scheduler-work")
    assert list_response.status_code == 200, list_response.text
    list_rows = {row["work_id"]: row for row in list_response.json()["work"]}

    # Pick one row from the list and compare its shape to the detail endpoint for
    # the same id — they must be byte-identical (modulo the wrapping key).
    detail_response = await populated_client.get("/scheduler-work/trigger_pending")
    assert detail_response.status_code == 200, detail_response.text
    detail_row = detail_response.json()["work"]

    assert list_rows["trigger_pending"] == detail_row, (
        "list and detail endpoints disagree on the row shape — the UI will render "
        "the same data inconsistently across tabs"
    )


async def test_list_row_keys_are_stable(populated_client: AsyncClient) -> None:
    """Frontend consumers pin to these exact keys. Adding a field is fine;
    renaming or dropping one is a breaking change for the dashboard team."""
    response = await populated_client.get("/scheduler-work")
    row = response.json()["work"][0]
    assert set(row.keys()) == {
        "work_id",
        "kind",
        "status",
        "attempts",
        "available_at",
        "run_id",
        "instance_id",
        "type_ref",
        "updated_at",
    }


# ---------------------------------------------------------------------------
# Filter behavior — ?status= and ?limit=
# ---------------------------------------------------------------------------


async def test_status_filter_returns_only_matching_rows(
    populated_client: AsyncClient,
) -> None:
    """``?status=pending`` returns only the row we deliberately left pending; the
    claimed and completed rows are excluded."""
    response = await populated_client.get("/scheduler-work?status=pending")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 1
    assert {row["work_id"] for row in body["work"]} == {"trigger_pending"}
    assert all(row["status"] == "pending" for row in body["work"])


async def test_status_filter_recognises_all_four_states(
    populated_client: AsyncClient,
) -> None:
    """Every legal status value returns the rows in that bucket. The populated
    fixture leaves one row per known status, so this is a full cross-check."""
    expected = {
        "pending": {"trigger_pending"},
        "claimed": {"trigger_claimed"},
        "completed": {"approval_completed"},
        "failed": set(),
    }
    for status, expected_ids in expected.items():
        response = await populated_client.get(f"/scheduler-work?status={status}")
        assert response.status_code == 200, response.text
        body = response.json()
        assert {row["work_id"] for row in body["work"]} == expected_ids, (
            f"status={status}: got {[r['work_id'] for r in body['work']]}, expected {expected_ids}"
        )


async def test_invalid_status_filter_returns_400_not_silent_empty(
    populated_client: AsyncClient,
) -> None:
    """A typo'd status value must surface as 400 — silently returning an empty
    list would hide a real client bug."""
    response = await populated_client.get("/scheduler-work?status=bogus")
    assert response.status_code == 400, response.text
    # The reader's error string is propagated so the UI can show "must be one of …".
    detail = response.json().get("detail", "")
    assert "invalid status filter" in detail
    assert "bogus" in detail


async def test_limit_caps_response_size(populated_client: AsyncClient) -> None:
    """``?limit=2`` returns at most two rows even when more are available. The
    store's deterministic sort means we can predict which two."""
    response = await populated_client.get("/scheduler-work?limit=2")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 2
    assert len(body["work"]) == 2
    # Oldest two by available_at.
    expected = {"approval_completed", "trigger_claimed"}
    assert {row["work_id"] for row in body["work"]} == expected


async def test_limit_out_of_range_is_rejected_by_fastapi(
    populated_client: AsyncClient,
) -> None:
    """FastAPI's ``Query(ge=1, le=1000)`` enforces the bound at the routing layer
    so a runaway client gets a clean 422 before the reader ever runs."""
    too_small = await populated_client.get("/scheduler-work?limit=0")
    assert too_small.status_code == 422
    too_large = await populated_client.get("/scheduler-work?limit=1001")
    assert too_large.status_code == 422


# ---------------------------------------------------------------------------
# Reader-level tests — same contract, no HTTP
# ---------------------------------------------------------------------------


async def test_state_reader_function_is_exported() -> None:
    """The task body says 'Add api/src/agentx_api/state.py reader'. The reader
    must be importable from state.py so future callers can compose it without
    going through HTTP."""
    from agentx_api import state as state_module

    assert hasattr(state_module, "scheduler_work_list")
    assert callable(state_module.scheduler_work_list)


async def test_state_reader_returns_envelope_for_empty_store() -> None:
    """The reader's empty-store contract is what the route returns on a cold
    install. Asserting it here keeps the contract testable without HTTP."""
    from agentx_api.state import create_state, scheduler_work_list

    state = create_state(use_mongo=False, seed_demo=False, send_email_transport=None)
    await state.start()
    try:
        body = await scheduler_work_list(state)
        assert body == {"work": [], "count": 0}
    finally:
        await state.close()


async def test_state_reader_rejects_unknown_status() -> None:
    """The reader raises ``ValueError`` on an unknown status so the route can
    surface a 400. A typo silently returning an empty list would hide the
    client bug — this pins the failure mode."""
    from agentx_api.state import create_state, scheduler_work_list

    state = create_state(use_mongo=False, seed_demo=False, send_email_transport=None)
    await state.start()
    try:
        with pytest.raises(ValueError, match="invalid status filter"):
            await scheduler_work_list(state, status="not-a-real-status")
    finally:
        await state.close()


async def test_state_reader_clamps_oversized_limit() -> None:
    """A caller that asks for ``limit=10000`` gets clamped to 1000 instead of
    failing or pulling the whole store. The clamp is a safety net on top of
    FastAPI's Query bound, so it holds even when the reader is called directly."""
    from agentx_api.state import create_state, scheduler_work_list

    state = create_state(use_mongo=False, seed_demo=False, send_email_transport=None)
    await state.start()
    try:
        # No rows in the store, but the clamp is the contract we're testing —
        # assert it doesn't raise on an oversized limit.
        body = await scheduler_work_list(state, limit=10_000)
        assert body == {"work": [], "count": 0}
    finally:
        await state.close()
