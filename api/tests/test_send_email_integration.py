"""End-to-end integration tests for the Phase-1 send-email syscall through the API.

These tests exercise:
  - the api-edge wiring that registers one SendEmailAdapter per MandateInstance.channel_binding
  - the adapter's per-instance sender identity (no shared/global sender)
  - the live `send_email` syscall going through the full kernel gateway + adapter
  - the human_task tail taking over when no transport is configured

Per HERMES_BUILD_PLAN §Phase 1: the cleanest path is the email syscall as a maturity ladder — the
adapter is the heart of this phase; the api-edge wiring is a thin composition step. We use the
in-memory OperatorRuntime (no Mongo) so the tests run with the same harness as the dashboard
operability tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from agentx_contracts.syscall import GatewayContext, SyscallRequest
from agentx_syscall.adapters import SentEmailReceipt
from httpx import ASGITransport, AsyncClient

from agentx_api.app import create_app

# --- Fakes ---------------------------------------------------------------


@dataclass
class _SentCall:
    from_addr: str
    to: str
    subject: str
    body: str


class _RecordingTransport:
    """Records every send, returns a fresh receipt each time."""

    name = "fake_recording"

    def __init__(self) -> None:
        self.calls: list[_SentCall] = []

    async def send(self, *, from_addr: str, to: str, subject: str, body: str, **_kwargs: Any) -> SentEmailReceipt:
        self.calls.append(_SentCall(from_addr=from_addr, to=to, subject=subject, body=body))
        return SentEmailReceipt(
            message_id=f"fake_{len(self.calls)}",
            to=to,
            from_addr=from_addr,
            subject=subject,
        )


# --- Test fixtures -------------------------------------------------------


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(
        use_mongo=False,
        seed_demo=False,
        operator_token="test-token-send-email",
        start_worker=False,
        send_email_transport=_RecordingTransport(),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer test-token-send-email"},
    ) as test_client:
        yield test_client


async def _post(client: AsyncClient, path: str, payload: dict[str, Any]) -> Any:
    return await client.post(path, json=payload)


def _now() -> datetime:
    return datetime.now(UTC)


# --- Tests ---------------------------------------------------------------


async def test_runtime_registers_send_email_adapter_when_transport_supplied() -> None:
    """The composition edge registers a SendEmailAdapter (one rung of the ladder)."""
    recording = _RecordingTransport()
    app = create_app(
        use_mongo=False,
        seed_demo=False,
        operator_token="test-token-send-email-2",
        start_worker=False,
        send_email_transport=recording,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-token-send-email-2"},
    ) as _client:
        adapter_names = [a.name for a in app.state.dashboard.runtime.registry.adapters()]
        assert "send_email" in adapter_names


async def test_runtime_does_not_register_send_email_adapter_when_transport_none() -> None:
    """No transport -> no send_email rung on the ladder -> human_task tail takes over (invariant #5)."""
    app = create_app(
        use_mongo=False,
        seed_demo=False,
        operator_token="test-token-send-email-3",
        start_worker=False,
        send_email_transport=None,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-token-send-email-3"},
    ) as _client:
        adapter_names = [a.name for a in app.state.dashboard.runtime.registry.adapters()]
        assert "send_email" not in adapter_names

        # Resolution still works: a send_email call resolves to the human_task tail.
        runtime = app.state.dashboard.runtime
        next(
            (a for a in runtime.registry.adapters() if a.name == "send_email"),
            None,
        )
        # If not registered, the ladder resolves to human_task.
        ctx = GatewayContext(
            instance_id="inst_1",
            run_id="run_1",
            tenant_id="tenant_1",
            ring="L2",
            now=_now(),
        )
        req = SyscallRequest(
            name="send_email",
            args={"to": "x", "subject": "s", "body": "b"},
            instance_id="inst_1",
            run_id="run_1",
            idempotency_key="idem_unknown",
            ring="L2",
        )
        resolved = runtime.registry.resolve(req, ctx)
        assert resolved.name == "human_task"
        assert resolved.is_terminal_fallback is True


async def test_send_email_via_gateway_uses_instance_sender_identity() -> None:
    """End-to-end: gateway -> SendEmailAdapter -> transport with per-instance From."""
    recording = _RecordingTransport()
    app = create_app(
        use_mongo=False,
        seed_demo=False,
        operator_token="test-token-send-email-4",
        start_worker=False,
        send_email_transport=recording,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-token-send-email-4"},
    ) as _client:
        # First seed an instance with a ChannelBinding so the per-instance resolver finds the sender.
        from agentx_contracts.mandate import ChannelBinding, MandateInstance

        state = app.state.dashboard
        # Ensure the canonical lead-finder type is registered so the test can instantiate.
        from agentx_mandate.library.lead_finder import build_lead_finder_type

        await state.runtime.control.register_mandate_type(build_lead_finder_type())
        await state.runtime.control.instantiate_mandate(
            MandateInstance(
                id="inst_acme",
                type_ref="lead-finder@0.1.0",
                customer_id="Acme Dental Test",
                ring="L2",
                heap_region_id="heap_acme",
                channel_binding=ChannelBinding(
                    channel="email",
                    sender_identity="ops@acme-dental.test",
                    opt_in=True,
                ),
            )
        )

        runtime = state.runtime
        ctx = GatewayContext(
            instance_id="inst_acme",
            run_id="run_send_1",
            tenant_id="tenant_1",
            ring="L2",
            now=_now(),
        )
        req = SyscallRequest(
            name="send_email",
            args={
                "to": "founder@target.test",
                "subject": "Intro",
                "body": "Hi.",
                # The kernel run-loop normally injects this from ChannelBinding. Tests do it
                # directly to keep the assertion tight on the adapter behaviour.
                "sender_identity": "ops@acme-dental.test",
            },
            instance_id="inst_acme",
            run_id="run_send_1",
            idempotency_key="idem_e2e_1",
            ring="L2",
        )
        outcome = await runtime.gateway.invoke(req, ctx)
        assert outcome.result is not None, f"gateway produced no result: {outcome!r}"
        assert outcome.result.status == "ok", outcome.result
        assert outcome.result.output["sent"] is True
        assert recording.calls, "transport was never called"
        assert recording.calls[0].from_addr == "ops@acme-dental.test"
        assert recording.calls[0].to == "founder@target.test"


async def test_send_email_idempotency_at_adapter_blocks_double_send() -> None:
    """Two execute() calls with the same idempotency_key -> one transport.send call."""
    recording = _RecordingTransport()
    app = create_app(
        use_mongo=False,
        seed_demo=False,
        operator_token="test-token-send-email-5",
        start_worker=False,
        send_email_transport=recording,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-token-send-email-5"},
    ) as _client:
        from agentx_contracts.mandate import ChannelBinding, MandateInstance

        state = app.state.dashboard
        from agentx_mandate.library.lead_finder import build_lead_finder_type

        await state.runtime.control.register_mandate_type(build_lead_finder_type())
        await state.runtime.control.instantiate_mandate(
            MandateInstance(
                id="inst_idem",
                type_ref="lead-finder@0.1.0",
                customer_id="Idem Test",
                ring="L2",
                heap_region_id="heap_idem",
                channel_binding=ChannelBinding(
                    channel="email",
                    sender_identity="ops@inst.test",
                    opt_in=True,
                ),
            )
        )

        runtime = state.runtime
        args = {
            "to": "founder@target.test",
            "subject": "Intro",
            "body": "Hi.",
            "sender_identity": "ops@inst.test",
        }
        ctx = GatewayContext(
            instance_id="inst_idem",
            run_id="run_idem",
            tenant_id="tenant_1",
            ring="L2",
            now=_now(),
        )
        first = await runtime.gateway.invoke(
            SyscallRequest(
                name="send_email",
                args=args,
                instance_id="inst_idem",
                run_id="run_idem",
                idempotency_key="idem_dedupe",
                ring="L2",
            ),
            ctx,
        )
        second = await runtime.gateway.invoke(
            SyscallRequest(
                name="send_email",
                args=args,
                instance_id="inst_idem",
                run_id="run_idem",
                idempotency_key="idem_dedupe",
                ring="L2",
            ),
            ctx,
        )
        assert first.result is not None
        assert second.result is not None
        assert first.result.status == "ok"
        assert second.result.status == "ok"
        # The adapter's own guard replays the receipt on the second call.
        assert (
            second.result.output.get("idempotent_replay") is True
            or second.result.output.get("message_id") == first.result.output.get("message_id")
        )
        assert len(recording.calls) == 1, f"transport was called {len(recording.calls)} times"
