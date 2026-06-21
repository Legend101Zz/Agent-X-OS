"""MANDATE-DISCOVERY v0.1.0 — discovers, validates, and prioritises mandate opportunities.

The mandate portfolio problem (HERMES_BUILD_PLAN §Phase 12 — next mandate the team builds):

  - The team has a fixed R&D budget.
  - The team can only build N mandates per quarter.
  - Which N maximises the chance of *some* customer paying?

This mandate is META to the platform: its output is the list of *candidate MandateTypes* the
team should build next, complete with the build spec (faculties + syscalls + MCP) and a
buyer-source manifest (exact channels where the first 100 prospects can be reached).

It is READ-ONLY: it never posts, comments, DMs, or engages in communities. We listen, we don't
talk. The hypothesis it validates is: "if we built this mandate, could we find 100 buyers
in 14 days?". The answer feeds the lead-finder's spawn rules (on_condition:
shortlist_approved).

The 7 faculties (F1–F7) are wired into the playbook as a deterministic trajectory. Each
faculty is realised as a function in ``mandate_discovery_faculties/``; this file only
defines the MandateType spec the kernel registers.

See ``docs/MANDATE_DISCOVERY_CHARTER.md`` (added alongside this code) for the full charter.
"""

from __future__ import annotations

from agentx_contracts.faculty import FacultyBinding
from agentx_contracts.mandate import (
    Charter,
    Condition,
    DomainPackRef,
    ExecutionProfile,
    MandateType,
    SettlementRules,
    SpawnRule,
    VerificationSuite,
)
from agentx_contracts.verification import Rubric, RubricCriterion


def build_mandate_discovery_type() -> MandateType:
    """The MandateDiscovery MandateType — emits the next-mandate portfolio claim.

    Charter postconditions (rules rung) — the verifier can check these mechanically against
    the facts the playbook claims:

      - pain_clusters >= 3        — the diversity bar (no mono-source mandates).
      - mandate_candidates >= 1   — at least one mandate-shaped opportunity surfaced.
      - moat_pass_count >= 1      — at least one candidate survived the saturation+defensibility
                                    gate (the "real opportunity" bar).
      - buyer_source_manifest     — every shortlist item has a concrete first-100-prospect
                                    channel (the "go-to-market bar").
      - mandate_portfolio         — the single atomic Fact commits the portfolio to the heap
                                    (the deliverable bar — what the platform actually consumes).

    Constraints (read-only) encode the mandate's hard rules: no outreach, no posting, no DMs,
    no vendor pitches in the input. Violations cause the run to escalate, not to commit.

    Settlement: fact_commit_confidence=0.6 (probation — the reality rung promotes or retires
    the portfolio facts based on whether the lead-finder's first-100-prospect outreach
    actually finds buyers). watch_window_hours=336 (14 days — the same window as the
    Rung 4 reality watch on the spec). spawn_rules auto-spawn a lead-finder per
    approved shortlist item — that's the bridge from "we have a mandate idea" to
    "we're testing the ICP".
    """
    return MandateType(
        id="type_mandate_discovery_v0",
        name="mandate-discovery",
        version="0.1.0",
        charter=Charter(
            goal=(
                "Continuously discover, validate, and prioritise mandate opportunities for "
                "Agent-X: business processes that should become the next MandateTypes the "
                "platform can sell. For each opportunity, produce a complete build spec "
                "(faculties + syscalls + MCP) and a buyer-source manifest (exact channels "
                "where the first 100 prospects can be reached)."
            ),
            preconditions=[
                Condition(
                    id="target_segment_specified",
                    description=(
                        "The run target must name a segment (e.g. 'Series A SaaS RevOps "
                        "leaders in the US') — without it the F1 community-source faculty "
                        "would sample the entire internet, which violates the 80–300 post "
                        "cost cap."
                    ),
                    rung="rules",
                    expr="fact:target_segment_specified exists",
                ),
            ],
            pathconditions=[
                Condition(
                    id="read_only_invariance",
                    description=(
                        "The mandate MUST NOT propose, draft, or execute any outbound "
                        "communication. Any faculty that returns a Call with risk_class "
                        "in {external_message, money, irreversible} escalates the run; "
                        "we listen, never talk."
                    ),
                    rung="rules",
                    expr="fact:read_only_invariance_holds exists",
                ),
            ],
            postconditions=[
                Condition(
                    id="pain_clusters_at_least_three",
                    description=(
                        "At least 3 distinct pain clusters surfaced, each backed by 2+ "
                        "distinct community sources — the diversity bar (no mono-source "
                        "mandates)."
                    ),
                    rung="rules",
                    expr="fact:pain_cluster_count exists",
                ),
                Condition(
                    id="mandate_candidates_at_least_one",
                    description=(
                        "At least 1 mandate-shaped candidate survived the F3 deterministic "
                        "gate (process + ICP + done-state, non-trivial, recurring)."
                    ),
                    rung="rules",
                    expr="fact:mandate_candidate_count exists",
                ),
                Condition(
                    id="moat_pass_count_at_least_one",
                    description=(
                        "At least 1 candidate passed the F4 moat bar "
                        "(saturation<0.7 AND defensibility>=0.3 — the saturated+no-moat "
                        "trap is the most common way mandates die)."
                    ),
                    rung="rules",
                    expr="fact:moat_pass_count exists",
                ),
                Condition(
                    id="buyer_source_manifest_present",
                    description=(
                        "Every shortlist item has a concrete buyer channel with a "
                        "first-100-prospect source query — the 'go-to-market bar' "
                        "(no candidate in the shortlist without a reachable channel)."
                    ),
                    rung="rules",
                    expr="fact:buyer_source_manifest exists",
                ),
                Condition(
                    id="mandate_portfolio_committed",
                    description=(
                        "One atomic `mandate_portfolio` fact was claimed to the heap with "
                        "full provenance — the platform-consumable deliverable (this is "
                        "what the roadmap board and lead-finder spawn rules actually read)."
                    ),
                    rung="rules",
                    expr="fact:mandate_portfolio exists",
                ),
            ],
            constraints=[
                "READ-ONLY research only: no outreach, no posting, no DMs",
                "Every pain signal must cite at least one source URL with author + timestamp",
                "No vendor pitches in the input (filter: SaaS-founder-self-promo, AI-thought-leadership, posts older than 12 months unless structural-shift)",  # noqa: E501
                "At least 4 distinct community sources must be sampled (single-source mandates are biased)",
                "At L1 the run PARKS for human review of the portfolio — no auto-commit",
            ],
            target={
                "segment": "Series A SaaS RevOps leaders in the US",
                "geography": "United States",
                "time_window": "last_12_months",
                "seed_mandates": ["lead-finder@0.1.0"],
                "max_pain_clusters": 12,
                "min_sources_per_cluster": 2,
            },
        ),
        faculties=[
            # F1 — community-source (read): samples Reddit/HN/X/Discord/forums/ProductHunt/G2/IndieHackers
            FacultyBinding(faculty_name="mandate_discovery_community_source"),
            # F2 — pain-extraction (read, LLM-on-scratchpad): proposes pain signals
            FacultyBinding(faculty_name="mandate_discovery_pain_extraction"),
            # F3 — demand-clustering (read, LLM-on-scratchpad): turns pain clusters into MandateCandidates
            FacultyBinding(faculty_name="mandate_discovery_demand_clustering"),
            # F4 — competitor-stress-test (read): existing solutions + moat assessment
            FacultyBinding(faculty_name="mandate_discovery_competitor_stress"),
            # F5 — buyer-mapping (read): locates where buyers congregate
            FacultyBinding(faculty_name="mandate_discovery_buyer_mapping"),
            # F6 — mandate-portfolio-builder (write, gated Claim): emits the atomic portfolio fact
            FacultyBinding(faculty_name="mandate_discovery_portfolio_builder"),
            # F7 — escalation: standard crash-upward faculty (shared with all mandates)
            FacultyBinding(faculty_name="escalation"),
        ],
        domain_pack=DomainPackRef(name="mandate-discovery", version="0.1.0"),
        verification=VerificationSuite(
            ladder=["rules", "judge", "human", "reality"],
            rules=[],
            rubrics=[
                Rubric(
                    name="mandate_discovery_quality",
                    pass_threshold=0.6,
                    criteria=[
                        RubricCriterion(
                            id="portfolio_is_actionable",
                            description=(
                                "Each shortlist item names a concrete ICP, a process with "
                                "measurable done-state, AND a first-100-prospect channel — "
                                "the user can act on it within 30 minutes."
                            ),
                            weight=0.4,
                        ),
                        RubricCriterion(
                            id="pain_signals_have_evidence",
                            description=(
                                "Each pain cluster cites >=2 distinct community sources with "
                                "author + timestamp; no mono-source mandates."
                            ),
                            weight=0.2,
                        ),
                        RubricCriterion(
                            id="moat_assessment_is_realistic",
                            description=(
                                "Each shortlist item's defensibility score is justified by "
                                "named adjacent tools and their weaknesses — not just a "
                                "self-claimed moat."
                            ),
                            weight=0.2,
                        ),
                        RubricCriterion(
                            id="buyer_channels_are_reachable",
                            description=(
                                "Each buyer channel has a non-zero audience_size_estimate "
                                "AND a first-100-prospect source query that could plausibly "
                                "return real posts in <30 minutes of searching."
                            ),
                            weight=0.2,
                        ),
                    ],
                ),
            ],
        ),
        settlement=SettlementRules(
            fact_commit_confidence=0.6,
            trust_on_success=1,
            trust_on_failure=-1,
            watch_window_hours=336,  # 14 days — the Rung 4 reality-watch window
            spawn_rules=[
                # On shortlist_approved (Rung 3 human approve), spawn a lead-finder per
                # shortlist item — that's the bridge from "validated mandate idea" to
                # "first-100-prospect test" (closing the loop).
                SpawnRule(
                    on_condition="shortlist_approved",
                    child_type_ref="lead-finder@0.1.0",
                    params={"mandate_shortlist_id": "{portfolio_id}"},
                    inherit_authority=False,
                ),
            ],
        ),
        gym_ref="gym:mandate-discovery",
        execution=ExecutionProfile(routing=[]),  # default routing; the live harness picks per-faculty
        service_ports=["mandate_opportunities"],
    )
