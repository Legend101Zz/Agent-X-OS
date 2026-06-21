"""C3 — Heap/memory read API (BLUEPRINT §8 row 1).

Per the UI overhaul spec, the Inspector's Memory tab needs a dedicated read endpoint that
returns the instance's facts in a shape that's ready for the UI:

    {
      "instance_id": "inst_demo",
      "facts": [
        {
          "id": "fact_demo_lead_score",
          "subject": "lead_orbit",
          "predicate": "qualified_lead_score",
          "object": "0.82",
          "confidence": 0.82,
          "status": "probation",          # probation | promoted (verified) | retired
          "source": "agent-inferred",
          "provenance": {
            "run_id": "run_demo_settled",
            "evidence": ["https://orbit.example/careers", "syscall_trace:..."],
            "note": "..."
          },
          "created_at": "2026-06-18T09:34:00+00:00",
          "updated_at": null
        },
        ...
      ]
    }

The endpoint must GRACEFULLY 404 (not raise, not 500) when:
  - the instance doesn't exist at all, OR
  - the instance exists but the projection store has no fact docs yet

This is read-only, uses the existing ``heap_fact`` projection store, and must not touch any
contracts.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from agentx_api.app import create_app

TEST_TOKEN = "test-operator-token-c3"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Memory-mode app with the seed_demo instance — has one probation fact (fact_demo_lead_score)."""
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


@pytest.fixture
async def empty_client() -> AsyncIterator[AsyncClient]:
    """Memory-mode app with NO seed_demo — so fact docs are absent (the projection store exists
    but has no heap_fact entries). Used to prove the route returns a graceful 404, not a 500."""
    app = create_app(
        use_mongo=False, seed_demo=False, operator_token=TEST_TOKEN, start_worker=False
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    ) as test_client:
        yield test_client


async def test_memory_returns_seeded_fact_in_ui_ready_shape(client: AsyncClient) -> None:
    """The happy path: the seeded ``inst_demo`` has one probation fact. The endpoint returns it
    with all the fields the Memory tab needs: subject/predicate/object, confidence, provenance
    (run_id + evidence), status."""
    response = await client.get("/instances/inst_demo/memory")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["instance_id"] == "inst_demo"

    facts = body["facts"]
    assert len(facts) == 1, f"expected one seeded fact, got {facts}"

    fact = facts[0]
    assert fact["id"] == "fact_demo_lead_score"
    assert fact["subject"] == "lead_orbit"
    assert fact["predicate"] == "qualified_lead_score"
    assert fact["object"] == "0.82"
    assert fact["confidence"] == 0.82
    assert fact["status"] in {"probation", "promoted", "retired"}
    # Provenance is the audit trail that makes "no fact without a commit" real.
    assert fact["provenance"]["run_id"] == "run_demo_settled"
    assert isinstance(fact["provenance"]["evidence"], list)
    assert len(fact["provenance"]["evidence"]) >= 1


async def test_memory_404s_gracefully_when_projection_store_has_no_facts(empty_client: AsyncClient) -> None:
    """The projection store exists but has no heap_fact docs. The route MUST 404 — not raise,
    not return 500, not return 200 with an empty list (because the spec says the Memory tab
    needs a heap-browse view; an empty instance is a real condition the UI must distinguish
    from "has facts but they're filtered out")."""
    response = await empty_client.get("/instances/inst_anything/memory")

    assert response.status_code == 404, response.text
    body = response.json()
    # Friendly envelope so the UI can render an EmptyState with a clear reason.
    assert body["missing"] is True
    assert body["instance_id"] == "inst_anything"
    assert "facts" not in body or body.get("facts") == []


async def test_memory_404s_gracefully_when_instance_id_is_garbage(client: AsyncClient) -> None:
    """Even with the seeded instance present, a nonsense instance id must 404 cleanly — same
    envelope as 'no facts yet', because the spec treats both as 'no fact docs yet'."""
    response = await client.get("/instances/inst_does_not_exist/memory")

    assert response.status_code == 404, response.text
    body = response.json()
    assert body["missing"] is True
    assert body["instance_id"] == "inst_does_not_exist"


async def test_memory_does_not_expose_other_instances_facts(client: AsyncClient) -> None:
    """Heap isolation (invariant #3): one instance's memory endpoint must never return facts
    belonging to another instance. We inject a foreign-instance fact directly into the heap
    projection store and verify it does NOT appear in inst_demo's response."""
    from datetime import UTC, datetime

    import agentx_db.collections as c
    from agentx_contracts.memory import Fact, Provenance

    # Reach into the runtime state to insert a foreign fact — the same way the HeapProjector
    # would have done for a different instance.
    state = client._transport.app.state.dashboard  # type: ignore[attr-defined]
    foreign_fact = Fact(
        id="fact_other_instance",
        instance_id="inst_other",
        subject="other_lead",
        predicate="qualified_lead_score",
        object="0.99",
        confidence=0.99,
        source="agent-inferred",
        provenance=Provenance(run_id="run_other", evidence=["trace:other"]),
        created_at=datetime(2026, 6, 21, 10, 0, tzinfo=UTC),
    )
    await state.store.upsert(c.HEAP_FACT, foreign_fact.id, foreign_fact.model_dump(mode="json"))

    response = await client.get("/instances/inst_demo/memory")
    assert response.status_code == 200, response.text
    body = response.json()
    # inst_demo only has its own seeded fact, NOT the foreign one — heap isolation (invariant #3).
    ids = {fact["id"] for fact in body["facts"]}
    assert ids == {"fact_demo_lead_score"}, (
        f"inst_demo's view leaked foreign facts: {ids}"
    )

    # And the foreign instance's own view DOES return its fact (200, not 404) — proving the
    # endpoint is correctly keyed by instance_id: inst_other has facts, so we serve them.
    foreign = await client.get("/instances/inst_other/memory")
    assert foreign.status_code == 200, foreign.text
    foreign_body = foreign.json()
    assert {fact["id"] for fact in foreign_body["facts"]} == {"fact_other_instance"}


async def test_memory_envelope_keys_are_stable(client: AsyncClient) -> None:
    """Frontend consumers pin to these exact keys; the route must not silently rename them."""
    response = await client.get("/instances/inst_demo/memory")
    body = response.json()
    assert set(body.keys()) == {"instance_id", "facts"}

    fact = body["facts"][0]
    expected_keys = {
        "id",
        "subject",
        "predicate",
        "object",
        "confidence",
        "status",
        "source",
        "provenance",
        "created_at",
        "updated_at",
    }
    assert expected_keys.issubset(set(fact.keys())), (
        f"missing keys: {expected_keys - set(fact.keys())}"
    )

    provenance_keys = {"run_id", "evidence"}
    assert provenance_keys.issubset(set(fact["provenance"].keys()))


async def test_state_reader_function_is_exported() -> None:
    """The task body says 'Add api/src/agentx_api/state.py reader'. The reader must be importable
    from state.py so future callers can compose it without going through HTTP."""
    from agentx_api import state as state_module

    assert hasattr(state_module, "instance_memory")
    assert callable(state_module.instance_memory)


async def test_state_reader_returns_facts_for_known_instance() -> None:
    """Direct reader call (no HTTP) returns the same shape the route returns."""
    from agentx_api.state import create_state, instance_memory

    state = create_state(use_mongo=False, seed_demo=True, send_email_transport=None)
    await state.start()
    try:
        body = await instance_memory(state, "inst_demo")
        assert body["instance_id"] == "inst_demo"
        assert len(body["facts"]) == 1
        fact = body["facts"][0]
        assert fact["subject"] == "lead_orbit"
        assert fact["provenance"]["run_id"] == "run_demo_settled"
    finally:
        await state.close()


async def test_state_reader_returns_missing_envelope_for_unknown_instance() -> None:
    """The reader's 'missing' contract is what the route translates into HTTP 404. Asserting it
    here keeps the contract testable without spinning up an HTTP client."""
    from agentx_api.state import create_state, instance_memory

    state = create_state(use_mongo=False, seed_demo=True, send_email_transport=None)
    await state.start()
    try:
        body = await instance_memory(state, "inst_does_not_exist")
        assert body["missing"] is True
        assert body["instance_id"] == "inst_does_not_exist"
        assert body.get("facts", []) == []
    finally:
        await state.close()


async def test_state_reader_returns_missing_when_no_facts_projected_yet() -> None:
    """Even when the instance exists in the mandate_instance collection but no RunSettled has
    ever populated heap_fact, the reader returns the missing envelope. (Hard to construct in
    seed_demo without a custom runner; we hit the projection store directly via the same path
    the reader takes.)"""
    from agentx_contracts.mandate import MandateInstance
    from agentx_mandate.library.lead_finder import build_lead_finder_type

    from agentx_api.state import create_state, instance_memory

    state = create_state(use_mongo=False, seed_demo=False, send_email_transport=None)
    await state.start()
    try:
        # Register the canonical mandate type so we can instantiate an instance against it,
        # then instantiate one without ever settling a run — so no heap_fact docs are produced.
        await state.control.register_mandate_type(build_lead_finder_type())
        await state.control.instantiate_mandate(
            MandateInstance(
                id="inst_factless",
                type_ref="lead-finder@0.1.0",
                customer_id="Empty Co",
                ring="L0",
                heap_region_id="heap_factless",
            )
        )
        body = await instance_memory(state, "inst_factless")
        assert body["missing"] is True
        assert body["instance_id"] == "inst_factless"
        assert body.get("facts", []) == []
    finally:
        await state.close()
