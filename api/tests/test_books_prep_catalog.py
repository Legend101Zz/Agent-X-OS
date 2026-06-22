"""Step 6 — books-prep catalog seeding + the additive 'document path(s)' studio surface.

Validates the design's two contract promises for v0:
  1. The catalog seeds ``lead-finder@0.1.0`` AND ``books-prep@0.1.0`` together when empty
     (the dashboard's ``type_ref`` picker resolves both out of the box).
  2. The ``documents`` field on the mandate target flows through the EXISTING
     ``InstantiateCommand.target_override`` (no new endpoint, no contract change) — the studio's
     "which documents to ingest" question is already an additive optional JSON field.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from agentx_mandate.library.books_prep import build_books_prep_type
from agentx_mandate.library.lead_finder import build_lead_finder_type
from httpx import ASGITransport, AsyncClient

from agentx_api.app import _ensure_canonical_mandate_registered, create_app

TEST_TOKEN = "test-operator-token-books-catalog"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(use_mongo=False, seed_demo=False, operator_token=TEST_TOKEN, start_worker=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    ) as test_client:
        yield test_client


async def test_canonical_seed_registers_lead_finder_and_books_prep(client: AsyncClient) -> None:
    """Empty catalog → ``_ensure_canonical_mandate_registered`` registers BOTH canonical types.

    The seed helper runs the first time a request hits the ``ensure_startup`` middleware; we
    invoke it directly here so the test does not depend on HTTP ordering. Both canonical types
    must be resolvable by their ``type_ref`` (``name@version``) and have the expected names.
    """
    state = client._transport.app.state.dashboard  # type: ignore[attr-defined]
    await state.start()
    await _ensure_canonical_mandate_registered(state)

    books = await state.control._registry.get_type("books-prep@0.1.0")
    assert books is not None, "books-prep@0.1.0 should be auto-seeded alongside lead-finder"
    assert books.name == "books-prep"
    assert books.version == "0.1.0"

    lead = await state.control._registry.get_type("lead-finder@0.1.0")
    assert lead is not None, "lead-finder@0.1.0 should still be auto-seeded (no regression)"
    assert lead.name == "lead-finder"

    # Both mandates share the same per-store id scheme (the canonical ``type_<name>_v0``).
    stored = await state.control._registry.list_types()
    stored_ids = {m.id for m in stored}
    assert "type_books_prep_v0" in stored_ids
    assert "type_lead_finder_v0" in stored_ids


async def test_books_prep_instantiate_with_documents_target_override(client: AsyncClient) -> None:
    """The studio's 'document path(s)' rides the EXISTING ``target_override`` field — additive,
    no new endpoint. A CA uploads two bank-statement PDFs; the trigger payload names them.

    The ``target_override`` is delivered to the worker via ``trigger_run``'s per-trigger
    target-merge (the canonical mandate carries the override once the worker invokes it); the
    instance persists with ``type_ref = books-prep@0.1.0`` and the canonical is findable.
    """
    state = client._transport.app.state.dashboard  # type: ignore[attr-defined]

    response = await client.post(
        "/commands/instantiate",
        json={
            "type_ref": "books-prep@0.1.0",
            "customer_id": "Sharma Textiles",
            "business_name": "sharma-textiles",
            "ring": "L1",
            "target_override": {
                "documents": [
                    "april-statement.pdf",
                    {"doc_id": "q1-consolidated", "path": "/intake/q1.pdf"},
                ],
                "output_format": "xlsx",
                "confidence_threshold": 0.85,
            },
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["supported"] is True
    instance_id = body["instance"]["id"]
    assert body["instance"]["type_ref"] == "books-prep@0.1.0"

    # The canonical mandate is findable (the per-instance override registration against a seeded
    # canonical is a no-op: target_override flows to the worker via trigger_run, not via a
    # second catalog row — see design §6 "approval cards are already generic").
    canonical = await state.control._registry.get_type("books-prep@0.1.0")
    assert canonical is not None

    # The instance was persisted with a tenant heap region.
    instance_doc = await state.get_doc("mandate_instance", instance_id)
    assert instance_doc is not None
    assert instance_doc["customer_id"] == "sharma-textiles"
    assert instance_doc["heap_region_id"] == f"tenant_{instance_id}"


async def test_books_prep_playbook_synthetic_end_to_end_in_sim(client: AsyncClient) -> None:
    """Smoke: instantiate books-prep → trigger a sim run → the instance persists with the
    correct type_ref. We don't drive the worker (start_worker=False); this proves the api surface
    resolves books-prep@0.1.0 end-to-end through instantiate + trigger without a 404 or a contract
    break.
    """
    inst = await client.post(
        "/commands/instantiate",
        json={
            "type_ref": "books-prep@0.1.0",
            "customer_id": "Demo Client",
            "business_name": "demo-books",
            "ring": "L2",
            "target_override": {
                "documents": ["april-statement.pdf"],
                "output_format": "xlsx",
                "confidence_threshold": 0.8,
            },
        },
    )
    assert inst.status_code == 201, inst.text
    instance_id = inst.json()["instance"]["id"]

    # trigger a sim run (the worker is off, so the trigger enqueues but doesn't execute)
    trig = await client.post(
        "/commands/trigger-run",
        json={
            "instance_id": instance_id,
            "mode": "sim",
            "actor": "manager:test",
        },
    )
    assert trig.status_code == 202, trig.text

    # The instance was persisted with a books-prep@0.1.0-derived type_ref.
    state = client._transport.app.state.dashboard  # type: ignore[attr-defined]
    found = await state.get_doc("mandate_instance", instance_id)  # type: ignore[arg-type]
    assert found is not None
    assert found["type_ref"] == "books-prep@0.1.0"


def test_build_books_prep_type_has_revised_charter_caveats_compliance() -> None:
    """Off the shelf — the MandateType from step-5 honours the caveats overrides
    (P0-1 GST sentinel as valid pass; P0-2 no_duplicate_commit; P0-3 extraction_suspect routing;
    P2-3 per-series balance_continuity). Without re-running the full kernel, this test pins the
    shape so a future change to books_prep.py can't silently regress the safety properties.
    """
    mandate = build_books_prep_type()
    rule_ids = {c.id for c in mandate.charter.postconditions if c.rung == "rules"}

    assert "has_transactions" in rule_ids
    assert "every_txn_has_source" in rule_ids
    assert "every_txn_has_ledger_head_and_confidence" in rule_ids
    # GST treatment is NOT a hard gate (P0-1) — the rule emits the sentinel as a valid pass.
    assert "gst_treatment_emitted" in rule_ids
    assert "low_confidence_queued" in rule_ids
    # Cross-batch dedup (P0-2) is gated, not just within-batch.
    assert "no_duplicate_commit" in rule_ids
    # balance_continuity is scoped per (account, statement_period) in the rule body (P2-3).
    balance = next(c for c in mandate.charter.postconditions if c.id == "balance_continuity")
    assert "(account" in balance.description and "statement period" in balance.description
    # Feed-forward fields are EMITTED, not gated.
    assert "vendor" not in rule_ids
    assert "gstin" not in rule_ids
    assert "missing_supporting_doc" not in rule_ids
    assert "receivable" not in rule_ids and "payable" not in rule_ids
    # The target carries a confidence_threshold (provisional default 0.8 — calibrated by P1 eval).
    assert mandate.charter.target is not None
    assert mandate.charter.target.get("confidence_threshold") == 0.8
    assert mandate.charter.target.get("output_format") == "xlsx"


def test_build_books_prep_type_mirrors_lead_finder_charter_shape() -> None:
    """The two mandates share the same structural shape (charter + faculties + domain pack +
    settlement + service_ports) — proving the generalisation goal of step-5 (a 3rd mandate is
    just config) by demonstrating two complete mandates side by side.
    """
    books = build_books_prep_type()
    lead = build_lead_finder_type()
    # Same set of public attributes, different content.
    assert type(books) is type(lead)
    assert books.name != lead.name
    assert books.version == "0.1.0"
    assert lead.version == "0.1.0"
    # Books has the deferred spawn rule seeded for gst-recon (declared, not implemented in v0).
    spawn_targets = {rule.child_type_ref for rule in books.settlement.spawn_rules}
    assert "gst-recon@0.1.0" in spawn_targets


def test_canonical_seeding_is_idempotent() -> None:
    """Invoking the seed helper twice (or against a catalog that already has the canonical)
    MUST be a no-op. Otherwise a hot-reload or a repeated first-request would 500."""

    async def run() -> None:
        app = create_app(use_mongo=False, seed_demo=False, operator_token=TEST_TOKEN, start_worker=False)
        state = app.state.dashboard
        await state.start()
        await _ensure_canonical_mandate_registered(state)
        # Second call must not raise (MandateTypeConflict on either type).
        await _ensure_canonical_mandate_registered(state)
        # And the catalog must still hold exactly the two canonical types.
        stored = await state.control._registry.list_types()
        names = sorted({m.name for m in stored})
        assert names == ["books-prep", "lead-finder"]
        await state.close()

    asyncio.run(run())