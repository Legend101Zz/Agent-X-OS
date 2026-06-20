"""Session I — POST /commands/run-swarm drives a sim swarm run from the dashboard.

The route wraps the already-proven swarm loop (tests/integration/test_swarm_end_to_end.py):

    load_builtin_scenario_pack -> build_sim_registry -> sim-bound Phase1RunInvoker
      -> invoke(mode="sim") -> Trace
      -> promptfoo Judge (deterministic fallback) -> Scorecard(origin="synthetic")
      -> PromotionGate BARS synthetic-only

and persists exactly one EvalCase(origin="synthetic") into c.EVAL_CASE plus one
ManagerAction(action="run_swarm") for the audit trail.

The Judge stays in its deterministic OFFLINE path here (no Node/network/keys) — the env is
scrubbed by the autouse fixture below so the unit suite is hermetic regardless of the dev's shell.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from agentx_api.app import create_app

TEST_TOKEN = "test-operator-token"

RUN_SWARM_PAYLOAD: dict[str, Any] = {
    "type_ref": "lead-finder@0.1.0",
    "pack_id": "indian_b2b_leads_v1",
    "ring": "L2",
    "actor": "manager:test",
}


@pytest.fixture(autouse=True)
def _deterministic_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the promptfoo Judge into its deterministic fallback (no subprocess/network)."""
    monkeypatch.delenv("JUDGE_MODEL_ID", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    # seed_demo=False so EVAL_CASE starts empty and the count delta is unambiguous.
    app = create_app(use_mongo=False, seed_demo=False, operator_token=TEST_TOKEN, start_worker=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    ) as test_client:
        yield test_client


async def _eval_case_count(client: AsyncClient) -> int:
    return len((await client.get("/eval-cases")).json()["eval_cases"])


async def test_run_swarm_returns_scorecard_gate_and_trace(client: AsyncClient) -> None:
    response = await client.post("/commands/run-swarm", json=RUN_SWARM_PAYLOAD)
    assert response.status_code == 200, response.text
    body = response.json()

    # A graded scorecard (synthetic) with a numeric score and pass verdict.
    scorecard = body["scorecard"]
    assert scorecard["origin"] == "synthetic"
    assert isinstance(scorecard["score"], (int, float))
    assert scorecard["passed"] is True

    # A gate decision that BARS the synthetic-only run.
    gate = body["gate_decision"]
    assert gate["allowed"] is False

    # A BLUEPRINT §5 timeline payload (trace_to_viewer_payload shape) with the real sim run events.
    trace = body["trace"]
    assert trace["run_id"] == body["run_id"]
    assert trace["events"], "expected a non-empty sim trace timeline"
    assert any(
        event["kind"] == "syscall_result" and event["summary"] == "send_email"
        for event in trace["events"]
    ), "the L2 sim run should fulfil send_email via the SimAdapter"


async def test_run_swarm_persists_exactly_one_synthetic_eval_case(client: AsyncClient) -> None:
    before = await _eval_case_count(client)
    response = await client.post("/commands/run-swarm", json=RUN_SWARM_PAYLOAD)
    assert response.status_code == 200, response.text
    after = await _eval_case_count(client)
    assert after - before == 1, f"expected exactly one new EvalCase, got delta {after - before}"

    body = response.json()
    cases = (await client.get("/eval-cases")).json()["eval_cases"]
    persisted = next(case for case in cases if case["id"] == body["eval_case_id"])
    assert persisted["origin"] == "synthetic"
    assert persisted["type_ref"] == "lead-finder@0.1.0"
    assert "indian_b2b_leads_v1" in persisted["tags"]
    assert "swarm" in persisted["tags"]

    # One ManagerAction(action="run_swarm") is journaled for the audit trail (linked by run_id).
    ledger = (
        await client.get("/journal", params={"run_id": body["run_id"], "kind": "manager_action"})
    ).json()
    run_swarm_actions = [event for event in ledger["events"] if event["action"] == "run_swarm"]
    assert len(run_swarm_actions) == 1
    assert run_swarm_actions[0]["detail"]["pack_id"] == "indian_b2b_leads_v1"
    assert run_swarm_actions[0]["detail"]["gate_allowed"] is False


async def test_run_swarm_gate_bars_synthetic_only(client: AsyncClient) -> None:
    response = await client.post("/commands/run-swarm", json=RUN_SWARM_PAYLOAD)
    assert response.status_code == 200, response.text
    gate = response.json()["gate_decision"]
    assert gate["allowed"] is False
    assert any(
        "synthetic-only evidence cannot promote customer-facing versions" in reason
        for reason in gate["reasons"]
    ), gate["reasons"]


async def test_run_swarm_never_touches_the_live_registry(client: AsyncClient) -> None:
    response = await client.post("/commands/run-swarm", json=RUN_SWARM_PAYLOAD)
    assert response.status_code == 200, response.text
    events = response.json()["trace"]["events"]
    fulfilled = [
        event["detail"].get("fulfilled_by")
        for event in events
        if event["kind"] == "syscall_result"
    ]
    assert fulfilled, "expected at least one fulfilled syscall in the sim trace"
    assert all(
        by == "sim_adapter" for by in fulfilled
    ), f"every effect must be fulfilled by the SimAdapter, got {fulfilled}"


async def test_run_swarm_requires_bearer_token() -> None:
    app = create_app(use_mongo=False, seed_demo=False, operator_token=TEST_TOKEN, start_worker=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon_client:
        response = await anon_client.post("/commands/run-swarm", json=RUN_SWARM_PAYLOAD)
        assert response.status_code == 401
        assert "Bearer" in response.json()["detail"]


async def test_run_swarm_eval_case_is_readable_with_top_level_score(client: AsyncClient) -> None:
    """The persisted doc carries top-level score/passed so the dashboard mapEvalCases renders it."""
    response = await client.post("/commands/run-swarm", json=RUN_SWARM_PAYLOAD)
    assert response.status_code == 200, response.text
    cases = (await client.get("/eval-cases")).json()["eval_cases"]
    persisted = next(case for case in cases if case["id"] == response.json()["eval_case_id"])
    assert isinstance(persisted["score"], (int, float))
    assert persisted["passed"] is True
    # EVAL_CASE has no projector — the write is a deliberate direct upsert.
    assert persisted.get("scorecard") is not None
