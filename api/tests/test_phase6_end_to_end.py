"""Phase 6 — end-to-end growth-loop integration (HERMES_BUILD_PLAN §Phase 6).

The per-phase unit suites prove each piece in isolation; THIS proves they COMPOSE through the
public API + the foundry compiler, on the in-memory backend:

  run-swarm a candidate (Phase I)                 -> synthetic EvalCase persisted + gate BARS synthetic
  stage a Creator-drafted candidate (Phase 3)     -> CANDIDATE store
  promote to L0 canary (Phase 4)                  -> synthetic + human ALLOWED, registered (the bridge)
  promote to L2 with synthetic-only (Phase 4)     -> BARRED (invariant #7)
  reality grades a run (Phase 2)                  -> a real EvalCase(origin="real") lands in the gym
                                                     (the watch->real-case MECHANISM is proven by
                                                      packages/kernel/tests/test_watch_maturation_production_judge.py;
                                                      here we assert the gym GROWS one + promote/compile read it)
  promote to L2 with real + human (Phase 4)       -> ALLOWED, registered (the #7 INVERSE)
  compile_candidate over the gym (Phase 5)        -> promotable WITH real evidence; NEVER synthetic-only

Two distinct candidate types are used so each registration happens exactly once (the test does not
depend on register-idempotency).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import agentx_db.collections as c
import pytest
from agentx_contracts.gym import EvalCase
from agentx_contracts.mandate import HydrationSnapshot
from agentx_contracts.verification import Scorecard
from agentx_mandate.library.lead_finder import build_lead_finder_type
from agentx_swarm.compiler import CompilerConfig, compile_candidate
from httpx import ASGITransport, AsyncClient

from agentx_api.app import create_app

TEST_TOKEN = "test-operator-token"


@pytest.fixture(autouse=True)
def _deterministic_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the swarm Judge into its deterministic offline fallback (hermetic)."""
    monkeypatch.delenv("JUDGE_MODEL_ID", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


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


# --- helpers ---------------------------------------------------------------


def _candidate_type(*, name: str, version: str = "0.1.0") -> Any:
    """A distinct candidate MandateType (a lead-finder variant) with its own id + name@version."""
    return build_lead_finder_type().model_copy(
        update={"id": f"type_{name.replace('-', '_')}", "name": name, "version": version}
    )


async def _stage_candidate(app: Any, *, candidate_id: str, mandate_type: Any) -> str:
    """Stage a Creator-drafted candidate into the CANDIDATE store (Phase 3 output shape)."""
    state = app.state.dashboard
    type_ref = f"{mandate_type.name}@{mandate_type.version}"
    await state.store.upsert(
        c.CANDIDATE,
        candidate_id,
        {"id": candidate_id, "type_ref": type_ref, "mandate_type": mandate_type.model_dump(mode="json")},
    )
    return type_ref


async def _seed_eval_case(app: Any, *, type_ref: str, origin: str, run_id: str, score: float) -> None:
    """Persist an EvalCase the way the run-swarm / watch-maturation paths do (top-level score/passed
    mirror that the contract forbids but the dashboard reads)."""
    state = app.state.dashboard
    scorecard = Scorecard(
        run_id=run_id, rubric_name="lead_quality", score=score, passed=score >= 0.5, origin=origin
    )
    eval_case = EvalCase(
        id=f"eval_{run_id}",
        type_ref=type_ref,
        origin=origin,
        hydration=HydrationSnapshot(frozen_at=datetime.now(UTC)),
        scorecard=scorecard,
        reality_outcome="success" if origin == "real" else None,
        tags=["phase6", origin],
    )
    doc = eval_case.model_dump(mode="json")
    doc["score"] = scorecard.score
    doc["passed"] = scorecard.passed
    await state.store.upsert(c.EVAL_CASE, eval_case.id, doc)


async def _catalog_type_refs(client: AsyncClient) -> set[str]:
    rows = (await client.get("/mandate-types")).json()["mandate_types"]
    return {f"{r.get('name')}@{r.get('version')}" for r in rows}


async def _load_gym(app: Any) -> list[EvalCase]:
    """Rebuild typed EvalCases from the store, dropping the dashboard-mirror keys (extra='forbid')."""
    state = app.state.dashboard
    gym: list[EvalCase] = []
    for doc in await state.store.find(c.EVAL_CASE, {}):
        clean = {k: v for k, v in doc.items() if k not in {"score", "passed"}}
        try:
            gym.append(EvalCase.model_validate(clean))
        except Exception:  # noqa: BLE001 — skip malformed rows
            continue
    return gym


async def _promote(client: AsyncClient, *, candidate_id: str, ring: str) -> Any:
    return await client.post(
        "/commands/promote",
        json={"candidate_id": candidate_id, "ring": ring, "human_approved": True},
    )


# --- the end-to-end ---------------------------------------------------------


async def test_phase6_growth_loop_end_to_end(client: AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]

    # 1. Phase I — swarm-test a candidate. A synthetic EvalCase is persisted; the gate BARS synthetic.
    rs = await client.post(
        "/commands/run-swarm",
        json={"type_ref": "lead-finder@0.1.0", "pack_id": "indian_b2b_leads_v1", "ring": "L2"},
    )
    assert rs.status_code == 200, rs.text
    assert rs.json()["gate_decision"]["allowed"] is False
    assert any(ec["origin"] == "synthetic" for ec in (await client.get("/eval-cases")).json()["eval_cases"])

    # 2. Phase 4 (canary bridge) — a Creator-drafted candidate with only a synthetic smoke pass is
    #    promotable to an L0 canary rung (synthetic is the bridge before any real run).
    canary_type = _candidate_type(name="lf-canary")
    canary_ref = await _stage_candidate(app, candidate_id="cand_canary", mandate_type=canary_type)
    await _seed_eval_case(app, type_ref=canary_ref, origin="synthetic", run_id="run_canary_synth", score=0.9)

    assert canary_ref not in await _catalog_type_refs(client)
    p_canary = await _promote(client, candidate_id="cand_canary", ring="L0")
    assert p_canary.status_code == 200, p_canary.text
    assert canary_ref in await _catalog_type_refs(client)  # registered at the canary rung

    # 3. Phase 4 + invariant #7 — a different candidate with ONLY synthetic evidence CANNOT reach a
    #    customer-facing (L2) ring.
    cust_type = _candidate_type(name="lf-cust")
    cust_ref = await _stage_candidate(app, candidate_id="cand_cust", mandate_type=cust_type)
    await _seed_eval_case(app, type_ref=cust_ref, origin="synthetic", run_id="run_cust_synth", score=0.95)

    p_barred = await _promote(client, candidate_id="cand_cust", ring="L2")
    assert p_barred.status_code == 422, p_barred.text
    assert any("synthetic" in r.lower() for r in p_barred.json()["reasons"])
    assert cust_ref not in await _catalog_type_refs(client)  # NOT registered

    # 4. Phase 2 — reality grades a run for that candidate: a real EvalCase lands in the gym.
    await _seed_eval_case(app, type_ref=cust_ref, origin="real", run_id="run_cust_real", score=0.86)
    assert any(ec["origin"] == "real" for ec in (await client.get("/eval-cases")).json()["eval_cases"])

    # 5. Phase 4 (the #7 INVERSE) — with real + human evidence the SAME candidate now promotes to L2.
    p_real = await _promote(client, candidate_id="cand_cust", ring="L2")
    assert p_real.status_code == 200, p_real.text
    assert cust_ref in await _catalog_type_refs(client)  # now registered customer-facing

    # 6. Phase 5 — the compiler reads the gym: promotable WITH real evidence; NEVER synthetic-only.
    gym = await _load_gym(app)
    assert any(ec.origin == "real" for ec in gym) and any(ec.origin == "synthetic" for ec in gym)

    config = CompilerConfig(target_skill_pack="skill_pack:lead-finder/research@0.1.0")
    compiled = compile_candidate(gym, config=config)
    assert compiled.real_case_count >= 1
    assert compiled.promotable is True
    assert compiled.proposed_skill_pack == "skill_pack:lead-finder/research@0.2.0"

    synthetic_only = [ec for ec in gym if ec.origin == "synthetic"]
    compiled_synth = compile_candidate(synthetic_only, config=config)
    assert compiled_synth.real_case_count == 0
    assert compiled_synth.promotable is False  # invariant #7, end to end
