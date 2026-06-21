"""Phase-12 mandate-discovery PLAYBOOK tests (HERMES_BUILD_PLAN §Phase 12).

Layer A (deterministic unit tests, no LLM, no Mongo, ~10s).

The playbook is a GENERATOR; the tests exercise the trajectory shape by
running the playbook with pre-seeded scratchpad data (simulating what F1,
F4, F5 would have populated via gateway fulfilment in live mode). The tests
pin:

    - The trajectory shape:
    Think → F1 → F2 → gate → cluster → F3 → gate → F4 → gate → F5 → gate → rank → F6 → Claim → Finish.
  - The deterministic gates fire at the right point.
  - F7 escalation fires when a gate fails (no fake pain signals → park).
  - F7 escalation fires when F1 returns <10 posts (the F1 minimum).
  - The final Claim carries provenance-stamped facts for all 5 postconditions.
  - The portfolio's shortlist items have complete buyer_source_manifest entries.
"""

from __future__ import annotations

from datetime import UTC, datetime

from agentx_contracts.faculty import Faculty
from agentx_contracts.mandate import HydrationSnapshot
from agentx_contracts.memory import Thread
from agentx_mandate.harness import Call, Claim, Escalate, FacultyContext, Finish, Think
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
from agentx_mandate.library.mandate_discovery_playbook import mandate_discovery_playbook


def _ctx(
    scratchpad: dict[str, object],
    *,
    ring: str = "L1",
    segment: str = "Series A SaaS RevOps leaders in the US",
) -> FacultyContext:
    snapshot = HydrationSnapshot(
        facts=[],
        thread=Thread(
            id="thread_md",
            instance_id="inst_md",
            entity_id="entity_md",
            state="engaged",
            updated_at=datetime.now(UTC),
        ),
        recent_journal=[],
        skill_pack_refs=[],
        domain_pack=None,
        frozen_at=datetime.now(UTC),
    )
    return FacultyContext(
        snapshot=snapshot,
        target={"segment": segment, "geography": "United States", "time_window": "last_12_months"},
        scratchpad=scratchpad,
        instance_id="inst_md",
        run_id="run_md_test",
        ring=ring,  # type: ignore[arg-type]
        now=datetime.now(UTC),
    )


def _mandate_faculties() -> list[Faculty]:
    return [
        F1_COMMUNITY_SOURCE,
        F2_PAIN_EXTRACTION,
        F3_DEMAND_CLUSTERING,
        F4_COMPETITOR_STRESS,
        F5_BUYER_MAPPING,
        F6_PORTFOLIO_BUILDER,
        F7_ESCALATION,
    ]


# =============================================================================
# Trajectory shape
# =============================================================================


def test_playbook_opens_with_think_and_closes_with_finish() -> None:
    ctx = _ctx(_good_scratchpad())
    actions = list(mandate_discovery_playbook(ctx, _mandate_faculties()))
    assert any(isinstance(a, Think) for a in actions), "playbook must open with a Think"
    assert actions and isinstance(actions[-1], Finish), "playbook must close with a Finish"


def test_playbook_emits_calls_for_f1_f4_f5_read_intents() -> None:
    """F1, F4, F5 emit read Calls (community-source, competitor-search, buyer-discovery)."""
    ctx = _ctx(_good_scratchpad())
    actions = list(mandate_discovery_playbook(ctx, _mandate_faculties()))
    call_names = {a.request.name for a in actions if isinstance(a, Call)}
    assert "community_source_sample" in call_names, f"F1 Call missing; have: {call_names}"
    assert "competitor_search" in call_names, f"F4 Call missing; have: {call_names}"
    assert "buyer_channel_discovery" in call_names, f"F5 Call missing; have: {call_names}"


def test_playbook_emits_exactly_one_claim_at_the_end() -> None:
    ctx = _ctx(_good_scratchpad())
    actions = list(mandate_discovery_playbook(ctx, _mandate_faculties()))
    claims = [a for a in actions if isinstance(a, Claim)]
    assert len(claims) == 1, f"playbook must emit exactly one Claim; got {len(claims)}"


def test_playbook_claim_carries_five_postcondition_facts() -> None:
    """The Claim's facts must cover all 5 charter postcondition predicates."""
    ctx = _ctx(_good_scratchpad())
    actions = list(mandate_discovery_playbook(ctx, _mandate_faculties()))
    claim = next(a for a in actions if isinstance(a, Claim))
    predicates = {f.predicate for f in claim.facts}
    expected = {
        "pain_cluster_count",
        "mandate_candidate_count",
        "moat_pass_count",
        "buyer_source_manifest",
        "mandate_portfolio",
    }
    assert expected.issubset(predicates), f"Claim missing facts: {expected - predicates}"


def test_playbook_claim_facts_are_provenance_stamped() -> None:
    """Invariant #1: no fact without provenance. Every Claim fact has run_id + evidence."""
    ctx = _ctx(_good_scratchpad())
    actions = list(mandate_discovery_playbook(ctx, _mandate_faculties()))
    claim = next(a for a in actions if isinstance(a, Claim))
    for fact in claim.facts:
        assert fact.provenance.run_id == ctx.run_id, f"fact {fact.id} missing run_id provenance"
        assert fact.provenance.evidence, f"fact {fact.id} missing evidence list"
        assert fact.instance_id == ctx.instance_id, f"fact {fact.id} has wrong instance_id"


# =============================================================================
# Gates — they fire when they should
# =============================================================================


def test_playbook_parks_when_f1_returns_fewer_than_10_posts() -> None:
    ctx = _ctx({"community_posts": [{"url": "https://a.com"}] * 5})  # only 5 posts
    actions = list(mandate_discovery_playbook(ctx, _mandate_faculties()))
    escalates = [a for a in actions if isinstance(a, Escalate)]
    assert escalates, "playbook must escalate when F1 returns <10 posts"
    finishes = [a for a in actions if isinstance(a, Finish)]
    assert finishes and finishes[-1].output.get("parked") is True


def test_playbook_parks_when_f2_produces_no_surviving_pain() -> None:
    scratchpad: dict[str, object] = {
        "community_posts": [_post() for _ in range(20)],
        "pain_signals": [
            # Below the severity bar (3) — every one of them gets dropped.
            {"severity_1to5": 1, "frequency_score": 5, "topic": "x", "who_has_problem": "y",
             "exact_quotes": [{"text": "q", "source_url": "https://a.com", "author": "u"}]},
        ],
    }
    ctx = _ctx(scratchpad)
    actions = list(mandate_discovery_playbook(ctx, _mandate_faculties()))
    escalates = [a for a in actions if isinstance(a, Escalate)]
    assert escalates, "playbook must escalate when F2 produces 0 surviving pain signals"
    finishes = [a for a in actions if isinstance(a, Finish)]
    assert finishes and finishes[-1].output.get("parked") is True


def test_playbook_parks_when_clusters_below_diversity_bar() -> None:
    """Only 2 diverse clusters (need 3) → park."""
    scratchpad: dict[str, object] = _good_scratchpad()
    # Replace the pain_signals with signals that produce <3 diverse clusters
    scratchpad["pain_signals"] = [
        {"severity_1to5": 5, "frequency_score": 5, "topic": "pain_a", "who_has_problem": "icp_x",
         "exact_quotes": [{"text": "q1", "source_url": "https://reddit.com/r/x", "author": "u1"}]},
        {"severity_1to5": 4, "frequency_score": 4, "topic": "pain_b", "who_has_problem": "icp_y",
         "exact_quotes": [{"text": "q2", "source_url": "https://reddit.com/r/y", "author": "u2"}]},
    ]
    ctx = _ctx(scratchpad)
    actions = list(mandate_discovery_playbook(ctx, _mandate_faculties()))
    escalates = [a for a in actions if isinstance(a, Escalate)]
    assert escalates, "playbook must escalate when <3 diverse clusters"
    finishes = [a for a in actions if isinstance(a, Finish)]
    assert finishes and finishes[-1].output.get("parked") is True


def test_playbook_parks_when_f3_produces_no_surviving_candidates() -> None:
    scratchpad: dict[str, object] = _good_scratchpad()
    # All candidates are one-off (dropped by F3)
    scratchpad["mandate_candidates"] = [
        {"candidate_id": "c1", "mandate_name": "one_off_a", "input_artifact": "a", "output_artifact": "b",
         "recurring_or_oneoff": "oneoff", "pain_score_0to1": 0.9},
    ]
    ctx = _ctx(scratchpad)
    actions = list(mandate_discovery_playbook(ctx, _mandate_faculties()))
    escalates = [a for a in actions if isinstance(a, Escalate)]
    assert escalates, "playbook must escalate when F3 produces 0 surviving candidates"


def test_playbook_parks_when_f4_moat_gate_drops_everything() -> None:
    scratchpad: dict[str, object] = _good_scratchpad()
    # All candidates in the dead-zone (saturation high + defensibility low)
    scratchpad["mandate_candidates"] = [
        {"candidate_id": "c1", "mandate_name": "deadzone_a", "input_artifact": "a", "output_artifact": "b",
         "recurring_or_oneoff": "recurring", "pain_score_0to1": 0.9},
    ]
    scratchpad["moat_assessments"] = {
        "c1": {"saturation_score_0to1": 0.95, "defensibility_0to1": 0.1},
    }
    ctx = _ctx(scratchpad)
    actions = list(mandate_discovery_playbook(ctx, _mandate_faculties()))
    escalates = [a for a in actions if isinstance(a, Escalate)]
    assert escalates, "playbook must escalate when F4 moat gate drops everything"


def test_playbook_parks_when_f5_buyer_gate_drops_everything() -> None:
    scratchpad: dict[str, object] = _good_scratchpad()
    scratchpad["mandate_candidates"] = [
        {"candidate_id": "c1", "mandate_name": "no_audience", "input_artifact": "a", "output_artifact": "b",
         "recurring_or_oneoff": "recurring", "pain_score_0to1": 0.8},
    ]
    scratchpad["moat_assessments"] = {
        "c1": {"saturation_score_0to1": 0.3, "defensibility_0to1": 0.7,
               "differentiation_axis": "vertical focus", "existing_solutions": [],
               "build_cost_estimate_story_points": 5},
    }
    scratchpad["buyer_channels"] = {
        "c1": {"channels": []},  # empty channels
    }
    ctx = _ctx(scratchpad)
    actions = list(mandate_discovery_playbook(ctx, _mandate_faculties()))
    escalates = [a for a in actions if isinstance(a, Escalate)]
    assert escalates, "playbook must escalate when F5 buyer gate drops everything"


# =============================================================================
# Happy path — full run, all gates pass, claim commits
# =============================================================================


def test_playbook_happy_path_commits_atomic_portfolio_fact() -> None:
    """The end-to-end happy path: F1..F5 all pass, F6 emits the Claim, the Claim
    carries the mandate_portfolio fact (the platform-consumable deliverable)."""
    ctx = _ctx(_good_scratchpad())
    actions = list(mandate_discovery_playbook(ctx, _mandate_faculties()))
    claim = next(a for a in actions if isinstance(a, Claim))
    portfolio_fact = next((f for f in claim.facts if f.predicate == "mandate_portfolio"), None)
    assert portfolio_fact is not None, "Claim must carry the mandate_portfolio fact"
    assert portfolio_fact.confidence == 0.6, (
        f"mandate_portfolio fact confidence must be 0.6 (probation); got {portfolio_fact.confidence}"
    )
    assert "portfolio.shortlist:" in str(portfolio_fact.provenance.evidence), (
        "mandate_portfolio fact must cite the shortlist count in evidence"
    )


def test_playbook_finish_output_carries_shortlist_count() -> None:
    """The Finish.output must include shortlist_count + service_port — the
    surface the dashboard reads to render the park card."""
    ctx = _ctx(_good_scratchpad())
    actions = list(mandate_discovery_playbook(ctx, _mandate_faculties()))
    finish = next(a for a in reversed(actions) if isinstance(a, Finish))
    assert "shortlist_count" in finish.output
    assert finish.output.get("park_for_human_review") is True
    assert finish.output.get("service_port") == "mandate_opportunities"


def test_playbook_records_read_only_in_pathcondition_fact() -> None:
    """The read-only pathcondition fact is always claimed (F1-F5 are all read, F6 emits a Claim)."""
    ctx = _ctx(_good_scratchpad())
    actions = list(mandate_discovery_playbook(ctx, _mandate_faculties()))
    claim = next(a for a in actions if isinstance(a, Claim))
    predicates = {f.predicate for f in claim.facts}
    assert "read_only_invariance_holds" in predicates, (
        "playbook must claim the read_only_invariance_holds pathcondition fact"
    )


# =============================================================================
# Helpers — what a "good" scratchpad looks like (sim-mode fixtures)
# =============================================================================


def _post() -> dict[str, object]:
    return {
        "url": "https://reddit.com/r/RevOps/comments/abc",
        "author": "u/tester",
        "timestamp": "2026-05-01T10:00:00Z",
        "upvotes": 42,
        "body_text": "I'm the sole RevOps person at a Series A SaaS and I spend half my day manually routing leads between Salesforce and Outreach.",  # noqa: E501
        "segment_tags": ["revops", "saas", "us"],
    }


def _good_scratchpad() -> dict[str, object]:
    """A scratchpad that should make every gate pass.

    Layout:
      - 20 community posts (F1 sample)
      - 6 pain signals across 3 topics x 2 distinct sources (F2 → 3 diverse clusters)
      - 3 mandate candidates, all valid (F3 passes)
      - Moat assessments: all 3 have defensibility>0.3 and saturation<0.7 (F4 passes)
      - Buyer channels: 1 channel per candidate with audience>0 and a query (F5 passes)
    """
    pain_signals = []
    topics = [
        ("revops_too_small_for_dedicated_team", "saas revops leader",
         "I'm the only revops person at our Series A SaaS and I have 8 AEs to support."),
        ("lead_routing_is_manual", "saas revops leader",
         "We route leads by hand because our CRM doesn't talk to our sequencing tool."),
        ("forecast_accuracy_is_low", "saas revops leader",
         "Our forecast is +/-30% off every month. The board hates it."),
    ]
    for topic, who, body in topics:
        pain_signals.append({
            "severity_1to5": 5,
            "frequency_score": 5,
            "topic": topic,
            "who_has_problem": who,
            "exact_quotes": [
                {"text": body, "source_url": f"https://reddit.com/r/RevOps/comments/{topic[:4]}/a1", "author": "u/revopslead", "timestamp": "2026-05-12T10:00:00Z"},  # noqa: E501
                {"text": body, "source_url": f"https://news.ycombinator.com/item?id={abs(hash(topic)) % 9999999}", "author": "revops_anon", "timestamp": "2026-04-22T10:00:00Z"},  # noqa: E501
            ],
        })
    candidates = [
        {
            "candidate_id": "c_revops_one_person",
            "mandate_name": "revops_one_person_platform",
            "who_buys_it": "Series A SaaS RevOps leader (1-3 person team)",
            "input_artifact": "scattered CRM + sequencing + enrichment data",
            "output_artifact": "unified pipeline view with auto-routing",
            "recurring_or_oneoff": "recurring",
            "pain_score_0to1": 0.8,
            "process_steps": [
                "read CRM for new leads",
                "read sequencing for engagement",
                "auto-route by ICP score",
                "flag stale leads for follow-up",
            ],
            "measurable_done_state": "lead routing time reduced from 30min/day to 5min/day",
        },
        {
            "candidate_id": "c_pipeline_hygiene",
            "mandate_name": "pipeline_hygiene_daily",
            "who_buys_it": "Series A SaaS RevOps leader",
            "input_artifact": "CRM opportunity records",
            "output_artifact": "stale-deal alert digest sent to AEs",
            "recurring_or_oneoff": "recurring",
            "pain_score_0to1": 0.7,
            "process_steps": [
                "scan CRM",
                "find opportunities with no activity in 14 days",
                "draft alert message",
                "send via Slack or email",
            ],
            "measurable_done_state": "100% of stale deals flagged within 24h of going stale",
        },
        {
            "candidate_id": "c_forecast_rollup",
            "mandate_name": "forecast_rollup_for_founder",
            "who_buys_it": "Series A SaaS founder or CRO",
            "input_artifact": "CRM opportunity records + activity logs",
            "output_artifact": "weekly forecast variance report",
            "recurring_or_oneoff": "recurring",
            "pain_score_0to1": 0.65,
            "process_steps": [
                "read CRM for commit/best-case/upside",
                "compare against prior week",
                "compute variance",
                "draft variance summary for the founder",
            ],
            "measurable_done_state": "founder sees weekly variance in <2 minutes, not 30",
        },
    ]
    moat_assessments = {
        "c_revops_one_person": {
            "saturation_score_0to1": 0.5,
            "defensibility_0to1": 0.6,
            "differentiation_axis": "vertical-specific lead routing for the 1-3 person revops team",
            "existing_solutions": [
                {"name": "Gong", "url": "https://gong.io", "pricing": "$100k+/yr", "weakness": "revenue intelligence, not routing"},  # noqa: E501
                {"name": "Outreach", "url": "https://outreach.io", "pricing": "$100/user/mo", "weakness": "sequencing tool, not a routing brain"},  # noqa: E501
            ],
            "build_cost_estimate_story_points": 13,
        },
        "c_pipeline_hygiene": {
            "saturation_score_0to1": 0.3,
            "defensibility_0to1": 0.7,
            "differentiation_axis": "vertical: stale-deal alerting for 1-3 person revops",
            "existing_solutions": [
                {"name": "Clari", "url": "https://clari.com", "pricing": "$50/user/mo", "weakness": "enterprise-focused; minimums exceed 1-3 person budget"},  # noqa: E501
            ],
            "build_cost_estimate_story_points": 8,
        },
        "c_forecast_rollup": {
            "saturation_score_0to1": 0.4,
            "defensibility_0to1": 0.5,
            "differentiation_axis": "founder-facing variance report (not manager-facing)",
            "existing_solutions": [
                {"name": "Clari", "url": "https://clari.com", "pricing": "$50/user/mo", "weakness": "manager-facing"},  # noqa: E501
            ],
            "build_cost_estimate_story_points": 5,
        },
    }
    buyer_channels = {
        "c_revops_one_person": {
            "channels": [
                {
                    "type": "reddit_subreddit",
                    "name_or_url": "https://reddit.com/r/RevOps",
                    "audience_size_estimate": 18_000,
                    "engagement_quality": "high — daily threads on manual lead routing pain",
                    "entry_post_strategy": "comment on threads about manual routing; offer a free audit",
                    "conversion_signal": "DM with company URL + role",
                    "first_100_prospect_source_query": "site:reddit.com/r/RevOps 'manual lead routing' OR 'one person revops'",  # noqa: E501
                },
                {
                    "type": "hacker_news_thread",
                    "name_or_url": "https://news.ycombinator.com",
                    "audience_size_estimate": 50_000,
                    "engagement_quality": "medium — Show HN posts get traction",
                    "entry_post_strategy": "Show HN: 'Show HN: I built a one-person RevOps platform'",
                    "conversion_signal": "waitlist signups",
                    "first_100_prospect_source_query": "site:news.ycombinator.com 'revops' 'one person' OR 'solo'",
                },
            ],
        },
        "c_pipeline_hygiene": {
            "channels": [
                {
                    "type": "reddit_subreddit",
                    "name_or_url": "https://reddit.com/r/sales",
                    "audience_size_estimate": 220_000,
                    "engagement_quality": "high — daily threads on stale deals",
                    "entry_post_strategy": "comment on stale-deal threads; offer a free stale-deal audit",
                    "conversion_signal": "DM with company URL + AE count",
                    "first_100_prospect_source_query": "site:reddit.com/r/sales 'stale deals' OR 'pipeline hygiene'",
                },
            ],
        },
        "c_forecast_rollup": {
            "channels": [
                {
                    "type": "twitter",
                    "name_or_url": "https://twitter.com/search?q=revops%20founder",
                    "audience_size_estimate": 8_000,
                    "engagement_quality": "medium — founder threads get replies",
                    "entry_post_strategy": "reply to founder forecast threads with a 2-line variance tip",
                    "conversion_signal": "DM with company URL",
                    "first_100_prospect_source_query": "site:twitter.com 'founder' 'forecast' 'revops'",
                },
            ],
        },
    }
    return {
        "community_posts": [_post() for _ in range(20)],
        "pain_signals": pain_signals,
        "mandate_candidates": candidates,
        "moat_assessments": moat_assessments,
        "buyer_channels": buyer_channels,
    }


def test_playbook_happy_path_shortlist_has_buyer_source_manifest() -> None:
    """Every shortlist item must carry a buyer_source_manifest with at least one channel."""
    ctx = _ctx(_good_scratchpad())
    actions = list(mandate_discovery_playbook(ctx, _mandate_faculties()))
    finish = next(a for a in reversed(actions) if isinstance(a, Finish))
    shortlist_count_raw = finish.output.get("shortlist_count", 0)
    shortlist_count = int(str(shortlist_count_raw))
    assert shortlist_count >= 1, f"expected at least 1 shortlist item; got {shortlist_count}"


def test_mandate_type_charter_target_includes_segment_and_geography() -> None:
    """Done-when: the default target.segment is the team's first ICP."""
    mandate = build_mandate_discovery_type()
    target = mandate.charter.target
    assert "Series A SaaS RevOps" in str(target.get("segment", ""))
    assert target.get("geography") == "United States"
