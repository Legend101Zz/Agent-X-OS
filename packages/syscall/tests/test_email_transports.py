"""Phase-1 email-transport tests — SMTP transport + provider selection.

The send adapter is transport-agnostic (it sees the ``EmailTransport`` Protocol). This file is the
spec for the live transports themselves:

  1. ``SmtpEmailTransport`` (Gmail App Password path) sends EXACTLY once, uses STARTTLS, logs in
     with the configured username/password, and sets From to the per-send ``from_addr``.
  2. ``build_configured_email_transport`` prefers SMTP (``SMTP_HOST`` + ``SMTP_PASSWORD``) over
     Resend (``RESEND_API_KEY``), falls back to Resend, and returns ``None`` with no keys.
  3. The real send stays gated on ``RUN_LIVE_EMAIL=1`` — without it, no transport is built (so the
     registry resolves ``send_email`` to the human_task tail, invariant #5).

Unit tests use a FAKE SMTP server (monkeypatched ``smtplib.SMTP``); no real network/credential.
"""

from __future__ import annotations

import smtplib
from typing import Any

import pytest
from agentx_syscall.email_transports import (
    ResendEmailTransport,
    SmtpEmailTransport,
    build_configured_email_transport,
)


class _FakeSMTP:
    """A monkeypatch double for ``smtplib.SMTP`` that records the whole send handshake."""

    instances: list[_FakeSMTP] = []

    def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.starttls_calls = 0
        self.ehlo_calls = 0
        self.login_args: tuple[str, str] | None = None
        self.sendmail_calls: list[dict[str, Any]] = []
        self.quit_called = False
        _FakeSMTP.instances.append(self)

    def ehlo(self) -> None:
        self.ehlo_calls += 1

    def starttls(self, context: Any = None) -> None:
        self.starttls_calls += 1
        self.tls_context = context

    def login(self, username: str, password: str) -> None:
        self.login_args = (username, password)

    def sendmail(self, from_addr: str, to_addrs: list[str], msg: Any) -> dict[str, Any]:
        self.sendmail_calls.append({"from": from_addr, "to": to_addrs, "msg": msg})
        return {}

    def quit(self) -> None:
        self.quit_called = True


@pytest.fixture(autouse=True)
def _reset_fake() -> None:
    _FakeSMTP.instances.clear()


async def test_smtp_transport_sends_once_with_starttls_and_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    transport = SmtpEmailTransport(
        host="smtp.gmail.com",
        port=587,
        username="founder@gmail.com",
        password="app-password",
        default_from="founder@gmail.com",
    )

    receipt = await transport.send(
        from_addr="founder@gmail.com",
        to="lead@target.test",
        subject="Quick intro",
        body="Hi there.",
    )

    assert len(_FakeSMTP.instances) == 1, "exactly one SMTP connection per send"
    server = _FakeSMTP.instances[0]
    assert server.host == "smtp.gmail.com"
    assert server.port == 587
    assert server.starttls_calls == 1, "must upgrade to TLS via STARTTLS"
    assert server.login_args == ("founder@gmail.com", "app-password")
    assert len(server.sendmail_calls) == 1, "transport must send exactly once"
    assert server.quit_called is True
    call = server.sendmail_calls[0]
    assert call["from"] == "founder@gmail.com"
    assert call["to"] == ["lead@target.test"]
    payload = call["msg"] if isinstance(call["msg"], str) else call["msg"].decode()
    assert "Subject: Quick intro" in payload
    assert "Hi there." in payload
    assert receipt.accepted is True
    assert receipt.message_id, "receipt must carry a Message-ID"
    assert receipt.to == "lead@target.test"
    assert receipt.from_addr == "founder@gmail.com"


async def test_smtp_transport_from_header_is_the_send_from_addr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    transport = SmtpEmailTransport(
        host="smtp.gmail.com",
        port=587,
        username="founder@gmail.com",
        password="app-password",
        default_from="founder@gmail.com",
        from_name="Agent-X Founder",
    )

    await transport.send(
        from_addr="founder@gmail.com",
        to="lead@target.test",
        subject="Hi",
        body="Body.",
    )

    server = _FakeSMTP.instances[0]
    call = server.sendmail_calls[0]
    payload = call["msg"] if isinstance(call["msg"], str) else call["msg"].decode()
    # The envelope sender and the From header both carry the per-send sender (invariant #8); the
    # configured display name decorates the header.
    assert call["from"] == "founder@gmail.com"
    assert "founder@gmail.com" in payload
    assert "Agent-X Founder" in payload


def test_build_configured_prefers_smtp_over_resend_when_both_present() -> None:
    env = {
        "RUN_LIVE_EMAIL": "1",
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_PORT": "587",
        "SMTP_USERNAME": "founder@gmail.com",
        "SMTP_PASSWORD": "app-password",
        "EMAIL_FROM": "founder@gmail.com",
        "RESEND_API_KEY": "re_123",
    }
    transport = build_configured_email_transport(env=env)
    assert isinstance(transport, SmtpEmailTransport)


def test_build_configured_uses_resend_when_only_resend_key() -> None:
    env = {"RUN_LIVE_EMAIL": "1", "RESEND_API_KEY": "re_123"}
    transport = build_configured_email_transport(env=env)
    assert isinstance(transport, ResendEmailTransport)


def test_build_configured_returns_none_without_any_keys() -> None:
    env = {"RUN_LIVE_EMAIL": "1"}
    assert build_configured_email_transport(env=env) is None


def test_build_configured_returns_none_without_run_live_email_even_with_smtp_keys() -> None:
    # The .env on a dev box carries SMTP keys; RUN_LIVE_EMAIL is the master gate that keeps a real
    # send from ever happening in sim/test runtimes (invariant: only the gated live proof sends).
    env = {
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_PASSWORD": "app-password",
        "EMAIL_FROM": "founder@gmail.com",
    }
    assert build_configured_email_transport(env=env) is None
