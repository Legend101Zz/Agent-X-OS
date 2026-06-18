"""Run one Phase-1 lead-finder instance against live services.

This is intentionally a thin wiring script: kernel package code still depends only on Protocols.
The script composes the live Mongo stores, live Hermes reasoner, and syscall registry at the edge.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from importlib.util import find_spec
from time import perf_counter

import agentx_db.collections as c
from agentx_contracts.config import Settings
from agentx_contracts.enums import Ring
from agentx_contracts.journal import RunVerified
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.mandate import InstanceBinding, MandateRun
from agentx_contracts.syscall import GatewayContext, SyscallRequest
from agentx_contracts.trigger import DeadlineTrigger
from agentx_db.setup import ensure_indexes
from agentx_kernel.control import KernelControl
from agentx_kernel.gateway import Gateway
from agentx_kernel.hermes import HermesClient
from agentx_kernel.hydration import HydrationLoader
from agentx_kernel.projections import Projections
from agentx_kernel.run_loop import Phase1RunInvoker
from agentx_kernel.settlement import SettlementCommitter
from agentx_kernel.stores.mongo import MongoJournalStore, MongoProjectionStore, MongoSyscallReceiptStore
from agentx_kernel.vault import ConfigVault
from agentx_kernel.verifier import RulesVerifier
from agentx_mandate.library.lead_finder import build_lead_finder_type
from agentx_mandate.settlement import build_settlement
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


def _instance(instance_id: str, ring: Ring) -> InstanceBinding:
    return InstanceBinding(
        instance_id=instance_id,
        type_ref="lead-finder@0.1.0",
        ring=ring,
        heap_region_id=f"tenant_{instance_id}",
    )


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
    mandate = build_lead_finder_type()
    mandate.charter.target = DOGFOOD_TARGET
    trigger = DeadlineTrigger(ts=now, reason="live_dogfood_sweep", entity_id="agentx_dogfood_icp")

    client: AsyncMongoClient[dict[str, object]] = AsyncMongoClient(settings.mongodb_uri.get_secret_value())
    try:
        await client.admin.command("ping")
        database = client[settings.mongodb_db_name]
        await ensure_indexes(database)

        journal = MongoJournalStore(database)
        projection_store = MongoProjectionStore(database)
        projections = Projections(projection_store, journal)
        gateway = Gateway(
            journal=journal,
            vault=ConfigVault(settings),
            registry=build_phase1_registry(),
            receipts=MongoSyscallReceiptStore(database),
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
            reasoner=HermesClient.from_settings(settings),
        )
        control = KernelControl(journal=journal, projections=projections, projection_store=projection_store)

        l1_started = perf_counter()
        parked = await invoker.invoke(
            mandate=mandate,
            instance=_instance(instance_id, "L1"),
            trigger=trigger,
            mode="live",
        )
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
        raw_args = card.get("args")
        idem = card.get("idempotency_key")
        if syscall != "draft_email" or not isinstance(raw_args, dict) or not isinstance(idem, str):
            raise RuntimeError(f"approval card cannot resume draft_email: {card}")

        draft = await gateway.invoke(
            SyscallRequest(
                name="draft_email",
                args=raw_args,
                instance_id=instance_id,
                run_id=parked.run_id,
                idempotency_key=idem,
                ring="L2",
                risk_class="external_message",
            ),
            GatewayContext(
                instance_id=instance_id,
                run_id=parked.run_id,
                tenant_id=f"tenant_{instance_id}",
                ring="L2",
                now=datetime.now(UTC),
            ),
        )
        if draft.result is None or draft.result.status != "ok":
            raise RuntimeError(f"draft_email did not complete after approval: {draft}")
        if draft.attempted is not None:
            await projections.apply(draft.attempted)
        if draft.settled is not None:
            await projections.apply(draft.settled)

        verify = invoker.verifier.verify_postconditions(mandate, claimed_facts=parked.claimed_facts)
        if not verify.passed:
            raise RuntimeError(f"postcondition verification failed: {verify.reasons}")
        await journal.append(
            RunVerified(
                event_id=f"{parked.run_id}:verified:approved",
                seq=0,
                ts=datetime.now(UTC),
                instance_id=instance_id,
                run_id=parked.run_id,
                rungs_passed=verify.rungs_passed,
            )
        )

        settlement_event = build_settlement(
            run=MandateRun(
                id=parked.run_id,
                instance_id=instance_id,
                type_ref="lead-finder@0.1.0",
                trigger=trigger,
                state="verifying",
                trace=parked.trace,
                claimed_facts=parked.claimed_facts,
                created_at=trigger.ts,
            ),
            rules=mandate.settlement,
            verified_facts=parked.claimed_facts,
            trigger_ctx={"success": True, "thread_state": "settled"},
            now=datetime.now(UTC),
        )
        settled = await settlement.commit(settlement_event)
        approval_seconds = perf_counter() - approval_started

        heap_facts = await projection_store.find(c.HEAP_FACT, {"instance_id": instance_id})
        run_events = await journal.read_run(parked.run_id)
        trace_rows = await projection_store.find(c.SYSCALL_TRACE, {"run_id": parked.run_id})

        print(f"INSTANCE_ID={instance_id}")
        print(f"RUN_ID={parked.run_id}")
        print(f"L1_STATE={parked.state} reason={parked.park.reason}")
        print(f"APPROVAL_INBOX_COUNT_BEFORE={len(inbox.items)}")
        print(f"DRAFT_STATUS={draft.result.status} fulfilled_by={draft.result.fulfilled_by}")
        print(f"SETTLED_EVENT={settled.event_id} seq={settled.seq}")
        print(f"HEAP_FACT_COUNT={len(heap_facts)}")
        print(f"JOURNAL_KINDS={','.join(event.kind for event in run_events)}")
        print(f"SYSCALL_TRACE_ROWS={len(trace_rows)}")
        print(f"LATENCY_SECONDS l1={l1_seconds:.2f} approval_to_settle={approval_seconds:.2f}")
        print("COST_OBSERVED=not_available_from_current_wrappers")
        print("TRACE")
        for event in parked.trace.events:
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
