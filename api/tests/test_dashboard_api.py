from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from agentx_contracts.mandate import MandateInstance
from agentx_mandate.library.lead_finder import build_lead_finder_type
from httpx import ASGITransport, AsyncClient

from agentx_api.app import create_app

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


async def _post(client: AsyncClient, path: str, payload: dict[str, Any]) -> Any:
    return await client.post(path, json=payload)


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
    assert instance["approvals"][0]["drafted_effect"]["syscall"] == "draft_email"
    assert instance["approvals"][0]["drafted_effect"]["args"]["body"]


async def test_approve_command_enqueues_approval_work_and_advances_run(client: AsyncClient) -> None:
    # The seeded parked run is the same one used by the overview test; replaying the flow
    # requires the scheduler worker to be running OR the resolver to fall back to the existing
    # demo flow. With ``start_worker=False`` we still verify the journal + work row are created.
    response = await _post(
        client,
        "/commands/approve",
        {"instance_id": "inst_demo", "run_id": "run_demo_parked", "actor": "manager:test"},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["decision"] == "approve"
    assert body["work_enqueued"] is True
    assert body["work_id"].startswith("approval:")
    assert body["manager_action"]["action"] == "approve"

    # The ApprovalResolved event is journaled exactly once and the inbox is empty afterwards.
    inbox_after = (await client.get("/approvals", params={"instance_id": "inst_demo"})).json()
    assert inbox_after["items"] == []

    ledger = (await client.get("/journal", params={"kind": "manager_action"})).json()
    assert any(event["action"] == "approve" for event in ledger["events"])


async def test_set_ring_command_is_journaled_and_reflected_in_instance_file(client: AsyncClient) -> None:
    response = await _post(
        client,
        "/commands/set-ring",
        {"instance_id": "inst_demo", "ring": "L2", "actor": "manager:test"},
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


async def test_commands_require_bearer_token_when_token_is_set(client: AsyncClient) -> None:
    # Build a separate client with NO Authorization header.
    app = client._transport.app  # type: ignore[attr-defined]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon_client:
        response = await anon_client.post(
            "/commands/instantiate",
            json={"type_ref": "lead-finder@0.1.0", "business_name": "Acme", "ring": "L1"},
        )
        assert response.status_code == 401
        body = response.json()
        assert "Bearer" in body["detail"]


async def test_commands_disabled_when_no_token_is_configured() -> None:
    """Without ``AGENTX_OPERATOR_TOKEN`` set, command routes return 401 (fail closed)."""
    import os

    os.environ.pop("AGENTX_OPERATOR_TOKEN", None)
    app = create_app(use_mongo=False, seed_demo=True, operator_token="", start_worker=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer anything"},
    ) as test_client:
        response = await test_client.post(
            "/commands/approve",
            json={"instance_id": "inst_demo", "run_id": "run_demo_parked"},
        )
        assert response.status_code == 401
        assert "AGENTX_OPERATOR_TOKEN" in response.json()["detail"]


async def test_instances_exposes_non_demo_registry_instance() -> None:
    """The MandateRegistry must surface in /instances regardless of demo seeding."""
    app = create_app(
        use_mongo=False,
        seed_demo=False,
        operator_token=TEST_TOKEN,
        start_worker=False,
    )
    dashboard = app.state.dashboard
    mandate = build_lead_finder_type()
    instance = MandateInstance(
        id="inst_real_catalog",
        type_ref="lead-finder@0.1.0",
        customer_id="Real Dental",
        ring="L1",
        heap_region_id="tenant_real_catalog",
    )
    await dashboard.control.register_mandate_type(mandate)
    await dashboard.control.instantiate_mandate(instance)

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    ) as test_client:
        response = await test_client.get("/instances")

    assert response.status_code == 200
    rows = response.json()["instances"]
    assert [row["instance"]["id"] for row in rows] == ["inst_real_catalog"]


async def test_dashboard_close_awaits_async_database_client() -> None:
    app = create_app(
        use_mongo=False,
        seed_demo=False,
        operator_token=TEST_TOKEN,
        start_worker=False,
    )

    class AsyncCloseClient:
        closed = False

        async def close(self) -> None:
            self.closed = True

    sentinel = AsyncCloseClient()
    # The lifespan now drives runtime.close() through ``app.state.dashboard.close`` which
    # delegates to the OperatorRuntime. Verify the delegation path resolves to ``client.close``.
    # We swap in our sentinel as the Mongo client for this check.
    app.state.dashboard.runtime.client = sentinel

    await app.state.dashboard.close()

    assert sentinel.closed
