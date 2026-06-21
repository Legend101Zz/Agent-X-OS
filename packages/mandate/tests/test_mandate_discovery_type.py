"""Phase-12 mandate-discovery MANDATE TYPE tests (HERMES_BUILD_PLAN §Phase 12).

Layer A (deterministic unit tests, no LLM, no Mongo, ~10s).

Done-when:
  - ``build_mandate_discovery_type()`` returns a valid ``MandateType``.
  - All 7 faculties are bound (F1-F7).
  - The 5 charter postconditions are machine-checkable (rung='rules' with expr).
  - The watch window is 14 days (336 hours — the Rung 4 reality-watch window).
  - The spawn rule wires to lead-finder@0.1.0 with the on_condition=shortlist_approved.
  - Each faculty resolves to a real library entry (FACULTY_LIBRARY guard).
  - The type exports a service_port for the roadmap board to consume.
"""

from __future__ import annotations

from agentx_contracts.mandate import Charter, DomainPackRef, MandateType, VerificationSuite
from agentx_mandate.library.mandate_discovery import build_mandate_discovery_type
from agentx_mandate.library.mandate_discovery_faculties import (
    F1_COMMUNITY_SOURCE,
    F2_PAIN_EXTRACTION,
    F3_DEMAND_CLUSTERING,
    F4_COMPETITOR_STRESS,
    F5_BUYER_MAPPING,
    F6_PORTFOLIO_BUILDER,
    F7_ESCALATION,
)


def test_build_mandate_discovery_type_returns_a_mandate_type() -> None:
    candidate = build_mandate_discovery_type()
    assert isinstance(candidate, MandateType)
    assert candidate.id == "type_mandate_discovery_v0"
    assert candidate.name == "mandate-discovery"
    assert candidate.version == "0.1.0"


def test_mandate_discovery_type_has_seven_faculties_f1_through_f7() -> None:
    """Done-when: F1 community-source + F2 pain-extraction + F3 demand-clustering +
    F4 competitor-stress + F5 buyer-mapping + F6 portfolio-builder + F7 escalation.
    """
    candidate = build_mandate_discovery_type()
    bound_names = {binding.faculty_name for binding in candidate.faculties}
    expected = {
        "mandate_discovery_community_source",
        "mandate_discovery_pain_extraction",
        "mandate_discovery_demand_clustering",
        "mandate_discovery_competitor_stress",
        "mandate_discovery_buyer_mapping",
        "mandate_discovery_portfolio_builder",
        "escalation",
    }
    assert expected.issubset(bound_names), f"missing faculties: {expected - bound_names}; have: {bound_names}"


def test_mandate_discovery_faculties_resolve_to_real_library_entries() -> None:
    """Every faculty the MandateType binds must exist in the F1-F7 library module.

    Guards against the case where the MandateType adds a new faculty but the
    library module forgets to define it. (Phase-12 lesson: the playbook looks
    up faculties by name; a missing module crashes the run.)
    """
    candidate = build_mandate_discovery_type()
    expected_in_library = {
        F1_COMMUNITY_SOURCE.name,
        F2_PAIN_EXTRACTION.name,
        F3_DEMAND_CLUSTERING.name,
        F4_COMPETITOR_STRESS.name,
        F5_BUYER_MAPPING.name,
        F6_PORTFOLIO_BUILDER.name,
        F7_ESCALATION.name,
    }
    for binding in candidate.faculties:
        assert binding.faculty_name in expected_in_library, (
            f"MandateDiscovery binds faculty {binding.faculty_name!r} but the F1-F7 library "
            f"module doesn't define it — the playbook will crash at run-time"
        )
        # And every discovery faculty declares a real skill_pack ref.
        lib_faculty = next(
            f for f in [
                F1_COMMUNITY_SOURCE,
                F2_PAIN_EXTRACTION,
                F3_DEMAND_CLUSTERING,
                F4_COMPETITOR_STRESS,
                F5_BUYER_MAPPING,
                F6_PORTFOLIO_BUILDER,
                F7_ESCALATION,
            ]
            if f.name == binding.faculty_name
        )
        assert lib_faculty.skill_pack.startswith("skill_pack:"), (
            f"faculty {binding.faculty_name!r} has no skill_pack ref (compiler-owned, versioned)"
        )


def test_mandate_discovery_charter_has_a_goal_and_machine_checkable_postconditions() -> None:
    """Done-when: charter goal + 5 rules-rung postconditions with exprs the verifier can run."""
    candidate = build_mandate_discovery_type()
    assert isinstance(candidate.charter, Charter)
    assert candidate.charter.goal, "MandateDiscovery's charter must have a non-empty goal"
    rules_post = [c for c in candidate.charter.postconditions if c.rung == "rules"]
    assert len(rules_post) >= 5, f"MandateDiscovery must declare >=5 rules postconditions; got {len(rules_post)}"
    for condition in rules_post:
        assert condition.expr, (
            f"rules postcondition {condition.id!r} must have an expr (rules-verifier evaluates it)"
        )
    expected_post_ids = {
        "pain_clusters_at_least_three",
        "mandate_candidates_at_least_one",
        "moat_pass_count_at_least_one",
        "buyer_source_manifest_present",
        "mandate_portfolio_committed",
    }
    actual_post_ids = {c.id for c in rules_post}
    assert expected_post_ids.issubset(actual_post_ids), (
        f"missing required postconditions: {expected_post_ids - actual_post_ids}"
    )


def test_mandate_discovery_type_watch_window_is_14_days() -> None:
    """Done-when: watch_window_hours=336 (14 days = the Rung 4 reality-watch window)."""
    candidate = build_mandate_discovery_type()
    assert candidate.settlement.watch_window_hours == 336, (
        f"mandate-discovery must watch for 14 days (336h); got {candidate.settlement.watch_window_hours}"
    )


def test_mandate_discovery_spawn_rule_wires_to_lead_finder() -> None:
    """Done-when: on_condition=shortlist_approved spawns a lead-finder@0.1.0 child."""
    candidate = build_mandate_discovery_type()
    assert len(candidate.settlement.spawn_rules) == 1, (
        f"mandate-discovery must declare exactly 1 spawn rule; got {len(candidate.settlement.spawn_rules)}"
    )
    rule = candidate.settlement.spawn_rules[0]
    assert rule.on_condition == "shortlist_approved", (
        f"the only spawn rule must trigger on human-approval of the shortlist; got {rule.on_condition!r}"
    )
    assert rule.child_type_ref == "lead-finder@0.1.0", (
        f"the spawn child must be lead-finder@0.1.0 (closing the loop); got {rule.child_type_ref!r}"
    )
    assert "mandate_shortlist_id" in rule.params, (
        "the spawn rule must carry mandate_shortlist_id in params (the bridge from portfolio to lead-finder)"
    )


def test_mandate_discovery_type_names_a_real_domain_pack() -> None:
    """Done-when: the domain_pack ref points at the mandate-discovery domain pack (v0.1.0)."""
    candidate = build_mandate_discovery_type()
    assert isinstance(candidate.domain_pack, DomainPackRef)
    assert candidate.domain_pack.name == "mandate-discovery"
    assert candidate.domain_pack.version == "0.1.0"


def test_mandate_discovery_type_has_a_verification_suite() -> None:
    """Done-when: verification ladder includes rules, judge, human, reality (the full 4-rung ladder)."""
    candidate = build_mandate_discovery_type()
    assert isinstance(candidate.verification, VerificationSuite)
    assert "rules" in candidate.verification.ladder
    assert "judge" in candidate.verification.ladder
    assert "human" in candidate.verification.ladder
    assert "reality" in candidate.verification.ladder


def test_mandate_discovery_type_exposes_mandate_opportunities_service_port() -> None:
    """Done-when: service_ports includes 'mandate_opportunities' (the roadmap-board contract)."""
    candidate = build_mandate_discovery_type()
    assert "mandate_opportunities" in candidate.service_ports, (
        f"service_ports must include 'mandate_opportunities'; got {candidate.service_ports}"
    )


def test_mandate_discovery_type_target_defaults_to_series_a_saas_revops() -> None:
    """Done-when: the default target.segment is the team's first ICP — Series A SaaS RevOps leaders."""
    candidate = build_mandate_discovery_type()
    target = candidate.charter.target
    assert target.get("segment"), "MandateDiscovery's target.segment must be set"
    assert "Series A SaaS RevOps" in str(target.get("segment", "")), (
        f"default target.segment should be the team's first ICP; got {target.get('segment')!r}"
    )


def test_mandate_discovery_constraints_are_read_only() -> None:
    """Done-when: constraints declare the read-only invariants the charter enforces."""
    candidate = build_mandate_discovery_type()
    constraint_text = " ".join(c.lower() for c in candidate.charter.constraints)
    assert "read-only" in constraint_text, "constraints must declare the read-only rule"
    assert "no outreach" in constraint_text or "no posting" in constraint_text, (
        "constraints must declare the no-outreach / no-posting rule"
    )
    assert "4 distinct community sources" in constraint_text, (
        "constraints must declare the >=4 distinct community sources rule"
    )


def test_mandate_discovery_rubric_includes_quality_dimensions() -> None:
    """Done-when: the rubric has 4 quality dimensions (actionable, evidence, moat, channels)."""
    candidate = build_mandate_discovery_type()
    rubrics = candidate.verification.rubrics
    assert rubrics, "mandate-discovery must carry at least one rubric"
    rubric = rubrics[0]
    assert rubric.pass_threshold >= 0.5, f"rubric pass_threshold too low: {rubric.pass_threshold}"
    criterion_ids = {c.id for c in rubric.criteria}
    expected_criteria = {
        "portfolio_is_actionable",
        "pain_signals_have_evidence",
        "moat_assessment_is_realistic",
        "buyer_channels_are_reachable",
    }
    assert expected_criteria.issubset(criterion_ids), (
        f"missing rubric criteria: {expected_criteria - criterion_ids}"
    )
