"""Live email transports for the Phase-1 send adapter.

Resend is the recommended Phase-1 transport (single ``POST /v1/emails`` endpoint, Bearer-token auth,
returns ``{id: ...}``). AgentMail and SMTP are placeholders documented below — both are pluggable
behind the same ``EmailTransport`` Protocol without changing the adapter.

Live send is gated on ``RUN_LIVE_EMAIL=1`` AND a configured provider key; if either is missing,
``build_configured_email_transport`` returns ``None`` so the registry resolves to the human_task
fallback (invariant #5). The adapter never imports these transports directly; it sees them through
the ``EmailTransport`` Protocol (invariant #2 — the secret is injected by the gateway when the
transport is built here at construction time, not held by the pod).
"""

from __future__ import annotations

import asyncio
import os
import smtplib
import ssl
from collections.abc import Callable, Mapping
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from .adapters import EmailTransport, SentEmailReceipt

# Resend endpoint — fixed. The SDK is a thin wrapper around this; we call httpx directly to avoid
# adding a new dep and to keep the credential boundary explicit (Bearer header, key inlined by the
# gateway at transport-construction time, never persisted into a pod).
_RESEND_URL = "https://api.resend.com/emails"


class ResendEmailTransport:
    """Thin Resend transport. Reads API key at construction (gateway-injected), no secret held by pod."""

    name = "resend"

    def __init__(self, api_key: str) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("ResendEmailTransport requires a non-empty api_key")
        self._api_key = api_key.strip()

    async def send(
        self,
        *,
        from_addr: str,
        to: str,
        subject: str,
        body: str,
        headers: Mapping[str, str] | None = None,
    ) -> SentEmailReceipt:
        import httpx

        payload: dict[str, object] = {
            "from": from_addr,
            "to": [to],
            "subject": subject,
            "text": body,
        }
        if headers:
            payload["headers"] = dict(headers)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                _RESEND_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Resend send failed: HTTP {response.status_code} {response.text[:500]}"
            )
        data = response.json()
        message_id = str(data.get("id") or "")
        return SentEmailReceipt(
            message_id=message_id or "resend_unknown",
            to=to,
            from_addr=from_addr,
            subject=subject,
            accepted=bool(message_id),
        )


class SmtpEmailTransport:
    """STARTTLS SMTP transport (Python stdlib ``smtplib``) — the founder's Gmail App Password path.

    Reads no env itself: the gateway builds it with explicit settings (invariant #2 — the password
    is injected at construction, kernel-side, never held by the pod). The blocking smtplib handshake
    runs in a worker thread so a send never blocks the event loop. Gmail rewrites ``From`` to the
    authenticated user, so ``EMAIL_FROM`` MUST equal ``SMTP_USERNAME`` for the header to stick.
    """

    name = "smtp"

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        default_from: str,
        from_name: str = "",
    ) -> None:
        if not host or not host.strip():
            raise ValueError("SmtpEmailTransport requires a non-empty host")
        if not password or not password.strip():
            raise ValueError("SmtpEmailTransport requires a non-empty password")
        self._host = host.strip()
        self._port = port
        self._username = username.strip()
        self._password = password.strip()
        self._default_from = (default_from or username).strip()
        self._from_name = from_name.strip()

    async def send(
        self,
        *,
        from_addr: str,
        to: str,
        subject: str,
        body: str,
        headers: Mapping[str, str] | None = None,
    ) -> SentEmailReceipt:
        sender = from_addr.strip() if from_addr and from_addr.strip() else self._default_from
        domain = sender.split("@")[-1] if "@" in sender else "agentx.local"
        message_id = make_msgid(domain=domain)
        message = EmailMessage()
        message["From"] = formataddr((self._from_name, sender)) if self._from_name else sender
        message["To"] = to
        message["Subject"] = subject
        message["Message-ID"] = message_id
        for key, value in (headers or {}).items():
            message[key] = value
        message.set_content(body)

        await asyncio.to_thread(self._deliver, sender, to, message.as_bytes())
        return SentEmailReceipt(
            message_id=message_id,
            to=to,
            from_addr=sender,
            subject=subject,
            accepted=True,
        )

    def _deliver(self, sender: str, to: str, payload: bytes) -> None:
        context = ssl.create_default_context()
        server = smtplib.SMTP(self._host, self._port, timeout=30)
        try:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(self._username, self._password)
            server.sendmail(sender, [to], payload)
        finally:
            try:
                server.quit()
            except Exception:  # noqa: BLE001 - quit is best-effort; the send already happened
                pass


def _read_env_value(name: str) -> str:
    """Read an env var, falling back to ``.env`` in the repo root.

    We don't widen the frozen ``agentx_contracts.config.Settings`` with per-transport fields
    (Phase 1 — read email settings directly). The ``dotenv`` module is transitively available via
    pydantic-settings, so loading ``.env`` here keeps the env-driven flow without touching the seam.
    """
    raw = os.environ.get(name)
    if raw is not None and raw.strip():
        return raw.strip()
    try:
        import pathlib

        import dotenv

        repo_root = pathlib.Path(__file__).resolve().parents[3]
        env_path = repo_root / ".env"
        if env_path.is_file():
            values = dotenv.dotenv_values(env_path)
            candidate = values.get(name)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    except Exception:  # noqa: BLE001 - dotenv unavailable -> env-var only, never fail import
        pass
    return ""


def _value_reader(env: Mapping[str, str] | None) -> Callable[[str], str]:
    """Return a ``name -> value`` reader.

    With an explicit ``env`` mapping (tests) we read ONLY that mapping — never the repo ``.env`` —
    so absence/selection tests are deterministic. With ``None`` (production) we read ``os.environ``
    and fall back to the repo ``.env`` via :func:`_read_env_value`.
    """
    if env is None:
        return _read_env_value

    def _read(name: str) -> str:
        raw = env.get(name)
        return raw.strip() if isinstance(raw, str) and raw.strip() else ""

    return _read


def _flag_enabled(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


def _parse_smtp_port(raw: str) -> int:
    try:
        port = int(raw)
    except (TypeError, ValueError):
        return 587
    return port if port > 0 else 587


def build_configured_email_transport(env: Mapping[str, str] | None = None) -> EmailTransport | None:
    """Build the live email transport, gated on ``RUN_LIVE_EMAIL=1``.

    Selection order once enabled: SMTP (``SMTP_HOST`` + ``SMTP_PASSWORD`` — the founder's Gmail App
    Password) > Resend (``RESEND_API_KEY``) > ``None``. ``None`` makes the registry resolve
    ``send_email`` to the ``human_task`` terminal fallback (invariant #5).

    ``RUN_LIVE_EMAIL`` gates CONSTRUCTION, not just the send: a dev ``.env`` carrying SMTP keys must
    never cause a sim/test runtime to build a real transport — only the gated live proof sends.
    """
    read = _value_reader(env)
    if not _flag_enabled(read("RUN_LIVE_EMAIL")):
        return None
    smtp_host = read("SMTP_HOST")
    smtp_password = read("SMTP_PASSWORD")
    if smtp_host and smtp_password:
        return SmtpEmailTransport(
            host=smtp_host,
            port=_parse_smtp_port(read("SMTP_PORT")),
            username=read("SMTP_USERNAME"),
            password=smtp_password,
            default_from=read("EMAIL_FROM") or read("SMTP_USERNAME"),
            from_name=read("EMAIL_FROM_NAME"),
        )
    resend_key = read("RESEND_API_KEY")
    if resend_key:
        return ResendEmailTransport(resend_key)
    return None
