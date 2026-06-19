"""Phase-4 tests for /commands/promote (HERMES_BUILD_PLAN §Phase 4 — closes G11).

Phase 4 is the candidate→live bridge. Promote is RING-AWARE:

  - L0/L1 (canary): requires human_approved + swarm-smoke-passed (synthetic OR real is OK).
    This is the bridge that lets a fresh Creator candidate (synthetic-only by design) reach
    a canary rung. The Creator run cannot run L2 until promoted; without this bridge no
    Creator candidate can ever go live.

  - L2/L3/L4 (autonomous): requires human_approved + REAL evidence via PromotionGate.
    Synthetic-only is barred (invariant #7 — no customer-facing synthetic versions).

The server gathers eval_cases by type_ref (never accepts client-supplied eval_case_ids —
that would let an operator cherry-pick favorable evidence).

Done-when (6 cases + 401 + retire-the-gap):
  1. L0 + synthetic-smoke + human  → ALLOWED, registers at L0.
  2. L0 + NO evidence             → BARRED.
  3. L2 + synthetic-only          → BARRED (PromotionGate).
  4. L2 + real + human            → ALLOWED, registers at L2.
  5. L2 + synthetic + real (mixed) → ALLOWED (real evidence present).
  6. unauthorized (no bearer)     → 401.
  7. command.promote retired from CORE_GAPS → KNOWN_CLOSED.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from agentx_contracts import (
    EvalCase,
    HydrationSnapshot,
    Scorecard,
    Thread,
)
from agentx_contracts.mandate import MandateType
from agentx_mandate.library.creator import build_creator_type
from agentx_mandate.library.lead_finder import build_lead_finder_type
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from agentx_api.app import create_app

TEST_TOKEN = "test-operator-token-9e3c0d4a"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Async client against a fresh app with NO seeded demo types — catalog starts empty."""
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


async def _seed_synthetic_eval_case_for(app: FastAPI, *, type_ref: str) -> str:
    """Run the sim swarm once so the kernel persists an origin='synthetic' eval_case for type_ref."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    ) as client:
        response = await client.post(
            "/commands/run-swarm",
            json={
                "type_ref": type_ref,
                "pack_id": "indian_b2b_leads_v1",
            },
        )
    assert response.status_code == 200, response.text
    return str(response.json()["eval_case_id"])


async def _seed_real_eval_case_for(client: AsyncClient, *, type_ref: str) -> str:
    """Insert a real-origin eval_case directly into the projection store.

    The promote gate reads eval_cases by type_ref — server-side gather is independent of
    how the case got into the catalog (sim run / real watch maturation / seeded).
    """
    app = client._transport.app  # type: ignore[attr-defined]
    state = app.state.dashboard
    case = EvalCase(
        id=f"eval_real_{type_ref}_v1",
        type_ref=type_ref,
        origin="real",
        hydration=HydrationSnapshot(
            facts=[],
            thread=Thread(
                id=f"thread_real_{type_ref}",
                instance_id="inst_real",
                entity_id="entity_real",
                state="engaged",
                updated_at=datetime.now(UTC),
            ),
            recent_journal=[],
            skill_pack_refs=[],
            domain_pack=None,
            frozen_at=datetime.now(UTC),
        ),
        scorecard=Scorecard(
            origin="real",
            run_id="run_real_seed",
            rubric_name="lead_quality",
            score=0.95,
            passed=True,
            criteria=[],
        ),
        reality_outcome="success",
        tags=["real", "seeded"],
    )
    await state.store.upsert("eval_case", case.id, case.model_dump(mode="json"))
    return case.id


async def _seed_candidate_in_store(
    app: FastAPI,
    *,
    candidate_id: str,
    type_ref: str,
    mandate: MandateType | None = None,
) -> None:
    """Insert a candidate draft directly into the candidate store.

    Tests pre-populate this; production wires the DraftCandidateTypeAdapter to call
    CandidateStore.upsert on every successful draft.

    Defaults: when type_ref is "lead-finder@0.1.0" we use the canonical Phase-1 lead-finder
    mandate (so the candidate matches the already-seeded type and ``register_mandate_type``
    takes its idempotent path). For other type_refs we default to the Creator's own mandate
    (which is what a real Creator draft would look like before promotion).

    Also seeds a corresponding MandateInstance keyed by ``inst_creator_seed`` so the
    promote's audit row (ManagerAction) is reachable via ``/journal?instance_id=...``.
    """
    state = app.state.dashboard
    if mandate is None:
        if type_ref == "lead-finder@0.1.0":
            # Use the canonical lead-finder shape exactly as Phase-1 seeded it, so the
            # ``register_mandate_type`` idempotent path takes over (same_version + equal).
            mandate = build_lead_finder_type()
        else:
            mandate = build_creator_type()
    candidate_doc = {
        "id": candidate_id,
        "type_ref": type_ref,
        "creator_instance_id": "inst_creator_seed",
        "creator_run_id": "run_creator_seed",
        "creator_id": "creator@0.1.0",
        "drafted_at": datetime.now(UTC).isoformat(),
        "mandate_type": mandate.model_dump(mode="json"),
    }
    await state.store.upsert("candidate", candidate_id, candidate_doc)

    # Mirror the Creator instance into the MANDATE_INSTANCE collection so /journal can find
    # the promote's audit row. In production this happens at instantiate-time; the test
    # pre-populates the candidate store without going through instantiate, so we add the
    # instance doc directly here.
    instance_doc = {
        "id": "inst_creator_seed",
        "type_ref": "creator@0.1.0",
        "customer_id": "creator-customer",
        "ring": "L1",
        "heap_region_id": "heap_creator_seed",
    }
    existing = await state.store.get(
        "mandate_instance", "inst_creator_seed"
    )
    if existing is None:
        await state.store.upsert(
            "mandate_instance", "inst_creator_seed", instance_doc
        )


async def _catalog_has_type(client: AsyncClient, type_ref: str) -> bool:
    response = await client.get("/mandate-types")
    assert response.status_code == 200
    types = response.json()["mandate_types"]
    return any(
        t["id"] == type_ref or f"{t['name']}@{t['version']}" == type_ref for t in types
    )


async def _catalog_count(client: AsyncClient) -> int:
    response = await client.get("/mandate-types")
    assert response.status_code == 200
    return len(response.json()["mandate_types"])


# ---------------------------------------------------------------------------
# Done-when #1: L0 + synthetic-smoke + human  → ALLOWED, registers at L0.
# ---------------------------------------------------------------------------
async def test_promote_to_L0_with_synthetic_smoke_and_human_allows_and_registers(
    client: AsyncClient,
) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    type_ref = "lead-finder@0.1.0"

    await _seed_synthetic_eval_case_for(app, type_ref=type_ref)
    await _seed_candidate_in_store(app, candidate_id="cand_lf_001", type_ref=type_ref)

    pre_count = await _catalog_count(client)

    response = await client.post(
        "/commands/promote",
        json={"candidate_id": "cand_lf_001", "ring": "L0", "human_approved": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "promoted", body
    assert body["ring"] == "L0"
    assert body["type_ref"] == type_ref

    # Catalog now lists the promoted type. Count may stay the same when the idempotent path
    # (same_version + equal) returns the existing type — what matters is the type is present.
    assert await _catalog_count(client) >= pre_count
    assert await _catalog_has_type(client, type_ref)

    # Audit row: one ManagerAction(promote) journaled (action lives in event.detail.action).
    # Filter by the candidate's instance_id (which is what the promote handler stamped on the event).
    ledger_all = (
        await client.get("/journal", params={"instance_id": "inst_creator_seed"})
    ).json()
    ledger = {
        **ledger_all,
        "events": [e for e in ledger_all["events"] if e.get("kind") == "manager_action"],
    }
    promote_actions = [
        e for e in ledger["events"]
        if e.get("kind") == "manager_action"
        and e.get("action") == "promote"
    ]
    assert len(promote_actions) == 1, (
        f"expected one ManagerAction(promote); got {len(promote_actions)}; "
        f"all events for instance_id=inst_creator_seed: "
        f"{[(e.get('kind'), e.get('action')) for e in ledger_all['events']]!r}"
    )
    detail = promote_actions[0]["detail"]
    assert detail["candidate_id"] == "cand_lf_001"
    assert detail["ring"] == "L0"
    assert detail["type_ref"] == type_ref


# ---------------------------------------------------------------------------
# Done-when #2: L0 with NO evidence → BARRED. (canary still requires swarm-smoke)
# ---------------------------------------------------------------------------
async def test_promote_to_L0_with_no_evidence_is_barred(client: AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    type_ref = "lead-finder@0.1.0"

    await _seed_candidate_in_store(
        app, candidate_id="cand_lf_no_evidence", type_ref=type_ref
    )

    pre_count = await _catalog_count(client)

    response = await client.post(
        "/commands/promote",
        json={
            "candidate_id": "cand_lf_no_evidence",
            "ring": "L0",
            "human_approved": True,
        },
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["status"] == "barred"
    assert body["ring_requested"] == "L0"
    reasons = body["reasons"]
    assert any(
        "evidence" in r.lower() or "smoke" in r.lower() or "scorecard" in r.lower()
        for r in reasons
    ), f"promote gate must surface the missing-evidence reason; got {reasons!r}"
    assert await _catalog_count(client) == pre_count


# ---------------------------------------------------------------------------
# Done-when #3: L2 with synthetic-only → BARRED (PromotionGate).
# ---------------------------------------------------------------------------
async def test_promote_to_L2_with_synthetic_only_is_barred_by_promotion_gate(
    client: AsyncClient,
) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    type_ref = "lead-finder@0.1.0"

    await _seed_synthetic_eval_case_for(app, type_ref=type_ref)
    await _seed_candidate_in_store(
        app, candidate_id="cand_l2_synth_only", type_ref=type_ref
    )

    pre_count = await _catalog_count(client)

    response = await client.post(
        "/commands/promote",
        json={
            "candidate_id": "cand_l2_synth_only",
            "ring": "L2",
            "human_approved": True,
        },
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["status"] == "barred"
    assert body["ring_requested"] == "L2"
    reasons = body["reasons"]
    assert any("synthetic" in r.lower() for r in reasons), (
        f"PromotionGate must surface the synthetic-only reason at L2; got {reasons!r}"
    )
    assert await _catalog_count(client) == pre_count


# ---------------------------------------------------------------------------
# Done-when #4: L2 with real + human → ALLOWED, registers at L2.
# ---------------------------------------------------------------------------
async def test_promote_to_L2_with_real_and_human_allows_and_registers(
    client: AsyncClient,
) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    type_ref = "lead-finder@0.1.0"

    await _seed_real_eval_case_for(client, type_ref=type_ref)
    await _seed_candidate_in_store(app, candidate_id="cand_l2_real", type_ref=type_ref)

    pre_count = await _catalog_count(client)

    response = await client.post(
        "/commands/promote",
        json={"candidate_id": "cand_l2_real", "ring": "L2", "human_approved": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "promoted"
    assert body["ring"] == "L2"
    assert body["type_ref"] == type_ref

    # Catalog lists the promoted type (count may stay the same via the idempotent path).
    assert await _catalog_count(client) >= pre_count
    assert await _catalog_has_type(client, type_ref)


# ---------------------------------------------------------------------------
# Done-when #5: L2 with synthetic + real (mixed) → ALLOWED (real evidence present).
# ---------------------------------------------------------------------------
async def test_promote_to_L2_with_mixed_synthetic_and_real_allows(
    client: AsyncClient,
) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    type_ref = "lead-finder@0.1.0"

    await _seed_synthetic_eval_case_for(app, type_ref=type_ref)
    await _seed_real_eval_case_for(client, type_ref=type_ref)
    await _seed_candidate_in_store(
        app, candidate_id="cand_l2_mixed", type_ref=type_ref
    )

    response = await client.post(
        "/commands/promote",
        json={"candidate_id": "cand_l2_mixed", "ring": "L2", "human_approved": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "promoted"
    assert body["ring"] == "L2"


# ---------------------------------------------------------------------------
# Done-when #6: unauthorized (no bearer) → 401.
# ---------------------------------------------------------------------------
async def test_promote_unauthorized_returns_401() -> None:
    app = create_app(
        use_mongo=False,
        seed_demo=False,
        operator_token=TEST_TOKEN,
        start_worker=False,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        response = await test_client.post(
            "/commands/promote",
            json={"candidate_id": "cand_x", "ring": "L0", "human_approved": True},
        )
        assert response.status_code == 401, response.text

        bad = AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": "Bearer wrong-token"},
        )
        async with bad:
            response = await bad.post(
                "/commands/promote",
                json={
                    "candidate_id": "cand_x",
                    "ring": "L0",
                    "human_approved": True,
                },
            )
            assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# Done-when #7: command.promote retired from CORE_GAPS → KNOWN_CLOSED.
# ---------------------------------------------------------------------------
def test_command_promote_is_retired_from_core_gaps_to_known_closed() -> None:
    from agentx_api import gaps

    assert "command.promote" in gaps.KNOWN_CLOSED
    open_ids = {gap["id"] for gap in gaps.CORE_GAPS if isinstance(gap["id"], str)}
    assert "command.promote" not in open_ids


# ---------------------------------------------------------------------------
# Bonus: L2 with no human approval → BARRED (regardless of evidence).
# ---------------------------------------------------------------------------
async def test_promote_to_L2_without_human_approval_is_barred(
    client: AsyncClient,
) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    type_ref = "lead-finder@0.1.0"
    await _seed_real_eval_case_for(client, type_ref=type_ref)
    await _seed_candidate_in_store(
        app, candidate_id="cand_l2_no_human", type_ref=type_ref
    )

    response = await client.post(
        "/commands/promote",
        json={
            "candidate_id": "cand_l2_no_human",
            "ring": "L2",
            "human_approved": False,
        },
    )
    assert response.status_code == 422, response.text
    body = response.json()
    reasons = body["reasons"]
    assert any("human" in r.lower() for r in reasons), (
        f"PromotionGate must surface missing-human reason; got {reasons!r}"
    )


# ---------------------------------------------------------------------------
# Bonus: candidate not found → 404 (NOT 422 — the gate has nothing to evaluate).
# ---------------------------------------------------------------------------
async def test_promote_unknown_candidate_returns_404(client: AsyncClient) -> None:
    response = await client.post(
        "/commands/promote",
        json={
            "candidate_id": "cand_does_not_exist",
            "ring": "L0",
            "human_approved": True,
        },
    )
    assert response.status_code == 404, response.text


# ---------------------------------------------------------------------------
# Bonus: invalid ring → 422 with reason.
# ---------------------------------------------------------------------------
async def test_promote_with_invalid_ring_is_barred(client: AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    type_ref = "lead-finder@0.1.0"
    await _seed_candidate_in_store(
        app, candidate_id="cand_bad_ring", type_ref=type_ref
    )

    response = await client.post(
        "/commands/promote",
        json={"candidate_id": "cand_bad_ring", "ring": "L9", "human_approved": True},
    )
    assert response.status_code == 422, response.text
    body = response.json()
    # The route can bar with {"status": "barred", "reasons": [...]} OR FastAPI can reject at
    # Pydantic validation (literal type mismatch) — both are valid 422 responses. We accept
    # either shape, as long as "ring" is mentioned somewhere in the body text.
    body_text = (body.get("reasons", []) or []) + [
        str(body.get("detail", "")),
        str(body),
    ]
    assert any("ring" in str(s).lower() for s in body_text), (
        f"must surface ring-validation reason; got {body!r}"
    )


# ---------------------------------------------------------------------------
# Bonus: client-supplied eval_case_ids are IGNORED — server gathers by type_ref.
# Structural proof that operators cannot cherry-pick favorable evidence.
# ---------------------------------------------------------------------------
async def test_promote_ignores_client_supplied_eval_case_ids_and_gathers_by_type_ref(
    client: AsyncClient,
) -> None:
    """An operator passing a hand-picked synthetic eval_case_id must NOT be enough to promote
    at L2 — the server gathers by the candidate's type_ref and that's the only source of truth."""
    app = client._transport.app  # type: ignore[attr-defined]
    type_ref = "lead-finder@0.1.0"
    await _seed_synthetic_eval_case_for(app, type_ref=type_ref)
    await _seed_candidate_in_store(
        app, candidate_id="cand_cherry_pick", type_ref=type_ref
    )

    response = await client.post(
        "/commands/promote",
        json={
            "candidate_id": "cand_cherry_pick",
            "ring": "L2",
            "human_approved": True,
            # Operator-supplied "proof" — must be IGNORED.
            "eval_case_ids": ["eval_real_fake_id_1", "eval_real_fake_id_2"],
            "scorecards": [
                {"origin": "real", "passed": True, "score": 0.99, "criteria": {}}
            ],
        },
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["status"] == "barred"
    reasons = " ".join(body["reasons"]).lower()
    assert "synthetic" in reasons
    assert "fake_id" not in reasons, (
        f"server leaked client-supplied eval_case_ids into the decision; reasons={body['reasons']!r}"
    )