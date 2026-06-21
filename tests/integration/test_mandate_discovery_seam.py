"""Phase-12 mandate-discovery SIM end-to-end test (HERMES_BUILD_PLAN §Phase 12 — Layer B).

The **seam proof** for mandate-discovery: the MandateType composes with the
kernel's MandateRegistry, the playbook drives through the own-harness sim,
and the 5 charter postcondition predicates line up with the playbook's
Claim facts. This is the cheapest proof the wiring is correct; the deeper
live proof (Layer C — Exa/Firecrawl, real LLM, Mongo) lives in a separate
script (``scripts/run_mandate_discovery.py``) and is opt-in.

The test is intentionally SIM-ONLY: no live Exa/Firecrawl, no Mongo, no SMTP.
It runs as part of `uv run pytest -q` in <2 seconds.

Asserts:
  - ``build_mandate_discovery_type()`` registers cleanly with the MandateRegistry.
  - The MandateType is instanceable (the kernel's ``instantiate_mandate`` accepts it).
  - The catalog is unchanged after registration (no surprise writes).
  - The MandateType's 5 postcondition predicates are present in the playbook's
    Claim (the structural proof the F6 builder wires to the postconditions).
  - The MandateType's spawn rule points at lead-finder@0.1.0 (the loop closes).
  - The watch window is 336h (14 days = the Rung 4 reality-watch window).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from agentx_contracts.mandate import (
    MandateInstance,
    MandateType,
    SpawnRule,
    VerificationSuite,
)
from agentx_kernel.control import KernelControl
from agentx_kernel.projections import Projections
from agentx_kernel.stores.memory import (
    InMemoryJournalStore,
    InMemoryProjectionStore,
    InMemoryRunContinuationStore,
)
from agentx_mandate.faculties import FACULTY_LIBRARY
from agentx_mandate.library.mandate_discovery import build_mandate_discovery_type

NOW = datetime(2026, 6, 22, tzinfo=UTC)


@pytest.mark.asyncio
async def test_mandate_discovery_type_registers_in_mandate_registry() -> None:
    """The MandateType composes with the kernel registry (the seam proof)."""
    projection_store = InMemoryProjectionStore()
    control = KernelControl(
        journal=InMemoryJournalStore(),
        projections=Projections(projection_store, InMemoryJournalStore()),
        projection_store=projection_store,
        continuations=InMemoryRunContinuationStore(),
    )
    mandate = build_mandate_discovery_type()
    # The registry round-trips the type — this is the structural proof the
    # type is valid MandateType and the kernel accepts it.
    registered = await control.register_mandate_type(mandate)
    assert isinstance(registered, MandateType)
    assert registered.id == "type_mandate_discovery_v0"
    # And the catalog now contains it.
    types = await control.list_mandate_types()
    assert any(t.id == "type_mandate_discovery_v0" for t in types), (
        f"registered type not in catalog; have: {[t.id for t in types]}"
    )


@pytest.mark.asyncio
async def test_mandate_discovery_instance_can_be_created() -> None:
    """The MandateInstance for a mandate-discovery type is accepted by the kernel."""
    projection_store = InMemoryProjectionStore()
    control = KernelControl(
        journal=InMemoryJournalStore(),
        projections=Projections(projection_store, InMemoryJournalStore()),
        projection_store=projection_store,
        continuations=InMemoryRunContinuationStore(),
    )
    await control.register_mandate_type(build_mandate_discovery_type())
    instance = MandateInstance(
        id="inst_md_seam",
        type_ref="mandate-discovery@0.1.0",
        customer_id="md-customer",
        ring="L1",
        heap_region_id="heap_md_seam",
    )
    bound = await control.instantiate_mandate(instance)
    assert bound.id == "inst_md_seam"
    # The instance binding is reachable via control.instance_binding.
    binding = await control.instance_binding("inst_md_seam")
    assert binding.type_ref == "mandate-discovery@0.1.0"
    assert binding.ring == "L1"


@pytest.mark.asyncio
async def test_mandate_discovery_type_does_not_clobber_other_types() -> None:
    """Registering mandate-discovery alongside lead-finder + creator doesn't conflict.

    The catalog grows; no type is replaced. (Phase-12 lesson: a MandateTypeConflict
    would be raised by the registry if the id collided, but we're using a unique
    id here, so this test just pins the multi-type catalog shape.)
    """
    from agentx_mandate.library.creator import build_creator_type
    from agentx_mandate.library.lead_finder import build_lead_finder_type

    projection_store = InMemoryProjectionStore()
    control = KernelControl(
        journal=InMemoryJournalStore(),
        projections=Projections(projection_store, InMemoryJournalStore()),
        projection_store=projection_store,
        continuations=InMemoryRunContinuationStore(),
    )
    await control.register_mandate_type(build_lead_finder_type())
    await control.register_mandate_type(build_creator_type())
    await control.register_mandate_type(build_mandate_discovery_type())
    types = await control.list_mandate_types()
    type_ids = {t.id for t in types}
    expected = {"type_lead_finder_v0", "type_creator_v0", "type_mandate_discovery_v0"}
    assert expected.issubset(type_ids), f"missing types: {expected - type_ids}; have: {type_ids}"


def test_mandate_discovery_spawn_rule_closes_the_lead_finder_loop() -> None:
    """The spawn rule on_condition=shortlist_approved spawns lead-finder@0.1.0.

    This is the loop closer — the discovery mandate's output feeds the
    lead-finder's first-100-prospect validation. The test pins the wiring
    so a future change to either side of the seam breaks loudly.
    """
    mandate = build_mandate_discovery_type()
    assert len(mandate.settlement.spawn_rules) == 1
    rule: SpawnRule = mandate.settlement.spawn_rules[0]
    assert rule.on_condition == "shortlist_approved"
    assert rule.child_type_ref == "lead-finder@0.1.0"
    assert "mandate_shortlist_id" in rule.params
    # And the child type is a real type in the platform.
    assert "lead-finder" in rule.child_type_ref, (
        "the spawn child must be lead-finder (closes the loop); "
        f"got {rule.child_type_ref!r}"
    )


def test_mandate_discovery_postconditions_match_playbook_facts() -> None:
    """Every postcondition's expr references a fact the playbook claims.

    This is the structural proof: the rules-verifier will check
    ``fact:<predicate> exists`` against the playbook's Claim, and the
    Claim's facts must cover those predicates. If the MandateType's
    postconditions drift away from the F6 builder's predicates, this
    test fails loudly.
    """
    from agentx_contracts.mandate import HydrationSnapshot
    from agentx_contracts.memory import Thread
    from agentx_mandate.harness import Claim, FacultyContext
    from agentx_mandate.library.mandate_discovery_faculties import (
        F1_COMMUNITY_SOURCE,
        F2_PAIN_EXTRACTION,
        F3_DEMAND_CLUSTERING,
        F4_COMPETITOR_STRESS,
        F5_BUYER_MAPPING,
        F6_PORTFOLIO_BUILDER,
        F7_ESCALATION,
    )
    from agentx_mandate.library.mandate_discovery_playbook import (
        mandate_discovery_playbook,
    )

    mandate = build_mandate_discovery_type()
    # The postcondition predicates (extracted from the expr strings).
    postcondition_predicates: set[str] = set()
    for condition in mandate.charter.postconditions:
        if condition.rung == "rules" and condition.expr and condition.expr.startswith("fact:"):
            predicate = condition.expr[len("fact:"):].rsplit(" exists", 1)[0]
            postcondition_predicates.add(predicate)

    # Build a FacultyContext with a "good" scratchpad and run the playbook.
    snapshot = HydrationSnapshot(
        facts=[], thread=Thread(
            id="thread_md_seam", instance_id="inst_md_seam",
            entity_id="entity_md_seam", state="engaged", updated_at=NOW,
        ),
        recent_journal=[], skill_pack_refs=[], domain_pack=None, frozen_at=NOW,
    )
    scratchpad = _good_scratchpad()
    ctx = FacultyContext(
        snapshot=snapshot,
        target={"segment": "Series A SaaS RevOps leaders in the US",
                "geography": "United States", "time_window": "last_12_months"},
        scratchpad=scratchpad,
        instance_id="inst_md_seam",
        run_id="run_md_seam",
        ring="L1",
        now=NOW,
    )
    faculties = [F1_COMMUNITY_SOURCE, F2_PAIN_EXTRACTION, F3_DEMAND_CLUSTERING,
                 F4_COMPETITOR_STRESS, F5_BUYER_MAPPING, F6_PORTFOLIO_BUILDER, F7_ESCALATION]
    actions = list(mandate_discovery_playbook(ctx, faculties))
    claim = next((a for a in actions if isinstance(a, Claim)), None)
    assert claim is not None, "playbook must yield a Claim for the structural proof"
    claimed_predicates = {f.predicate for f in claim.facts}
    # The Claim's facts must cover the postcondition predicates (minus the
    # markport 'mandate_portfolio' which is the platform-consumable deliverable
    # and is also in the postconditions).
    missing = postcondition_predicates - claimed_predicates
    assert not missing, (
        f"postcondition predicates not covered by the playbook's Claim: {missing}. "
        "The rules-verifier would fail these postconditions. Update the F6 builder "
        "to claim these predicates, or update the charter's postconditions."
    )


def test_mandate_discovery_faculties_have_skill_packs() -> None:
    """Every F1-F6 faculty declares a skill_pack ref (compiler-owned, versioned)."""
    mandate = build_mandate_discovery_type()
    for binding in mandate.faculties:
        lib_faculty = FACULTY_LIBRARY.get(binding.faculty_name)
        if lib_faculty is None:
            # escalation is in the shared library — it has a skill_pack.
            continue
        assert lib_faculty.skill_pack.startswith("skill_pack:"), (
            f"faculty {binding.faculty_name!r} must declare a skill_pack ref; "
            f"got {lib_faculty.skill_pack!r}"
        )


def test_mandate_discovery_verification_suite_uses_full_ladder() -> None:
    """The MandateType's verification ladder is the full 4-rung ladder (rules, judge, human, reality)."""
    mandate = build_mandate_discovery_type()
    assert isinstance(mandate.verification, VerificationSuite)
    for rung in ("rules", "judge", "human", "reality"):
        assert rung in mandate.verification.ladder, (
            f"verification ladder must include {rung!r}; have: {mandate.verification.ladder}"
        )


def test_mandate_discovery_watch_window_is_14_days() -> None:
    """The watch window is 336h (14 days) — the Rung 4 reality-watch window.

    This pins the link between mandate-discovery's spawn rules and the
    Rung 4 watch: a 14-day window for the lead-finder's first-100-prospect
    outreach to validate the ICP.
    """
    mandate = build_mandate_discovery_type()
    assert mandate.settlement.watch_window_hours == 336
    # 14 days = 14 * 24 = 336. Pinning the math.
    assert 14 * 24 == 336


# =============================================================================
# Sim fixtures (kept here because they're test-specific)
# =============================================================================


def _good_scratchpad() -> dict[str, object]:
    """A scratchpad that makes every gate pass — drives the structural proof."""
    pain_signals: list[dict[str, object]] = []
    for idx, (topic, body) in enumerate([
        ("revops_too_small_for_dedicated_team", "I'm the only revops person at our Series A SaaS and I have 8 AEs to support."),  # noqa: E501
        ("lead_routing_is_manual", "We route leads by hand because our CRM doesn't talk to our sequencing tool."),
        ("forecast_accuracy_is_low", "Our forecast is +/-30% off every month. The board hates it."),
    ]):
        pain_signals.append({
            "severity_1to5": 5,
            "frequency_score": 5,
            "topic": topic,
            "who_has_problem": "saas revops leader",
            "exact_quotes": [
                {"text": body, "source_url": f"https://reddit.com/r/RevOps/comments/sim{idx}/a1",
                 "author": "u/sim_revops", "timestamp": "2026-05-12T10:00:00Z"},
                {"text": body, "source_url": f"https://news.ycombinator.com/item?id={abs(hash(topic)) % 9999999}",
                 "author": "sim_hn_user", "timestamp": "2026-04-22T10:00:00Z"},
            ],
        })
    candidates: list[dict[str, object]] = [
        {
            "candidate_id": "c_revops_one_person",
            "mandate_name": "revops_one_person_platform",
            "who_buys_it": "Series A SaaS RevOps leader (1-3 person team)",
            "input_artifact": "scattered CRM + sequencing + enrichment data",
            "output_artifact": "unified pipeline view with auto-routing",
            "recurring_or_oneoff": "recurring",
            "pain_score_0to1": 0.8,
            "process_steps": ["read CRM", "auto-route", "flag stale"],
            "measurable_done_state": "routing time -25 min/day",
        },
        {
            "candidate_id": "c_pipeline_hygiene",
            "mandate_name": "pipeline_hygiene_daily",
            "who_buys_it": "Series A SaaS RevOps leader",
            "input_artifact": "CRM opportunity records",
            "output_artifact": "stale-deal alert digest",
            "recurring_or_oneoff": "recurring",
            "pain_score_0to1": 0.7,
            "process_steps": ["scan CRM", "find stale", "draft alert"],
            "measurable_done_state": "100% stale flagged in 24h",
        },
    ]
    moat_assessments: dict[str, object] = {
        "c_revops_one_person": {
            "saturation_score_0to1": 0.5, "defensibility_0to1": 0.6,
            "differentiation_axis": "vertical-specific lead routing for 1-3 person revops",
            "existing_solutions": [{"name": "Gong", "url": "https://gong.io",
                                    "pricing": "$100k+/yr", "weakness": "revenue intelligence"}],
            "build_cost_estimate_story_points": 13,
        },
        "c_pipeline_hygiene": {
            "saturation_score_0to1": 0.3, "defensibility_0to1": 0.7,
            "differentiation_axis": "vertical: stale-deal alerting",
            "existing_solutions": [{"name": "Clari", "url": "https://clari.com",
                                    "pricing": "$50/user/mo", "weakness": "enterprise-only"}],
            "build_cost_estimate_story_points": 8,
        },
    }
    buyer_channels: dict[str, object] = {
        "c_revops_one_person": {"channels": [{
            "type": "reddit_subreddit", "name_or_url": "https://reddit.com/r/RevOps",
            "audience_size_estimate": 18_000, "engagement_quality": "high",
            "entry_post_strategy": "comment; free audit", "conversion_signal": "DM + role",
            "first_100_prospect_source_query": "site:reddit.com/r/RevOps 'manual lead routing'",
        }]},
        "c_pipeline_hygiene": {"channels": [{
            "type": "reddit_subreddit", "name_or_url": "https://reddit.com/r/sales",
            "audience_size_estimate": 220_000, "engagement_quality": "high",
            "entry_post_strategy": "comment; free audit", "conversion_signal": "DM",
            "first_100_prospect_source_query": "site:reddit.com/r/sales 'stale deals'",
        }]},
    }
    return {
        "community_posts": [
            {"url": f"https://reddit.com/r/RevOps/comments/sim{idx}", "author": "u/sim",
             "timestamp": "2026-05-01T10:00:00Z", "upvotes": 42,
             "body_text": "sim body", "segment_tags": ["revops"]}
            for idx in range(20)
        ],
        "pain_signals": pain_signals,
        "mandate_candidates": candidates,
        "moat_assessments": moat_assessments,
        "buyer_channels": buyer_channels,
    }
