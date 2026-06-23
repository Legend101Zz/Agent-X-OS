"""C — `POST /commands/resolve-manual-task` (books-prep Flag #1, per-row CA review).

The route looks up a flagged transaction row from the manual-queue card, runs the engine's
`BooksReviewResolver` micro-run, closes the card, and returns the `BooksReviewResolution` fields.
These tests verify the HTTP wiring + card lookup/close + auth — the resolution behaviour itself is
covered exhaustively in `packages/kernel`'s `test_books_review_resolution.py`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import agentx_db.collections as c
import pytest
from agentx_contracts.mandate import MandateInstance
from agentx_contracts.syscall import SyscallRequest
from agentx_mandate.library.books_prep import build_books_prep_type
from httpx import ASGITransport, AsyncClient

from agentx_api.app import create_app

TEST_TOKEN = "test-operator-token"
INSTANCE_ID = "inst_books_api"


def _flagged_row() -> dict[str, Any]:
    return {
        "dedupe_key": "txn_api_1",
        "date": "2026-04-05",
        "narration": "UPI/AMAZON/office stationery purchase",
        "debit": 1800.0,
        "credit": 0.0,
        "balance": 98200.0,
        "ref": "SIM0002",
        "source": {"doc_id": "april-statement.pdf", "page": 1, "line": 3},
        "account_id": "XXXX1234",
        "statement_period": "2026-04",
        "ledger_head": "Suspense",
        "gst_treatment": "indeterminate_from_source",
        "confidence": 0.4,
        "queued": True,
        "queue_reason": "low categorisation confidence",
    }


async def _seed_books_instance_and_task(app: Any) -> str:
    """Register books-prep, instantiate an instance, and enqueue one review_transaction card."""
    state = app.state.dashboard
    await state.control.register_mandate_type(build_books_prep_type())
    await state.control.instantiate_mandate(
        MandateInstance(
            id=INSTANCE_ID,
            type_ref="books-prep@0.1.0",
            customer_id="Test CA",
            ring="L1",
            heap_region_id="heap_books_api",
        )
    )
    task = state.manual_tasks.enqueue(
        SyscallRequest(
            name="queue_manual_action",
            args={"action": "review_transaction", "reason": "low conf", "transaction": _flagged_row()},
            instance_id=INSTANCE_ID,
            run_id="run_seed",
            idempotency_key="seed:queue:1",
            ring="L1",
            risk_class="reversible_write",
        ),
        source_adapter="queue_manual_action",
    )
    return str(task.id)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(use_mongo=False, operator_token=TEST_TOKEN, start_worker=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    ) as test_client:
        test_client._app = app  # type: ignore[attr-defined]  # stash for setup helpers
        yield test_client


async def test_approve_commits_and_closes_the_card(client: AsyncClient) -> None:
    app = client._app  # type: ignore[attr-defined]
    task_id = await _seed_books_instance_and_task(app)

    response = await client.post(
        "/commands/resolve-manual-task",
        json={"instance_id": INSTANCE_ID, "task_id": task_id, "decision": "approve", "actor": "ca_priya"},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["decision"] == "approve"
    assert body["committed_fact_id"]
    assert body["already_resolved"] is False

    # The fact landed in the shared heap projection.
    state = app.state.dashboard
    facts = await state.store.find(c.HEAP_FACT, {"subject": "txn_api_1", "predicate": "ledger_transaction"})
    assert len(facts) == 1

    # The card left the open review queue.
    queue = (await client.get("/manual-queue")).json()
    assert all(item["id"] != task_id for item in queue["items"])


async def test_edit_commits_corrected_fields(client: AsyncClient) -> None:
    app = client._app  # type: ignore[attr-defined]
    task_id = await _seed_books_instance_and_task(app)

    response = await client.post(
        "/commands/resolve-manual-task",
        json={
            "instance_id": INSTANCE_ID,
            "task_id": task_id,
            "decision": "edit",
            "edits": {"ledger_head": "Office Supplies", "gst_treatment": "input_tax_credit"},
            "actor": "ca_priya",
        },
    )
    assert response.status_code == 202, response.text

    state = app.state.dashboard
    facts = await state.store.find(c.HEAP_FACT, {"subject": "txn_api_1"})
    assert len(facts) == 1
    import json

    payload = json.loads(str(facts[0]["object"]))
    assert payload["ledger_head"] == "Office Supplies"
    assert payload["gst_treatment"] == "input_tax_credit"


async def test_edit_without_edits_is_422(client: AsyncClient) -> None:
    app = client._app  # type: ignore[attr-defined]
    task_id = await _seed_books_instance_and_task(app)
    response = await client.post(
        "/commands/resolve-manual-task",
        json={"instance_id": INSTANCE_ID, "task_id": task_id, "decision": "edit", "actor": "ca_priya"},
    )
    assert response.status_code == 422, response.text


async def test_resolving_twice_is_idempotent(client: AsyncClient) -> None:
    app = client._app  # type: ignore[attr-defined]
    task_id = await _seed_books_instance_and_task(app)
    payload = {"instance_id": INSTANCE_ID, "task_id": task_id, "decision": "approve", "actor": "ca_priya"}

    first = await client.post("/commands/resolve-manual-task", json=payload)
    second = await client.post("/commands/resolve-manual-task", json=payload)
    assert first.json()["already_resolved"] is False
    assert second.json()["already_resolved"] is True

    state = app.state.dashboard
    facts = await state.store.find(c.HEAP_FACT, {"subject": "txn_api_1"})
    assert len(facts) == 1


async def test_unknown_task_is_404(client: AsyncClient) -> None:
    app = client._app  # type: ignore[attr-defined]
    await _seed_books_instance_and_task(app)
    response = await client.post(
        "/commands/resolve-manual-task",
        json={"instance_id": INSTANCE_ID, "task_id": "manual_999", "decision": "approve", "actor": "ca"},
    )
    assert response.status_code == 404, response.text


async def test_requires_bearer_token() -> None:
    app = create_app(use_mongo=False, operator_token=TEST_TOKEN, start_worker=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon:
        response = await anon.post(
            "/commands/resolve-manual-task",
            json={"instance_id": INSTANCE_ID, "task_id": "manual_1", "decision": "approve", "actor": "ca"},
        )
    assert response.status_code in (401, 403), response.text
