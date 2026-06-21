"""C15 — Economy / P&L read API (BLUEPRINT §8 row 2).

Per the UI overhaul spec (2026-06-21-agentx-ui-overhaul-design.md §6 Economy view and
§8 backend gap row 2):

  GET /economy?instance_id=...
  GET /economy/units

Aggregates the per-instance P&L from the kernel projections that ``BillingProjector``
and ``ResumeProjector`` already maintain. Both are READ-ONLY — the projectors remain the
sole writers of ``billing_line`` and ``resume`` (invariant #1, no fact without a commit).

The P&L envelope shape is dictated by what the Economy view + Home P&L tile render:

  Per-instance (``GET /economy?instance_id=...``):
    {
      "instance_id": "inst_demo",
      "billing_total": 250.0,
      "currency": "INR",
      "settled_count": 1,
      "trust_score": 1,
      "settlements": [
        {"run_id": "run_demo_settled", "amount": 250.0, "ts": "2026-06-18T09:36:00+00:00"}
      ]
    }

  Per-business-unit (``GET /economy/units``):
    {
      "units": [
        {
          "customer_id": "Orbit Dental Co",
          "instance_count": 1,
          "instance_ids": ["inst_demo"],
          "billing_total": 250.0,
          "settled_count": 1,
          "trust_score": 1,
          "currency": "INR"
        }
      ],
      "totals": {"billing_total": 250.0, "settled_count": 1, "currency": "INR"}
    }

404 contract for /economy (per-instance):
  - instance does not exist at all, OR
  - instance exists but has never settled (no billing_line doc).

Both translate to a graceful 404 envelope ``{"missing": true, "instance_id": ...}``.
The /economy/units route always returns 200 — an empty fleet is a real condition the UI
renders as an EmptyState, not an error.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from agentx_api.app import create_app

TEST_TOKEN = "test-operator-token-c15"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Memory-mode app with the seed_demo instance: one RunSettled (billing_amount=250,
    trust_delta=1) projecting to one billing_line doc for inst_demo. Customer_id on the
    seeded instance is 'Orbit Dental Co'."""
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
    """Memory-mode app with NO seed_demo — projection store exists but no billing_line
    docs. Used to prove the /economy route returns a graceful 404, not a 500."""
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


# ---------------------------------------------------------------------------
# /economy?instance_id=... — per-instance P&L
# ---------------------------------------------------------------------------


async def test_economy_returns_per_instance_pnl_aggregating_runsettled(
    client: AsyncClient,
) -> None:
    """Happy path: the seeded inst_demo has one RunSettled (billing_amount=250,
    trust_delta=1). The endpoint aggregates RunSettled.billing_amount + trust_delta into
    the per-instance P&L envelope the Economy view expects."""
    response = await client.get("/economy", params={"instance_id": "inst_demo"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["instance_id"] == "inst_demo"
    # One settled run of 250 INR each.
    assert body["billing_total"] == 250.0
    assert body["currency"] == "INR"
    assert body["settled_count"] == 1
    # trust_delta=1 from the seeded settle → trust_score=1 (the ResumeProjector sums).
    assert body["trust_score"] == 1
    # The settlement detail is per-run so the Economy view can show a transaction list.
    settlements = body["settlements"]
    assert len(settlements) == 1
    assert settlements[0]["run_id"] == "run_demo_settled"
    assert settlements[0]["amount"] == 250.0
    assert isinstance(settlements[0]["ts"], str)


async def test_economy_envelope_keys_are_stable(client: AsyncClient) -> None:
    """Frontend consumers pin to these exact keys; the route must not silently rename them."""
    response = await client.get("/economy", params={"instance_id": "inst_demo"})
    body = response.json()
    assert set(body.keys()) == {
        "instance_id",
        "billing_total",
        "currency",
        "settled_count",
        "trust_score",
        "settlements",
    }

    settlement = body["settlements"][0]
    assert set(settlement.keys()) == {"run_id", "amount", "ts"}


async def test_economy_404s_when_instance_missing(empty_client: AsyncClient) -> None:
    """When no instance exists at all (and therefore no billing_line doc), the route
    MUST 404 with a friendly missing envelope — not raise, not return 500, not return
    a zero-everything 200 (because a missing instance is a real condition the UI must
    distinguish from 'has settles but total is zero')."""
    response = await empty_client.get("/economy", params={"instance_id": "inst_anything"})

    assert response.status_code == 404, response.text
    body = response.json()
    assert body["missing"] is True
    assert body["instance_id"] == "inst_anything"


async def test_economy_404s_when_instance_exists_but_no_settles(empty_client: AsyncClient) -> None:
    """Instance is present but no RunSettled has happened yet → graceful 404 envelope.
    The spec treats both 'no instance' and 'no settled runs' as 'missing' so the UI
    renders an EmptyState without distinguishing the two. We reach into the
    empty_client's app state to instantiate a mandate_instance doc directly — the
    BillingProjector hasn't fired, so no billing_line doc exists, and the route must
    return a graceful 404."""
    from agentx_contracts.mandate import MandateInstance
    from agentx_mandate.library.lead_finder import build_lead_finder_type

    # Reach into the live app state the `empty_client` fixture built.
    state = empty_client._transport.app.state.dashboard  # type: ignore[attr-defined]
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

    response = await empty_client.get("/economy", params={"instance_id": "inst_factless"})
    assert response.status_code == 404, response.text
    body = response.json()
    assert body["missing"] is True
    assert body["instance_id"] == "inst_factless"


async def test_economy_missing_instance_id_returns_422(client: AsyncClient) -> None:
    """The endpoint is useless without an instance_id (the spec keys everything per
    instance). Missing the query param must be a clear 422 (FastAPI's default for a
    required Query param), not a silent default."""
    response = await client.get("/economy")
    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# /economy/units — per-business-unit rollup
# ---------------------------------------------------------------------------


async def test_units_groups_by_customer_id_and_aggregates_billing(client: AsyncClient) -> None:
    """The seeded instance has customer_id='Orbit Dental Co' and one RunSettled of 250.
    /economy/units groups by customer_id (business unit) and rolls up billing across
    instances of the same unit."""
    response = await client.get("/economy/units")
    assert response.status_code == 200, response.text
    body = response.json()

    units = body["units"]
    assert len(units) == 1
    unit = units[0]
    assert unit["customer_id"] == "Orbit Dental Co"
    assert unit["instance_count"] == 1
    assert unit["instance_ids"] == ["inst_demo"]
    assert unit["billing_total"] == 250.0
    assert unit["settled_count"] == 1
    assert unit["trust_score"] == 1
    assert unit["currency"] == "INR"

    # Totals roll up across units (here just one).
    totals = body["totals"]
    assert totals["billing_total"] == 250.0
    assert totals["settled_count"] == 1
    assert totals["currency"] == "INR"


async def test_units_envelope_keys_are_stable(client: AsyncClient) -> None:
    """Frontend pins to these keys. Pin the schema in a test so refactors can't silently
    rename them."""
    response = await client.get("/economy/units")
    body = response.json()
    assert set(body.keys()) == {"units", "totals"}

    assert set(body["totals"].keys()) == {"billing_total", "settled_count", "currency"}
    assert set(body["units"][0].keys()) == {
        "customer_id",
        "instance_count",
        "instance_ids",
        "billing_total",
        "settled_count",
        "trust_score",
        "currency",
    }


async def test_units_returns_empty_list_when_no_instances(empty_client: AsyncClient) -> None:
    """No mandate instances exist at all → units: [] with zero totals. This is a real
    condition on a fresh boot — the Economy view renders an EmptyState, not a 404."""
    response = await empty_client.get("/economy/units")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["units"] == []
    assert body["totals"] == {"billing_total": 0, "settled_count": 0, "currency": "INR"}


async def test_units_aggregates_across_instances_of_same_customer(
    client: AsyncClient,
) -> None:
    """When a single business unit (customer_id) has multiple instances, /economy/units
    sums billing_total + settled_count + trust_score across all of them. We register a
    second instance for the same customer via the client fixture's app state (NOT a
    separate in-memory state — the `client` fixture owns the only live state) and emit
    a RunSettled against it so BillingProjector + ResumeProjector write the new docs
    into the same projection store the route reads from."""
    from agentx_contracts.journal import RunCreated, RunHydrated, RunSettled
    from agentx_contracts.mandate import MandateInstance
    from agentx_contracts.memory import Fact, Provenance
    from agentx_contracts.trigger import DeadlineTrigger
    from agentx_mandate.library.lead_finder import build_lead_finder_type

    from agentx_api.state import _append_and_project

    # Reach into the live app state the `client` fixture built — same pattern C3 used
    # to inject a foreign fact into the heap projection store.
    state = client._transport.app.state.dashboard  # type: ignore[attr-defined]

    # CRITICAL: explicitly call state.start() NOW (not lazily on first HTTP request)
    # so the seed_demo instance lands in the projection store BEFORE we add our
    # sibling. Otherwise _maybe_seed_demo sees only our new instance and short-circuits
    # without seeding inst_demo.
    await state.start()
    await state.control.register_mandate_type(build_lead_finder_type())
    await state.control.instantiate_mandate(
        MandateInstance(
            id="inst_demo_sibling",
            type_ref="lead-finder@0.1.0",
            customer_id="Orbit Dental Co",
            ring="L1",
            heap_region_id="heap_demo_sibling",
        )
    )

    # Append a RunSettled for the sibling: billing 175, trust_delta 2.
    now = datetime(2026, 6, 19, 9, 0, tzinfo=UTC)
    trigger = DeadlineTrigger(
        ts=now, reason="morning sibling sweep", entity_id="lead_orbit_sibling"
    )
    await _append_and_project(
        state,
        RunCreated(
            event_id="run_sibling:created",
            seq=0,
            ts=trigger.ts,
            instance_id="inst_demo_sibling",
            run_id="run_demo_sibling",
            type_ref="lead-finder@0.1.0",
            trigger=trigger,
        ),
    )
    await _append_and_project(
        state,
        RunHydrated(
            event_id="run_sibling:hydrated",
            seq=0,
            ts=trigger.ts,
            instance_id="inst_demo_sibling",
            run_id="run_demo_sibling",
            fact_count=0,
            thread_id="inst_demo_sibling:lead_orbit_sibling",
        ),
    )
    fact = Fact(
        id="fact_sibling",
        instance_id="inst_demo_sibling",
        subject="lead_orbit_sibling",
        predicate="qualified_lead_score",
        object="0.55",
        confidence=0.55,
        source="agent-inferred",
        provenance=Provenance(run_id="run_demo_sibling", evidence=["trace:sibling"]),
        created_at=now,
    )
    await _append_and_project(
        state,
        RunSettled(
            event_id="run_sibling:settled",
            seq=0,
            ts=now,
            instance_id="inst_demo_sibling",
            run_id="run_demo_sibling",
            facts=[fact],
            billing_amount=175.0,
            trust_delta=2,
        ),
    )

    response = await client.get("/economy/units")
    body = response.json()
    units = body["units"]
    assert len(units) == 1, f"expected one customer unit, got {units}"
    unit = units[0]
    assert unit["customer_id"] == "Orbit Dental Co"
    assert unit["instance_count"] == 2
    assert sorted(unit["instance_ids"]) == ["inst_demo", "inst_demo_sibling"]
    # 250 (inst_demo) + 175 (sibling) = 425
    assert unit["billing_total"] == 425.0
    assert unit["settled_count"] == 2
    # trust_score: 1 (inst_demo ResumeProjector) + 2 (sibling ResumeProjector) = 3
    assert unit["trust_score"] == 3
    assert unit["currency"] == "INR"
    # Totals match.
    assert body["totals"]["billing_total"] == 425.0
    assert body["totals"]["settled_count"] == 2


async def test_units_separates_distinct_customers(client: AsyncClient) -> None:
    """Two distinct customer_ids → two units (each rolled up independently), no
    cross-contamination."""
    from agentx_contracts.mandate import MandateInstance
    from agentx_mandate.library.lead_finder import build_lead_finder_type

    # Reach into the live app state the `client` fixture built.
    state = client._transport.app.state.dashboard  # type: ignore[attr-defined]
    # CRITICAL: force-start so seed_demo's inst_demo lands BEFORE we add our new
    # instance (otherwise _maybe_seed_demo sees only inst_other_customer and skips
    # seeding inst_demo — see the sibling-rollup test for the full explanation).
    await state.start()
    await state.control.register_mandate_type(build_lead_finder_type())
    # Different customer_id → different business unit.
    await state.control.instantiate_mandate(
        MandateInstance(
            id="inst_other_customer",
            type_ref="lead-finder@0.1.0",
            customer_id="Nova Care Clinics",
            ring="L0",
            heap_region_id="heap_other",
        )
    )

    response = await client.get("/economy/units")
    body = response.json()
    units = body["units"]
    customer_ids = {unit["customer_id"] for unit in units}
    assert customer_ids == {"Orbit Dental Co", "Nova Care Clinics"}, units
    # No billing for Nova yet → its billing_total is 0 but it still shows up as a unit.
    nova = next(unit for unit in units if unit["customer_id"] == "Nova Care Clinics")
    assert nova["instance_count"] == 1
    assert nova["billing_total"] == 0
    assert nova["settled_count"] == 0
    assert nova["trust_score"] == 0


# ---------------------------------------------------------------------------
# State-reader direct tests (no HTTP) — keep the contract testable.
# ---------------------------------------------------------------------------


async def test_state_economy_reader_is_exported() -> None:
    """Per the task body 'add state.py reader' — the reader must be importable from
    state.py so future callers can compose it without going through HTTP."""
    from agentx_api import state as state_module

    assert hasattr(state_module, "instance_economy")
    assert callable(state_module.instance_economy)
    assert hasattr(state_module, "economy_units")
    assert callable(state_module.economy_units)


async def test_state_instance_economy_returns_envelope_for_seeded_instance() -> None:
    """Direct reader call returns the same shape the route returns."""
    from agentx_api.state import create_state, instance_economy

    state = create_state(use_mongo=False, seed_demo=True, send_email_transport=None)
    await state.start()
    try:
        body = await instance_economy(state, "inst_demo")
        assert body["instance_id"] == "inst_demo"
        assert body["billing_total"] == 250.0
        assert body["settled_count"] == 1
        assert body["trust_score"] == 1
        assert body["currency"] == "INR"
    finally:
        await state.close()


async def test_state_instance_economy_returns_missing_for_unknown_instance() -> None:
    """Reader's 'missing' contract is what the route translates into HTTP 404."""
    from agentx_api.state import create_state, instance_economy

    state = create_state(use_mongo=False, seed_demo=False, send_email_transport=None)
    await state.start()
    try:
        body = await instance_economy(state, "inst_does_not_exist")
        assert body["missing"] is True
        assert body["instance_id"] == "inst_does_not_exist"
    finally:
        await state.close()


async def test_state_economy_units_returns_per_customer_rollup() -> None:
    """Direct reader returns the per-customer rollup shape."""
    from agentx_api.state import create_state, economy_units

    state = create_state(use_mongo=False, seed_demo=True, send_email_transport=None)
    await state.start()
    try:
        body = await economy_units(state)
        assert "units" in body
        assert "totals" in body
        assert len(body["units"]) == 1
        assert body["units"][0]["customer_id"] == "Orbit Dental Co"
    finally:
        await state.close()
