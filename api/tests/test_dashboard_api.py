from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from agentx_api.app import create_app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(use_mongo=False, seed_demo=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def test_overview_and_instance_detail_are_kernel_projection_views(client: AsyncClient) -> None:
    overview = (await client.get("/system/overview")).json()

    assert overview["counts"]["instances"] == 1
    assert overview["counts"]["parked_awaiting_approval"] == 1
    assert overview["counts"]["settled"] == 1
    assert overview["pnl"]["total"] == 250.0
    assert overview["rings"] == {"L1": 1}

    instance = (await client.get("/instances/inst_demo")).json()

    assert instance["instance"]["id"] == "inst_demo"
    assert instance["resume"]["ring"] == "L1"
    assert instance["facts"][0]["provenance"]["run_id"] == "run_demo_settled"
    assert instance["billing"]["total"] == 250.0
    assert instance["approvals"][0]["run_id"] == "run_demo_parked"


async def test_approve_command_calls_kernel_control_and_updates_ledger(client: AsyncClient) -> None:
    before = (await client.get("/runs?state=parked")).json()
    assert [run["run_id"] for run in before["runs"]] == ["run_demo_parked"]

    response = await client.post(
        "/commands/approve",
        json={"instance_id": "inst_demo", "run_id": "run_demo_parked", "actor": "manager:test"},
    )

    assert response.status_code == 200
    assert response.json()["action"]["action"] == "approve"
    assert (await client.get("/runs?state=parked")).json()["runs"] == []

    ledger = (await client.get("/journal", params={"kind": "manager_action"})).json()
    assert any(event["action"] == "approve" for event in ledger["events"])


async def test_set_ring_command_is_journaled_and_reflected_in_instance_file(client: AsyncClient) -> None:
    response = await client.post(
        "/commands/set-ring",
        json={"instance_id": "inst_demo", "ring": "L2", "actor": "manager:test"},
    )

    assert response.status_code == 200
    assert response.json()["action"]["detail"] == {"ring": "L2"}

    instance = (await client.get("/instances/inst_demo")).json()
    assert instance["resume"]["ring"] == "L2"


async def test_capability_registry_and_manual_queue_are_exposed_without_credentials(client: AsyncClient) -> None:
    capabilities = (await client.get("/capabilities")).json()["capabilities"]
    names = {capability["name"] for capability in capabilities}

    assert {"lead_research_batch", "draft_email", "human_task"}.issubset(names)
    assert all("credential" not in capability for capability in capabilities)
    assert next(cap for cap in capabilities if cap["name"] == "human_task")["is_terminal_fallback"] is True

    queue = (await client.get("/manual-queue")).json()
    assert queue["items"][0]["request_name"] == "queue_manual_action"


async def test_missing_core_commands_return_explicit_core_gap(client: AsyncClient) -> None:
    response = await client.post(
        "/commands/instantiate",
        json={"type_ref": "lead-finder@0.1.0", "business_name": "Acme Dental", "ring": "L1"},
    )

    assert response.status_code == 501
    body = response.json()
    assert body["supported"] is False
    assert body["gap"]["id"] == "command.instantiate"

    gaps = (await client.get("/core-gaps")).json()["gaps"]
    assert any(gap["id"] == "command.trigger_run" for gap in gaps)
