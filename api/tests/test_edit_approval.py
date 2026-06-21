from __future__ import annotations

"""C7 — /commands/edit (edit-with-diff) closes BLUEPRINT §5 kill-condition #2.

The route accepts edited args for a parked approval, rewrites the continuation's
``pending_call.args`` so the resume worker uses the edited args, journals
``ApprovalResolved(edited=True, decision=approve)`` (the same shape as /commands/approve,
plus an ``edit`` sub-document with the before/after diff the dashboard renders), and
returns the same ``work_id`` / ``manager_action`` as approve so the front-end can poll
the scheduler for the resumed run.

These tests cover:
  1. Pure helper ``_arg_diff_keys`` returns added/removed/changed entries.
  2. The ``/commands/edit`` route validates edited_args (422 on empty / non-dict).
  3. Happy path: returns 202, decision="approve", edited=True, work enqueued,
     the ``edit`` sub-doc carries a before/after diff_keys list, the inbox empties,
     and the journal records an ``approval_resolved`` event with ``edited=True``.
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from agentx_api.app import _arg_diff_keys, create_app

TEST_TOKEN = "test-operator-token"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(
        use_mongo=False, seed_demo=True, operator_token=TEST_TOKEN, start_worker=False
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    ) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Pure helper
# ---------------------------------------------------------------------------


def test_arg_diff_keys_classifies_added_removed_changed() -> None:
    """``_arg_diff_keys`` is the shared shape for /commands/edit + the inbox diff view."""
    before = {"to": "a@x", "subject": "Hello", "sent": False}
    after = {"to": "a@x", "subject": "Hello (edited)", "body": "tailored"}

    diff = _arg_diff_keys(before, after)
    by_key = {entry["key"]: entry for entry in diff}

    # `subject` changed (same key, different value) — op="changed" with before+after.
    assert by_key["subject"]["op"] == "changed"
    assert by_key["subject"]["before"] == "Hello"
    assert by_key["subject"]["after"] == "Hello (edited)"

    # `body` was added — op="added" with before=None, after=tailored body.
    assert by_key["body"]["op"] == "added"
    assert by_key["body"]["before"] is None
    assert by_key["body"]["after"] == "tailored"

    # `sent` was removed — op="removed" with before=False, after=None.
    assert by_key["sent"]["op"] == "removed"
    assert by_key["sent"]["before"] is False
    assert by_key["sent"]["after"] is None

    # `to` is unchanged → NOT in the diff (the operator only sees what they need to review).
    assert "to" not in by_key


def test_arg_diff_keys_handles_empty_inputs() -> None:
    """Empty dicts return an empty diff — guard against spurious 'changed' rows."""
    assert _arg_diff_keys({}, {}) == []
    assert _arg_diff_keys({"a": 1}, {}) == [{"key": "a", "op": "removed", "before": 1, "after": None}]
    assert _arg_diff_keys({}, {"a": 1}) == [{"key": "a", "op": "added", "before": None, "after": 1}]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


async def test_edit_rejects_empty_edited_args(client: AsyncClient) -> None:
    """An empty edit is meaningless and risks rewriting args to ``{}`` silently — reject 422."""
    response = await client.post(
        "/commands/edit",
        json={
            "instance_id": "inst_demo",
            "run_id": "run_demo_parked",
            "actor": "manager:test",
            "edited_args": {},
        },
    )
    assert response.status_code == 422, response.text
    assert "empty" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_edit_rewrites_continuation_and_journals_edited_resolve(client: AsyncClient) -> None:
    """End-to-end: edit succeeds, inbox empties, journal records edited=True, work enqueued.

    Original seeded args for ``run_demo_parked`` are
    ``{"to", "subject", "body", "sent": False}`` — we edit the body and add a new
    ``cc`` field, so the diff should contain one ``changed`` (body) and one ``added`` (cc).
    """
    inbox_before = (await client.get("/approvals", params={"instance_id": "inst_demo"})).json()
    assert len(inbox_before["items"]) == 1
    parked = inbox_before["items"][0]
    original_args = parked["drafted_effect"]["args"]
    assert original_args["to"] == "founder-review@agent-x.local"

    edited_args = {
        **original_args,
        "body": "EDITED: tailored body for the manager review.",
        "cc": "ops@agent-x.local",
    }

    response = await client.post(
        "/commands/edit",
        json={
            "instance_id": "inst_demo",
            "run_id": "run_demo_parked",
            "actor": "manager:test",
            "edited_args": edited_args,
        },
    )

    assert response.status_code == 202, response.text
    body: dict[str, Any] = response.json()

    # Same shape as /commands/approve, plus the edit sub-doc.
    assert body["supported"] is True
    assert body["decision"] == "approve"
    assert body["edited"] is True
    assert body["work_enqueued"] is True
    assert body["work_id"].startswith("approval:")
    assert body["manager_action"]["action"] == "approve"

    # The diff sub-doc lets the dashboard render a before/after table.
    assert body["edit"]["before"] == original_args
    assert body["edit"]["after"] == edited_args
    diff_by_key = {entry["key"]: entry for entry in body["edit"]["diff_keys"]}
    assert diff_by_key["body"]["op"] == "changed"
    assert diff_by_key["body"]["before"] == original_args["body"]
    assert diff_by_key["body"]["after"] == edited_args["body"]
    assert diff_by_key["cc"]["op"] == "added"
    assert diff_by_key["cc"]["before"] is None
    assert diff_by_key["cc"]["after"] == "ops@agent-x.local"

    # Inbox is empty (the parked card was consumed by resolve_approval).
    inbox_after = (await client.get("/approvals", params={"instance_id": "inst_demo"})).json()
    assert inbox_after["items"] == []

    # Journal records an ``approval_resolved`` event with edited=True (gold-tier gym case).
    ledger = (await client.get("/journal", params={"kind": "approval_resolved"})).json()
    resolves = [event for event in ledger["events"] if event.get("kind") == "approval_resolved"]
    assert resolves, "expected at least one approval_resolved journal event after edit"
    edited_resolves = [event for event in resolves if event.get("edited") is True]
    assert edited_resolves, "expected the resolve to be flagged edited=True in the journal"
    assert any(
        event.get("decision") == "approve" and event.get("edited") is True
        for event in edited_resolves
    )


async def test_edit_returns_404_when_parked_approval_missing(client: AsyncClient) -> None:
    """The route is ring-aware — if the run_id isn't parked, we 404 not 500."""
    response = await client.post(
        "/commands/edit",
        json={
            "instance_id": "inst_demo",
            "run_id": "run_does_not_exist",
            "actor": "manager:test",
            "edited_args": {"body": "nope"},
        },
    )
    assert response.status_code == 404, response.text
    assert "run_does_not_exist" in response.json()["detail"]
