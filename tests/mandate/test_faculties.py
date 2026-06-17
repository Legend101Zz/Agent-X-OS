"""M2 — Phase-1 faculties as pure mandate code.

The four faculties are reusable capability contracts. They may propose syscall intents or facts, but
they do not hold credentials, do not perform I/O, and keep harness memory as per-run scratch only.
"""

from datetime import UTC, datetime

import pytest
from agentx_contracts.mandate import HydrationSnapshot
from agentx_mandate.faculties import FACULTY_LIBRARY, get_faculty, propose
from agentx_mandate.harness import Call, Claim, Escalate, FacultyContext

NOW = datetime(2026, 6, 17, tzinfo=UTC)


def _ctx(*, error: str | None = None) -> FacultyContext:
    return FacultyContext(
        snapshot=HydrationSnapshot(frozen_at=NOW),
        target={"icp": "independent dental clinics", "location": "Pune", "count": 2},
        scratchpad={},
        instance_id="inst_a",
        run_id="run_1",
        ring="L1",
        now=NOW,
        error=error,
    )


def test_faculty_library_contains_exactly_phase1_faculties() -> None:
    assert set(FACULTY_LIBRARY) == {"research", "judgment", "memory-craft", "escalation"}


def test_each_faculty_binds_hermes_with_effectful_tools_to_gateway_and_scratch_memory() -> None:
    for faculty in FACULTY_LIBRARY.values():
        assert faculty.harness_adapter.harness == "hermes"
        assert faculty.harness_adapter.effectful_tools_to_gateway is True
        assert faculty.harness_adapter.memory_mode == "per_run_scratch"


def test_get_faculty_returns_library_entry_and_rejects_unknown_name() -> None:
    assert get_faculty("research") is FACULTY_LIBRARY["research"]
    with pytest.raises(KeyError):
        get_faculty("unknown")


def test_research_proposes_read_intent_and_caches_candidate_leads() -> None:
    ctx = _ctx()

    actions = propose("research", ctx)

    assert len(actions) == 1
    action = actions[0]
    assert isinstance(action, Call)
    assert action.request.name == "lead_research_batch"
    assert action.request.risk_class == "read"
    assert action.request.instance_id == "inst_a"
    assert action.request.run_id == "run_1"
    assert action.request.ring == "L1"
    assert action.request.args == ctx.target
    assert ctx.scratchpad["leads"] == [
        {
            "id": "lead_1",
            "company": "independent dental clinics lead 1",
            "location": "Pune",
            "evidence": ["lead_research_batch:run_1:1"],
        },
        {
            "id": "lead_2",
            "company": "independent dental clinics lead 2",
            "location": "Pune",
            "evidence": ["lead_research_batch:run_1:2"],
        },
    ]


def test_judgment_scores_cached_leads_in_scratchpad() -> None:
    ctx = _ctx()
    ctx.scratchpad["leads"] = [
        {"id": "lead_1", "company": "A", "evidence": ["source:a"]},
        {"id": "lead_2", "company": "B", "evidence": ["source:b"]},
    ]

    assert propose("judgment", ctx) == []

    assert ctx.scratchpad["scores"] == {
        "lead_1": {"score": 0.7, "reason": "evidence-backed candidate"},
        "lead_2": {"score": 0.7, "reason": "evidence-backed candidate"},
    }


def test_memory_craft_claims_probationary_agent_inferred_facts_with_provenance() -> None:
    ctx = _ctx()
    ctx.scratchpad["leads"] = [
        {"id": "lead_1", "company": "A", "evidence": ["source:a"]},
        {"id": "lead_2", "company": "B", "evidence": ["source:b"]},
    ]
    ctx.scratchpad["scores"] = {
        "lead_1": {"score": 0.7, "reason": "evidence-backed candidate"},
        "lead_2": {"score": 0.4, "reason": "thin evidence"},
    }

    actions = propose("memory-craft", ctx)

    assert len(actions) == 1
    action = actions[0]
    assert isinstance(action, Claim)
    assert len(action.facts) == 2
    for fact in action.facts:
        assert fact.instance_id == "inst_a"
        assert fact.provenance.run_id == "run_1"
        assert fact.provenance.evidence
        assert 0.0 <= fact.confidence <= 1.0
        assert fact.source == "agent-inferred"
        assert fact.status == "probation"
        assert fact.created_at == NOW


def test_escalation_crashes_upward_only_when_context_has_error() -> None:
    assert propose("escalation", _ctx()) == []

    actions = propose("escalation", _ctx(error="research timeout"))

    assert len(actions) == 1
    action = actions[0]
    assert isinstance(action, Escalate)
    assert action.reason == "research timeout"
    assert action.detail["run_id"] == "run_1"
