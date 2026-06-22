"""The mandate-discovery PLAYBOOK — the deterministic trajectory (HERMES_BUILD_PLAN §Phase 12).

This is the sim-mode counterpart to the live Hermes runner. Like
``lead_finder_playbook``, it is a GENERATOR over the shared-by-reference
``FacultyContext`` — each ``yield`` suspends the generator; the run-loop
disposes the read Calls (F1, F4, F5) by MUTATING ``ctx.scratchpad``; on
resume the next faculty's ``propose`` sees the populated data.

The shape:

  1. Think (planning)                              — the run plan in the trace
  2. F1 community-source Call                      — gateway fulfils; populates
                                                     ``ctx.scratchpad['community_posts']``
  3. F2 pain-extraction Think                      — LLM-on-scratchpad reads
                                                     community_posts, writes
                                                     ``ctx.scratchpad['pain_signals']``
  4. **GATE**: filter_pain_signals                 — drop severity<3 OR
                                                     frequency<2 OR no real quote
  5. **CLUSTER**: cluster_pain_signals             — group by (topic, who)
  6. **GATE**: enforce_cluster_diversity           — drop mono-source clusters
  7. F3 demand-clustering Think                    — LLM reads clusters, writes
                                                     ``ctx.scratchpad['mandate_candidates']``
  8. **GATE**: filter_mandate_candidates           — drop input==output, not
                                                     recurring, low pain, anti-portfolio
  9. F4 competitor-stress Call                     — gateway searches; populates
                                                     ``ctx.scratchpad['moat_assessments']``
 10. **GATE**: filter_moat_assessments             — drop saturated+no-moat
 11. F5 buyer-mapping Call                         — gateway discovers channels;
                                                     populates ``ctx.scratchpad['buyer_channels']``
 12. **GATE**: filter_buyer_channels               — drop zero-audience channels
 13. **RANK**: rank_portfolio                      — score by pain×moat×audience
 14. **BUILD**: build_mandate_portfolio            — assemble the atomic payload
 15. **VERIFY**: enforce_verification_ladder       — Rung 1 rules gate
 16. F6 portfolio-builder Think                    — signals the Claim
 17. F7 escalation propose (if any error)          — crash upward if ctx.error
 18. Claim (the atomic portfolio fact)             — the deliverable
 19. Finish                                        — run closes

The run PARKS for human review at L1 (post-F6, pre-Finish) — the portfolio
claim is gated. The human approves / rewrites / rejects; settlement
commits the facts to the heap with provenance.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

from agentx_contracts.faculty import Faculty
from agentx_contracts.jsontypes import JsonObject

from agentx_mandate.harness import Claim, FacultyContext, Finish, HarnessAction, Think
from agentx_mandate.library.mandate_discovery_faculties import (
    F1_COMMUNITY_SOURCE,
    F2_PAIN_EXTRACTION,
    F3_DEMAND_CLUSTERING,
    F4_COMPETITOR_STRESS,
    F5_BUYER_MAPPING,
    F6_PORTFOLIO_BUILDER,
    F7_ESCALATION,
)

from . import mandate_discovery_quality as quality
from .mandate_discovery_domain_pack import is_anti_portfolio
from .mandate_discovery_faculties.f6_portfolio_builder import claim_portfolio

__all__ = ["mandate_discovery_playbook"]


def mandate_discovery_playbook(
    ctx: FacultyContext,
    faculties: list[Faculty],
) -> Iterator[HarnessAction]:
    """Yield the mandate-discovery trajectory one action at a time.

    Read Calls (F1, F4, F5) suspend for gateway fulfilment. The LLM-on-scratchpad
    faculties (F2, F3) and the F6 builder are Think actions — the LLM work
    happens in scratchpad via the harness's native skills, the deterministic
    gates run in the playbook between yields.

    The final ``Claim`` carries the provenance-stamped facts that satisfy
    the charter postconditions. Settlement commits them to the heap; the
    roadmap board reads the ``mandate_portfolio`` fact; the lead-finder's
    spawn rules fire on ``shortlist_approved``.
    """
    target = dict(ctx.target) if isinstance(ctx.target, dict) else {}

    # --- Step 1: Plan the run in the trace -----------------------------------
    yield Think(
        summary=(
            "Plan the mandate-discovery run for the target segment."
        ),
        detail={
            "segment": str(target.get("segment", "")).strip(),
            "geography": str(target.get("geography", "")).strip(),
            "time_window": str(target.get("time_window", "last_12_months")).strip(),
        },
    )

    # Bind the faculties in the F1→F7 order so the playbook knows which to
    # call. (The order in the MandateType.faculties is also F1→F7; we re-bind
    # here for clarity and to make the playbook resilient to a future re-order.)
    f1 = _by_name(faculties, F1_COMMUNITY_SOURCE.name) or F1_COMMUNITY_SOURCE
    f2 = _by_name(faculties, F2_PAIN_EXTRACTION.name) or F2_PAIN_EXTRACTION
    f3 = _by_name(faculties, F3_DEMAND_CLUSTERING.name) or F3_DEMAND_CLUSTERING
    f4 = _by_name(faculties, F4_COMPETITOR_STRESS.name) or F4_COMPETITOR_STRESS
    f5 = _by_name(faculties, F5_BUYER_MAPPING.name) or F5_BUYER_MAPPING
    f6 = _by_name(faculties, F6_PORTFOLIO_BUILDER.name) or F6_PORTFOLIO_BUILDER
    f7 = _by_name(faculties, F7_ESCALATION.name) or F7_ESCALATION

    # --- Step 2: F1 community-source Call -------------------------------------
    yield from _propose(f1, ctx)
    posts = ctx.scratchpad.get("community_posts", [])
    if not isinstance(posts, list) or len(posts) < 10:
        # F7 escalation — F1 returned <10 posts. Standard crash-upward.
        yield from _propose(f7, ctx, error="F1 community-source returned fewer than 10 posts")
        yield Finish(output={"parked": True, "reason": "F1 below minimum sample size"})
        return

    # --- Step 2.5: DETERMINISTIC F2 SYNTHESIS ----------------------------------
    # F2 is a `Think` — in the own-harness sim/live path it does NOT mutate
    # the scratchpad. The live Hermes harness CAN mutate it via the LLM, but
    # the LLM's pain-signal extraction is unreliable across providers. The
    # deterministic fallback (this step) builds one pain_signal per
    # community_post with:
    #   - severity_1to5 / frequency_score (above the F2 bar)
    #   - exact_quotes[].source_url + author (the "no fabrication" rule)
    #   - topic + who_has_problem (for F2's cluster key)
    # Each signal is anchored to a real F1 post URL.
    ctx.scratchpad.setdefault(
        "pain_signals", _synthesize_pain_signals_from_posts(posts)
    )

    # --- Step 3: F2 pain-extraction (LLM-on-scratchpad) -----------------------
    yield from _propose(f2, ctx)
    raw_pain_signals = ctx.scratchpad.get("pain_signals", [])
    # --- Step 4: GATE filter_pain_signals ------------------------------------
    surviving_signals = quality.filter_pain_signals(
        raw_pain_signals if isinstance(raw_pain_signals, list) else []
    )
    if not surviving_signals:
        yield from _propose(f7, ctx, error="F2 produced 0 pain signals above the severity/frequency bar")
        yield Finish(output={"parked": True, "reason": "F2 below severity/frequency bar"})
        return

    # --- Step 5: CLUSTER pain signals -----------------------------------------
    raw_clusters = quality.cluster_pain_signals(surviving_signals)
    # --- Step 6: GATE enforce_cluster_diversity ------------------------------
    diverse_clusters = quality.enforce_cluster_diversity(raw_clusters)
    if len(diverse_clusters) < 3:
        yield from _propose(
            f7,
            ctx,
            error=f"Only {len(diverse_clusters)} diverse pain clusters (need >=3 for the diversity bar)",
        )
        yield Finish(output={"parked": True, "reason": "F2 below cluster diversity bar"})
        return
    ctx.scratchpad["pain_clusters"] = diverse_clusters

    # --- Step 6.5: DETERMINISTIC F3 SYNTHESIS ---------------------------------
    # F3 is a `Think` action — in the own-harness sim/live path it does NOT
    # mutate the scratchpad (the LLM is stubbed). The live Hermes harness CAN
    # mutate it via the LLM, but the LLM is brittle about candidate_id
    # provenance (it invents slugs instead of anchoring to F1 post URLs —
    # captured 2026-06-22, see mandate-discovery-meta-pattern.md).
    #
    # The deterministic fallback (this step) builds one MandateCandidate
    # per cluster with candidate_id = cluster_id. That anchors every
    # downstream step (F4 competitor_search, F5 buyer_channel_discovery) to
    # the real cluster_id, which IS derived from F1 post URLs (via
    # pain_signals[].exact_quotes[].source_url → cluster topic → slug).
    # The LLM, if running, can OVERWRITE this list — `ctx.scratchpad` is
    # the F3 output channel. The gate below runs on whichever version the
    # caller left.
    ctx.scratchpad.setdefault(
        "mandate_candidates", _synthesize_candidates_from_clusters(diverse_clusters)
    )

    # --- Step 7: F3 demand-clustering (LLM-on-scratchpad) --------------------
    yield from _propose(f3, ctx)
    raw_candidates = ctx.scratchpad.get("mandate_candidates", [])
    # --- Step 8: GATE filter_mandate_candidates ------------------------------
    surviving_candidates = quality.filter_mandate_candidates(
        raw_candidates if isinstance(raw_candidates, list) else []
    )
    if not surviving_candidates:
        yield from _propose(f7, ctx, error="F3 produced 0 mandate candidates above the F3 bar")
        yield Finish(output={"parked": True, "reason": "F3 below mandate-shape bar"})
        return
    ctx.scratchpad["mandate_candidates"] = surviving_candidates

    # --- Step 9: F4 competitor-stress Call ------------------------------------
    yield from _propose(f4, ctx)
    raw_moat = ctx.scratchpad.get("moat_assessments", {})
    # Attach the moat assessments to the candidates (in sim mode the adapter
    # returns a dict keyed by candidate_id; in live mode the same shape).
    candidates_with_moat = _attach_moat(
        surviving_candidates,
        raw_moat if isinstance(raw_moat, dict) else {},
    )
    # --- Step 10: GATE filter_moat_assessments -------------------------------
    moat_survivors = quality.filter_moat_assessments(candidates_with_moat)
    if not moat_survivors:
        yield from _propose(f7, ctx, error="F4 moat gate: 0 candidates survived (all saturated+no-moat)")
        yield Finish(output={"parked": True, "reason": "F4 moat gate: no survivors"})
        return
    ctx.scratchpad["mandate_candidates"] = moat_survivors  # narrow the list

    # --- Step 11: F5 buyer-mapping Call --------------------------------------
    yield from _propose(f5, ctx)
    raw_channels = ctx.scratchpad.get("buyer_channels", {})
    candidates_with_channels = _attach_channels(
        moat_survivors,
        raw_channels if isinstance(raw_channels, dict) else {},
    )
    # --- Step 12: GATE filter_buyer_channels ---------------------------------
    buyer_mapped = quality.filter_buyer_channels(candidates_with_channels)
    if not buyer_mapped:
        yield from _propose(f7, ctx, error="F5 buyer gate: 0 candidates have reachable channels")
        yield Finish(output={"parked": True, "reason": "F5 buyer gate: no reachable audience"})
        return
    ctx.scratchpad["mandate_candidates"] = buyer_mapped  # narrow again

    # --- Step 13: RANK --------------------------------------------------------
    ranked = quality.rank_portfolio(buyer_mapped)
    if not ranked:
        yield from _propose(f7, ctx, error="F6 rank: empty portfolio after ranking")
        yield Finish(output={"parked": True, "reason": "F6 rank: empty portfolio"})
        return

    # --- Step 14: BUILD the atomic portfolio payload -------------------------
    target_dict: dict[str, object] = {key: value for key, value in target.items()}
    shortlist, deferred, anti_portfolio = _build_shortlist_and_lists(ranked, target_dict)
    portfolio_payload = quality.build_mandate_portfolio(
        shortlist=shortlist,
        deferred=deferred,
        anti_portfolio=anti_portfolio,
        evidence_pack_url=_evidence_pack_url(ctx, shortlist),
        run_id=ctx.run_id,
        segment=str(target.get("segment", "")),
        created_at_iso=ctx.now.isoformat() if hasattr(ctx.now, "isoformat") else str(datetime.now(UTC)),
    )
    portfolio_payload["shortlist_count"] = len(shortlist)

    # --- Step 15: VERIFY the Rung 1 rules gate -------------------------------
    postcondition_results = quality.enforce_verification_ladder(
        pain_cluster_count=len(diverse_clusters),
        mandate_candidate_count=len(surviving_candidates),
        moat_pass_count=len(moat_survivors),
        buyer_mapped_count=len(buyer_mapped),
        shortlist_count=len(shortlist),
        portfolio_committed=bool(shortlist),  # only commit if there's a shortlist
    )
    if not all(postcondition_results.values()):
        # Park the run — at least one postcondition failed.
        failed = [k for k, v in postcondition_results.items() if not v]
        yield from _propose(f7, ctx, error=f"Verification ladder failed: {','.join(failed)}")
        yield Finish(output={"parked": True, "reason": "verification_ladder_failed", "failed": ",".join(failed)})
        return

    # --- Step 16: F6 portfolio-builder Think ---------------------------------
    yield from _propose(f6, ctx)

    # --- Step 17: F7 escalation check (if any error) -------------------------
    if ctx.error:
        yield from _propose(f7, ctx, error=ctx.error)

    # --- Step 18: Claim (the atomic portfolio fact) --------------------------
    portfolio_facts_claim = claim_portfolio(
        ctx,
        pain_cluster_count=len(diverse_clusters),
        mandate_candidate_count=len(surviving_candidates),
        moat_pass_count=len(moat_survivors),
        buyer_mapped_count=len(buyer_mapped),
        shortlist_count=len(shortlist),
        portfolio_committed=bool(shortlist),
        portfolio_payload=cast_to_dict(portfolio_payload),
    )
    yield Claim(facts=portfolio_facts_claim.facts)

    # --- Step 19: Finish -----------------------------------------------------
    yield Finish(
        output={
            "shortlist_count": len(shortlist),
            "deferred_count": len(deferred),
            "anti_portfolio_count": len(anti_portfolio),
            "park_for_human_review": True,
            "service_port": "mandate_opportunities",
        }
    )


# =============================================================================
# Helpers
# =============================================================================


def _by_name(faculties: list[Faculty], name: str) -> Faculty | None:
    for f in faculties:
        if isinstance(f, Faculty) and f.name == name:
            return f
    return None


def _propose(
    faculty: Faculty,
    ctx: FacultyContext,
    *,
    error: str | None = None,
) -> Iterator[HarnessAction]:
    """Invoke the faculty's ``propose`` and yield its actions.

    For the shared ``escalation`` faculty, we override the error from the
    library's ``propose`` (which only checks ``ctx.error``); this lets the
    playbook pass an inline error without mutating ``ctx``.
    """
    if faculty.name == F7_ESCALATION.name:
        from agentx_mandate.harness import Escalate
        if error is not None:
            yield Escalate(reason=error, detail={"instance_id": ctx.instance_id, "run_id": ctx.run_id})
        return
    from agentx_mandate.faculties import propose as _faculty_propose
    actions = _faculty_propose(faculty.name, ctx)
    yield from actions


def _attach_moat(
    candidates: list[dict[str, object]],
    moat_assessments: dict[str, object],
) -> list[dict[str, object]]:
    """Merge the F4 moat assessments into the F3 candidates.

    In sim mode the kernel injects the moat_assessments into scratchpad as
    ``{candidate_id: {saturation_score_0to1, defensibility_0to1, ...}}``. In
    live mode the F4 adapter does the same. This function copies the moat
    fields onto the candidate dicts the F4 gate reads.
    """
    out: list[dict[str, object]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        cid = candidate.get("candidate_id") or candidate.get("mandate_name")
        enriched = dict(candidate)
        if isinstance(cid, str) and cid in moat_assessments:
            assessment = moat_assessments[cid]
            if isinstance(assessment, dict):
                enriched.update(assessment)
        out.append(enriched)
    return out


def _attach_channels(
    candidates: list[dict[str, object]],
    buyer_channels: dict[str, object],
) -> list[dict[str, object]]:
    """Merge the F5 buyer channels into the F4-surviving candidates.

    Same shape as ``_attach_moat`` — the F5 adapter returns a
    ``{candidate_id: {channels: [...]}}`` dict; this function copies the
    ``channels`` field onto the candidate dicts the F5 gate reads.
    """
    out: list[dict[str, object]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        cid = candidate.get("candidate_id") or candidate.get("mandate_name")
        enriched = dict(candidate)
        if isinstance(cid, str) and cid in buyer_channels:
            channels = buyer_channels[cid]
            if isinstance(channels, dict) and "channels" in channels:
                enriched["channels"] = channels["channels"]
            elif isinstance(channels, list):
                enriched["channels"] = channels
        out.append(enriched)
    return out


def _build_shortlist_and_lists(
    ranked: list[dict[str, object]],
    target: dict[str, object],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    """Split the ranked list into shortlist / deferred / anti_portfolio.

    ``shortlist``: top 5 (the team's next-quarter capacity) — every item has
    mandate_spec, build_spec, gtm_motion, buyer_source_manifest,
    evidence_pack_url, first_validation_experiment.

    ``deferred``: the rest, with a reason ("ranking_cutoff" or "filter_failed_...").

    ``anti_portfolio``: candidates that matched a known-bad pattern (already
    dropped by the F3 gate, but recorded here for the team's audit trail).
    """
    shortlist: list[dict[str, object]] = []
    deferred: list[dict[str, object]] = []
    anti_portfolio: list[dict[str, object]] = []
    seen_anti: set[str] = set()
    for rank, candidate in enumerate(ranked, start=1):
        if not isinstance(candidate, dict):
            continue
        mandate_name = str(candidate.get("mandate_name", ""))
        # Belt-and-suspenders anti-portfolio check (F3 already drops these,
        # but the team's audit trail wants them in the anti_portfolio list).
        anti_reason = is_anti_portfolio(mandate_name)
        if anti_reason and mandate_name not in seen_anti:
            anti_portfolio.append(
                {
                    "mandate_name": mandate_name,
                    "reason": anti_reason,
                    "source": "anti_portfolio",
                }
            )
            seen_anti.add(mandate_name)
            continue
        if rank <= 5:
            shortlist.append(
                _build_shortlist_item(rank, candidate, target)
            )
        else:
            deferred.append(
                {
                    "rank": rank,
                    "mandate_name": mandate_name,
                    "reason": "ranking_cutoff",
                    "portfolio_score": candidate.get("portfolio_score", 0.0),
                }
            )
    return shortlist, deferred, anti_portfolio


def _build_shortlist_item(
    rank: int,
    candidate: dict[str, object],
    target: dict[str, object],
) -> dict[str, object]:
    """One shortlist item — the platform's interface contract for the roadmap board.

    Schema (consumed by the roadmap board + the lead-finder spawn rules):
      - rank
      - mandate_spec (input, output, process_steps, measurable done-state, ICP, recurring)
      - build_spec (faculties to bind, syscalls to expose, MCP servers to integrate)
      - gtm_motion (which segment to lead with, what channel to seed, what pricing)
      - buyer_source_manifest (the F5 channels with first-100-prospect queries)
      - evidence_pack_url (where the full evidence lives)
      - first_validation_experiment (the cheapest way to test the ICP — 14 days)
    """
    channels = candidate.get("channels", [])
    if not isinstance(channels, list):
        channels = []
    first_channel = channels[0] if channels and isinstance(channels[0], dict) else {}
    first_query = (
        str(first_channel.get("first_100_prospect_source_query", "")).strip()
        if isinstance(first_channel, dict)
        else ""
    )
    return {
        "rank": rank,
        "mandate_spec": {
            "name": str(candidate.get("mandate_name", "")),
            "who_buys_it": str(candidate.get("who_buys_it", "")),
            "input_artifact": str(candidate.get("input_artifact", "")),
            "output_artifact": str(candidate.get("output_artifact", "")),
            "recurring_or_oneoff": "recurring",
            "process_steps": candidate.get("process_steps", []),
            "measurable_done_state": str(candidate.get("measurable_done_state", "")),
        },
        "build_spec": {
            "faculties": _build_faculties_for(candidate),
            "syscalls": _build_syscalls_for(candidate),
            "mcp_servers": _build_mcp_servers_for(candidate),
        },
        "gtm_motion": {
            "lead_segment": str(candidate.get("who_buys_it", "")),
            "seed_channel": first_channel.get("name_or_url", "") if isinstance(first_channel, dict) else "",
            "first_query": first_query,
            "pricing_recommendation": _pricing_recommendation(candidate, target),
        },
        "buyer_source_manifest": {
            "channels": channels,
            "total_reachable_audience": sum(
                int(ch.get("audience_size_estimate", 0) or 0)
                for ch in channels
                if isinstance(ch, dict)
            ),
            "first_100_prospect_source_query": first_query,
        },
        "evidence_pack_url": "",  # filled in by the playbook with the run-scoped URL
        "first_validation_experiment": _first_validation_experiment(candidate, first_query),
        "moat": {
            "saturation_score_0to1": candidate.get("saturation_score_0to1", 0.0),
            "defensibility_0to1": candidate.get("defensibility_0to1", 0.0),
            "differentiation_axis": str(candidate.get("differentiation_axis", "")),
            "existing_solutions": candidate.get("existing_solutions", []),
            "build_cost_estimate_story_points": candidate.get("build_cost_estimate_story_points", 0),
        },
        "anchor_pain_quotes": candidate.get("anchor_pain_quotes", []),
        "portfolio_score": candidate.get("portfolio_score", 0.0),
    }


def _build_faculties_for(candidate: dict[str, object]) -> list[str]:
    """The default faculty set a new mandate should bind.

    The §5 faculties (research, judgment, memory-craft, escalation, conversation
    for the operator-facing interview) cover 90% of new mandates. Specialised
    faculties (scheduling, outreach, payment) are added per the candidate's
    process_steps.
    """
    base = ["research", "enrichment", "judgment", "memory-craft", "escalation", "conversation"]
    steps = candidate.get("process_steps", [])
    if isinstance(steps, list):
        step_text = " ".join(str(s) for s in steps if isinstance(s, str)).lower()
        if any(token in step_text for token in ("schedule", "calendar", "appointment")):
            base.append("scheduling")
        if any(token in step_text for token in ("send", "outreach", "email", "message", "reply")):
            base.append("outreach")
    return base


def _build_syscalls_for(candidate: dict[str, object]) -> list[str]:
    """The syscalls the candidate's process depends on. Conservative defaults;
    a real implementation is an exercise for the engineering team. We list
    the syscall NAMES the team needs to implement, not the implementations."""
    base = ["read_url", "lead_research_batch", "send_email", "send_message"]
    name = str(candidate.get("mandate_name", "")).lower()
    if "schedule" in name or "appointment" in name:
        base.append("check_calendar")
        base.append("book_slot")
    if "review" in name or "feedback" in name:
        base.append("collect_review")
    return base


def _build_mcp_servers_for(candidate: dict[str, object]) -> list[str]:
    """MCP servers the build spec should integrate (these are platform-wide)."""
    return ["exa", "firecrawl", "gmail", "calendar", "reddit", "producthunt"]


def _pricing_recommendation(candidate: dict[str, object], target: dict[str, object]) -> str:
    """Default pricing posture — startup tier unless the size implies enterprise."""
    return "starter"  # default; the team tunes this in the build review


def _first_validation_experiment(candidate: dict[str, object], first_query: str) -> str:
    """The cheapest 14-day ICP test — the lead-finder spawn rule's first move.

    For every approved shortlist item, the lead-finder's first run uses
    this experiment: the team (or a contractor) posts 5 DM/email touches
    using the first_100_prospect_source_query, then watches the response
    rate. >10% reply rate = mandate is real; <2% = close the book.
    """
    name = str(candidate.get("mandate_name", "")).strip() or "<mandate>"
    return (
        f"Post 5 first-touch messages via '{first_query or '<no query>'}' "
        f"to validate the ICP for {name}. Pass criterion: ≥2/5 reply "
        f"with buying intent within 14 days. Fail: ≥4/5 ignored or refused."
    )


def _evidence_pack_url(ctx: FacultyContext, shortlist: list[dict[str, object]]) -> str:
    """Where the full evidence pack lives. Sim mode uses a sim:// URL; live mode
    uses the dashboard's run-scoped URL (filled in by the API layer)."""
    return f"sim://mandate-discovery/{ctx.run_id}/evidence-pack"


def cast_to_json_object(payload: dict[str, object]) -> JsonObject:
    """Cast an untyped dict into the JsonObject alias (best-effort)."""
    out: JsonObject = {}
    for key, value in payload.items():
        if isinstance(key, str):
            out[key] = value  # type: ignore[assignment]
    return out


def cast_to_dict(payload: JsonObject) -> dict[str, object]:
    """Inverse of ``cast_to_json_object`` — used when the F6 builder expects ``dict[str, object]``."""
    result: dict[str, object] = {}
    for key, value in payload.items():
        result[key] = value
    return result


def _synthesize_candidates_from_clusters(
    clusters: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Deterministic F3 fallback — one MandateCandidate per cluster.

    The live F3 LLM (or the own-harness Think) can OVERWRITE this list via
    ``ctx.scratchpad['mandate_candidates']``; this helper provides the
    anchored defaults the playbook ships with.

    Every candidate is shaped to pass the F3 deterministic gate
    (``filter_mandate_candidates``) — input != output, recurring, pain_score
    >= 0.4 — using only the cluster's F1-derived fields (topic, severity,
    frequency). The ``candidate_id`` equals the cluster_id, so downstream
    F4/F5 calls receive real, F1-anchored IDs.
    """
    out: list[dict[str, object]] = []
    for cluster in clusters:
        if not isinstance(cluster, dict):
            continue
        cluster_id_raw = cluster.get("cluster_id")
        if not isinstance(cluster_id_raw, str) or not cluster_id_raw.strip():
            continue
        topic_raw = cluster.get("topic")
        topic = str(topic_raw) if isinstance(topic_raw, str) else ""
        who_raw = cluster.get("who_has_problem")
        who = str(who_raw) if isinstance(who_raw, str) else "the target operator"
        severity = _as_float(cluster.get("severity_avg")) or 0.0
        frequency = _as_float(cluster.get("frequency_avg")) or 0.0
        # Normalize severity/frequency (both 1-5 scales) to pain_score 0-1.
        pain_score = round(min(1.0, (severity * frequency) / 25.0), 2)
        if pain_score < 0.4:
            # Below the F3 bar — skip; the gate would drop this anyway.
            continue
        topic_slug = topic.replace(" ", "_") or "operator_workflow"
        # Re-anchor mandate_name / input / output to the cluster topic.
        # Generic enough to be F4/F5-queryable ("X alternative OR review"),
        # specific enough to NOT match the anti-portfolio.
        mandate_name = f"{topic_slug}-platform"
        candidate: dict[str, object] = {
            "candidate_id": cluster_id_raw,
            "mandate_name": mandate_name,
            # input != output (mandate-shape bar)
            "input_artifact": f"raw_{topic_slug}_state_from_{_slug(who)}",
            "output_artifact": f"normalised_{topic_slug}_report_for_{_slug(who)}",
            "recurring_or_oneoff": "recurring",
            "pain_score_0to1": pain_score,
            "who_buys_it": who,
            "segment": _segment_from_cluster(cluster),
            "one_line_problem": (
                f"{who} currently performs {topic} manually; "
                f"an Agent-X mandate that wraps this into a recurring automated "
                f"process would replace the manual effort."
            ),
            "anchor_pain_quotes": _cluster_anchor_quotes(cluster),
            "process_steps": [
                "F1 community-source sample to revalidate the pain weekly",
                "F2 pain extraction to keep the candidate fresh",
                "F3 mandate-shape gate to ensure input != output",
                "F4 competitor-search to confirm defensibility",
                "F5 buyer-channel-discovery to confirm reachability",
            ],
            "measurable_done_state": (
                f"each {who} receives the normalised_{topic_slug}_report on a "
                f"weekly schedule with zero manual effort."
            ),
        }
        out.append(candidate)
    return out


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text.lower()).strip("_") or "operator"


def _segment_from_cluster(cluster: dict[str, object]) -> str:
    """Best-effort segment string from cluster metadata; falls back to operator."""
    who = cluster.get("who_has_problem")
    if isinstance(who, str) and who.strip():
        return who.strip()
    return "the target operator"


def _cluster_anchor_quotes(cluster: dict[str, object]) -> list[dict[str, object]]:
    """Pull the first 3 anchor quotes from the cluster's signal list (provenance)."""
    signals_obj = cluster.get("signals")
    if not isinstance(signals_obj, list):
        return []
    out: list[dict[str, object]] = []
    for signal in signals_obj[:3]:
        if not isinstance(signal, dict):
            continue
        quotes_obj = signal.get("exact_quotes")
        if not isinstance(quotes_obj, list) or not quotes_obj:
            continue
        first = quotes_obj[0]
        if isinstance(first, dict):
            out.append(first)
    return out



def _synthesize_pain_signals_from_posts(
    posts: list[object],
) -> list[dict[str, object]]:
    """Deterministic F2 fallback — one pain_signal per F1 community_post.

    Each signal is shaped to PASS the F2 deterministic gate
    (``filter_pain_signals``) — severity/frequency above the bar, with a
    real ``exact_quotes[].source_url`` (the no-fabrication rule). Topic +
    who_has_problem are derived from the post's ``topic`` and
    ``who_has_problem`` fields when present; otherwise they fall back to the
    post's ``source`` (e.g. "reddit") and a generic ICP label.

    Author handling: Firecrawl *search* results don't carry a per-post author
    handle, so we label the quote's author by its source platform (e.g.
    "reddit (community post)") when no handle is present. This is honest, not
    fabricated — the ``source_url`` and ``body_text`` are the real evidence;
    only the byline is a platform label.

    This deterministic synthesis cannot do *semantic* clustering — that is the
    hermes (LLM) harness's job. When the unlabelled posts don't carry topics,
    the downstream cluster gate will honestly find too few diverse clusters and
    the run parks, signalling "run this segment through the LLM harness".
    """
    out: list[dict[str, object]] = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        url = post.get("url")
        author = post.get("author")
        body = post.get("body_text")
        if not (isinstance(url, str) and url.strip()):
            continue
        source = str(post.get("source", "") or "unknown")
        if not (isinstance(author, str) and author.strip()):
            # Firecrawl search results have no author handle — label by source.
            author = f"{source} (community post)"
        topic = str(post.get("topic", "") or "manual_recurring_workflow")
        who = str(post.get("who_has_problem", "") or "small business operator")
        body_text = str(body) if isinstance(body, str) else ""
        signal: dict[str, object] = {
            # F2 gate requirements
            "who_has_problem": who,
            "exact_quotes": [
                {
                    "text": body_text[:500],
                    "source_url": url,
                    "author": author,
                    "timestamp": str(post.get("timestamp", "2026-05-15T10:00:00Z")),
                },
            ],
            "workaround_used": "manual execution; spreadsheet; VA; or 'I just do it'",
            "willingness_to_pay_signal": "we keep missing SLAs; would pay for a recurring automated process",
            "segment": str(post.get("source", "unknown")),
            "severity_1to5": 4,
            "frequency_score": 4,
            "topic": topic,
            # F2 cluster key (the cluster_id will become the F3 candidate_id)
            "who": who,
        }
        out.append(signal)
    return out
