"""SESSION D (eval) scratch inspector — NOT committed product code.

Runs ONE live lead-finder instance end-to-end (park -> approve -> draft -> verify -> settle) like
scripts/run_lead_finder.py, but ALSO surfaces what the thin runner hides: the rendered draft_email
body, every settled heap fact (subject/predicate/object/provenance/status), and the thread/resume/
watch/syscall_trace projections + journal seq monotonicity. ICP is overridable via env so we can run
two different ICPs without mutating the committed script.

Usage:  AGENTX_EVAL_ICP_JSON='{"icp":"...","location":"...","count":3}' uv run python scripts/_eval_d_inspect.py
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
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

DEFAULT_TARGET: JsonObject = {
    "icp": "founders, agencies, and SMB operators buying an AI lead-finder",
    "location": "United States and India",
    "count": 3,
}


def _target() -> JsonObject:
    raw = os.environ.get("AGENTX_EVAL_ICP_JSON")
    if raw:
        loaded = json.loads(raw)
        assert isinstance(loaded, dict)
        return loaded
    return DEFAULT_TARGET


def _instance(instance_id: str, ring: Ring) -> InstanceBinding:
    return InstanceBinding(
        instance_id=instance_id, type_ref="lead-finder@0.1.0", ring=ring,
        heap_region_id=f"tenant_{instance_id}",
    )


def _dump(label: str, obj: object) -> None:
    print(f"\n----- {label} -----")
    print(json.dumps(obj, indent=2, default=str))


async def main() -> int:
    settings = Settings()
    target = _target()
    now = datetime.now(UTC)
    instance_id = f"agentx_evald_{int(now.timestamp())}"
    print(f"ICP_TARGET={json.dumps(target)}")

    mandate = build_lead_finder_type()
    mandate.charter.target = target
    trigger = DeadlineTrigger(ts=now, reason="evald_sweep", entity_id="agentx_evald_icp")

    client: AsyncMongoClient[dict[str, object]] = AsyncMongoClient(settings.mongodb_uri.get_secret_value())
    try:
        await client.admin.command("ping")
        database = client[settings.mongodb_db_name]
        await ensure_indexes(database)
        journal = MongoJournalStore(database)
        pstore = MongoProjectionStore(database)
        projections = Projections(pstore, journal)
        gateway = Gateway(
            journal=journal,
            vault=ConfigVault(settings),
            registry=build_phase1_registry(),
            receipts=MongoSyscallReceiptStore(database),
        )
        hydration = HydrationLoader(pstore, journal)
        settlement = SettlementCommitter(journal=journal, projections=projections)
        invoker = Phase1RunInvoker(
            journal=journal, projections=projections, hydration=hydration, gateway=gateway,
            settlement=settlement, verifier=RulesVerifier(), reasoner=HermesClient.from_settings(settings),
        )
        control = KernelControl(journal=journal, projections=projections, projection_store=pstore)

        t0 = perf_counter()
        parked = await invoker.invoke(mandate=mandate, instance=_instance(instance_id, "L1"),
                                      trigger=trigger, mode="live")
        l1 = perf_counter() - t0
        if parked.state != "parked" or parked.park is None:
            raise RuntimeError(f"expected park, got {parked.state}")

        print(f"INSTANCE_ID={instance_id}")
        print(f"RUN_ID={parked.run_id}")
        print(f"L1_STATE={parked.state} reason={parked.park.reason} required_ring={parked.park.required_ring}")
        print(f"L1_LATENCY_S={l1:.2f}")

        print("\n===== TRACE (full) =====")
        for ev in parked.trace.events:
            print(f"  {ev.seq}. {ev.kind}: {ev.summary} :: {json.dumps(ev.detail, default=str)[:1500]}")

        # The draft body lives in the approval card args (what the manager would see / approve).
        _dump("APPROVAL_CARD (what a dashboard must surface)", parked.park.approval_card)

        # Dashboard contract probe: what does approval_inbox actually expose?
        inbox = await control.approval_inbox(instance_id=instance_id)
        _dump("APPROVAL_INBOX items (KernelControl.approval_inbox)",
              [i.model_dump(mode="json") for i in inbox.items])

        t1 = perf_counter()
        await control.approve(instance_id=instance_id, run_id=parked.run_id,
                              actor="manager:evald", now=datetime.now(UTC))
        card = parked.park.approval_card
        raw_args = card.get("args")
        raw_idempotency_key = card.get("idempotency_key")
        if not isinstance(raw_args, dict) or not isinstance(raw_idempotency_key, str):
            raise RuntimeError(f"invalid approval card: {card}")
        draft = await gateway.invoke(
            SyscallRequest(name="draft_email", args=raw_args, instance_id=instance_id,
                           run_id=parked.run_id, idempotency_key=raw_idempotency_key,
                           ring="L2", risk_class="external_message"),
            GatewayContext(instance_id=instance_id, run_id=parked.run_id,
                           tenant_id=f"tenant_{instance_id}", ring="L2", now=datetime.now(UTC)),
        )
        if draft.result is None or draft.result.status != "ok":
            raise RuntimeError(f"draft failed: {draft}")
        if draft.attempted is not None:
            await projections.apply(draft.attempted)
        if draft.settled is not None:
            await projections.apply(draft.settled)

        _dump("RENDERED DRAFT (draft_email adapter output)", draft.result.output)

        verify = invoker.verifier.verify_postconditions(mandate, claimed_facts=parked.claimed_facts)
        await journal.append(RunVerified(event_id=f"{parked.run_id}:verified:approved", seq=0,
                                         ts=datetime.now(UTC), instance_id=instance_id,
                                         run_id=parked.run_id, rungs_passed=verify.rungs_passed))
        settled = await settlement.commit(build_settlement(
            run=MandateRun(id=parked.run_id, instance_id=instance_id, type_ref="lead-finder@0.1.0",
                           trigger=trigger, state="verifying", trace=parked.trace,
                           claimed_facts=parked.claimed_facts, created_at=trigger.ts),
            rules=mandate.settlement, verified_facts=parked.claimed_facts,
            trigger_ctx={"success": True, "thread_state": "settled"}, now=datetime.now(UTC)))
        settle_s = perf_counter() - t1
        print(f"\nSETTLED_EVENT={settled.event_id} seq={settled.seq} VERIFY_PASSED={verify.passed} "
              f"rungs={verify.rungs_passed}")
        print(f"APPROVAL_TO_SETTLE_S={settle_s:.2f}")

        # ---- MEMORY / HEAP HEALTH (E6) ----
        heap = await pstore.find(c.HEAP_FACT, {"instance_id": instance_id})
        _dump(f"HEAP FACTS (count={len(heap)}) — settled, with provenance", heap)
        thread = await pstore.find(c.THREAD, {"instance_id": instance_id})
        _dump("THREAD docs", thread)
        resume = await pstore.get(c.RESUME, instance_id)
        _dump("RESUME doc", resume)
        watch = await pstore.find(c.WATCH, {"instance_id": instance_id})
        _dump(f"WATCH docs (count={len(watch)})", watch)
        trace_rows = await pstore.find(c.SYSCALL_TRACE, {"run_id": parked.run_id})
        _dump(f"SYSCALL_TRACE rows (count={len(trace_rows)})", trace_rows)

        # ---- EVENT SOURCING (E3): journal kinds + per-instance seq monotonicity ----
        events = await journal.read_instance(instance_id)
        seqs = [(e.seq, e.kind) for e in events]
        monotonic = all(seqs[i][0] < seqs[i + 1][0] for i in range(len(seqs) - 1))
        print(f"\nJOURNAL_EVENT_COUNT={len(events)} SEQ_STRICTLY_INCREASING={monotonic}")
        print("JOURNAL_SEQ_KINDS=" + ", ".join(f"{s}:{k}" for s, k in seqs))
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
