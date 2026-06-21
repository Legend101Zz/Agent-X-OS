"""Phase-12 mandate-discovery QUALITY GATE tests (HERMES_BUILD_PLAN §Phase 12).

Layer A (deterministic unit tests, no LLM, no Mongo, ~10s).

These tests pin the four deterministic gates (F2 filter, F3 filter, F4 moat
filter, F5 buyer filter) + the anti-portfolio + the Rung 1 verification ladder.
They run the LLM-PROPOSES / DETERMINISTIC-DISPOSES invariant end-to-end without
spinning up an LLM — the tests inject fabricated proposals into the gate
functions and assert the gate outcomes.

If a future change tweaks a threshold (e.g. MOAT_SATURATION_MAX), the tests
that pin the threshold will fail loudly with a clear message. The team's
"this is the constitution" bar is enforced here.
"""

from __future__ import annotations

import pytest
from agentx_mandate.library import mandate_discovery_quality as q
from agentx_mandate.library.mandate_discovery_domain_pack import (
    ANTI_PORTFOLIO,
    COMPANY_SIZES,
    INDUSTRIES,
    ROLES,
    is_anti_portfolio,
    normalise_segment,
)

# =============================================================================
# F2 — pain filter
# =============================================================================


def test_pain_filter_drops_below_severity_bar() -> None:
    signals = [
        {"severity_1to5": 2, "frequency_score": 5, "exact_quotes": [
            {"text": "x", "source_url": "https://a.com", "author": "u"}
        ], "topic": "x", "who_has_problem": "y"},
    ]
    assert q.filter_pain_signals(signals) == []


def test_pain_filter_drops_below_frequency_bar() -> None:
    signals = [
        {"severity_1to5": 5, "frequency_score": 1, "exact_quotes": [
            {"text": "x", "source_url": "https://a.com", "author": "u"}
        ], "topic": "x", "who_has_problem": "y"},
    ]
    assert q.filter_pain_signals(signals) == []


def test_pain_filter_drops_quote_without_url() -> None:
    """The 'real author + URL' rule — no fake quotes."""
    signals = [
        {"severity_1to5": 5, "frequency_score": 5, "exact_quotes": [
            {"text": "x", "source_url": "", "author": "u"}
        ], "topic": "x", "who_has_problem": "y"},
    ]
    assert q.filter_pain_signals(signals) == []


def test_pain_filter_drops_quote_without_author() -> None:
    signals = [
        {"severity_1to5": 5, "frequency_score": 5, "exact_quotes": [
            {"text": "x", "source_url": "https://a.com", "author": ""}
        ], "topic": "x", "who_has_problem": "y"},
    ]
    assert q.filter_pain_signals(signals) == []


def test_pain_filter_keeps_above_both_bars_with_real_quote() -> None:
    signals = [
        {"severity_1to5": 4, "frequency_score": 4, "exact_quotes": [
            {"text": "real pain", "source_url": "https://reddit.com/r/x/comments/1", "author": "u/revopsguy", "timestamp": "2026-05-01"}  # noqa: E501
        ], "topic": "real_pain", "who_has_problem": "saas revops leader"},
    ]
    surviving = q.filter_pain_signals(signals)
    assert len(surviving) == 1


def test_pain_filter_drops_non_dict_inputs() -> None:
    """A non-dict signal (e.g. a string) doesn't crash the filter."""
    signals: list[object] = [{"severity_1to5": 4, "frequency_score": 4, "exact_quotes": [
        {"text": "x", "source_url": "https://a.com", "author": "u"}
    ], "topic": "x", "who_has_problem": "y"}, "not a dict", 42]
    surviving = q.filter_pain_signals(signals)  # type: ignore[arg-type]
    assert len(surviving) == 1


# =============================================================================
# F2 — clustering
# =============================================================================


def test_cluster_pain_signals_groups_by_topic_and_who() -> None:
    signals = [
        {"topic": "RevOps Too Small", "who_has_problem": "SaaS RevOps leader",
         "severity_1to5": 5, "frequency_score": 5,
         "exact_quotes": [{"text": "q1", "source_url": "https://reddit.com/r/x", "author": "u1"}]},
        {"topic": "revops_too_small", "who_has_problem": "saas revops leader",
         "severity_1to5": 4, "frequency_score": 4,
         "exact_quotes": [{"text": "q2", "source_url": "https://news.ycombinator.com/item?id=1", "author": "u2"}]},
        {"topic": "lead routing", "who_has_problem": "saas revops leader",
         "severity_1to5": 3, "frequency_score": 4,
         "exact_quotes": [{"text": "q3", "source_url": "https://x.com/u3/status/1", "author": "u3"}]},
    ]
    surviving = q.filter_pain_signals(signals)
    clusters = q.cluster_pain_signals(surviving)
    # Two clusters: (revops_too_small, saas revops leader) + (lead routing, saas revops leader)
    assert len(clusters) == 2
    # The bigger cluster is first (severity × frequency sort).
    assert clusters[0]["signals"][0]["topic"].lower() == clusters[0]["topic"].lower()


def test_enforce_cluster_diversity_drops_mono_source_clusters() -> None:
    """A cluster with only 1 distinct source is biased — the diversity bar drops it."""
    clusters = [
        # Cluster A: both quotes point to reddit.com — the source list is pre-deduped by
        # ``_build_cluster`` (a set), so this is the "1 distinct source" case.
        {"distinct_sources": ["reddit.com"], "topic": "t", "who_has_problem": "w"},
        # Cluster B: quotes from two different domains — the "2 distinct sources" case.
        {"distinct_sources": ["reddit.com", "news.ycombinator.com"], "topic": "t", "who_has_problem": "w"},
    ]
    surviving = q.enforce_cluster_diversity(clusters)
    assert len(surviving) == 1
    assert surviving[0]["distinct_sources"] == ["reddit.com", "news.ycombinator.com"]


def test_enforce_cluster_diversity_default_minimum_is_two() -> None:
    """Pin: the diversity bar's default is 2 (matches the charter's per-cluster rule)."""
    assert q.CLUSTER_MIN_DISTINCT_SOURCES == 2
    # A cluster with 2 distinct sources survives the default gate.
    clusters = [{"distinct_sources": ["a.com", "b.com"], "topic": "t", "who_has_problem": "w"}]
    assert len(q.enforce_cluster_diversity(clusters)) == 1
    # A cluster with 1 distinct source is dropped.
    clusters = [{"distinct_sources": ["a.com"], "topic": "t", "who_has_problem": "w"}]
    assert q.enforce_cluster_diversity(clusters) == []


def test_enforce_cluster_diversity_custom_minimum() -> None:
    """Callers can tighten the bar via min_distinct_sources — the per-run override."""
    clusters = [{"distinct_sources": ["a.com", "b.com"], "topic": "t", "who_has_problem": "w"}]
    # With min=3, the 2-source cluster is dropped.
    assert q.enforce_cluster_diversity(clusters, min_distinct_sources=3) == []


# =============================================================================
# F3 — mandate candidate filter
# =============================================================================


def test_candidate_filter_drops_input_equal_output() -> None:
    """input_artifact == output_artifact means transformation, not process."""
    candidates = [{
        "mandate_name": "transformation", "input_artifact": "same", "output_artifact": "same",
        "recurring_or_oneoff": "recurring", "pain_score_0to1": 0.8,
    }]
    assert q.filter_mandate_candidates(candidates) == []


def test_candidate_filter_drops_one_off() -> None:
    """One-off work is a feature, not a mandate."""
    candidates = [{
        "mandate_name": "oneoff", "input_artifact": "a", "output_artifact": "b",
        "recurring_or_oneoff": "oneoff", "pain_score_0to1": 0.8,
    }]
    assert q.filter_mandate_candidates(candidates) == []


def test_candidate_filter_drops_low_pain_score() -> None:
    candidates = [{
        "mandate_name": "low_pain", "input_artifact": "a", "output_artifact": "b",
        "recurring_or_oneoff": "recurring", "pain_score_0to1": 0.3,
    }]
    assert q.filter_mandate_candidates(candidates) == []


def test_candidate_filter_drops_anti_portfolio() -> None:
    """The 'general purpose AI' / 'ai email writer' etc. anti-portfolio entries are auto-dropped."""
    candidates = [{
        "mandate_name": "ai_email_writer_v2", "input_artifact": "lead", "output_artifact": "outreach",
        "recurring_or_oneoff": "recurring", "pain_score_0to1": 0.8,
    }]
    assert q.filter_mandate_candidates(candidates) == []


def test_candidate_filter_keeps_valid_candidate() -> None:
    candidates = [{
        "mandate_name": "revops_one_person_platform", "input_artifact": "disparate data",
        "output_artifact": "unified pipeline", "recurring_or_oneoff": "recurring",
        "pain_score_0to1": 0.8,
    }]
    surviving = q.filter_mandate_candidates(candidates)
    assert len(surviving) == 1


# =============================================================================
# F4 — moat filter
# =============================================================================


def test_moat_filter_drops_saturated_no_moat() -> None:
    """The dead-zone: saturation > 0.7 AND defensibility < 0.3 = no opportunity."""
    candidates = [{
        "mandate_name": "deadzone", "saturation_score_0to1": 0.9, "defensibility_0to1": 0.2,
    }]
    assert q.filter_moat_assessments(candidates) == []


def test_moat_filter_keeps_saturated_with_moat() -> None:
    """Saturated is OK if you have a real moat (vertical hook, proprietary data, etc.)."""
    candidates = [{
        "mandate_name": "vertical_ai_email", "saturation_score_0to1": 0.8, "defensibility_0to1": 0.6,
    }]
    assert len(q.filter_moat_assessments(candidates)) == 1


def test_moat_filter_keeps_unsaturated_no_moat() -> None:
    """Unsaturated is always OK — there's room."""
    candidates = [{
        "mandate_name": "fresh_market", "saturation_score_0to1": 0.3, "defensibility_0to1": 0.2,
    }]
    assert len(q.filter_moat_assessments(candidates)) == 1


# =============================================================================
# F5 — buyer channel filter
# =============================================================================


def test_buyer_filter_drops_no_channels() -> None:
    candidates = [{"mandate_name": "no_channels", "channels": []}]
    assert q.filter_buyer_channels(candidates) == []


def test_buyer_filter_drops_zero_audience() -> None:
    candidates = [{
        "mandate_name": "zero_audience", "channels": [
            {"audience_size_estimate": 0, "first_100_prospect_source_query": "q"},
        ],
    }]
    assert q.filter_buyer_channels(candidates) == []


def test_buyer_filter_drops_no_query() -> None:
    candidates = [{
        "mandate_name": "no_query", "channels": [
            {"audience_size_estimate": 5000, "first_100_prospect_source_query": ""},
        ],
    }]
    assert q.filter_buyer_channels(candidates) == []


def test_buyer_filter_keeps_valid_channels() -> None:
    candidates = [{
        "mandate_name": "valid", "channels": [
            {"audience_size_estimate": 5000, "first_100_prospect_source_query": "site:reddit.com/r/RevOps 'manual lead routing'"},  # noqa: E501
        ],
    }]
    assert len(q.filter_buyer_channels(candidates)) == 1


# =============================================================================
# F6 — portfolio ranking
# =============================================================================


def test_rank_portfolio_orders_by_score() -> None:
    candidates = [
        {"mandate_name": "low", "pain_score_0to1": 0.4, "defensibility_0to1": 0.3,
         "saturation_score_0to1": 0.5, "channels": [{"audience_size_estimate": 1000, "first_100_prospect_source_query": "q"}]},  # noqa: E501
        {"mandate_name": "high", "pain_score_0to1": 0.9, "defensibility_0to1": 0.8,
         "saturation_score_0to1": 0.2, "channels": [{"audience_size_estimate": 10000, "first_100_prospect_source_query": "q"}]},  # noqa: E501
    ]
    ranked = q.rank_portfolio(candidates)
    assert ranked[0]["mandate_name"] == "high"
    assert ranked[0]["portfolio_score"] > ranked[1]["portfolio_score"]


# =============================================================================
# Rung 1 — verification ladder
# =============================================================================


def test_verification_ladder_passes_full_run() -> None:
    results = q.enforce_verification_ladder(
        pain_cluster_count=5, mandate_candidate_count=3, moat_pass_count=2,
        buyer_mapped_count=2, shortlist_count=2, portfolio_committed=True,
    )
    assert all(results.values()), f"verification ladder failed: {results}"


def test_verification_ladder_fails_low_pain_clusters() -> None:
    results = q.enforce_verification_ladder(
        pain_cluster_count=2, mandate_candidate_count=3, moat_pass_count=2,
        buyer_mapped_count=2, shortlist_count=2, portfolio_committed=True,
    )
    assert not results["pain_clusters_at_least_three"]


def test_verification_ladder_fails_zero_moat() -> None:
    results = q.enforce_verification_ladder(
        pain_cluster_count=5, mandate_candidate_count=3, moat_pass_count=0,
        buyer_mapped_count=0, shortlist_count=0, portfolio_committed=False,
    )
    assert not results["moat_pass_count_at_least_one"]


# =============================================================================
# Domain pack — anti-portfolio + normalise
# =============================================================================


def test_anti_portfolio_recognises_known_bad_patterns() -> None:
    """The v0.1.0 anti-portfolio has 6 known-bad patterns; each must match fuzzy."""
    bad_names = [
        "general purpose ai agent",
        "universal inbox",
        "ai email writer for SMBs",
        "ai_meeting_summarizer",
        "personal ai assistant",
        "ai chatbot for website",
    ]
    for name in bad_names:
        assert is_anti_portfolio(name) is not None, f"anti-portfolio missed: {name!r}"


def test_anti_portfolio_does_not_match_clean_mandate() -> None:
    assert is_anti_portfolio("revops_one_person_platform") is None
    assert is_anti_portfolio("dental_appointment_intake") is None


def test_anti_portfolio_is_case_insensitive_and_punctuation_tolerant() -> None:
    assert is_anti_portfolio("AI Email Writer!") is not None
    assert is_anti_portfolio("GENERAL PURPOSE AI") is not None


def test_normalise_segment_known_segment() -> None:
    result = normalise_segment("US-based Series A SaaS RevOps leaders")
    assert result["industry_id"] == "b2b_saas"
    assert result["role_id"] == "revops_leader"
    assert result["geography"] == "United States"


def test_normalise_segment_indian_agency() -> None:
    result = normalise_segment("Indian SMB marketing agency founder")
    assert result["industry_id"] == "indian_smb_agencies"
    assert result["role_id"] == "agency_founder"
    assert result["geography"] == "India"


def test_normalise_segment_handles_garbage_input() -> None:
    """Non-string input or empty input returns the empty struct, no crash."""
    result = normalise_segment("")
    assert result == {"industry_id": "", "role_id": "", "size_id": "", "geography": ""}
    result = normalise_segment("totally unrelated query")
    assert isinstance(result, dict)


def test_domain_pack_vocabulary_is_non_empty() -> None:
    """Domain pack shouldn't ship empty — the playbook needs at least the Phase-12 baseline."""
    assert len(INDUSTRIES) >= 3
    assert len(ROLES) >= 3
    assert len(COMPANY_SIZES) >= 3
    assert len(ANTI_PORTFOLIO) >= 3


# =============================================================================
# Constants — pin the constitution
# =============================================================================


def test_constitution_thresholds_have_not_drifted() -> None:
    """The thresholds below are the mandate's constitution. Bumping them is a
    one-line change here + a test update + a CHANGELOG note. If these fail,
    someone has changed the constitution without re-pinning the tests.
    """
    assert q.PAIN_SEVERITY_MIN == 3
    assert q.PAIN_FREQUENCY_MIN == 2
    assert q.CLUSTER_MIN_DISTINCT_SOURCES == 2
    assert q.MANDATE_PAIN_SCORE_MIN == 0.4
    assert q.MOAT_SATURATION_MAX == 0.7
    assert q.MOAT_DEFENSIBILITY_MIN == 0.3
    assert q.PORTFOLIO_SHORTLIST_MIN == 0


if __name__ == "__main__":
    # Allow running as a smoke test: `python -m pytest test_mandate_discovery_quality.py`
    pytest.main([__file__, "-v"])
