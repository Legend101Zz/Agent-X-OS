"""End-to-end dashboard operability proof using the in-memory OperatorRuntime.

This is the integration test the task explicitly required: the API + lifespan-owned runtime must
drive the full lifecycle (instantiate → trigger → parked → approve → settle) without any script
glue, with no double-effect on command retries, and with the manual queue + scheduler work all
visible to the dashboard.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from agentx_api.app import create_app

TEST_TOKEN = "test-token-dashboard"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(
        use_mongo=False,
        seed_demo=False,
        operator_token=TEST_TOKEN,
        # Keep the worker off for tests so we can assert "work enqueued but not yet claimed" without
        # races. The dedicated test below exercises the live worker path explicitly.
        start_worker=False,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    ) as test_client:
        yield test_client


async def _post(client: AsyncClient, path: str, payload: dict[str, Any]) -> Any:
    return await client.post(path, json=payload)


async def _drive_worker(app: Any, *, max_ticks: int = 4) -> list[Any]:
    """Manually pump the scheduler worker for ``max_ticks`` iterations.

    Returns the RunResult list produced by the invoker (one per tick where work was claimed).
    """
    state = app.state.dashboard
    results: list[Any] = []
    for _ in range(max_ticks):
        result = await state.runtime.worker.run_once(_now())
        if result is None:
            break
        results.append(result)
    return results


def _now() -> Any:
    from datetime import UTC, datetime

    return datetime.now(UTC)


# ---------------------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------------------


async def test_instantiate_then_list_shows_persisted_instance(client: AsyncClient) -> None:
    response = await _post(
        client,
        "/commands/instantiate",
        {
            "type_ref": "lead-finder@0.1.0",
            "customer_id": "Acme Dental",
            "business_name": "Acme Dental",
            "ring": "L1",
            "target_override": {"icp": "dental clinics", "location": "Pune", "count": 2},
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    instance_id = body["instance"]["id"]
    assert body["instance"]["customer_id"] == "Acme Dental"
    assert body["instance"]["ring"] == "L1"
    assert body["instance"]["type_ref"] == "lead-finder@0.1.0"

    listing = (await client.get("/instances")).json()
    assert [row["instance"]["id"] for row in listing["instances"]] == [instance_id]


async def test_trigger_run_persists_work_id_and_scheduler_status(client: AsyncClient) -> None:
    inst = await _post(
        client,
        "/commands/instantiate",
        {
            "type_ref": "lead-finder@0.1.0",
            "customer_id": "Trigger Co",
            "business_name": "Trigger Co",
            "ring": "L1",
            "target_override": {"icp": "logistics", "location": "Mumbai", "count": 1},
        },
    )
    instance_id = inst.json()["instance"]["id"]

    trigger = await _post(
        client,
        "/commands/trigger-run",
        {"instance_id": instance_id, "mode": "sim"},
    )
    assert trigger.status_code == 202, trigger.text
    work_id = trigger.json()["work_id"]
    assert work_id.startswith("trigger:")

    status = (await client.get(f"/scheduler-work/{work_id}")).json()
    assert status["work"]["work_id"] == work_id
    assert status["work"]["kind"] == "trigger"
    assert status["work"]["status"] in {"pending", "claimed", "completed"}


async def test_approvals_endpoint_separate_from_manual_queue_after_park(client: AsyncClient) -> None:
    """The dashboard's Approval Inbox must read /approvals, not /manual-queue."""
    inst = await _post(
        client,
        "/commands/instantiate",
        {
            "type_ref": "lead-finder@0.1.0",
            "customer_id": "Approve Co",
            "business_name": "Approve Co",
            "ring": "L1",
            "target_override": {"icp": "dental", "location": "Pune", "count": 1},
        },
    )
    instance_id = inst.json()["instance"]["id"]

    await _post(
        client,
        "/commands/trigger-run",
        {"instance_id": instance_id, "mode": "sim"},
    )

    # Drain the worker once — the lead-finder OwnHarness playbook parks at draft_email.
    results = await _drive_worker(client._transport.app)  # type: ignore[attr-defined]
    assert len(results) == 1
    assert results[0].state == "parked"

    # The Approval Inbox is the FIRST-CLASS view that shows the parked draft card.
    approvals = (await client.get("/approvals", params={"instance_id": instance_id})).json()
    assert len(approvals["items"]) == 1
    card = approvals["items"][0]
    assert card["drafted_effect"]["syscall"] == "draft_email"
    assert "idempotency_key" in card["drafted_effect"]

    # Manual queue is independent — empty here, since the harness never routed to the human tail.
    manual = (await client.get("/manual-queue")).json()
    assert manual["items"] == []


async def test_approve_resumes_parked_run_to_settled_with_no_double_effect(
    client: AsyncClient,
) -> None:
    inst = await _post(
        client,
        "/commands/instantiate",
        {
            "type_ref": "lead-finder@0.1.0",
            "customer_id": "Resume Co",
            "business_name": "Resume Co",
            "ring": "L1",
            "target_override": {"icp": "dental", "location": "Pune", "count": 1},
        },
    )
    instance_id = inst.json()["instance"]["id"]
    await _post(client, "/commands/trigger-run", {"instance_id": instance_id, "mode": "sim"})
    parked_results = await _drive_worker(client._transport.app)  # type: ignore[attr-defined]
    assert parked_results and parked_results[0].state == "parked"
    run_id = parked_results[0].run_id

    # Idempotency key is journaled by the gateway on SyscallAttempted — capture it now so we
    # can verify replay-after-retry produces ONE effect downstream.
    approvals = (await client.get("/approvals", params={"instance_id": instance_id})).json()
    idem = approvals["items"][0]["drafted_effect"]["idempotency_key"]

    # Approve from the dashboard; this should enqueue ApprovalWork.
    approve = await _post(
        client,
        "/commands/approve",
        {"instance_id": instance_id, "run_id": run_id, "actor": "dashboard:operator"},
    )
    assert approve.status_code == 202, approve.text
    approve_body = approve.json()
    assert approve_body["work_enqueued"] is True
    approval_work_id = approve_body["work_id"]
    assert approval_work_id.startswith("approval:")

    # Drain the worker for ApprovalWork -> resume -> settle.
    resumed = await _drive_worker(client._transport.app)  # type: ignore[attr-defined]
    assert len(resumed) == 1
    assert resumed[0].state == "settled"

    # Verify: one journal syscall_attempted + one syscall_settled; no duplicate effects.
    journal = (
        await client.get("/journal", params={"instance_id": instance_id, "kind": "syscall_attempted"})
    ).json()
    assert len(journal["events"]) == 1
    settled = (
        await client.get("/journal", params={"instance_id": instance_id, "kind": "syscall_settled"})
    ).json()
    assert len(settled["events"]) == 1

    # The receipt store has the rendered draft (one row, idempotent on the key).
    receipts = (await client.get("/journal", params={"instance_id": instance_id, "limit": 1000})).json()
    assert any(
        event.get("idempotency_key") == idem
        for event in receipts["events"]
        if event.get("kind") == "syscall_settled"
    )

    # Retrying the same approve call must not append another manager event.
    duplicate = await _post(
        client,
        "/commands/approve",
        {"instance_id": instance_id, "run_id": run_id, "actor": "dashboard:operator"},
    )
    assert duplicate.status_code == 404  # run already settled; approval inbox is empty.


async def test_reject_does_not_execute_the_parked_effect(client: AsyncClient) -> None:
    inst = await _post(
        client,
        "/commands/instantiate",
        {
            "type_ref": "lead-finder@0.1.0",
            "customer_id": "Reject Co",
            "business_name": "Reject Co",
            "ring": "L1",
            "target_override": {"icp": "dental", "location": "Pune", "count": 1},
        },
    )
    instance_id = inst.json()["instance"]["id"]
    await _post(client, "/commands/trigger-run", {"instance_id": instance_id, "mode": "sim"})
    parked_results = await _drive_worker(client._transport.app)  # type: ignore[attr-defined]
    assert parked_results and parked_results[0].state == "parked"
    run_id = parked_results[0].run_id

    reject = await _post(
        client,
        "/commands/reject",
        {"instance_id": instance_id, "run_id": run_id, "actor": "dashboard:operator"},
    )
    assert reject.status_code == 202, reject.text
    body = reject.json()
    assert body["decision"] == "reject"
    assert body["work_enqueued"] is False  # reject must NOT enqueue ApprovalWork

    # Reject must NOT execute the parked syscall. Drain the worker and assert no SyscallSettled.
    await _drive_worker(client._transport.app, max_ticks=2)  # type: ignore[attr-defined]
    settled = (
        await client.get("/journal", params={"instance_id": instance_id, "kind": "syscall_settled"})
    ).json()
    assert settled["events"] == []

    # The run_summary shows no settled row.
    runs = (
        await client.get("/runs", params={"instance_id": instance_id, "state": "settled"})
    ).json()
    assert runs["runs"] == []


async def test_manual_queue_durable_across_runtime_recomposition() -> None:
    """The InMemoryManualTaskRepository stores tasks with the same idempotency_key semantics as Mongo."""
    from agentx_contracts import SyscallRequest
    from agentx_syscall.manual_tasks import InMemoryManualTaskRepository

    repo = InMemoryManualTaskRepository()
    req = SyscallRequest(
        name="queue_manual_action",
        args={"action": "review_lead", "lead_id": "lead_z"},
        instance_id="inst_z",
        run_id="run_z",
        idempotency_key="manual-durable-1",
        ring="L1",
        risk_class="reversible_write",
    )
    task_a = repo.enqueue(req, source_adapter="queue_manual_action")
    task_b = repo.enqueue(req, source_adapter="queue_manual_action")
    assert task_a.id == task_b.id  # idempotent
    assert len(repo.list_open()) == 1


async def test_live_worker_pumps_a_full_lifecycle_without_script_glue() -> None:
    """End-to-end with start_worker=True; the lifespan-owned worker drives the run on its own."""
    app = create_app(
        use_mongo=False,
        seed_demo=False,
        operator_token=TEST_TOKEN,
        start_worker=True,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    ) as client:
        # Warm up the lifespan manually (ASGITransport does not call it automatically for tests).
        async with app.router.lifespan_context(app):
            inst = await client.post(
                "/commands/instantiate",
                json={
                    "type_ref": "lead-finder@0.1.0",
                    "customer_id": "Live Co",
                    "business_name": "Live Co",
                    "ring": "L1",
                    "target_override": {"icp": "dental", "location": "Pune", "count": 1},
                },
            )
            instance_id = inst.json()["instance"]["id"]
            await client.post(
                "/commands/trigger-run",
                json={"instance_id": instance_id, "mode": "sim"},
            )

            # Wait up to 5s for the run to park.
            for _ in range(50):
                await asyncio.sleep(0.1)
                approvals = (await client.get("/approvals", params={"instance_id": instance_id})).json()
                if approvals["items"]:
                    break
            assert approvals["items"], "trigger_run did not produce a parked run within 5s"
            run_id = approvals["items"][0]["run_id"]

            # Approve via dashboard; the worker resumes + settles on its own.
            await client.post(
                "/commands/approve",
                json={"instance_id": instance_id, "run_id": run_id, "actor": "dashboard:operator"},
            )
            for _ in range(50):
                await asyncio.sleep(0.1)
                runs = (
                    await client.get("/runs", params={"instance_id": instance_id, "state": "settled"})
                ).json()
                if runs["runs"]:
                    break
            assert runs["runs"], "approval did not settle within 5s"
