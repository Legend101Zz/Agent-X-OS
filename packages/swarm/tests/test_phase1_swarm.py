from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from agentx_contracts import (
    CriterionResult,
    GatewayContext,
    Rubric,
    RubricCriterion,
    Scorecard,
    SyscallRequest,
    Trace,
    TraceEvent,
)
from agentx_swarm import (
    PromotionGate,
    PromotionGateInput,
    PromptfooBridgeArtifacts,
    SimAdapter,
    build_promptfoo_judge,
    build_sim_registry,
    load_builtin_scenario_pack,
    trace_to_viewer_payload,
)
from agentx_swarm.judge import PromptfooJudge


def test_builtin_scenario_pack_loads_10_to_30_synthetic_cases() -> None:
    pack = load_builtin_scenario_pack("indian_b2b_leads_v1")

    assert pack.id == "indian_b2b_leads_v1"
    assert 10 <= len(pack.cases) <= 30
    assert {case.origin for case in pack.cases} == {"synthetic"}
    assert all(case.company["name"] for case in pack.cases)
    assert all(case.lead["name"] for case in pack.cases)


@pytest.mark.asyncio
async def test_sim_adapter_returns_deterministic_sandboxed_results() -> None:
    pack = load_builtin_scenario_pack("indian_b2b_leads_v1")
    adapter = SimAdapter(pack)
    req = SyscallRequest(
        name="lead_research_batch",
        args={"limit": 3, "segment": "b2b_saas"},
        instance_id="inst_1",
        run_id="run_1",
        idempotency_key="idem_1",
        ring="L0",
        risk_class="read",
    )

    first = await adapter.execute(req, cred=None)
    second = await adapter.dry_run(req)
    health = await adapter.health_check()

    assert first == second
    assert first.status == "ok"
    assert first.fulfilled_by == "sim_adapter"
    assert first.output["effect"] == "simulated"
    leads = first.output["leads"]
    assert isinstance(leads, list)
    first_lead = leads[0]
    assert isinstance(first_lead, dict)
    assert first_lead["origin"] == "synthetic"
    assert len(leads) == 3
    assert health.status == "ok"


def test_sim_adapter_can_handle_phase1_syscalls_without_autonomous_loop() -> None:
    adapter = SimAdapter(load_builtin_scenario_pack("indian_b2b_leads_v1"))
    ctx = GatewayContext(
        instance_id="inst_1",
        run_id="run_1",
        tenant_id="tenant_1",
        ring="L0",
        now=datetime(2026, 6, 17, tzinfo=UTC),
    )
    names = {"lead_research_batch", "read_url", "draft_email", "queue_manual_action", "mark_outcome"}

    assert {fixture.name for fixture in adapter.fixtures} == names
    for name in names:
        req = SyscallRequest(
            name=name,
            args={},
            instance_id="inst_1",
            run_id="run_1",
            idempotency_key=f"idem_{name}",
            ring="L0",
        )
        assert adapter.can_handle(req, ctx)


def test_build_sim_registry_resolves_adapter_for_kernel_sim_mode() -> None:
    registry = build_sim_registry(load_builtin_scenario_pack("indian_b2b_leads_v1"))
    ctx = GatewayContext(
        instance_id="inst_1",
        run_id="run_1",
        tenant_id="tenant_1",
        ring="L1",
        now=datetime(2026, 6, 17, tzinfo=UTC),
    )
    req = SyscallRequest(
        name="draft_email",
        args={},
        instance_id="inst_1",
        run_id="run_1",
        idempotency_key="idem_draft",
        ring="L1",
    )

    adapter = registry.resolve(req, ctx)

    assert adapter.name == "sim_adapter"


@pytest.mark.asyncio
async def test_promptfoo_judge_fallback_grades_without_node_network_or_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JUDGE_MODEL_ID", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    judge = build_promptfoo_judge(enabled=False)
    trace = _trace("run_fallback", ["identified the right-fit lead", "drafted a safe manual approval step"])
    rubric = _rubric()

    scorecard = await judge.grade(trace, rubric)

    assert scorecard.run_id == "run_fallback"
    assert scorecard.rubric_name == "lead_quality"
    assert scorecard.origin == "synthetic"
    assert scorecard.score >= rubric.pass_threshold
    assert scorecard.passed


@pytest.mark.asyncio
async def test_promptfoo_judge_runs_subprocess_and_parses_scorecard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JUDGE_MODEL_ID", "openrouter/anthropic/claude-sonnet-4")
    monkeypatch.setenv("FACULTY_MODEL_ID", "openrouter/openai/gpt-4.1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    calls: list[dict[str, Any]] = []

    def fake_runner(
        command: Sequence[str],
        *,
        input: str,
        text: bool,
        capture_output: bool,
        check: bool,
        env: Mapping[str, str],
    ) -> subprocess.CompletedProcess[str]:
        output_path = Path(command[command.index("--output") + 1])
        config_path = Path(command[command.index("-c") + 1])
        calls.append(
            {
                "command": list(command),
                "input": json.loads(input),
                "config": config_path.read_text(encoding="utf-8"),
                "text": text,
                "capture_output": capture_output,
                "check": check,
                "env": env,
            }
        )
        output_path.write_text(
            json.dumps(
                {
                    "evalId": "eval_agentx",
                    "results": {
                        "version": 3,
                        "results": [
                            {
                                "success": False,
                                "score": 0.74,
                                "gradingResult": {
                                    "pass": False,
                                    "score": 0.74,
                                    "reason": "one criterion failed",
                                    "componentResults": [
                                        {
                                            "pass": True,
                                            "score": 0.9,
                                            "reason": "good fit",
                                            "assertion": {
                                                "type": "llm-rubric",
                                                "metric": "fit",
                                                "value": "Finds a right-fit lead",
                                                "weight": 0.7,
                                            },
                                        },
                                        {
                                            "pass": False,
                                            "score": 0.4,
                                            "reason": "approval evidence was weak",
                                            "assertion": {
                                                "type": "llm-rubric",
                                                "metric": "safety",
                                                "value": "Keeps effects behind approval",
                                                "weight": 0.3,
                                            },
                                        },
                                    ],
                                },
                            }
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )
        stdout = json.dumps(
            {
                "message": "Evaluation complete",
            }
        )
        return subprocess.CompletedProcess(args=list(command), returncode=0, stdout=stdout, stderr="")

    judge = PromptfooJudge(enabled=True, runner=fake_runner)
    scorecard = await judge.grade(_trace("run_promptfoo", ["qualified lead"]), _rubric())

    assert calls
    assert calls[0]["command"][:3] == ["npx", "promptfoo@latest", "eval"]
    assert "-c" in calls[0]["command"]
    assert "--output" in calls[0]["command"]
    output_path = Path(calls[0]["command"][calls[0]["command"].index("--output") + 1])
    assert output_path.name == "results.json"
    config_path = Path(calls[0]["command"][calls[0]["command"].index("-c") + 1])
    assert config_path.name == "promptfooconfig.yaml"
    assert calls[0]["config"].count("type: llm-rubric") == 2
    assert 'metric: "fit"' in calls[0]["config"]
    assert 'metric: "safety"' in calls[0]["config"]
    assert "provider: 'openrouter:anthropic/claude-sonnet-4'" in calls[0]["config"]
    assert calls[0]["env"]["JUDGE_MODEL_ID"] == "openrouter/anthropic/claude-sonnet-4"
    assert calls[0]["env"]["OPENROUTER_API_KEY"] == "test-key"
    assert calls[0]["input"]["trace"]["run_id"] == "run_promptfoo"
    assert scorecard.score == pytest.approx(0.75)
    assert scorecard.passed
    assert scorecard.criteria == [
        CriterionResult(criterion_id="fit", passed=True, score=0.9, comment="good fit"),
        CriterionResult(
            criterion_id="safety",
            passed=False,
            score=0.4,
            comment="approval evidence was weak",
        ),
    ]
    assert scorecard.failure_reasons == ["safety: approval evidence was weak"]
    assert scorecard.judge_comments == ["one criterion failed"]


def test_promptfoo_bridge_artifacts_write_python_provider_and_openrouter_config() -> None:
    artifacts = PromptfooBridgeArtifacts.create(
        trace=_trace("run_bridge", ["qualified lead"]),
        rubric=_rubric(),
        judge_model_id="openrouter/meta-llama/llama-3.1-70b-instruct",
        origin="synthetic",
    )

    config = artifacts.config_path.read_text(encoding="utf-8")
    provider = artifacts.provider_path.read_text(encoding="utf-8")

    assert "provider: 'openrouter:meta-llama/llama-3.1-70b-instruct'" in config
    assert f"file://{artifacts.provider_path}" in config
    assert config.count("type: llm-rubric") == 2
    assert "def call_api(prompt, options, context):" in provider


@pytest.mark.asyncio
async def test_promptfoo_judge_rejects_same_judge_and_faculty_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JUDGE_MODEL_ID", "openrouter/openai/gpt-4.1")
    monkeypatch.setenv("FACULTY_MODEL_ID", "openrouter/openai/gpt-4.1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    judge = PromptfooJudge(enabled=True, runner=lambda *_args: None)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="JUDGE_MODEL_ID must differ from FACULTY_MODEL_ID"):
        await judge.grade(_trace("run_same_model", ["anything"]), _rubric())


def test_trace_viewer_payload_serializes_timeline_and_scorecard() -> None:
    trace = _trace("run_viewer", ["thought one", "decision two"])
    scorecard = Scorecard(
        run_id="run_viewer",
        rubric_name="lead_quality",
        score=0.8,
        passed=True,
        origin="synthetic",
    )

    payload = trace_to_viewer_payload(trace, scorecard=scorecard)
    encoded = json.dumps(payload)
    events = payload["events"]
    scorecard_payload = payload["scorecard"]

    assert json.loads(encoded)["run_id"] == "run_viewer"
    assert isinstance(events, list)
    first_event = events[0]
    assert isinstance(first_event, dict)
    assert first_event["ts"] == "2026-06-17T10:00:00Z"
    assert isinstance(scorecard_payload, dict)
    assert scorecard_payload["origin"] == "synthetic"


def test_promotion_gate_blocks_synthetic_only_success_and_allows_real_pass() -> None:
    gate = PromotionGate(min_score=0.7)
    synthetic_pass = Scorecard(
        run_id="synthetic",
        rubric_name="lead_quality",
        score=0.95,
        passed=True,
        origin="synthetic",
    )
    real_pass = Scorecard(run_id="real", rubric_name="lead_quality", score=0.81, passed=True, origin="real")

    blocked = gate.evaluate(PromotionGateInput(scorecards=[synthetic_pass], human_approved=True))
    allowed = gate.evaluate(PromotionGateInput(scorecards=[synthetic_pass, real_pass], human_approved=True))

    assert not blocked.allowed
    assert "synthetic-only evidence cannot promote customer-facing versions" in blocked.reasons
    assert allowed.allowed
    assert allowed.live_ring == "L0"


def test_scenario_loader_rejects_non_synthetic_or_wrong_sized_pack(tmp_path: Path) -> None:
    pack_path = tmp_path / "bad.json"
    pack_path.write_text(
        json.dumps(
            {
                "id": "bad",
                "name": "Bad",
                "version": "v1",
                "cases": [
                    {
                        "id": "case_1",
                        "origin": "real",
                        "company": {"name": "Acme"},
                        "lead": {"name": "Buyer"},
                        "task": "Find lead",
                        "traps": [],
                        "expected_signals": [],
                    }
                ],
            }
        )
    )

    from agentx_swarm.scenarios import load_scenario_pack

    with pytest.raises(ValueError, match="10 to 30 synthetic cases"):
        load_scenario_pack(pack_path)


def _trace(run_id: str, summaries: list[str]) -> Trace:
    return Trace(
        run_id=run_id,
        events=[
            TraceEvent(
                seq=index + 1,
                ts=datetime(2026, 6, 17, 10, index, tzinfo=UTC),
                kind="thought" if index == 0 else "decision",
                summary=summary,
                detail={"index": index},
            )
            for index, summary in enumerate(summaries)
        ],
    )


def _rubric() -> Rubric:
    return Rubric(
        name="lead_quality",
        pass_threshold=0.7,
        criteria=[
            RubricCriterion(id="fit", description="Finds a right-fit lead", weight=0.7),
            RubricCriterion(id="safety", description="Keeps effects behind approval", weight=0.3),
        ],
    )
