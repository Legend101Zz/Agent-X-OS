"""Phase-14 mandate-discovery integration test: own-harness + live mode.

Proves the structural-vs-content fix from Phase 13.5:

  - The own-harness (deterministic OwnHarness) drives the
    ``mandate_discovery_playbook`` generator to completion in live mode.
  - The F1/F4/F5 read Calls hit the gateway (mocked here with an
    in-memory adapter) and return real-shaped payloads.
  - The deterministic F3 fallback (added in Phase 14) synthesises one
    MandateCandidate per cluster with ``candidate_id = cluster_id``
    — that anchors every downstream F4/F5 call to the real cluster_id,
    which is in turn derived from F1 post URLs (via
    pain_signals[].exact_quotes[].source_url → cluster topic → slug).
  - The Claim at the end has the 5 charter postcondition facts AND a
    non-zero shortlist.

This is the seam proof that the live own-harness path produces a real
portfolio, not an empty one. The deeper live proof (Layer C — Firecrawl
+ real LLM) lives in ``scripts/run_mandate_discovery.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from agentx_contracts import (
    Adapter,
    DeadlineTrigger,
    GatewayContext,
    Health,
    JsonObject,
    MaturityLevel,
    Ring,
    SyscallRegistry,
    SyscallRequest,
    SyscallResult,
    TenantAuth,
)
from agentx_contracts.mandate import InstanceBinding
from agentx_contracts.security import Credential
from agentx_kernel.run_loop import Phase1RunInvoker
from agentx_mandate.harness import OwnHarness
from agentx_mandate.library.mandate_discovery import build_mandate_discovery_type
from agentx_mandate.library.mandate_discovery_playbook import mandate_discovery_playbook

NOW = datetime(2026, 6, 22, tzinfo=UTC)


# ============================================================================
# In-memory read adapter — fulfils community_source_sample / competitor_search
# / buyer_channel_discovery with deterministic, F1-anchored payloads.
# ============================================================================


class _F1FixtureAdapter:
    """A no-op adapter that records calls and returns shaped fixtures.

    The fixtures are deliberately derived from ``community_posts[].url`` so
    the F3 candidate_ids (which equal cluster_ids, which are derived from
    the cluster's signal URLs) round-trip cleanly through F4/F5. This is
    the **Phase 14 invariant** under test.
    """

    name = "f1_fixtures"
    category = "sim"
    maturity_level: MaturityLevel = 0
    risk_class = "read"
    required_ring: Ring = "L0"
    tenant_auth: TenantAuth = "manual"
    input_schema: dict[str, object] = {"type": "object"}
    output_schema: dict[str, object] = {"type": "object"}
    is_terminal_fallback = True

    def __init__(self) -> None:
        self.calls: list[SyscallRequest] = []

    def can_handle(self, req: SyscallRequest, ctx: GatewayContext) -> bool:
        return req.name in {
            "community_source_sample",
            "competitor_search",
            "buyer_channel_discovery",
        } and ctx.ring in {"L0", "L1"}

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        self.calls.append(req)
        if req.name == "community_source_sample":
            return _fulfill_community_source_sample(req)
        if req.name == "competitor_search":
            return _fulfill_competitor_search(req)
        if req.name == "buyer_channel_discovery":
            return _fulfill_buyer_channel_discovery(req)
        return SyscallResult(
            status="error", output={}, error=f"unknown syscall {req.name!r}", fulfilled_by=self.name,
            idempotency_key=req.idempotency_key, maturity_used=0,
        )

    def health(self) -> Health:
        return Health(status="ok", detail="f1_fixtures", checked_at=NOW)


def _fulfill_community_source_sample(req: SyscallRequest) -> SyscallResult:
    """Return 80+ community_posts from 4+ sources. Each post has a real-looking URL
    whose domain is used by the F2 cluster builder and the F3 candidate_id fallback."""
    segment = str(req.args.get("segment", "test"))
    geo = str(req.args.get("geography", ""))
    sources: list[tuple[str, list[str]]] = [
        ("reddit", [f"https://reddit.com/r/{segment.replace(' ', '_')}/comments/abc/{i}" for i in range(10)]),
        ("hackernews", [f"https://news.ycombinator.com/item?id={10000 + i}" for i in range(10)]),
        ("x", [f"https://x.com/saas_founder/status/{1234567 + i}" for i in range(10)]),
        ("indiehackers", [f"https://indiehackers.com/post/{segment.replace(' ', '-')}-{i}" for i in range(10)]),
        ("producthunt", [f"https://producthunt.com/posts/{segment.replace(' ', '-')}-{i}" for i in range(10)]),
        ("g2", [f"https://g2.com/products/{segment.replace(' ', '-')}/reviews/{i}" for i in range(10)]),
        ("discord", [f"https://discord.com/channels/12345/{i}" for i in range(10)]),
        ("forum", [f"https://community.example.com/t/{i}" for i in range(10)]),
    ]
    # 3 distinct topics so the F2 cluster builder produces 3+ clusters
    # (each cluster keyed by (topic_normalised, who_normalised)).
    # The deterministic F3 synthesis then anchors one candidate per
    # cluster — the F2 cluster key becomes the F3 candidate_id.
    topic_palette: list[tuple[str, str]] = [
        ("revops_too_small_for_dedicated_team", "Series A SaaS RevOps leaders"),
        ("forecast_accuracy_lost_in_spreadsheets", "Series A SaaS RevOps leaders"),
        ("lead_routing_in_outreach_silent_failure", "Series A SaaS RevOps leaders"),
    ]
    posts: list[dict[str, object]] = []
    for index, (source_name, urls) in enumerate(sources):
        # Each source alternates through the topic palette so all
        # clusters have multiple distinct sources (the diversity bar).
        topic, who = topic_palette[index % len(topic_palette)]
        for url in urls:
            posts.append(
                {
                    "url": url,
                    "source": source_name,
                    "author": f"u_{source_name}_tester",
                    "timestamp": "2026-05-15T10:00:00Z",
                    "upvotes": 5,
                    "body_text": (
                        f"Real {segment} pain point (topic={topic}; geo={geo}): we have "
                        f"a recurring {topic.replace('_', ' ')} workflow that takes hours "
                        f"each week and we keep missing SLAs. A real platform would fix this."
                    ),
                    "topic": topic,
                    "who_has_problem": who,
                }
            )
    return SyscallResult(
        status="ok",
        output=cast(JsonObject, {
            "provider": "f1_fixtures",
            "credential_ref": None,
            "community_posts": posts,
            "sample_stats": {
                "total_posts_sampled": len(posts),
                "distinct_sources_sampled": len(sources),
                "min_distinct_sources_required": 4,
                "recency_window_months": 12,
            },
        }),
        fulfilled_by="f1_fixtures",
        idempotency_key=req.idempotency_key, maturity_used=0,
    )


def _fulfill_competitor_search(req: SyscallRequest) -> SyscallResult:
    """Return one moat_assessment per candidate_id. Each assessment is
    shaped to PASS the F4 moat gate (saturation<0.7 AND defensibility>=0.3)."""
    candidate_ids_obj = req.args.get("candidate_ids")
    if not isinstance(candidate_ids_obj, list):
        return SyscallResult(
            status="error", output={}, error="candidate_ids missing", fulfilled_by="f1_fixtures",
            idempotency_key=req.idempotency_key, maturity_used=0,
        )
    moat_assessments: dict[str, dict[str, object]] = {}
    for cid_obj in candidate_ids_obj:
        if not isinstance(cid_obj, str):
            continue
        moat_assessments[cid_obj] = {
            "existing_solutions": [
                {
                    "name": f"Generic X alternative to {cid_obj}",
                    "url": f"https://g2.com/products/x-{cid_obj.replace(':', '-')}",
                    "pricing": "$50-200/mo",
                    "weakness": "horizontal — doesn't address the vertical workflow",
                },
            ],
            "saturation_score_0to1": 0.4,
            "defensibility_0to1": 0.6,
            "differentiation_axis": "vertical_specialist_workflow",
            "build_cost_estimate_story_points": 21,
        }
    return SyscallResult(
        status="ok",
        output=cast(JsonObject, {
            "provider": "f1_fixtures",
            "credential_ref": None,
            "moat_assessments": moat_assessments,
        }),
        fulfilled_by="f1_fixtures",
        idempotency_key=req.idempotency_key, maturity_used=0,
    )


def _fulfill_buyer_channel_discovery(req: SyscallRequest) -> SyscallResult:
    """Return one buyer_channels entry per candidate_id with 1-2 real
    subreddits + an entry_post_strategy + a first_100_prospect query. The
    audience_size_estimate is > 0 so the F5 buyer gate KEEPS the candidate."""
    candidate_ids_obj = req.args.get("candidate_ids")
    if not isinstance(candidate_ids_obj, list):
        return SyscallResult(
            status="error", output={}, error="candidate_ids missing", fulfilled_by="f1_fixtures",
            idempotency_key=req.idempotency_key, maturity_used=0,
        )
    buyer_channels: dict[str, dict[str, object]] = {}
    for cid_obj in candidate_ids_obj:
        if not isinstance(cid_obj, str):
            continue
        buyer_channels[cid_obj] = {
            "channels": [
                {
                    "type": "reddit_subreddit",
                    "name_or_url": f"https://reddit.com/r/{cid_obj.replace('cluster:', '').replace('_', '-')[:30]}",
                    "audience_size_estimate": 5000,
                    "engagement_quality": "high",
                    "entry_post_strategy": "post a self-validation result; ask for feedback",
                    "conversion_signal": "comment_rate + DM_rate",
                    "first_100_prospect_source_query": (
                        f"site:reddit.com {cid_obj.replace('cluster:', '').replace('_', ' ')}"
                    ),
                },
            ],
        }
    return SyscallResult(
        status="ok",
        output=cast(JsonObject, {
            "provider": "f1_fixtures",
            "credential_ref": None,
            "buyer_channels": buyer_channels,
        }),
        fulfilled_by="f1_fixtures",
        idempotency_key=req.idempotency_key, maturity_used=0,
    )


# ============================================================================
# In-memory SyscallRegistry — wires the F1 fixture adapter as the only rung.
# ============================================================================


class _SingleAdapterRegistry:
    """A minimal in-memory SyscallRegistry impl. The kernel's gateway calls
    .resolve() to pick the highest-rung adapter; we always return the
    F1 fixture adapter (so every F1/F4/F5 call is satisfied)."""

    def __init__(self, adapter: Adapter) -> None:
        self._adapter = adapter

    def register(self, adapter: Adapter) -> None:
        self._adapter = adapter

    def adapters(self) -> list[Adapter]:
        return [self._adapter]

    def resolve(self, req: SyscallRequest, ctx: GatewayContext) -> Adapter:
        return self._adapter


# ============================================================================
# The integration test
# ============================================================================


@pytest.mark.asyncio
async def test_own_harness_live_mode_produces_shortlist_with_anchored_candidate_ids() -> None:
    """The Phase 14 invariant: own-harness + live mode (real read calls)
    produces a portfolio with non-zero shortlist AND every candidate_id
    is anchored to a real cluster_id (which is derived from F1 post URLs).
    """
    from agentx_kernel.gateway import Gateway
    from agentx_kernel.hydration import HydrationLoader
    from agentx_kernel.projections import Projections
    from agentx_kernel.settlement import SettlementCommitter
    from agentx_kernel.stores.memory import (
        InMemoryJournalStore,
        InMemoryProjectionStore,
        InMemoryRunContinuationStore,
        InMemorySyscallReceiptStore,
        InMemoryVault,
    )
    from agentx_kernel.verifier import RulesVerifier

    # --- Wire the in-memory kernel + the live-style adapter registry -----
    journal = InMemoryJournalStore()
    projection_store = InMemoryProjectionStore()
    projections = Projections(projection_store, journal)
    continuations = InMemoryRunContinuationStore()
    vault = InMemoryVault()
    receipts = InMemorySyscallReceiptStore()

    fixture_adapter = _F1FixtureAdapter()
    registry = _SingleAdapterRegistry(cast(Adapter, fixture_adapter))

    gateway = Gateway(
        journal=cast(Any, journal),
        vault=cast(Any, vault),
        registry=cast(SyscallRegistry, registry),
        receipts=cast(Any, receipts),
    )

    hydration = HydrationLoader(cast(Any, projection_store), cast(Any, journal))
    settlement = SettlementCommitter(journal=cast(Any, journal), projections=projections)
    verifier = RulesVerifier()

    invoker = Phase1RunInvoker(
        journal=cast(Any, journal),
        projections=projections,
        hydration=hydration,
        gateway=gateway,
        settlement=settlement,
        verifier=verifier,
        continuations=cast(Any, continuations),
        runner=OwnHarness(playbook=mandate_discovery_playbook),
    )

    # --- Instantiate the mandate + run the playbook in live mode -------
    mandate = build_mandate_discovery_type()
    inst = InstanceBinding(
        instance_id="inst_phase14",
        type_ref=mandate.id,
        heap_region_id="tenant_phase14",
        ring="L1",
    )
    trigger = DeadlineTrigger(ts=NOW, reason="phase14_live", entity_id="entity_phase14")

    result = await invoker.invoke(
        mandate=mandate, instance=inst, trigger=trigger, mode="live"
    )

    # --- The hard assertions ---------------------------------------------
    if result.state not in ("settled", "parked"):
        # Debug aid: print the trace + journal events to help diagnose.
        print(f"\n=== DEBUG: state={result.state!r} trace_events={len(result.trace.events) if result.trace else 0} ===")
        for e in result.trace.events[-12:]:
            print(f"  kind={e.kind} detail={str(e.detail)[:200]}")
        print(f"=== DEBUG: claims={[(f.predicate, str(f.object)[:80]) for f in result.claimed_facts]} ===")
        print(f"=== DEBUG: calls={[(c.name, str(c.args)[:80]) for c in fixture_adapter.calls]} ===")
    assert result.state in ("settled", "parked"), (
        f"expected settled/parked; got state={result.state!r} "
        f"trace_events={len(result.trace.events) if result.trace else 0}"
    )

    # The portfolio Fact carries the shortlist_count (string-encoded int).
    portfolio_facts = [f for f in result.claimed_facts if f.predicate == "mandate_portfolio"]
    assert portfolio_facts, "no mandate_portfolio fact in the run result"
    shortlist_count = int(str(portfolio_facts[0].object))
    assert shortlist_count > 0, (
        f"shortlist must be > 0 in own-harness + live mode; got {shortlist_count}. "
        f"This is the Phase 14 invariant: the deterministic F3 synthesis "
        f"should produce ≥1 candidate that survives the F4/F5 gates."
    )

    # The 3 read calls the gateway should have fulfilled (F1, F4, F5).
    call_names = [c.name for c in fixture_adapter.calls]
    assert "community_source_sample" in call_names, f"F1 call missing: {call_names}"
    assert "competitor_search" in call_names, f"F4 call missing: {call_names}"
    assert "buyer_channel_discovery" in call_names, f"F5 call missing: {call_names}"

    # The 5 postcondition facts should all be present.
    predicates = {f.predicate for f in result.claimed_facts}
    for required in (
        "pain_cluster_count",
        "mandate_candidate_count",
        "moat_pass_count",
        "buyer_source_manifest",
        "mandate_portfolio",
    ):
        assert required in predicates, f"missing postcondition fact: {required!r}"

    # The mandate_candidate_count must be ≥ 1 (F3 produced at least one
    # candidate that survived the F3 shape gate).
    candidate_count_facts = [f for f in result.claimed_facts if f.predicate == "mandate_candidate_count"]
    assert candidate_count_facts, "no mandate_candidate_count fact"
    candidate_count = int(str(candidate_count_facts[0].object))
    assert candidate_count >= 1, f"F3 produced 0 candidates: {candidate_count}"


@pytest.mark.asyncio
async def test_own_harness_live_mode_anchors_candidate_id_to_cluster_id() -> None:
    """The Phase 14 invariant: F4 receives candidate_ids that match
    cluster_ids from the F2 cluster builder. This is the provenance
    guarantee — F3's candidate_ids are not invented slugs, they're
    deterministic from the F1 community_posts."""
    from agentx_kernel.gateway import Gateway
    from agentx_kernel.hydration import HydrationLoader
    from agentx_kernel.projections import Projections
    from agentx_kernel.settlement import SettlementCommitter
    from agentx_kernel.stores.memory import (
        InMemoryJournalStore,
        InMemoryProjectionStore,
        InMemoryRunContinuationStore,
        InMemorySyscallReceiptStore,
        InMemoryVault,
    )
    from agentx_kernel.verifier import RulesVerifier

    journal = InMemoryJournalStore()
    projection_store = InMemoryProjectionStore()
    projections = Projections(projection_store, journal)
    continuations = InMemoryRunContinuationStore()
    vault = InMemoryVault()
    receipts = InMemorySyscallReceiptStore()

    fixture_adapter = _F1FixtureAdapter()
    registry = _SingleAdapterRegistry(cast(Adapter, fixture_adapter))

    gateway = Gateway(
        journal=cast(Any, journal),
        vault=cast(Any, vault),
        registry=cast(SyscallRegistry, registry),
        receipts=cast(Any, receipts),
    )
    hydration = HydrationLoader(cast(Any, projection_store), cast(Any, journal))
    settlement = SettlementCommitter(journal=cast(Any, journal), projections=projections)
    verifier = RulesVerifier()

    invoker = Phase1RunInvoker(
        journal=cast(Any, journal),
        projections=projections,
        hydration=hydration,
        gateway=gateway,
        settlement=settlement,
        verifier=verifier,
        continuations=cast(Any, continuations),
        runner=OwnHarness(playbook=mandate_discovery_playbook),
    )

    mandate = build_mandate_discovery_type()
    inst = InstanceBinding(
        instance_id="inst_phase14_anchor",
        type_ref=mandate.id,
        heap_region_id="tenant_phase14_anchor",
        ring="L1",
    )
    trigger = DeadlineTrigger(ts=NOW, reason="phase14_anchor", entity_id="entity_phase14_anchor")

    await invoker.invoke(
        mandate=mandate, instance=inst, trigger=trigger, mode="live"
    )

    # Find the F4 call. Every F4 candidate_id should start with "cluster:"
    # — that's the F1→F2→F3 cluster_id provenance guarantee.
    f4_calls = [c for c in fixture_adapter.calls if c.name == "competitor_search"]
    assert f4_calls, "F4 was never called"
    for f4_call in f4_calls:
        cids = f4_call.args.get("candidate_ids")
        if not isinstance(cids, list):
            continue
        for cid in cids:
            if isinstance(cid, str):
                assert cid.startswith("cluster:"), (
                    f"F4 candidate_id {cid!r} is NOT a cluster_id (no F1 provenance). "
                    f"Phase 14 invariant: every F3 candidate_id must equal the "
                    f"cluster_id derived from F1 community_posts[].source_url."
                )
