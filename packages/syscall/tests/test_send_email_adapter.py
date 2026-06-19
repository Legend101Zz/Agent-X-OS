"""Phase-1 send-email adapter tests — the spec for "draft -> really sent" (HERMES_BUILD_PLAN §Phase 1).

Done-when assertions (one test per assertion):
  1. Adapter exists, maturity_level >= 2, risk_class == "external_message", gated at a ring that
     requires human approval; registered and resolvable.
  2. Execute with fake transport returns {sent: True, message_id: ...} and calls transport.send EXACTLY
     once.
  3. Execute TWICE with the same idempotency_key -> transport.send called ONCE (no double-send) and
     replays the receipt.
  4. The From / sender identity equals the INSTANCE's channel identity, not a shared/global one.
  5. No transport configured -> resolves to the human_task terminal tail (never None).
  6. Credential boundary stays green (full gate).

The real send path is gated on RUN_LIVE_EMAIL=1; unit tests use a FAKE transport.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest
from agentx_contracts import GatewayContext, SyscallRequest
from agentx_contracts.mandate import ChannelBinding
from agentx_syscall.adapters import HumanTaskAdapter, ManualTaskStore, SentEmailReceipt
from agentx_syscall.registry import Phase1SyscallRegistry

# --- Test fakes -----------------------------------------------------------


class FakeEmailTransport:
    """A fake transport with call-counting + configurable behaviour.

    Mirrors the seam a real transport (Resend/AgentMail/SMTP) would plug into — the adapter NEVER
    holds the secret material (it sees a ``Credential`` from the gateway, builds a request, and
    delegates to the transport).
    """

    name = "fake_email"

    def __init__(
        self,
        *,
        receipts: list[SentEmailReceipt] | None = None,
        raise_on_send: Exception | None = None,
    ) -> None:
        self.send_calls: list[dict[str, Any]] = []
        self._receipts = list(receipts or [])
        self._raise = raise_on_send
        self.from_addr: str = ""
        self.subject_prefix: str = ""

    async def send(
        self,
        *,
        from_addr: str,
        to: str,
        subject: str,
        body: str,
        headers: Mapping[str, str] | None = None,
    ) -> SentEmailReceipt:
        self.send_calls.append(
            {"from": from_addr, "to": to, "subject": subject, "body": body, "headers": dict(headers or {})}
        )
        if self._raise is not None:
            raise self._raise
        if not self._receipts:
            receipt = SentEmailReceipt(
                message_id=f"msg_{len(self.send_calls)}",
                to=to,
                from_addr=from_addr,
                subject=subject,
            )
        else:
            receipt = self._receipts.pop(0)
        return receipt


def _ctx(*, instance_id: str = "inst_1", run_id: str = "run_1", tenant_id: str = "tenant_1") -> GatewayContext:
    return GatewayContext(
        instance_id=instance_id,
        run_id=run_id,
        tenant_id=tenant_id,
        ring="L2",
        now=datetime.now(UTC),
    )


def _req(
    name: str,
    args: dict[str, Any] | None = None,
    *,
    instance_id: str = "inst_1",
    run_id: str = "run_1",
    idempotency_key: str | None = None,
) -> SyscallRequest:
    return SyscallRequest(
        name=name,
        args=args or {},
        instance_id=instance_id,
        run_id=run_id,
        idempotency_key=idempotency_key or f"idem_{name}",
        ring="L2",
    )


def _channel_binding(*, channel: str = "email", sender: str = "Agent-X <hello@agentx.dev>") -> ChannelBinding:
    return ChannelBinding(channel=channel, sender_identity=sender, opt_in=True)


def _import_send_email_adapter() -> type[Any]:
    """Import the SendEmailAdapter class from ``agentx_syscall.adapters``.

    Deferred so tests RED cleanly before the symbol exists. The return type is loose (``type[Any]``)
    to keep mypy happy with the forward reference; the type is statically known at runtime.
    """
    from agentx_syscall.adapters import SendEmailAdapter

    return SendEmailAdapter


# --- Done-when #1 — adapter shape & registration --------------------------------------


def test_send_email_adapter_is_registered_with_external_message_ring_and_maturity() -> None:
    SendEmailAdapter = _import_send_email_adapter()
    adapter = SendEmailAdapter(transport=FakeEmailTransport(), instance_sender="sender@inst")

    assert adapter.name == "send_email"
    assert adapter.category == "communication"
    assert adapter.maturity_level >= 2, "send_email must be at least semi-auto (maturity 2)"
    assert adapter.risk_class == "external_message"
    assert adapter.required_ring in {"L2", "L3", "L4"}, "send must require human approval ring"
    assert adapter.is_terminal_fallback is False
    # Fixture: every adapter ships a SyscallTestCase per the seam contract.
    assert adapter.fixtures and adapter.fixtures[0].expect_output_contains.get("sent") is True


def test_send_email_adapter_resolves_in_registry() -> None:
    SendEmailAdapter = _import_send_email_adapter()
    registry = Phase1SyscallRegistry(terminal_fallback=HumanTaskAdapter(store=ManualTaskStore()))
    transport = FakeEmailTransport()
    registry.register(SendEmailAdapter(transport=transport, instance_sender="ops@inst"))

    resolved = registry.resolve(_req("send_email", {"to": "x@y.z", "subject": "Hi", "body": "Hi."}), _ctx())

    assert resolved.name == "send_email"
    assert resolved.is_terminal_fallback is False


# --- Done-when #2 — execute returns sent + calls transport once -------------------------


@pytest.mark.asyncio
async def test_send_email_returns_sent_and_calls_transport_exactly_once() -> None:
    SendEmailAdapter = _import_send_email_adapter()
    transport = FakeEmailTransport()
    adapter = SendEmailAdapter(
        transport=transport,
        instance_sender="ops@agentx.dev",
    )

    result = await adapter.execute(
        _req(
            "send_email",
            {
                "to": "founder@example.com",
                "subject": "Quick intro",
                "body": "Hi there.",
                "sender_identity": "ops@agentx.dev",
            },
        ),
        cred=None,
    )

    assert result.status == "ok"
    assert result.output["sent"] is True
    assert result.output["mode"] == "sent"
    assert "message_id" in result.output
    assert len(transport.send_calls) == 1
    assert transport.send_calls[0]["to"] == "founder@example.com"
    assert transport.send_calls[0]["from"] == "ops@agentx.dev"


# --- Done-when #3 — idempotency prevents double-send ----------------------------------


@pytest.mark.asyncio
async def test_send_email_idempotent_key_replays_receipt_and_calls_transport_once() -> None:
    SendEmailAdapter = _import_send_email_adapter()
    transport = FakeEmailTransport()
    adapter = SendEmailAdapter(transport=transport, instance_sender="ops@agentx.dev")

    args = {
        "to": "founder@example.com",
        "subject": "Quick intro",
        "body": "Hi there.",
        "sender_identity": "ops@agentx.dev",
    }
    req1 = _req("send_email", args, idempotency_key="idem_send_alpha")
    req2 = _req("send_email", args, idempotency_key="idem_send_alpha")

    first = await adapter.execute(req1, cred=None)
    second = await adapter.execute(req2, cred=None)

    assert first.status == "ok"
    assert second.status == "ok"
    assert second.output["message_id"] == first.output["message_id"]
    assert second.output["sent"] is True
    assert len(transport.send_calls) == 1, "adapter must enforce its own no-double-send guard"
    assert second.output.get("idempotent_replay") is True


# --- Done-when #4 — per-instance sender identity (no shared/global sender) -------------


@pytest.mark.asyncio
async def test_send_email_uses_instance_sender_not_a_shared_global() -> None:
    SendEmailAdapter = _import_send_email_adapter()
    transport_a = FakeEmailTransport()
    transport_b = FakeEmailTransport()
    adapter_a = SendEmailAdapter(transport=transport_a, instance_sender="alpha@inst-a.com")
    adapter_b = SendEmailAdapter(transport=transport_b, instance_sender="bravo@inst-b.com")

    args_a = {"to": "lead@x.com", "subject": "Hi", "body": "Body", "sender_identity": "alpha@inst-a.com"}
    args_b = {"to": "lead@y.com", "subject": "Hi", "body": "Body", "sender_identity": "bravo@inst-b.com"}

    await adapter_a.execute(_req("send_email", args_a), cred=None)
    await adapter_b.execute(_req("send_email", args_b), cred=None)

    # Instance A's transport was called with instance A's sender; B with B's. No cross-leak.
    assert transport_a.send_calls[0]["from"] == "alpha@inst-a.com"
    assert transport_b.send_calls[0]["from"] == "bravo@inst-b.com"
    assert transport_a.send_calls[0]["from"] != transport_b.send_calls[0]["from"]


@pytest.mark.asyncio
async def test_send_email_rejects_sender_identity_mismatch() -> None:
    """If a caller claims a sender_identity in args that isn't the instance's, refuse (no shared blast radius)."""
    SendEmailAdapter = _import_send_email_adapter()
    transport = FakeEmailTransport()
    adapter = SendEmailAdapter(transport=transport, instance_sender="alpha@inst-a.com")

    bad_args = {
        "to": "lead@x.com",
        "subject": "Hi",
        "body": "Body",
        "sender_identity": "spoof@someone-else.com",
    }
    result = await adapter.execute(_req("send_email", bad_args), cred=None)

    assert result.status == "error"
    assert "sender_identity" in (result.error or "")
    assert len(transport.send_calls) == 0


# --- Done-when #5 — no transport configured -> human_task tail (never None) -----------


def test_send_email_without_transport_is_terminal_fallback_in_registry() -> None:
    SendEmailAdapter = _import_send_email_adapter()
    registry = Phase1SyscallRegistry(terminal_fallback=HumanTaskAdapter(store=ManualTaskStore()))
    # Adapter registered with no transport available: can_handle must say False so the registry
    # resolves to the terminal human_task fallback (invariant #5 — resolve never returns None).
    registry.register(
        SendEmailAdapter(
            transport=None,
            instance_sender="alpha@inst-a.com",
            transport_factory=lambda: None,
        )
    )

    resolved = registry.resolve(_req("send_email", {"to": "x", "subject": "s", "body": "b"}), _ctx())

    assert resolved.name == "human_task"
    assert resolved.is_terminal_fallback is True


@pytest.mark.asyncio
async def test_send_email_transport_unavailable_returns_human_task_via_can_handle() -> None:
    SendEmailAdapter = _import_send_email_adapter()
    adapter = SendEmailAdapter(
        transport=None,
        instance_sender="alpha@inst-a.com",
        transport_factory=lambda: None,
    )
    assert adapter.can_handle(_req("send_email"), _ctx()) is False


# --- Done-when #6 — credential boundary stays green ----------------------------------
# Covered by the repo-wide `tests/test_credential_boundary.py` (no mandate imports credentials).
# We add an explicit per-adapter invariant: the adapter MUST NOT import config/security/db
# directly (the secret arrives via cred at call time; runtime selection is via transport_factory).
# The adapter import below would FAIL at module load if a future change re-introduced the leak.


def test_send_email_adapter_module_does_not_import_credential_roots() -> None:
    import ast
    import pathlib

    SendEmailAdapter = _import_send_email_adapter()
    candidates = list(pathlib.Path("packages/syscall/src").rglob("*.py"))
    src_file = next((p for p in candidates if SendEmailAdapter.__name__ in p.read_text()), None)
    assert src_file is not None, f"could not locate source file for {SendEmailAdapter}"

    forbidden = ("agentx_contracts.security", "agentx_contracts.config", "agentx_db", "pymongo")
    tree = ast.parse(src_file.read_text())
    leaked: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if any(alias.name.startswith(root) for root in forbidden):
                    leaked.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if any(module == root or module.startswith(root + ".") for root in forbidden):
                leaked.append(module)
    assert not leaked, f"SendEmailAdapter must not import credential roots: {leaked}"
