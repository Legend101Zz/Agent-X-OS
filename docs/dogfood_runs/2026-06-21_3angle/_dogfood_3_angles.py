"""Three-angle dogfood: run the lead-finder mandate three times against three distinct
ICP angles (Agent-X self-targeting). Each run instantiates a fresh MandateInstance
(customer_id="Agent-X dogfood"), triggers the L1 run, lets it park, then approves and
settles. Each run produces exactly ONE draft (the top-scored actionable lead) per
the current playbook — three runs give us three drafts.

No code changes to existing files. Writes structured per-run JSON to
/tmp/agentx_dogfood_3angles_<timestamp>/ and prints a final summary table.

Usage:
    cd /Volumes/Mrigesh\\ SSD/Startup/Agent-X-OS
    source .venv/bin/activate
    python scripts/_dogfood_3_angles.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

# Force RUN_LIVE_EMAIL=1 so the post-approval send actually executes (SMTP is configured).
os.environ.setdefault("RUN_LIVE_EMAIL", "1")

from agentx_contracts.config import Settings
from agentx_contracts.journal import ApprovalResolved, RunSettled
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.mandate import MandateInstance
from agentx_contracts.trigger import DeadlineTrigger
from agentx_db.collections import HEAP_FACT, MANDATE_TYPE, SCHEDULER_WORK, SYSCALL_TRACE
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
from agentx_mandate.library.lead_finder import build_lead_finder_type
from agentx_syscall.registry import build_phase1_registry
from pymongo import AsyncMongoClient

OUT_DIR = Path(f"/tmp/agentx_dogfood_3angles_{int(datetime.now(UTC).timestamp())}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Three distinct ICP angles. Each targets Agent-X's actual buyer.
DOGFOOD_RUNS: list[tuple[str, JsonObject]] = [
    (
        "A_founders_buying_AI_lead_gen",
        {
            "icp": "early-stage SaaS founders and indie operators actively buying an AI lead-generation tool",
            "location": "United States",
            "count": 3,
        },
    ),
    (
        "B_growth_agencies_evaluating_AI_SDR",
        {
            "icp": "B2B growth and outbound agencies evaluating AI SDR or autonomous lead-finder tools",
            "location": "India",
            "count": 3,
        },
    ),
    (
        "C_revops_saas_20to200",
        {
            "icp": "RevOps and sales-ops leaders at 20-200 person B2B SaaS companies doing manual outbound",
            "location": "United States",
            "count": 3,
        },
    ),
]


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
    firecrawl_ok = settings.firecrawl_api_key is not None and bool(
        settings.firecrawl_api_key.get_secret_value().strip()
    )
    if not firecrawl_ok:
        missing.append("FIRECRAWL_API_KEY")
    return missing


async def _run_one(
    *,
    label: str,
    target: JsonObject,
    client: AsyncMongoClient,
    settings: Settings,
    control: KernelControl,
    registry_modules: dict,
    database,
) -> dict:
    """One dogfood run. Caller must have already registered the MandateType once."""
    now = datetime.now(UTC)
    instance_id = f"agentx_dogfood_{label}_{int(now.timestamp())}"

    journal = registry_modules["journal"]
    projection_store = registry_modules["projection_store"]
    projections = registry_modules["projections"]
    receipts = registry_modules["receipts"]
    gateway = registry_modules["gateway"]
    hydration = registry_modules["hydration"]
    settlement = registry_modules["settlement"]
    invoker = registry_modules["invoker"]
    scheduler_store = registry_modules["scheduler_store"]
    worker = registry_modules["worker"]

    canonical_mandate = build_lead_finder_type()
    persisted_instance = MandateInstance(
        id=instance_id,
        type_ref=f"{canonical_mandate.name}@{canonical_mandate.version}",
        customer_id="Agent-X dogfood",
        ring="L1",
        heap_region_id=f"tenant_{instance_id}",
    )
    await control.instantiate_mandate(persisted_instance)
    instance = await control.instance_binding(instance_id)
    mandate = canonical_mandate.model_copy(deep=True)
    mandate.charter.target = dict(target)

    trigger = DeadlineTrigger(
        ts=now, reason=f"dogfood_{label}", entity_id=f"agentx_dogfood_icp_{label}"
    )
    trigger_work = TriggerWork.schedule(
        mandate=mandate, instance=instance, trigger=trigger, mode="live"
    )
    await scheduler_store.enqueue(trigger_work)
    t0 = perf_counter()
    parked = await worker.run_once(datetime.now(UTC))
    l1_seconds = perf_counter() - t0
    if parked is None:
        raise RuntimeError(f"[{label}] scheduler worker found no trigger work")
    if parked.state != "parked" or parked.park is None:
        raise RuntimeError(f"[{label}] expected L1 approval park, got state={parked.state}")

    inbox = await control.approval_inbox(instance_id=instance_id)
    t1 = perf_counter()
    await control.approve(
        instance_id=instance_id,
        run_id=parked.run_id,
        actor=f"manager:dogfood_3angles/{label}",
        now=datetime.now(UTC),
    )
    approval = next(
        (
            ev
            for ev in reversed(await journal.read_run(parked.run_id))
            if isinstance(ev, ApprovalResolved)
        ),
        None,
    )
    if approval is None:
        raise RuntimeError(f"[{label}] approval command did not append ApprovalResolved")
    approval_work = ApprovalWork.schedule(approval)
    await scheduler_store.enqueue(approval_work)
    resumed = await worker.run_once(datetime.now(UTC))
    approval_seconds = perf_counter() - t1
    if resumed is None:
        raise RuntimeError(f"[{label}] scheduler worker found no approval work")
    if resumed.state != "settled":
        raise RuntimeError(f"[{label}] kernel resume did not settle: state={resumed.state}")

    heap_facts = await projection_store.find(HEAP_FACT, {"instance_id": instance_id})
    run_events = await journal.read_run(parked.run_id)
    trace_rows = await projection_store.find(SYSCALL_TRACE, {"run_id": parked.run_id})
    settled = next(ev for ev in reversed(run_events) if isinstance(ev, RunSettled))

    # Pull the actual draft body out of the parked card (the human saw this).
    card = parked.park.approval_card
    if not isinstance(card, dict):
        raise RuntimeError(f"[{label}] approval_card not a dict")
    syscall = card.get("syscall")
    idem = card.get("idempotency_key")
    raw_args = card.get("args", {})
    args: JsonObject = raw_args if isinstance(raw_args, dict) else {}
    draft_receipt = await receipts.get(idem) if isinstance(idem, str) else None

    # Pull actionable_lead facts and the lead bodies
    actionable_facts = [f for f in heap_facts if f.get("predicate") == "actionable_lead"]
    score_facts = [f for f in heap_facts if f.get("predicate") == "qualified_lead_score"]

    summary = {
        "label": label,
        "instance_id": instance_id,
        "run_id": parked.run_id,
        "trigger_work_id": trigger_work.work_id,
        "approval_work_id": approval_work.work_id,
        "icp_target": target,
        "l1_state": parked.state,
        "park_reason": parked.park.reason,
        "approval_card": {
            "syscall": syscall,
            "subject": args.get("subject") if isinstance(args, dict) else None,
            "to": args.get("to") if isinstance(args, dict) else None,
            "body": args.get("body") if isinstance(args, dict) else None,
            "lead_id": args.get("lead_id") if isinstance(args, dict) else None,
        },
        "draft_receipt": {
            "status": draft_receipt.result.status if draft_receipt else None,
            "fulfilled_by": draft_receipt.result.fulfilled_by if draft_receipt else None,
        },
        "settled_event": settled.event_id,
        "heap_fact_count": len(heap_facts),
        "actionable_lead_facts": [
            {
                "subject": f.get("subject"),
                "object": f.get("object"),
                "confidence": f.get("confidence"),
                "provenance_evidence": (f.get("provenance") or {}).get("evidence"),
                "provenance_note": (f.get("provenance") or {}).get("note"),
            }
            for f in actionable_facts
        ],
        "qualified_lead_score_facts": [
            {
                "subject": f.get("subject"),
                "object": f.get("object"),
                "confidence": f.get("confidence"),
            }
            for f in score_facts
        ],
        "journal_kinds": [ev.kind for ev in run_events],
        "syscall_trace_rows": len(trace_rows),
        "latency_seconds": {"l1": round(l1_seconds, 2), "approval_to_settle": round(approval_seconds, 2)},
        "trace_events": [
            {"seq": ev.seq, "kind": ev.kind, "summary": ev.summary, "detail": ev.detail}
            for ev in resumed.trace.events
        ],
    }
    out_path = OUT_DIR / f"run_{label}.json"
    out_path.write_text(json.dumps(summary, indent=2, default=str))
    return summary


async def main() -> int:
    settings = Settings()
    missing = _missing_env(settings)
    if missing:
        print("STOP missing required .env values: " + ", ".join(missing))
        return 2

    print(f"=== Agent-X 3-angle dogfood ===")
    print(f"OUT_DIR = {OUT_DIR}")
    print(f"MongoDB = {settings.mongodb_db_name} @ (set, hidden)")
    print()

    client: AsyncMongoClient = AsyncMongoClient(settings.mongodb_uri.get_secret_value())
    database = client[settings.mongodb_db_name]
    await ensure_indexes(database)

    # Guard: refuse if there are stale unrelated due scheduler items
    pending_due = await database[SCHEDULER_WORK].count_documents(
        {"status": "pending", "available_at": {"$lte": datetime.now(UTC)}}
    )
    if pending_due:
        print(f"STOP refusing run: {pending_due} stale scheduler item(s) due")
        await client.close()
        return 3

    # Build kernel modules ONCE and register the MandateType ONCE
    journal = MongoJournalStore(database)
    projection_store = MongoProjectionStore(database)
    projections = Projections(projection_store, journal)
    receipts = MongoSyscallReceiptStore(database)
    gateway = Gateway(
        journal=journal,
        vault=ConfigVault(settings),
        registry=build_phase1_registry(),
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

    canonical_mandate = build_lead_finder_type()
    # Idempotent register: skip if already registered (avoid Pydantic equality false positives
    # when stored doc has an _id field Pydantic rejects on round-trip).
    existing = await projection_store.find(MANDATE_TYPE, {"id": canonical_mandate.id})
    if existing:
        print(f"  MandateType already registered (id={canonical_mandate.id}) - skipping re-registration")
    else:
        await control.register_mandate_type(canonical_mandate)
        print(f"Registered MandateType: {canonical_mandate.name}@{canonical_mandate.version}")

    registry_modules = {
        "journal": journal,
        "projection_store": projection_store,
        "projections": projections,
        "receipts": receipts,
        "gateway": gateway,
        "hydration": hydration,
        "settlement": settlement,
        "invoker": invoker,
        "scheduler_store": scheduler_store,
        "worker": worker,
    }

    summaries: list[dict] = []
    try:
        for label, target in DOGFOOD_RUNS:
            print(f"\n--- RUN {label} ---")
            print(f"  target.icp     = {target['icp']!r}")
            print(f"  target.location= {target['location']!r}")
            print(f"  target.count   = {target['count']}")
            try:
                summary = await _run_one(
                    label=label,
                    target=target,
                    client=client,
                    settings=settings,
                    control=control,
                    registry_modules=registry_modules,
                    database=database,
                )
                summaries.append(summary)
                card = summary["approval_card"]
                print(f"  RESULT: parked L1, approved, settled")
                print(f"          instance_id = {summary['instance_id']}")
                print(f"          run_id      = {summary['run_id']}")
                print(f"          draft to    = {card.get('to')!r}")
                print(f"          subject     = {card.get('subject')!r}")
                print(f"          lead_id     = {card.get('lead_id')!r}")
                print(f"          actionable  = {len(summary['actionable_lead_facts'])}")
                print(f"          latency     = {summary['latency_seconds']}")
            except Exception as e:
                print(f"  FAILED: {type(e).__name__}: {e}")
                traceback.print_exc()
                summaries.append({"label": label, "error": f"{type(e).__name__}: {e}"})

        # Final summary file
        final = {
            "generated_at": datetime.now(UTC).isoformat(),
            "out_dir": str(OUT_DIR),
            "runs": summaries,
        }
        (OUT_DIR / "summary.json").write_text(json.dumps(final, indent=2, default=str))
        print()
        print("=== SUMMARY ===")
        for s in summaries:
            if "error" in s:
                print(f"  {s['label']}: ERROR - {s['error']}")
            else:
                card = s["approval_card"]
                n_actionable = len(s["actionable_lead_facts"])
                subject = card.get("subject") or "<none>"
                to = card.get("to") or "<none>"
                print(f"  {s['label']}: drafted {n_actionable} lead(s) -> subject={subject!r} to={to!r}")
        print()
        print(f"All artifacts in: {OUT_DIR}")
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))