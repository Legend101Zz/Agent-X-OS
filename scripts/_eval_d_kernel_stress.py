"""SESSION D (eval) scratch — kernel stress probe (E3). NOT committed product code.

Exercises the gateway directly (in-memory stores, real Gateway + build_phase1_registry):
 1. idempotency replay: same idempotency_key twice -> no double effect; inspect replayed output.
 2. rings L0/L1/L2: draft_email parks below L2, executes at L2.
 3. unsupported intent + score_lead (no adapter) -> human_task terminal tail (nothing "unimplemented").
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from agentx_contracts.enums import Ring
from agentx_contracts.journal import SyscallSettled
from agentx_contracts.syscall import GatewayContext, SyscallRequest
from agentx_kernel.gateway import Gateway
from agentx_kernel.stores.memory import InMemoryJournalStore, InMemorySyscallReceiptStore, InMemoryVault
from agentx_syscall.registry import build_phase1_registry


def _ctx(instance_id: str, ring: Ring) -> GatewayContext:
    return GatewayContext(instance_id=instance_id, run_id=f"{instance_id}:run", tenant_id=f"tenant_{instance_id}",
                          ring=ring, now=datetime.now(UTC))


def _draft_req(instance_id: str, idem: str) -> SyscallRequest:
    return SyscallRequest(name="draft_email",
                          args={"to": "x@y.z", "subject": "S", "body": "B"},
                          instance_id=instance_id, run_id=f"{instance_id}:run",
                          idempotency_key=idem, ring="L2", risk_class="external_message")


async def main() -> int:
    # ---------- 1. IDEMPOTENCY ----------
    print("===== 1. IDEMPOTENCY (replay must not double-effect) =====")
    j = InMemoryJournalStore()
    gw = Gateway(
        journal=j,
        vault=InMemoryVault(),
        registry=build_phase1_registry(),
        receipts=InMemorySyscallReceiptStore(),
    )
    iid = "idem_inst"
    idem = f"{iid}:run:draft_email"
    first = await gw.invoke(_draft_req(iid, idem), _ctx(iid, "L2"))
    second = await gw.invoke(_draft_req(iid, idem), _ctx(iid, "L2"))
    assert first.result is not None
    assert second.result is not None
    settled_for_key = [e for e in await j.read_instance(iid)
                       if isinstance(e, SyscallSettled) and e.idempotency_key == idem]
    print(f"FIRST  status={first.result.status} body_in_output={'body' in (first.result.output or {})} "
          f"output={json.dumps(first.result.output)}")
    print(f"SECOND status={second.result.status} attempted_event={second.attempted} settled_event={second.settled} "
          f"output={json.dumps(second.result.output)}")
    print(f"SyscallSettled events for idem key = {len(settled_for_key)}  (expect 1 = no double effect)")
    print(f"REPLAY_LOSSY = {first.result.output != second.result.output}  "
          f"(True => replay drops the original output payload)")

    # ---------- 2. RINGS ----------
    print("\n===== 2. RINGS (draft_email requires L2) =====")
    for ring in ("L0", "L1", "L2"):
        ji = InMemoryJournalStore()
        gwi = Gateway(
            journal=ji,
            vault=InMemoryVault(),
            registry=build_phase1_registry(),
            receipts=InMemorySyscallReceiptStore(),
        )
        rid = f"ring_{ring}"
        out = await gwi.invoke(_draft_req(rid, f"{rid}:run:draft_email"), _ctx(rid, ring))
        if out.parked is not None:
            print(f"  ring={ring}: PARKED reason='{out.parked.reason}' required_ring={out.parked.required_ring} "
                  f"awaiting={out.parked.awaiting}")
        elif out.result is not None:
            print(f"  ring={ring}: EXECUTED status={out.result.status} fulfilled_by={out.result.fulfilled_by} "
                  f"sent={out.result.output.get('sent')}")

    # ---------- 3. UNSUPPORTED INTENT + score_lead -> human_task tail ----------
    print("\n===== 3. UNSUPPORTED INTENT -> human_task terminal tail (nothing 'unimplemented') =====")
    for name in ("translate_document", "score_lead", "lead_research_batch"):
        ji = InMemoryJournalStore()
        gwi = Gateway(
            journal=ji,
            vault=InMemoryVault(),
            registry=build_phase1_registry(),
            receipts=InMemorySyscallReceiptStore(),
        )
        hid = f"h_{name}"
        req = SyscallRequest(name=name, args={"criteria": {"icp": "x"}, "count": 1},
                             instance_id=hid, run_id=f"{hid}:run",
                             idempotency_key=f"{hid}:run:{name}", ring="L0", risk_class="read")
        out = await gwi.invoke(req, _ctx(hid, "L0"))
        if out.result is not None:
            print(f"  intent={name:20s} -> status={out.result.status} fulfilled_by={out.result.fulfilled_by} "
                  f"maturity={out.result.maturity_used}")
        elif out.parked is not None:
            print(f"  intent={name:20s} -> PARKED {out.parked.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
