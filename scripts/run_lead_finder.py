"""Run one Phase-1 lead-finder instance against live services.

This is intentionally a thin wiring script: kernel package code still depends only on Protocols.
The script composes the live Mongo stores, live Hermes reasoner, and syscall registry at the edge.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from importlib.util import find_spec
from time import perf_counter

import agentx_db.collections as c
from agentx_contracts.config import Settings
from agentx_contracts.journal import ApprovalResolved, RunSettled
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.mandate import MandateInstance
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
from agentx_mandate.library.lead_finder import build_lead_finder_type
from agentx_syscall.registry import build_phase1_registry
from pymongo import AsyncMongoClient

DOGFOOD_TARGET: JsonObject = {
    "icp": "founders, agencies, and SMB operators buying an AI lead-finder",
    "location": "United States and India",
    "count": 3,
}


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
    exa_ok = settings.exa_api_key is not None and bool(settings.exa_api_key.get_secret_value().strip())
    firecrawl_ok = (
        settings.firecrawl_api_key is not None and bool(settings.firecrawl_api_key.get_secret_value().strip())
    )
    if not (exa_ok or firecrawl_ok):
        missing.append("EXA_API_KEY or FIRECRAWL_API_KEY")
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
    instance_id = f"agentx_dogfood_{int(now.timestamp())}"
    trigger = DeadlineTrigger(ts=now, reason="live_dogfood_sweep", entity_id="agentx_dogfood_icp")

    client: AsyncMongoClient[dict[str, object]] = AsyncMongoClient(settings.mongodb_uri.get_secret_value())
    try:
        await client.admin.command("ping")
        database = client[settings.mongodb_db_name]
        await ensure_indexes(database)

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
        control = KernelControl(journal=journal, projections=projections, projection_store=projection_store)
        scheduler_store = MongoSchedulerStore(database)
        worker = SchedulerWorker(store=scheduler_store, invoker=invoker)
        canonical_mandate = build_lead_finder_type()
        # Skip-if-exists guard: the type persists across runs, so re-registering
        # the same id raises MandateTypeConflict. (Mirrors run_mandate_discovery.)
        existing = await projection_store.find(c.MANDATE_TYPE, {"id": canonical_mandate.id})
        if existing:
            print(f"INFO MandateType {canonical_mandate.id!r} already registered; skipping re-registration")
        else:
            await control.register_mandate_type(canonical_mandate)
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
        # Target is overridable via env so the same script can validate a
        # mandate-discovery pick (its target segment becomes the lead-finder ICP).
        target = dict(DOGFOOD_TARGET)
        if os.environ.get("LEAD_FINDER_ICP", "").strip():
            target["icp"] = os.environ["LEAD_FINDER_ICP"].strip()
        if os.environ.get("LEAD_FINDER_LOCATION", "").strip():
            target["location"] = os.environ["LEAD_FINDER_LOCATION"].strip()
        if os.environ.get("LEAD_FINDER_COUNT", "").strip().isdigit():
            target["count"] = int(os.environ["LEAD_FINDER_COUNT"].strip())
        print(f"LEAD_FINDER_TARGET={target}")
        mandate.charter.target = dict(target)

        pending_due = await database[c.SCHEDULER_WORK].count_documents(
            {"status": "pending", "available_at": {"$lte": datetime.now(UTC)}}
        )
        if pending_due:
            raise RuntimeError(f"refusing live run with {pending_due} unrelated due scheduler item(s)")
        l1_started = perf_counter()
        trigger_work = TriggerWork.schedule(
            mandate=mandate,
            instance=instance,
            trigger=trigger,
            mode="live",
        )
        await scheduler_store.enqueue(trigger_work)
        parked = await worker.run_once(datetime.now(UTC))
        if parked is None:
            raise RuntimeError("scheduler worker found no trigger work")
        l1_seconds = perf_counter() - l1_started
        if parked.state != "parked" or parked.park is None:
            raise RuntimeError(f"expected L1 approval park, got state={parked.state}")

        inbox = await control.approval_inbox(instance_id=instance_id)
        approval_started = perf_counter()
        await control.approve(
            instance_id=instance_id,
            run_id=parked.run_id,
            actor="manager:codex-live-validation",
            now=datetime.now(UTC),
        )

        card = parked.park.approval_card
        syscall = card.get("syscall")
        idem = card.get("idempotency_key")
        if syscall != "draft_email" or not isinstance(idem, str):
            raise RuntimeError(f"approval card cannot resume draft_email: {card}")
        approval = next(
            (
                event
                for event in reversed(await journal.read_run(parked.run_id))
                if isinstance(event, ApprovalResolved)
            ),
            None,
        )
        if approval is None:
            raise RuntimeError("approval command did not append ApprovalResolved")
        approval_work = ApprovalWork.schedule(approval)
        await scheduler_store.enqueue(approval_work)
        resumed = await worker.run_once(datetime.now(UTC))
        if resumed is None:
            raise RuntimeError("scheduler worker found no approval work")
        if resumed.state != "settled":
            raise RuntimeError(f"kernel resume did not settle: {resumed.state}")
        draft_receipt = await receipts.get(idem)
        if draft_receipt is None or draft_receipt.result.status != "ok":
            raise RuntimeError("draft_email receipt missing after kernel resume")
        approval_seconds = perf_counter() - approval_started

        heap_facts = await projection_store.find(c.HEAP_FACT, {"instance_id": instance_id})
        run_events = await journal.read_run(parked.run_id)
        trace_rows = await projection_store.find(c.SYSCALL_TRACE, {"run_id": parked.run_id})
        settled = next(event for event in reversed(run_events) if isinstance(event, RunSettled))

        print(f"INSTANCE_ID={instance_id}")
        print(f"RUN_ID={parked.run_id}")
        print(f"TRIGGER_WORK_ID={trigger_work.work_id}")
        print(f"APPROVAL_WORK_ID={approval_work.work_id}")
        print(f"L1_STATE={parked.state} reason={parked.park.reason}")
        print(f"APPROVAL_INBOX_COUNT_BEFORE={len(inbox.items)}")
        print(
            f"DRAFT_STATUS={draft_receipt.result.status} "
            f"fulfilled_by={draft_receipt.result.fulfilled_by}"
        )
        print(f"SETTLED_EVENT={settled.event_id} seq={settled.seq}")
        print(f"HEAP_FACT_COUNT={len(heap_facts)}")
        print(f"JOURNAL_KINDS={','.join(event.kind for event in run_events)}")
        print(f"SYSCALL_TRACE_ROWS={len(trace_rows)}")
        print(f"LATENCY_SECONDS l1={l1_seconds:.2f} approval_to_settle={approval_seconds:.2f}")
        print("COST_OBSERVED=not_available_from_current_wrappers")
        print("TRACE")
        for event in resumed.trace.events:
            print(f"  {event.seq}. {event.kind}: {event.summary} {event.detail}")
        if heap_facts:
            first = heap_facts[0]
            provenance = first.get("provenance")
            print(f"FIRST_HEAP_FACT_ID={first.get('id')} provenance={provenance}")
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
