"""Session F live diagnostic / proof instrument — run the LLM-driven loop and print the FULL trace
regardless of outcome (no raise), so we can see the trajectory + any crash reason.

ICP override:  AGENTX_EVAL_ICP_JSON='{"icp":"...","location":"...","count":3}' uv run python scripts/_f_diag_live.py
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime

from agentx_contracts.config import Settings
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
from agentx_kernel.settlement import SettlementCommitter
from agentx_kernel.stores.mongo import (
    MongoJournalStore,
    MongoProjectionStore,
    MongoRunContinuationStore,
    MongoSyscallReceiptStore,
)
from agentx_kernel.vault import ConfigVault
from agentx_kernel.verifier import RulesVerifier
from agentx_mandate.library.lead_finder import build_lead_finder_type
from agentx_syscall.registry import build_phase1_registry
from pymongo import AsyncMongoClient

DEFAULT_ICP = {
    "icp": "founders, agencies, and SMB operators buying an AI lead-finder",
    "location": "United States and India",
    "count": 3,
}


class LoggingTransport:
    """Wraps the chat transport to print, per turn, what the model SAW and the action it chose."""

    def __init__(self, inner: HermesClient) -> None:
        self._inner = inner
        self.turn = 0

    async def complete_chat(
        self, *, messages: list[dict[str, object]], tools: list[dict[str, object]]
    ) -> dict[str, object]:
        response = await self._inner.complete_chat(messages=messages, tools=tools)
        self.turn += 1
        last = messages[-1]
        print(f"-- TURN {self.turn} | model saw [{last.get('role')}]: {str(last.get('content'))[:500]}")
        choices = response.get("choices")
        msg = choices[0]["message"] if isinstance(choices, list) and choices else {}
        tcs = msg.get("tool_calls") if isinstance(msg, dict) else None
        if isinstance(tcs, list) and tcs:
            fn = tcs[0]["function"]
            print(f"   -> CALLED {fn['name']}({str(fn['arguments'])[:400]})")
        else:
            print(f"   -> NO TOOL CALL; content={str(msg.get('content'))[:300] if isinstance(msg, dict) else None}")
        return response


def _icp() -> dict[str, object]:
    raw = os.environ.get("AGENTX_EVAL_ICP_JSON")
    if raw:
        loaded = json.loads(raw)
        if isinstance(loaded, dict):
            return loaded
    return dict(DEFAULT_ICP)


async def main() -> int:
    settings = Settings()
    now = datetime.now(UTC)
    instance_id = f"agentx_f_{int(now.timestamp())}"
    trigger = DeadlineTrigger(ts=now, reason="session_f_live", entity_id="agentx_f_icp")

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
        invoker = Phase1RunInvoker(
            journal=journal,
            projections=projections,
            hydration=HydrationLoader(pstore, journal),
            gateway=gateway,
            settlement=SettlementCommitter(journal=journal, projections=projections),
            verifier=RulesVerifier(),
            continuations=MongoRunContinuationStore(database),
            runner=HermesRunner(transport=LoggingTransport(HermesClient.from_settings(settings))),
        )
        control = KernelControl(journal=journal, projections=projections, projection_store=pstore)
        mandate = build_lead_finder_type()
        await control.register_mandate_type(mandate)
        await control.instantiate_mandate(
            MandateInstance(
                id=instance_id,
                type_ref=f"{mandate.name}@{mandate.version}",
                customer_id="Agent-X session F",
                ring="L1",
                heap_region_id=f"tenant_{instance_id}",
            )
        )
        instance = await control.instance_binding(instance_id)
        mandate = mandate.model_copy(deep=True)
        mandate.charter.target = _icp()

        result = await invoker.invoke(mandate=mandate, instance=instance, trigger=trigger, mode="live")

        print(f"ICP={json.dumps(mandate.charter.target)}")
        print(f"INSTANCE_ID={instance_id}")
        print(f"RUN_ID={result.run_id}")
        print(f"STATE={result.state}")
        print(f"CLAIMED_FACTS={len(result.claimed_facts)}")
        for fact in result.claimed_facts:
            print(f"  FACT {fact.predicate} subject={fact.subject} object={fact.object!r}")
            print(f"       evidence={fact.provenance.evidence}")
        if result.park is not None:
            print(f"PARK reason={result.park.reason} awaiting={result.park.awaiting}")
            print(f"APPROVAL_CARD={json.dumps(result.park.approval_card)}")
        print("TRACE")
        for event in result.trace.events:
            print(f"  {event.seq}. [{event.kind}] {event.summary} :: {json.dumps(event.detail)[:600]}")
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
