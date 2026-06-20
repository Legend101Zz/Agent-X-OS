"""LIVE PROOF: a lead-finder run sends ONE real email on human approval.

Gated on RUN_LIVE_EMAIL=1 (set here) + SMTP_* in the repo ``.env``. The email is sent FROM and TO
the founder's own ``EMAIL_FROM`` (send-to-self dogfood) — the first real outbound settle. The flow
is the same the dashboard drives: instantiate (L1) -> trigger-run -> PARK (no send) -> approve ->
resume -> real send. Prints the SMTP Message-ID receipt.

Run from the api package env so ``agentx_api`` imports:

    cd api && uv run python ../scripts/_send_loop_live_proof.py
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import Any

os.environ.setdefault("RUN_LIVE_EMAIL", "1")


class _CapturingTransport:
    """Wrap the real transport to record each receipt while really sending."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.name = inner.name
        self.receipts: list[Any] = []

    async def send(self, **kwargs: Any) -> Any:
        receipt = await self.inner.send(**kwargs)
        self.receipts.append(receipt)
        return receipt


def _now() -> datetime:
    return datetime.now(UTC)


async def _drive(app: Any, *, max_ticks: int = 8) -> Any:
    last = None
    for _ in range(max_ticks):
        result = await app.state.dashboard.runtime.worker.run_once(_now())
        if result is None:
            break
        last = result
    return last


def _print_errors(run_result: Any) -> None:
    trace = getattr(run_result, "trace", None)
    if trace is None:
        return
    for event in trace.events:
        if event.kind == "error":
            print(f"  trace error: {event.summary} :: {event.detail}")


async def main() -> int:
    from agentx_api.app import create_app
    from agentx_syscall.email_transports import _read_env_value, build_configured_email_transport
    from httpx import ASGITransport, AsyncClient

    sender = _read_env_value("EMAIL_FROM") or _read_env_value("SMTP_USERNAME")
    if not sender:
        print("ABORT: EMAIL_FROM/SMTP_USERNAME not set in .env")
        return 1
    real = build_configured_email_transport()
    if real is None:
        print("ABORT: no live transport (need RUN_LIVE_EMAIL=1 + SMTP_HOST+SMTP_PASSWORD in .env)")
        return 1
    print(f"transport={real.name}  sender={sender}")
    capture = _CapturingTransport(real)

    app = create_app(
        use_mongo=False,
        seed_demo=False,
        operator_token="live-proof",
        start_worker=False,
        send_email_transport=capture,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://live",
        headers={"Authorization": "Bearer live-proof"},
    ) as client:
        inst = await client.post(
            "/commands/instantiate",
            json={
                "type_ref": "lead-finder@0.1.0",
                "customer_id": "Founder Dogfood",
                "business_name": "Founder Dogfood",
                "ring": "L1",
                "sender_identity": sender,
                "target_override": {"icp": "dental clinics", "location": "Pune", "count": 1},
            },
        )
        instance_id = inst.json()["instance"]["id"]
        print(f"instantiated {instance_id} (ring L1, sender={sender})")

        await client.post("/commands/trigger-run", json={"instance_id": instance_id, "mode": "sim"})
        parked = await _drive(app)
        print(f"after trigger: state={getattr(parked, 'state', None)}  sends_so_far={len(capture.receipts)}")
        if parked is None or parked.state != "parked":
            print("ABORT: expected a parked outreach awaiting approval")
            return 1
        if capture.receipts:
            print("ABORT: an email was sent BEFORE approval — gate violated")
            return 1
        run_id = parked.run_id

        approvals = (await client.get("/approvals", params={"instance_id": instance_id})).json()
        card = approvals["items"][0]["drafted_effect"]
        args = card["args"]
        print(f"approval card: syscall={card['syscall']}  to={args.get('to')}")
        print(f"  subject={args.get('subject')!r}")

        print(">>> APPROVING (the human gate) ...")
        await client.post(
            "/commands/approve",
            json={"instance_id": instance_id, "run_id": run_id, "actor": "founder:live-proof"},
        )
        settled = await _drive(app)
        print(f"after approve: state={getattr(settled, 'state', None)}  sends={len(capture.receipts)}")

        if not capture.receipts:
            print("FAIL: no real send after approval. Diagnostics:")
            _print_errors(settled)
            return 1
        receipt = capture.receipts[-1]
        print("=== REAL SEND RECEIPT ===")
        print(f"  message_id = {receipt.message_id}")
        print(f"  from       = {receipt.from_addr}")
        print(f"  to         = {receipt.to}")
        print(f"  subject    = {receipt.subject}")
        print(f"  accepted   = {receipt.accepted}")
        print(f"sends total  = {len(capture.receipts)} (must be 1)")
        print(f"run state    = {getattr(settled, 'state', None)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
