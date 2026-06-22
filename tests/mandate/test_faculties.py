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


def test_faculty_library_contains_phase1_phase3_and_phase12_faculties() -> None:
    # Phase-1 (lead-finder): research, enrichment, judgment, memory-craft, escalation
    # Phase-3 (Creator, BLUEPRINT §5): conversation, scheduling
    # Phase-12 (mandate-discovery, HERMES_BUILD_PLAN §Phase 12): the 6 F1-F6 faculties
    #   (F7 escalation is the shared library entry above).
    # Phase-13/14 (PR #8): deep_research — used by mandate-discovery's live-mode research path.
    # books-prep thin faculties (Phase 7): extraction + ledger-export
    expected = {
        "research",
        "enrichment",
        "judgment",
        "memory-craft",
        "escalation",
        "outreach",
        "conversation",
        "scheduling",
        "deep_research",
        "extraction",
        "ledger-export",
        "mandate_discovery_community_source",
        "mandate_discovery_pain_extraction",
        "mandate_discovery_demand_clustering",
        "mandate_discovery_competitor_stress",
        "mandate_discovery_buyer_mapping",
        "mandate_discovery_portfolio_builder",
    }
    assert set(FACULTY_LIBRARY) == expected, (
        f"faculty library drifted: missing={expected - set(FACULTY_LIBRARY)}; "
        f"extra={set(FACULTY_LIBRARY) - expected}"
    )


def test_each_faculty_binds_hermes_with_effectful_tools_to_gateway_and_scratch_memory() -> None:
    for faculty in FACULTY_LIBRARY.values():
        assert faculty.harness_adapter.harness == "hermes"
        assert faculty.harness_adapter.effectful_tools_to_gateway is True
        assert faculty.harness_adapter.memory_mode == "per_run_scratch"


def test_get_faculty_returns_library_entry_and_rejects_unknown_name() -> None:
    assert get_faculty("research") is FACULTY_LIBRARY["research"]
    with pytest.raises(KeyError):
        get_faculty("unknown")


def test_research_proposes_read_intent_without_fabricating_leads() -> None:
    """Research emits ONLY the read intent. Real leads are produced where the read is fulfilled
    (live gateway → Exa/Firecrawl, or sim native fixtures), NEVER fabricated by the faculty itself."""
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
    # Args carry research CRITERIA (count split out for the provider), not pre-built leads.
    assert action.request.args == {
        "criteria": {
            "icp": "independent dental clinics",
            "location": "Pune",
            "query": "Pune dental clinic official website contact book appointment consultation",
            "exclude_domains": [
                "youtube.com",
                "instagram.com",
                "facebook.com",
                "linkedin.com",
                "reddit.com",
                "medium.com",
            ],
        },
        "count": 2,
    }
    # The faculty must NOT fabricate leads into scratch — that was the bug this kills.
    assert "leads" not in ctx.scratchpad


def test_judgment_scores_cached_leads_in_scratchpad() -> None:
    ctx = _ctx()
    ctx.scratchpad["leads"] = [
        {
            "id": "lead_1",
            "company": "A",
                "url": "https://a.example/contact",
                "contact_role": "Practice owner",
                "contact_url": "https://a.example/contact",
                "buying_signal": "Accepting new patient appointments",
                "buying_signal_evidence": "Accepting new patient appointments",
                "evidence": ["source:a", "Accepting new patient appointments"],
            "actionable": True,
        },
        {"id": "lead_2", "company": "B", "url": "https://youtube.com/watch/2", "evidence": ["source:b"]},
    ]

    assert propose("judgment", ctx) == []

    scores = ctx.scratchpad["scores"]
    assert isinstance(scores, dict)
    assert scores["lead_1"]["score"] >= 0.8
    assert scores["lead_2"]["score"] == 0.0


def test_enrichment_emits_at_most_three_reads_and_skips_content_domains() -> None:
    ctx = _ctx()
    ctx.scratchpad["leads"] = [
        {"id": "lead_1", "company": "Clinic One", "url": "https://clinic-one.example"},
        {"id": "bad", "company": "Video", "url": "https://youtube.com/watch?v=1"},
        {"id": "lead_2", "company": "Clinic Two", "url": "https://clinic-two.example"},
        {"id": "lead_3", "company": "Clinic Three", "url": "https://clinic-three.example"},
        {"id": "lead_4", "company": "Clinic Four", "url": "https://clinic-four.example"},
    ]

    actions = propose("enrichment", ctx)

    assert [action.request.args["lead_id"] for action in actions if isinstance(action, Call)] == [
        "lead_1",
        "lead_2",
        "lead_3",
    ]
    assert all(isinstance(action, Call) and action.request.name == "read_url" for action in actions)


def test_memory_craft_claims_probationary_agent_inferred_facts_with_provenance() -> None:
    ctx = _ctx()
    ctx.scratchpad["leads"] = [
        {
            "id": "lead_1",
            "company": "A",
                "url": "https://a.example/contact",
                "contact_role": "Practice owner",
                "contact_url": "https://a.example/contact",
                "buying_signal": "Accepting new patients",
                "buying_signal_evidence": "Accepting new patients",
                "evidence": ["source:a", "Accepting new patients"],
            "actionable": True,
        },
        {"id": "lead_2", "company": "B", "evidence": ["source:b"], "actionable": False},
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
    assert {fact.predicate for fact in action.facts} == {"qualified_lead_score", "actionable_lead"}
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
