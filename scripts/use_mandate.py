"""Operate the live lead-finder against a supplied lead or an ICP.

This is the human-in-the-loop CLI until the dashboard command path is complete. It runs live research,
prints the exact parked approval card, and resumes only after explicit operator approval.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import UTC, datetime
from importlib.util import find_spec

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Agent-X lead-finder against one supplied lead or an ICP."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--lead-url", help="Specific organisation URL to research and qualify.")
    target.add_argument("--icp", help="ICP to search for when no specific lead is supplied.")
    parser.add_argument("--lead-company", help="Company name for --lead-url mode.")
    parser.add_argument(
        "--task",
        default="Research this lead, qualify it using cited evidence, and draft truthful outreach.",
        help="Operator instruction for the mandate.",
    )
    parser.add_argument("--location", default="", help="Location context for ICP search.")
    parser.add_argument("--count", type=int, default=1, help="Requested candidate count for ICP mode.")
    parser.add_argument("--customer", default="Agent-X operator", help="Customer/business label.")
    parser.add_argument("--instance-id", help="Optional stable instance id; default creates a new one.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Approve the parked draft without an interactive prompt. Review output carefully.",
    )
    return parser.parse_args()


def build_target(args: argparse.Namespace) -> JsonObject:
    if args.lead_url:
        return {
            "lead_url": args.lead_url,
            "lead_company": args.lead_company or "",
            "task": args.task,
            "count": 1,
        }
    return {
        "icp": args.icp,
        "location": args.location,
        "count": max(1, args.count),
        "task": args.task,
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
    exa = settings.exa_api_key is not None and bool(settings.exa_api_key.get_secret_value().strip())
    firecrawl = (
        settings.firecrawl_api_key is not None and bool(settings.firecrawl_api_key.get_secret_value().strip())
    )
    if not (exa or firecrawl):
        missing.append("EXA_API_KEY or FIRECRAWL_API_KEY")
    return missing


def _missing_sdks(settings: Settings) -> list[str]:
    missing: list[str] = []
    if settings.exa_api_key is not None and settings.exa_api_key.get_secret_value().strip():
        if find_spec("exa_py") is None:
            missing.append("exa-py")
    if settings.firecrawl_api_key is not None and settings.firecrawl_api_key.get_secret_value().strip():
        if find_spec("firecrawl") is None:
            missing.append("firecrawl-py")
    return missing


def _instance_id(args: argparse.Namespace, now: datetime) -> str:
    if args.instance_id:
        return args.instance_id
    label = args.lead_company or args.icp or "lead"
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:32] or "lead"
    return f"agentx_{slug}_{int(now.timestamp())}"


def _approved(answer: str) -> bool:
    return answer.strip().lower() in {"y", "yes", "approve"}


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    missing = _missing_env(settings)
    if missing:
        print("STOP missing required .env values: " + ", ".join(missing))
        return 2
    missing_sdks = _missing_sdks(settings)
    if missing_sdks:
        print("STOP missing research SDK package(s): " + ", ".join(missing_sdks))
        return 2

    now = datetime.now(UTC)
    instance_id = _instance_id(args, now)
    target = build_target(args)
    trigger = DeadlineTrigger(ts=now, reason="operator_requested_lead_work", entity_id=instance_id)
    client: AsyncMongoClient[dict[str, object]] = AsyncMongoClient(settings.mongodb_uri.get_secret_value())
    try:
        await client.admin.command("ping")
        database = client[settings.mongodb_db_name]
        await ensure_indexes(database)
        journal = MongoJournalStore(database)
        store = MongoProjectionStore(database)
        projections = Projections(store, journal)
        receipts = MongoSyscallReceiptStore(database)
        invoker = Phase1RunInvoker(
            journal=journal,
            projections=projections,
            hydration=HydrationLoader(store, journal),
            gateway=Gateway(
                journal=journal,
                vault=ConfigVault(settings),
                registry=build_phase1_registry(),
                receipts=receipts,
            ),
            settlement=SettlementCommitter(journal=journal, projections=projections),
            verifier=RulesVerifier(),
            continuations=MongoRunContinuationStore(database),
            runner=HermesRunner(transport=HermesClient.from_settings(settings)),
        )
        control = KernelControl(journal=journal, projections=projections, projection_store=store)
        scheduler = MongoSchedulerStore(database)
        worker = SchedulerWorker(store=scheduler, invoker=invoker)

        mandate = build_lead_finder_type()
        await control.register_mandate_type(mandate)
        existing = {item.id for item in await control.list_mandate_instances()}
        if instance_id not in existing:
            await control.instantiate_mandate(
                MandateInstance(
                    id=instance_id,
                    type_ref=f"{mandate.name}@{mandate.version}",
                    customer_id=args.customer,
                    ring="L1",
                    heap_region_id=f"tenant_{instance_id}",
                )
            )
        instance = await control.instance_binding(instance_id)
        mandate = mandate.model_copy(deep=True)
        mandate.charter.target = target

        work = TriggerWork.schedule(mandate=mandate, instance=instance, trigger=trigger, mode="live")
        await scheduler.enqueue(work)
        print(f"INSTANCE_ID={instance_id}")
        print(f"TRIGGER_WORK_ID={work.work_id}")
        print(f"TARGET={json.dumps(target)}")
        print("Running live research; this may take several minutes and may incur provider/model cost...")
        result = await worker.run_once(datetime.now(UTC))
        if result is None:
            raise RuntimeError("scheduler found no trigger work")
        if result.state != "parked" or result.park is None:
            print(f"RUN_ID={result.run_id}")
            print(f"STATE={result.state}")
            print("The mandate did not produce an approval draft.")
            for event in result.trace.events:
                print(f"  {event.seq}. {event.kind}: {event.summary}")
            return 1 if result.state == "crashed" else 0

        print(f"\nRUN_ID={result.run_id}")
        print("STATE=parked — awaiting your approval")
        print("\nAPPROVAL CARD")
        print(json.dumps(result.park.approval_card, indent=2, default=str))
        if not args.yes:
            answer = input("\nApprove this draft and let the kernel resume + settle? [y/N]: ")
            if not _approved(answer):
                print("NOT APPROVED. The run remains parked in Mongo for later operator action.")
                return 0

        await control.approve(
            instance_id=instance_id,
            run_id=result.run_id,
            actor="manager:operator-cli",
            now=datetime.now(UTC),
        )
        approval = next(
            (
                event
                for event in reversed(await journal.read_run(result.run_id))
                if isinstance(event, ApprovalResolved)
            ),
            None,
        )
        if approval is None:
            raise RuntimeError("approval did not append ApprovalResolved")
        approval_work = ApprovalWork.schedule(approval)
        await scheduler.enqueue(approval_work)
        settled_result = await worker.run_once(datetime.now(UTC))
        if settled_result is None or settled_result.state != "settled":
            state = settled_result.state if settled_result is not None else "missing"
            raise RuntimeError(f"resume did not settle; state={state}")

        events = await journal.read_run(result.run_id)
        settled = next(event for event in reversed(events) if isinstance(event, RunSettled))
        facts = await store.find(c.HEAP_FACT, {"instance_id": instance_id})
        print("\nAPPROVED AND SETTLED")
        print(f"APPROVAL_WORK_ID={approval_work.work_id}")
        print(f"SETTLED_EVENT={settled.event_id} seq={settled.seq}")
        print(f"FACT_COUNT={len(facts)}")
        print("The effect is a stored draft only; no email was sent.")
        return 0
    finally:
        await client.close()


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
