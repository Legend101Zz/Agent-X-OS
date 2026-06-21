"""Capability health detail — read-only extension of GET /capabilities.

The Spec (§8 row 4 — C11) asks the capability registry to expose, in addition to the per-adapter
ladder rows already surfaced:

  * **Provider reachability** — for each underlying provider (research: Exa/Firecrawl; outbound
    email: Resend/SMTP), whether it is configured AND whether its own ``health_check`` reports it
    usable right now. Reachability is per-provider (not per-adapter) so the Providers view can
    surface "Exa key present + reachable" / "Firecrawl unreachable" as separate facts.
  * **Transport configured** — what outbound email transport is wired (resend vs smtp), whether the
    live-send gate (``RUN_LIVE_EMAIL``) is on, and the non-secret connection details the operator
    needs to verify the right transport was selected. No credentials cross this seam.
  * **Model routing** — which model the kernel uses for faculties (Hermes → Minimax OpenAI-compat)
    and which model the promptfoo judge uses (OpenRouter slug), so an operator can confirm the
    routing matches ``.env`` expectations without grepping.

This module is **read-only**. It does not modify the Adapter contract, does not call any effectful
API, and does not surface secret material — only configuration shape (``host``, ``username``,
``model_id``) and presence booleans (``configured`` / ``reachable``).

Why a separate module: keeps the new section logic out of ``state.py`` (already long) and makes
each section independently unit-testable. The endpoint composes the three sections alongside the
existing per-adapter rows.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agentx_contracts.config import Settings, get_settings


def provider_reachability(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Return one row per underlying provider — research first, email second.

    Each row: ``{name, kind, configured, reachable, error}``. ``configured`` is True iff the
    relevant secret/env is present (key for Exa/Firecrawl, the right combination for email).
    ``reachable`` is True iff the provider's own ``health_check`` reports it usable RIGHT NOW.

    For research providers we instantiate the lightweight wrappers via
    ``build_configured_research_providers`` (idempotent — only constructs objects with the key, no
    network calls) and ask each ``ResearchProvider.health_check()`` whether it considers itself
    usable. For email we surface a single ``email`` row whose ``reachable`` mirrors whether the
    configured email transport object reports ``ok`` on its own health probe — but we keep the
    per-transport detail in the ``transport`` section to avoid duplicating fields.
    """
    settings = settings or get_settings()
    rows: list[dict[str, Any]] = []

    rows.extend(_research_provider_rows(settings))
    rows.extend(_email_provider_row(settings))

    return rows


def transport_status(settings: Settings | None = None) -> dict[str, Any]:
    """Return the email transport's configuration shape + the live-send gate state.

    The shape mirrors the constructor of each transport (``SmtpEmailTransport``, future variants).
    We deliberately omit ``password`` / ``api_key`` — invariant #2: no credential in user space.
    ``live_gated`` reflects ``RUN_LIVE_EMAIL`` (the master switch the kernel checks before allowing
    a real outbound send). When no transport is configured we return ``{"configured": False, ...}``
    so callers can render a disabled pill instead of crashing on missing fields.
    """
    settings = settings or get_settings()
    live_gated = bool(settings.run_live_email)

    transport_obj = _build_email_transport_safe(settings)
    if transport_obj is None:
        return {
            "configured": False,
            "name": None,
            "live_gated": live_gated,
            "details": {},
        }

    name = getattr(transport_obj, "name", transport_obj.__class__.__name__.lower())
    details = _transport_details(transport_obj, settings)
    return {
        "configured": True,
        "name": name,
        "live_gated": live_gated,
        "details": details,
    }


def model_routing_status(settings: Settings | None = None) -> dict[str, Any]:
    """Return the model routing shape — which model runs faculties, which runs the judge.

    ``faculty_model`` is the Minimax-OpenAI-compatible model the kernel uses to drive Hermes
    faculties. ``judge_model`` is the OpenRouter slug the promptfoo judge uses for verification.
    Both are surface-level metadata so the Providers view can render "faculty = X / judge = Y" and
    the operator can confirm they point where they expect.
    """
    settings = settings or get_settings()
    faculty = {
        "provider": "minimax",
        "configured": bool(settings.minimax_api_key and settings.faculty_model_id),
        "base_url": settings.faculty_model_base_url,
        "model_id": settings.faculty_model_id,
    }
    judge = {
        "via": "openrouter",
        "configured": bool(settings.openrouter_api_key and settings.judge_model_id),
        "model_id": settings.judge_model_id,
    }
    return {
        "faculty_model": faculty,
        "judge_model": judge,
        "checked_at": datetime.now(UTC).isoformat(),
    }


# ---- internals --------------------------------------------------------------------------------


def _research_provider_rows(settings: Settings) -> list[dict[str, Any]]:
    """Probe each configured research provider via the existing adapters module.

    We import lazily so the api composition edge stays bootable even when the research providers'
    SDK deps are absent (the same dance ``build_configured_research_providers`` does internally).
    """
    rows: list[dict[str, Any]] = []

    # Always emit the canonical pair of research providers — even if not configured — so the
    # Providers view can render an explicit "not configured" pill rather than a missing row.
    configured = _build_research_providers_safe(settings)
    configured_names = {provider.name for provider in configured}

    exa_key_present = bool(settings.exa_api_key and settings.exa_api_key.get_secret_value())
    firecrawl_key_present = bool(
        settings.firecrawl_api_key and settings.firecrawl_api_key.get_secret_value()
    )

    rows.append(_research_row("exa", exa_key_present, "exa" in configured_names, configured))
    rows.append(
        _research_row("firecrawl", firecrawl_key_present, "firecrawl" in configured_names, configured)
    )
    return rows


def _research_row(
    name: str, configured: bool, built: bool, configured_providers: list[Any]
) -> dict[str, Any]:
    reachable = False
    error: str | None = None
    for provider in configured_providers:
        if provider.name == name:
            try:
                # ResearchProvider.health_check() is async — but the lightweight wrappers
                # (ExaResearchProvider, FirecrawlResearchProvider) only inspect the key, so a sync
                # probe would suffice. We use the async path anyway because the Protocol declares it
                # async; if the loop is closed the row simply reports unreachable.
                import asyncio

                try:
                    reachable = bool(asyncio.run(provider.health_check()))
                except RuntimeError:
                    # No event loop in this thread (e.g. sync test). Fall back to inspecting
                    # ``_api_key`` directly via duck-typing — keeps the section usable from both
                    # sync and async call sites.
                    reachable = bool(getattr(provider, "_api_key", ""))
            except Exception as exc:  # noqa: BLE001 - diagnostics surface, never crash
                reachable = False
                error = str(exc)
            break
    return {
        "name": name,
        "kind": "research",
        "configured": configured,
        "reachable": reachable if configured else False,
        "error": error,
    }


def _email_provider_row(settings: Settings) -> list[dict[str, Any]]:
    """Emit a single ``email`` provider row that mirrors transport-level reachability.

    Reachability here means "a transport object built successfully and reports ok on its own
    health probe" — not "the SMTP server is reachable" (we don't open a socket for a status
    endpoint). That kind of real reachability belongs to a separate liveness probe, not a config
    snapshot.
    """
    transport_obj = _build_email_transport_safe(settings)
    configured = transport_obj is not None
    reachable = False
    error: str | None = None
    if configured and transport_obj is not None:
        try:
            health = transport_obj.health_check()
            reachable = bool(getattr(health, "status", "") == "ok")
        except Exception as exc:  # noqa: BLE001
            reachable = False
            error = str(exc)
    return [
        {
            "name": "email",
            "kind": "outbound",
            "configured": configured,
            "reachable": reachable,
            "live_gated": bool(settings.run_live_email),
            "error": error,
        }
    ]


def _transport_details(transport_obj: Any, settings: Settings) -> dict[str, Any]:
    """Return the non-secret shape of the configured email transport.

    For SMTP: host/port/username/default_from/from_name. For Resend (current shape — name only,
    no host): an empty details dict so the field is always present (consumers can always read
    ``transport.details["host"]`` without a KeyError).
    """
    cls_name = transport_obj.__class__.__name__
    if cls_name == "SmtpEmailTransport":
        return {
            "host": getattr(transport_obj, "_host", settings.smtp_host),
            "port": getattr(transport_obj, "_port", settings.smtp_port),
            "username": getattr(transport_obj, "_username", settings.smtp_username),
            "default_from": getattr(transport_obj, "_default_from", settings.email_from),
            "from_name": getattr(transport_obj, "_from_name", settings.email_from_name),
        }
    # Resend + future variants: the transport object only carries an api_key + name. We surface
    # only the name — never the key (invariant #2).
    return {}


def _build_research_providers_safe(settings: Settings) -> list[Any]:
    """Lazy + dep-tolerant wrapper around ``build_configured_research_providers``.

    Returns the configured list (possibly empty). Never raises — diagnostics, not policy.
    """
    try:
        from agentx_syscall.adapters import build_configured_research_providers

        return list(build_configured_research_providers())
    except Exception:  # noqa: BLE001 - SDKs missing, dotenv missing, whatever
        return []


def _build_email_transport_safe(settings: Settings | None = None) -> Any | None:
    """Lazy + dep-tolerant wrapper around ``build_configured_email_transport``.

    Returns the transport object or None. Never raises. Same contract the operator composition
    edge uses — but here we don't try to register it, just surface its config.

    We pass an ``env`` mapping derived from ``Settings`` (rather than letting the constructor read
    ``os.environ`` directly) so the diagnostic section reflects the SAME configuration the rest of
    the api uses. Without this, tests that build a synthetic ``Settings`` would still see the
    machine's actual env — which silently disagrees with the operator's view in
    :func:`transport_status`.
    """
    try:
        from agentx_syscall.email_transports import build_configured_email_transport

        settings = settings or get_settings()
        env = _settings_to_env(settings)
        return build_configured_email_transport(env=env)
    except Exception:  # noqa: BLE001
        return None


def _settings_to_env(settings: Settings) -> dict[str, str]:
    """Project ``Settings`` email fields into an ``env`` mapping for the transport constructor.

    ``run_live_email`` is a boolean — serialised as ``"1"`` / ``"0"`` (the
    :func:`_flag_enabled` contract in ``email_transports``). All other fields are str (or empty
    str when unset). SecretStr is unwrapped to its value because the constructor only reads the
    mapping — it does not retain the wrapper; invariant #2 is enforced by the fact that the
    returned mapping never leaves this function (it is consumed immediately and discarded).

    Note: Resend is not in the typed Settings today — the SMTP path is the only wired transport
    (C6/C7 send-loop live proof). When Resend lands in ``Settings`` it should be appended here
    alongside the SMTP fields; the constructor already prefers SMTP > Resend so the ordering is
    preserved automatically.
    """
    return {
        "RUN_LIVE_EMAIL": "1" if settings.run_live_email else "",
        "SMTP_HOST": settings.smtp_host,
        "SMTP_PORT": str(settings.smtp_port) if settings.smtp_port else "",
        "SMTP_USERNAME": settings.smtp_username,
        "SMTP_PASSWORD": (
            settings.smtp_password.get_secret_value() if settings.smtp_password else ""
        ),
        "EMAIL_FROM": settings.email_from,
        "EMAIL_FROM_NAME": settings.email_from_name,
    }


__all__ = [
    "model_routing_status",
    "provider_reachability",
    "transport_status",
]
