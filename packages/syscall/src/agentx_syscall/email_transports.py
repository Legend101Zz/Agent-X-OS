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

import os
from collections.abc import Mapping
from dataclasses import dataclass

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


@dataclass(frozen=True)
class _LiveEmailGate:
    """Single source of truth: live send is on only when RUN_LIVE_EMAIL=1 AND a key is configured."""

    enabled: bool
    provider: str | None
    api_key: str | None


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


def _read_gate() -> _LiveEmailGate:
    flag = _read_env_value("RUN_LIVE_EMAIL").lower() in {"1", "true", "yes", "on"}
    # Resend is the recommended Phase-1 provider (per HERMES_BUILD_PLAN §Phase 1). AgentMail and
    # SMTP keys are recognized but not yet wrapped (place a transport here when you adopt one).
    resend_key = _read_env_value("RESEND_API_KEY")
    if flag and resend_key:
        return _LiveEmailGate(enabled=True, provider="resend", api_key=resend_key)
    return _LiveEmailGate(enabled=False, provider=None, api_key=None)


def build_configured_email_transport() -> EmailTransport | None:
    """Build the live email transport ONLY when ``RUN_LIVE_EMAIL=1`` AND a key is present.

    Returns ``None`` when unconfigured — the registry then resolves ``send_email`` to the
    ``human_task`` terminal fallback (invariant #5). The transport never touches the filesystem
    or network outside its single ``send`` call.
    """
    gate = _read_gate()
    if not gate.enabled or gate.api_key is None:
        return None
    if gate.provider == "resend":
        return ResendEmailTransport(gate.api_key)
    return None
