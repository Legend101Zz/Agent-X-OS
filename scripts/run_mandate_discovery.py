"""Run one Phase-12 mandate-discovery instance against live services.

This is the Layer C dogfood driver for mandate-discovery. The mandate is
READ-ONLY (no outreach, no DMs, no posting) so the L1 park happens at the
Rung 3 human-review rung of the portfolio — the user reviews the
``mandate_portfolio`` Fact in the heap, approves / rewrites / rejects
the shortlist, and the on_condition=shortlist_approved spawn rule fires
a lead-finder@0.1.0 per approved item (closing the loop).

Layer C bar (per the mandate-testing-protocol):
  - L1 park at the right rung (portfolio review, not draft_email approval).
  - The Claim commits the mandate_portfolio fact to the heap with provenance.
  - The 5 charter postconditions are all checked by the rules-verifier.
  - The instance settles on human approval.
  - Spawns lead-finder children for each approved shortlist item.

Pre-flight: same env-var checks as run_lead_finder.py, plus a note that
the read-only nature means we don't need SMTP / Gmail / transport.

Like run_lead_finder.py, this script:
  - Builds the kernel stack ONCE (no per-iteration re-build).
  - Registers the MandateType with a skip-if-exists guard (Pitfall 1 of
    the multi-angle-dogfood doc — Pydantic round-trip on _id).
  - Wraps the run in a 15-minute asyncio.wait_for watchdog.
  - Writes a JSON artifact + prints a structured summary.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from importlib.util import find_spec
from pathlib import Path
from time import perf_counter
from typing import Any

import agentx_db.collections as c
from agentx_contracts.config import Settings
from agentx_contracts.journal import ApprovalResolved, RunSettled
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.mandate import MandateInstance, MandateType
from agentx_contracts.memory import Fact
from agentx_contracts.trigger import DeadlineTrigger
from agentx_db.setup import ensure_indexes
from agentx_kernel.control import KernelControl
from agentx_kernel.gateway import Gateway
from agentx_kernel.hermes import HermesClient
from agentx_kernel.hermes_runner import HermesRunner
from agentx_kernel.hydration import HydrationLoader
from agentx_kernel.projections import Projections
from agentx_kernel.run_loop import Phase1RunInvoker
from agentx_kernel.scheduler import ApprovalWork, SchedulerWorker, TriggerWork
from agentx_kernel.settlement import SettlementCommitter
from agentx_kernel.stores.mongo import (
    MongoJournalStore,
    MongoProjectionStore,
    MongoRunContinuationStore,
    MongoSchedulerStore,
    MongoSyscallReceiptStore,
)
from agentx_kernel.vault import ConfigVault
from agentx_kernel.verifier import RulesVerifier
from agentx_mandate.library.mandate_discovery import build_mandate_discovery_type
from agentx_syscall.discovery_adapters import (
    BuyerChannelDiscoveryAdapter,
    CommunitySourceSampleAdapter,
    CompetitorSearchAdapter,
)
from agentx_syscall.registry import build_phase1_registry
from pymongo import AsyncMongoClient

# The team's first ICP — Series A SaaS RevOps leaders in the US.
# Per the mandate-discovery charter: every run default-targets this segment
# so the F1 community-source + F2 pain-extraction + F3 demand-clustering
# pipeline produces a portfolio the team can act on. Override with
# ``--target-segment`` on the CLI to re-target (e.g. to "Indian SMB
# marketing agency founders" for a different quarter).
DEFAULT_TARGET: JsonObject = {
    "segment": "Series A SaaS RevOps leaders in the US",
    "geography": "United States",
    "time_window": "last_12_months",
    "seed_mandates": ["lead-finder@0.1.0"],
    # The per-mandate-type harness overrides. The live kernel's Hermes runner
    # (packages/kernel/src/agentx_kernel/hermes_runner.py) reads these from
    # ctx.target — that's how a new mandate type teaches the LLM its own
    # vocabulary (community_source_sample, competitor_search, etc.) instead
    # of defaulting to lead-finder's research-and-draft loop. The prior live
    # run (agentx_discovery_1782075713_default) failed with 0 portfolio
    # facts because the LLM didn't know these syscall names existed.
    "system_prompt_override": (
        "You are the mandate-discovery faculty of Agent-X, an accountable agent OS. "
        "Your job is to find the next MandateType the team should build — a business process "
        "the platform can sell. The mandate is READ-ONLY: no outreach, no DMs, no posting. "
        "You listen; you never talk.\n\n"
        "Target segment: ${segment} in ${geography} (time window: ${time_window}).\n\n"
        "Act ONE STEP AT A TIME — call exactly ONE tool per turn. Tools available:\n"
        "  - think(summary): a brief private reasoning note. No real-world effect.\n"
        "  - community_source_sample(segment, geography, sources, post_count, min_post_age_months): "
        "READ-ONLY. Sample community posts (Reddit / Hacker News / X / IndieHackers / ProductHunt / G2 / Discord) "
        "matching the target segment. Returns community_posts (each with url/author/timestamp/upvotes/body_text) "
        "and sample_stats. Use sources=[\"reddit\",\"hackernews\",\"x\",\"indiehackers\",\"producthunt\",\"g2_reviews\",\"discord\",\"forum\"] "
        "for the diversity bar. post_count=80 by default, cap 300. Call this AT MOST ONCE PER SOURCE — if Reddit returns "
        "20 posts, that's enough; don't call it 5 more times to get more. The playbook enforces the diversity bar.\n"
        "  - competitor_search(candidate_ids, include_pricing, include_weaknesses): "
        "READ-ONLY. For each candidate id, returns existing_solutions, saturation_score_0to1, "
        "defensibility_0to1, differentiation_axis, build_cost_estimate_story_points. The F4 moat gate "
        "kills saturated+no-moat combinations (saturation>0.7 AND defensibility<0.3). Call this AT MOST ONCE.\n"
        "  - buyer_channel_discovery(candidate_ids, max_channels_per_candidate): "
        "READ-ONLY. For each candidate, returns channels (subreddits / Discord / X threads) with "
        "audience_size_estimate, entry_post_strategy, conversion_signal, and first_100_prospect_source_query. "
        "The F5 buyer gate kills candidates with no channel of audience>0 and a first-query. Call this AT MOST ONCE.\n"
        "  - claim_facts(facts): commit verified facts to memory. The kernel RUNS THE RULES VERIFIER "
        "against the facts you claim. If you skip this, the run crashes (state=crashed). Use these predicates "
        "IN THIS EXACT ORDER at the end of the run:\n"
        "    1. pain_cluster_count (object=str(count of pain clusters you identified, e.g. \"3\"))\n"
        "    2. mandate_candidate_count (object=str(count of mandate candidates you surfaced))\n"
        "    3. moat_pass_count (object=str(count of candidates that pass the F4 moat gate))\n"
        "    4. buyer_source_manifest (object=str(shortlist summary, e.g. \"shortlist=2: revops_one_person_platform, pipeline_hygiene_daily\"))\n"
        "    5. mandate_portfolio (object=str(shortlist_count, e.g. \"2\")\n"
        "  - finish(summary): end the run. Call this AFTER claim_facts has committed all 5 postcondition facts.\n\n"
        "Mandatory sequence (do not deviate):\n"
        "  1. ONE community_source_sample call (sources=all 8) → you get ~80 posts from 4+ sources.\n"
        "  2. ONE think (decide the pain clusters you see).\n"
        "  3. ONE competitor_search (for the mandate candidates you want to assess).\n"
        "  4. ONE buyer_channel_discovery (for those same candidates).\n"
        "  5. ONE claim_facts with the 5 postcondition facts (pain_cluster_count, mandate_candidate_count, "
        "moat_pass_count, buyer_source_manifest, mandate_portfolio) — this is the MANDATORY final step before finish.\n"
        "  6. ONE finish.\n\n"
        "If a tool returns an error or empty results, broaden the query and retry — never repeat the same failing call. "
        "If you call community_source_sample 5 times in a row without progress, you will time out the run.\n\n"
        "Hard rules:\n"
        "1. READ-ONLY. You MUST NOT call draft_email, send_email, send_message, queue_manual_action, or any "
        "external_message/money/irreversible syscall. The mandate is LISTEN, not TALK. If you try, the run parks.\n"
        "2. RESEARCH BEFORE CLAIMING. Ground every claim in a real community post URL you actually saw in the "
        "F1 community_source_sample response. Never invent pain points, sources, or quotes.\n"
        "3. DIVERSITY: the F1 sample must come from 4+ distinct community sources (Reddit + HN + X + forum at "
        "minimum). A mono-source mandate is biased and the playbook will park.\n"
        "4. CLAIM_FACTS IS NOT OPTIONAL. The kernel's rules-verifier checks the 5 postcondition facts at the end of "
        "the run. If you don't call claim_facts with all 5 predicates, the run crashes. This is the single most "
        "common failure mode.\n"
        "5. NO DRAFT_EMAIL. The mandate-discovery mandate's outcome is a mandate_portfolio Fact in the heap, "
        "not an email draft. The F6 portfolio-builder commits it. If you try to draft an email, the run parks "
        "for L2 approval and the whole thing stalls."
    ),
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "think",
                "description": "Record a brief private reasoning note. No real-world effect.",
                "parameters": {
                    "type": "object",
                    "properties": {"summary": {"type": "string"}},
                    "required": ["summary"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "community_source_sample",
                "description": (
                    "READ-ONLY. Sample 80+ community posts (Reddit/HN/X/IndieHackers/ProductHunt/G2/Discord) "
                    "matching the segment. Returns community_posts and sample_stats. The F1 sampling rule: "
                    "min 80 posts, cap 300, min 4 distinct sources, recency < 12 months."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "segment": {"type": "string", "description": "the ICP / topic (e.g. 'Series A SaaS RevOps')"},
                        "geography": {"type": "string", "description": "geography filter (optional)"},
                        "sources": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "which sources to sample (reddit/hackernews/x/indiehackers/producthunt/g2_reviews/discord/forum)"
                            ),
                        },
                        "post_count": {"type": "integer", "description": "min posts (default 80, cap 300)"},
                        "min_post_age_months": {"type": "integer", "description": "recency cutoff (default 12)"},
                    },
                    "required": ["segment"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "competitor_search",
                "description": (
                    "READ-ONLY. For each candidate id, return existing_solutions, saturation_score_0to1, "
                    "defensibility_0to1, differentiation_axis, build_cost_estimate_story_points."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "candidate_ids": {"type": "array", "items": {"type": "string"}},
                        "include_pricing": {"type": "boolean"},
                        "include_weaknesses": {"type": "boolean"},
                    },
                    "required": ["candidate_ids"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "buyer_channel_discovery",
                "description": (
                    "READ-ONLY. For each candidate, return channels (subreddits, Discord servers, X threads) "
                    "with audience_size_estimate, entry_post_strategy, conversion_signal, and "
                    "first_100_prospect_source_query."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "candidate_ids": {"type": "array", "items": {"type": "string"}},
                        "max_channels_per_candidate": {"type": "integer"},
                    },
                    "required": ["candidate_ids"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "claim_facts",
                "description": (
                    "Commit verified facts to memory. Predicates: pain_cluster_count, "
                    "mandate_candidate_count, moat_pass_count, buyer_source_manifest, mandate_portfolio. "
                    "Each fact MUST cite a real evidence URL from the F1 community_source_sample response."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "facts": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "subject": {"type": "string"},
                                    "predicate": {"type": "string"},
                                    "object": {"type": "string"},
                                    "confidence": {"type": "number"},
                                    "evidence": {"type": "array", "items": {"type": "string"}},
                                },
                                "required": ["subject", "predicate", "object", "evidence"],
                            },
                        },
                    },
                    "required": ["facts"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "finish",
                "description": "End the run. Provide a structured summary of the mandate-discovery outcome.",
                "parameters": {
                    "type": "object",
                    "properties": {"summary": {"type": "string"}},
                    "required": ["summary"],
                },
            },
        },
    ],
    "tool_risk_map": {
        "community_source_sample": "read",
        "competitor_search": "read",
        "buyer_channel_discovery": "read",
        "think": "read",
        "claim_facts": "read",
        "finish": "read",
    },
}

# 15-minute wall-clock watchdog per the multi-angle-dogfood doc (Pitfall 4).
PER_RUN_TIMEOUT_SECONDS: float = 900.0

# Output directory for the JSON artifact + summary (per-run, durable).
OUTPUT_ROOT = Path("/tmp/agentx_discovery_dogfood")


def _missing_env(settings: Settings) -> list[str]:
    missing: list[str] = []
    if not settings.mongodb_uri.get_secret_value().strip():
        missing.append("MONGODB_URI")
    if settings.minimax_api_key is None or not settings.minimax_api_key.get_secret_value().strip():
        missing.append("MINIMAX_API_KEY")
    if not settings.faculty_model_base_url.strip():
        missing.append("FACULTY_MODEL_BASE_URL")
    if not settings.faculty_model_id.strip():
        missing.append("FACULTY_MODEL_ID")
    # mandate-discovery is read-only: no SMTP / no transport needed.
    # But it DOES need at least one community-source adapter (Reddit/HN/X).
    # Exa + Firecrawl are the live backends the F1 community-source faculty
    # routes to. The lead-finder's research batch is the closest precedent.
    exa_ok = settings.exa_api_key is not None and bool(settings.exa_api_key.get_secret_value().strip())
    firecrawl_ok = (
        settings.firecrawl_api_key is not None and bool(settings.firecrawl_api_key.get_secret_value().strip())
    )
    if not (exa_ok or firecrawl_ok):
        missing.append("EXA_API_KEY or FIRECRAWL_API_KEY (for F1 community_source_sample)")
    return missing


def _missing_research_sdks(settings: Settings) -> list[str]:
    missing: list[str] = []
    if settings.exa_api_key is not None and settings.exa_api_key.get_secret_value().strip():
        if find_spec("exa_py") is None:
            missing.append("exa-py")
    if settings.firecrawl_api_key is not None and settings.firecrawl_api_key.get_secret_value().strip():
        if find_spec("firecrawl") is None:
            missing.append("firecrawl-py")
    return missing


def _format_fact_summary(fact: Fact) -> str:
    """One-line summary of a fact for the console output."""
    return (
        f"{fact.id} predicate={fact.predicate!r} object={str(fact.object)[:60]!r} "
        f"confidence={fact.confidence:.2f} status={fact.status!r}"
    )


async def _run_one(
    *,
    label: str,
    target: JsonObject,
    instance_id: str,
    run_started: datetime,
    journal: MongoJournalStore,
    projection_store: MongoProjectionStore,
    receipts: MongoSyscallReceiptStore,
    control: KernelControl,
    invoker: Phase1RunInvoker,
    scheduler_store: MongoSchedulerStore,
    worker: SchedulerWorker,
    mandate: MandateType,
    database: Any,
) -> dict[str, object]:
    """Run one mandate-discovery instance to L1 park + (optional) approval settlement.

    Returns a dict summary (also written as JSON to OUTPUT_ROOT/<label>.json).
    The summary includes: park reason, Claim predicates, heap facts, journal
    sequence, and the artefact location. The caller decides whether to
    also drive the approval cycle (the human_review of the portfolio is
    the Rung 3 step; the script parks for that).
    """
    trigger = DeadlineTrigger(ts=run_started, reason=f"mandate_discovery_{label}", entity_id=label)
    persisted_instance = MandateInstance(
        id=instance_id,
        type_ref=f"{mandate.name}@{mandate.version}",
        customer_id="Agent-X mandate-discovery",
        ring="L1",
        heap_region_id=f"tenant_{instance_id}",
    )
    await control.instantiate_mandate(persisted_instance)
    instance = await control.instance_binding(instance_id)
    mandate_run = mandate.model_copy(deep=True)
    mandate_run.charter.target = dict(target)

    # Stale-scheduler guard: refuse to start if there are unrelated due items.
    pending_due = await database[c.SCHEDULER_WORK].count_documents(
        {"status": "pending", "available_at": {"$lte": datetime.now(UTC)}}
    )
    if pending_due:
        raise RuntimeError(f"refusing live run with {pending_due} unrelated due scheduler item(s)")

    l1_started = perf_counter()
    trigger_work = TriggerWork.schedule(
        mandate=mandate_run,
        instance=instance,
        trigger=trigger,
        mode="live",
    )
    await scheduler_store.enqueue(trigger_work)
    parked = await worker.run_once(datetime.now(UTC))
    if parked is None:
        raise RuntimeError("scheduler worker found no trigger work")
    l1_seconds = perf_counter() - l1_started

    # mandate-discovery is read-only. The L1 park reason should be either
    # "portfolio review" (the portfolio is staged for human approval) or
    # "F2/F3/F4/F5 gate failed" (the run couldn't surface a portfolio).
    # The Rung 3 human-review cycle is then a SEPARATE flow — the user
    # inspects the heap facts and either approves the shortlist (which
    # fires the on_condition=shortlist_approved spawn rule) or rejects.
    if parked.state not in ("parked", "settled"):
        # The Hermes live harness may end in "crashed" if the LLM didn't call
        # claim_facts (the rules-verifier then can't find the postcondition facts).
        # That's a quality issue, not a fatal error — the run is over and the
        # journal has the record. The live-run quality report covers this case.
        raise RuntimeError(
            f"unexpected run state={parked.state!r} "
            f"(expected 'parked' or 'settled' — see /tmp/mandate_discovery_v*.log for details)"
        )

    # Pull the Claim's facts from the journal — the run produced them
    # at L1; settlement commits them on approve.
    # Facts are stored on the RunSettled event (the single atomic commit
    # carries the whole fan-out per BLUEPRINT §2 step 6), not as separate
    # journal events. We read them via the heap projection instead.
    run_events = await journal.read_run(parked.run_id)
    settled_event = next((e for e in reversed(run_events) if isinstance(e, RunSettled)), None)
    claim_facts: list[Fact] = list(settled_event.facts) if settled_event is not None else []
    fact_predicates = sorted({f.predicate for f in claim_facts})

    heap_facts = await projection_store.find(c.HEAP_FACT, {"instance_id": instance_id})
    trace_rows = await projection_store.find(c.SYSCALL_TRACE, {"run_id": parked.run_id})

    # The mandate_portfolio fact's `object` field carries the shortlist_count
    # (a string-encoded int per the F6 builder); pull it for the summary.
    portfolio_fact = next(
        (f for f in claim_facts if f.predicate == "mandate_portfolio"),
        None,
    )
    shortlist_count: int | None = None
    if portfolio_fact is not None:
        try:
            shortlist_count = int(str(portfolio_fact.object))
        except (TypeError, ValueError):
            shortlist_count = None

    summary: dict[str, object] = {
        "label": label,
        "instance_id": instance_id,
        "run_id": parked.run_id,
        "trigger_work_id": trigger_work.work_id,
        "park_reason": parked.park.reason if parked.park is not None else "(no park — run ended)",
        "l1_state": parked.state,
        "l1_seconds": round(l1_seconds, 2),
        "fact_predicates": fact_predicates,
        "heap_fact_count": len(heap_facts),
        "trace_row_count": len(trace_rows),
        "settled_at_settle_event": settled_event.event_id if settled_event else None,
        "shortlist_count": shortlist_count,
        "target_segment": str(target.get("segment", "")),
    }
    return summary


async def _approve_and_settle(
    *,
    instance_id: str,
    run_id: str,
    actor: str,
    journal: MongoJournalStore,
    scheduler_store: MongoSchedulerStore,
    control: KernelControl,
    worker: SchedulerWorker,
) -> dict[str, object]:
    """Drive the human approval cycle for one parked run.

    The mandate-discovery run parks awaiting the Rung 3 portfolio review.
    This helper enqueues an ApprovalWork, runs the worker, and confirms
    the run settled. Returns a summary dict.
    """
    inbox = await control.approval_inbox(instance_id=instance_id)
    approval_started = perf_counter()
    await control.approve(
        instance_id=instance_id,
        run_id=run_id,
        actor=actor,
        now=datetime.now(UTC),
    )
    resolved: ApprovalResolved = next(
        event
        for event in reversed(await journal.read_run(run_id))
        if isinstance(event, ApprovalResolved)
    )
    work = ApprovalWork.schedule(resolved)
    await scheduler_store.enqueue(work)
    resumed = await worker.run_once(datetime.now(UTC))
    if resumed is None or resumed.state != "settled":
        raise RuntimeError(f"kernel resume did not settle: state={resumed.state if resumed else 'None'}")
    approval_seconds = perf_counter() - approval_started
    return {
        "approval_seconds": round(approval_seconds, 2),
        "approval_resolved_event": getattr(resolved, "event_id", None),
        "settled": True,
    }


async def main() -> int:
    settings = Settings()
    missing = _missing_env(settings)
    if missing:
        print("STOP missing required .env values: " + ", ".join(missing))
        return 2
    missing_sdks = _missing_research_sdks(settings)
    if missing_sdks:
        print("STOP missing research SDK package(s): " + ", ".join(missing_sdks))
        return 2

    now = datetime.now(UTC)
    run_id_stub = f"agentx_discovery_{int(now.timestamp())}"
    output_dir = OUTPUT_ROOT / run_id_stub
    output_dir.mkdir(parents=True, exist_ok=True)

    client: AsyncMongoClient[dict[str, object]] = AsyncMongoClient(settings.mongodb_uri.get_secret_value())
    try:
        await client.admin.command("ping")
        database = client[settings.mongodb_db_name]
        await ensure_indexes(database)

        # Build the kernel stack ONCE (Pitfall 2 of multi-angle-dogfood.md).
        journal = MongoJournalStore(database)
        projection_store = MongoProjectionStore(database)
        projections = Projections(projection_store, journal)
        receipts = MongoSyscallReceiptStore(database)
        # Build the live syscall registry; include the Phase-12 mandate-discovery
        # read adapters if Firecrawl is configured (the F1/F4/F5 Calls otherwise
        # fall to the human-task terminal fallback — the run parks for human).
        firecrawl_key = (
            settings.firecrawl_api_key.get_secret_value()
            if settings.firecrawl_api_key is not None
            else ""
        )
        if firecrawl_key:
            registry = build_phase1_registry(
                discovery_adapters=[
                    CommunitySourceSampleAdapter(api_key=firecrawl_key),
                    CompetitorSearchAdapter(api_key=firecrawl_key),
                    BuyerChannelDiscoveryAdapter(api_key=firecrawl_key),
                ]
            )
        else:
            registry = build_phase1_registry()
        gateway = Gateway(
            journal=journal,
            vault=ConfigVault(settings),
            registry=registry,
            receipts=receipts,
        )
        hydration = HydrationLoader(projection_store, journal)
        settlement = SettlementCommitter(journal=journal, projections=projections)
        invoker = Phase1RunInvoker(
            journal=journal,
            projections=projections,
            hydration=hydration,
            gateway=gateway,
            settlement=settlement,
            verifier=RulesVerifier(),
            continuations=MongoRunContinuationStore(database),
            runner=HermesRunner(transport=HermesClient.from_settings(settings)),
        )
        control = KernelControl(
            journal=journal, projections=projections, projection_store=projection_store
        )
        scheduler_store = MongoSchedulerStore(database)
        worker = SchedulerWorker(store=scheduler_store, invoker=invoker)

        # Register the MandateType ONCE with the skip-if-exists guard (Pitfall 1).
        canonical_mandate = build_mandate_discovery_type()
        existing = await projection_store.find(c.MANDATE_TYPE, {"id": canonical_mandate.id})
        if existing:
            print(f"INFO MandateType {canonical_mandate.id!r} already registered; skipping re-registration")
        else:
            await control.register_mandate_type(canonical_mandate)

        # Per-run helper closure — re-uses the pre-built kernel stack.
        async def drive(
            label: str,
            target: JsonObject,
            *,
            approve: bool,
        ) -> dict[str, object]:
            instance_id = f"{run_id_stub}_{label}"
            run_started = datetime.now(UTC)
            # 15-minute wall-clock watchdog (Pitfall 4 of multi-angle-dogfood.md).
            summary = await asyncio.wait_for(
                _run_one(
                    label=label,
                    target=target,
                    instance_id=instance_id,
                    run_started=run_started,
                    journal=journal,
                    projection_store=projection_store,
                    receipts=receipts,
                    control=control,
                    invoker=invoker,
                    scheduler_store=scheduler_store,
                    worker=worker,
                    mandate=canonical_mandate,
                    database=database,
                ),
                timeout=PER_RUN_TIMEOUT_SECONDS,
            )
            if approve and summary.get("l1_state") == "parked":
                run_id = str(summary.get("run_id", ""))
                approval = await asyncio.wait_for(
                    _approve_and_settle(
                        instance_id=instance_id,
                        run_id=run_id,
                        actor="manager:codex-live-validation",
                        journal=journal,
                        scheduler_store=scheduler_store,
                        control=control,
                        worker=worker,
                    ),
                    timeout=PER_RUN_TIMEOUT_SECONDS,
                )
                summary.update(approval)
            artifact = output_dir / f"{label}.json"
            artifact.write_text(json.dumps(summary, indent=2, default=str))
            summary["artifact"] = str(artifact)
            return summary

        # Phase 13 first run: the default Series A SaaS RevOps target.
        # Override via env var MANDATE_DISCOVERY_SEGMENT to re-target.
        import os
        override_segment = os.environ.get("MANDATE_DISCOVERY_SEGMENT", "").strip()
        target = dict(DEFAULT_TARGET)
        if override_segment:
            target["segment"] = override_segment

        summary = await drive(label="default", target=target, approve=False)

        # Print the structured summary (the dashboard reads these lines).
        print(f"INSTANCE_ID={summary['instance_id']}")
        print(f"RUN_ID={summary['run_id']}")
        print(f"PARK_REASON={summary['park_reason']}")
        print(f"L1_STATE={summary['l1_state']}")
        print(f"LATENCY_SECONDS l1={summary['l1_seconds']}")
        fact_predicates_value = summary.get("fact_predicates", [])
        if not isinstance(fact_predicates_value, list):
            fact_predicates_value = []
        print(f"FACT_PREDICATES={','.join(str(p) for p in fact_predicates_value)}")
        print(f"HEAP_FACT_COUNT={summary['heap_fact_count']}")
        print(f"TRACE_ROW_COUNT={summary['trace_row_count']}")
        print(f"SHORTLIST_COUNT={summary['shortlist_count']}")
        print(f"ARTIFACT={summary['artifact']}")
        print("PARK_FOR_HUMAN_REVIEW=yes — inspect the heap, then call:")
        print(
            f"  /api/v1/approvals/{summary['instance_id']}/resolve "
            f"--decision=approve --actor=manager:human-reviewer"
        )
        print("On approve, the on_condition=shortlist_approved spawn rule fires")
        print("and lead-finder@0.1.0 children are enqueued for each shortlist item.")
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
