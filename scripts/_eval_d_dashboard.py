"""SESSION D (eval) scratch — dashboard contract probe (E5). NOT committed product code.

Proves the approval-card reconstruction bug: the dashboard API reconstructs the "drafted_effect" a manager
approves from the LAST SyscallAttempted in the journal (api/state.py:_drafted_effect). But the real gateway
parks for insufficient ring BEFORE journaling any SyscallAttempted (gateway.py:78-85 returns before the
append at :122). So on a REAL parked draft_email run there is no draft SyscallAttempted -> the card shows the
WRONG effect (the earlier research read) instead of the draft. The api seed_demo masks this by manually
inserting a SyscallAttempted(draft_email) before RunParked (state.py:260-293) — which a real run never does.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from agentx_contracts.journal import JournalEvent, SyscallAttempted
from agentx_contracts.trigger import DeadlineTrigger
from agentx_kernel.control import KernelControl
from agentx_kernel.gateway import Gateway
from agentx_kernel.hydration import HydrationLoader
from agentx_kernel.projections import Projections
from agentx_kernel.run_loop import Phase1RunInvoker
from agentx_kernel.settlement import SettlementCommitter
from agentx_kernel.stores.memory import (
    InMemoryJournalStore,
    InMemoryProjectionStore,
    InMemorySyscallReceiptStore,
    InMemoryVault,
)
from agentx_kernel.verifier import RulesVerifier
from agentx_mandate.library.lead_finder import build_lead_finder_type
from agentx_syscall.registry import build_phase1_registry


def _drafted_effect(events: list[JournalEvent]) -> dict[str, object] | None:
    """Faithful copy of api/src/agentx_api/state.py:_drafted_effect (the dashboard card reconstruction)."""
    for event in reversed(events):
        if isinstance(event, SyscallAttempted):
            return {"syscall": event.syscall, "args": event.args, "required_ring": event.ring_required}
    return None


async def main() -> int:
    journal = InMemoryJournalStore()
    store = InMemoryProjectionStore()
    projections = Projections(store, journal)
    gateway = Gateway(
        journal=journal,
        vault=InMemoryVault(),
        registry=build_phase1_registry(),
        receipts=InMemorySyscallReceiptStore(),
    )
    invoker = Phase1RunInvoker(
        journal=journal, projections=projections, hydration=HydrationLoader(store, journal),
        gateway=gateway, settlement=SettlementCommitter(journal=journal, projections=projections),
        verifier=RulesVerifier(), reasoner=None,
    )
    control = KernelControl(journal=journal, projections=projections, projection_store=store)

    from agentx_contracts.mandate import InstanceBinding
    inst = InstanceBinding(instance_id="inst_dash", type_ref="lead-finder@0.1.0", ring="L1",
                           heap_region_id="heap_dash")
    # sim mode at L1: research fulfilled natively -> draft_email Call hits gateway -> parks (L1 < L2).
    parked = await invoker.invoke(mandate=build_lead_finder_type(), instance=inst,
                                  trigger=DeadlineTrigger(ts=datetime.now(UTC), reason="dash probe",
                                                          entity_id="dash_icp"),
                                  mode="sim")
    print(f"RUN_STATE={parked.state} (expect parked)")

    events = await journal.read_run(parked.run_id)
    kinds = [e.kind for e in events]
    print(f"JOURNAL_KINDS_AT_PARK={kinds}")
    attempted = [e.syscall for e in events if isinstance(e, SyscallAttempted)]
    print(f"SyscallAttempted_in_journal_at_park={attempted}  (note: NO draft_email)")

    inbox = await control.approval_inbox(instance_id=inst.instance_id)
    print(f"\nKernelControl.approval_inbox items = {[i.model_dump(mode='json') for i in inbox.items]}")
    print("  ^ no syscall/args/draft -> a manager would approve BLIND from KernelControl alone")

    # What the dashboard reconstructs as the effect to approve:
    drafted = _drafted_effect(events)
    print(f"\nDASHBOARD drafted_effect(events) = {json.dumps(drafted)}")
    if drafted is not None and drafted.get("syscall") == "draft_email":
        print("  -> shows draft_email (CORRECT)")
    else:
        shown = drafted.get("syscall") if drafted else None
        print(f"  -> shows '{shown}', NOT draft_email == BUG: manager sees the wrong/earlier effect, "
              f"and never sees the actual draft body they're approving.")

    # In-memory state of parked.park.approval_card DOES have the draft — but it is never journaled:
    print(f"\nIN-MEMORY parked.park.approval_card (lost on process exit, never persisted) = "
          f"{json.dumps(parked.park.approval_card) if parked.park else None}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
