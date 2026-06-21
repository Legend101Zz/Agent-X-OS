"""Spec §8 row 4 (C11) — capability health detail extension of GET /capabilities.

These tests cover the three new sections surfaced alongside the existing per-adapter rows:

  * ``providers``     — provider reachability (research: Exa/Firecrawl; outbound email)
  * ``transport``     — configured email transport + live-send gate + non-secret connection details
  * ``model_routing`` — faculty model (Hermes → Minimax OpenAI-compat) + judge model (OpenRouter)

The sections are pure read-only diagnostics over ``Settings`` + the email transport's own
``health_check``. They must NEVER surface secret material — invariant #2.

Two layers of coverage:

  1. **Unit** (``_unit_*``) — call the three builders directly with a hand-built ``Settings`` so
     each section is verifiable without booting the FastAPI app.
  2. **Integration** (``test_*_via_endpoint``) — boot the app via ``create_app`` and assert the
     ``/capabilities`` payload shape, so the wiring in ``app.py`` is also covered.

Both layers assert: (a) the sections are present and have the right keys; (b) no credential-like
field ever appears in the response (``password``, ``api_key``, ``secret``, ``token``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from agentx_contracts.config import Settings
from agentx_contracts.config import get_settings as _get_settings_cached
from httpx import ASGITransport, AsyncClient

from agentx_api.app import create_app
from agentx_api.capability_health import (
    model_routing_status,
    provider_reachability,
    transport_status,
)


TEST_TOKEN = "test-operator-token"


# ---- helpers -----------------------------------------------------------------------------------


_FORBIDDEN_CREDENTIAL_SUBSTRINGS = (
    "password",
    "api_key",
    "apikey",
    "secret",
    "token",
    "credential",
)


def _assert_no_credentials(payload: Any, path: str = "$") -> None:
    """Recursively scan ``payload`` and fail on any credential-like field name.

    Invariant #2 is the bedrock: no secret crosses the user-space seam. This scan is paranoid on
    purpose — it catches a future regression where someone adds ``smtp_password`` to
    ``transport.details`` or ``api_key`` to a provider row.
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            assert not any(
                substring in key.lower() for substring in _FORBIDDEN_CREDENTIAL_SUBSTRINGS
            ), f"credential-like field {key!r} present at {path}.{key}"
            _assert_no_credentials(value, f"{path}.{key}")
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            _assert_no_credentials(item, f"{path}[{index}]")


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(
        use_mongo=False, seed_demo=True, operator_token=TEST_TOKEN, start_worker=False
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    ) as test_client:
        yield test_client


# ---- unit tests: each builder in isolation ----------------------------------------------------


def test_unit_provider_reachability_emits_research_and_email_rows() -> None:
    """With no provider keys set, both research providers are reported as ``configured=False``.

    The email row is always present too — never omitted — so the UI can render an explicit
    "not configured" pill instead of a missing row.
    """
    settings = Settings()
    rows = provider_reachability(settings)
    names = {row["name"] for row in rows}
    assert {"exa", "firecrawl", "email"}.issubset(names)

    for row in rows:
        assert set(row) >= {"name", "kind", "configured", "reachable"}
        assert row["configured"] is False
        assert row["reachable"] is False

    _assert_no_credentials(rows)


def test_unit_provider_reachability_with_exa_key_marks_exa_configured() -> None:
    """Setting the Exa key flips ``exa.configured`` True; Firecrawl + email stay False."""
    from pydantic import SecretStr

    settings = Settings(exa_api_key=SecretStr("test-exa-key"))
    rows = provider_reachability(settings)
    by_name = {row["name"]: row for row in rows}

    assert by_name["exa"]["configured"] is True
    assert by_name["firecrawl"]["configured"] is False
    assert by_name["email"]["configured"] is False

    # The Exa key value must NOT appear in the response payload anywhere.
    _assert_no_credentials(rows)


def test_unit_transport_status_with_no_transport_reports_not_configured() -> None:
    """No SMTP/Resend settings → ``transport.configured`` is False and details is empty."""
    settings = Settings()
    snapshot = transport_status(settings)

    assert snapshot["configured"] is False
    assert snapshot["name"] is None
    assert snapshot["live_gated"] is False
    assert snapshot["details"] == {}

    _assert_no_credentials(snapshot)


def test_unit_transport_status_with_smtp_settings_reports_smtp_details() -> None:
    """When the SMTP settings are present, ``transport.configured`` is True with non-secret fields.

    We exercise the SMTP path here (rather than Resend) because the SMTP settings have non-trivial
    details (host/port/username) that the section is supposed to surface.
    """
    from pydantic import SecretStr

    settings = Settings(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="agent@example.com",
        smtp_password=SecretStr("super-secret-password"),
        email_from="agent@example.com",
        email_from_name="Agent-X",
        run_live_email=True,
    )
    snapshot = transport_status(settings)

    assert snapshot["configured"] is True
    assert snapshot["name"] == "smtp"
    assert snapshot["live_gated"] is True
    details = snapshot["details"]
    assert details["host"] == "smtp.example.com"
    assert details["port"] == 587
    assert details["username"] == "agent@example.com"
    assert details["default_from"] == "agent@example.com"
    assert details["from_name"] == "Agent-X"

    # Invariant #2: the SMTP password must NOT appear anywhere in the response.
    full_payload = {"transport": snapshot}
    _assert_no_credentials(full_payload)
    # Defence in depth: string-search the rendered payload too.
    assert "super-secret-password" not in str(full_payload)


def test_unit_model_routing_reports_faculty_and_judge_shape() -> None:
    """Both routing entries are present with the documented keys; ``configured`` reflects key presence."""
    settings = Settings()
    routing = model_routing_status(settings)

    assert set(routing) >= {"faculty_model", "judge_model", "checked_at"}
    assert routing["faculty_model"]["provider"] == "minimax"
    assert routing["judge_model"]["via"] == "openrouter"
    # No keys set in this test → both report ``configured: False``.
    assert routing["faculty_model"]["configured"] is False
    assert routing["judge_model"]["configured"] is False

    _assert_no_credentials(routing)


def test_unit_model_routing_with_keys_marks_configured() -> None:
    """When the faculty + judge keys are present, both report ``configured: True`` with the model id."""
    from pydantic import SecretStr

    settings = Settings(
        minimax_api_key=SecretStr("test-minimax-key"),
        faculty_model_id="MiniMax-M2",
        faculty_model_base_url="https://api.minimax.io/v1",
        openrouter_api_key=SecretStr("test-openrouter-key"),
        judge_model_id="anthropic/claude-sonnet-4",
    )
    routing = model_routing_status(settings)

    assert routing["faculty_model"]["configured"] is True
    assert routing["faculty_model"]["model_id"] == "MiniMax-M2"
    assert routing["faculty_model"]["base_url"] == "https://api.minimax.io/v1"
    assert routing["judge_model"]["configured"] is True
    assert routing["judge_model"]["model_id"] == "anthropic/claude-sonnet-4"

    _assert_no_credentials(routing)


# ---- integration tests: hit the endpoint via the FastAPI app ----------------------------------


async def test_capabilities_endpoint_surfaces_all_three_sections(client: AsyncClient) -> None:
    """``/capabilities`` returns ``capabilities`` + ``providers`` + ``transport`` + ``model_routing``.

    The existing per-adapter rows are untouched (the section is purely additive — no behaviour
    change for current consumers). The three new sections are present and well-formed.
    """
    response = await client.get("/capabilities")
    assert response.status_code == 200
    body = response.json()

    # Backwards-compatible: the per-adapter rows are still here.
    assert "capabilities" in body
    assert isinstance(body["capabilities"], list)
    names = {row["name"] for row in body["capabilities"]}
    assert {"lead_research_batch", "draft_email", "human_task"}.issubset(names)

    # New sections (Spec §8 row 4).
    assert "providers" in body
    assert isinstance(body["providers"], list)
    assert "transport" in body
    assert isinstance(body["transport"], dict)
    assert "model_routing" in body
    assert isinstance(body["model_routing"], dict)

    # Provider rows are well-formed.
    for row in body["providers"]:
        assert set(row) >= {"name", "kind", "configured", "reachable"}

    # Transport shape — both configured/not-configured variants satisfy the documented keys.
    transport = body["transport"]
    assert set(transport) >= {"configured", "name", "live_gated", "details"}

    # Model routing shape.
    routing = body["model_routing"]
    assert set(routing) >= {"faculty_model", "judge_model"}

    # Invariant #2 across the whole payload — no secret material ever crosses the seam.
    _assert_no_credentials(body)


async def test_capabilities_endpoint_routes_do_not_leak_settings_secret_fields(client: AsyncClient) -> None:
    """String-scan the full payload as a defence-in-depth check for any leaked secret.

    The recursive key-name scan catches credential-like FIELD NAMES; this scan catches accidental
    value leaks (e.g. a future regression that surfaces ``base_url`` with a key embedded in the
    query string). Belt-and-braces for invariant #2.
    """
    body = (await client.get("/capabilities")).json()
    payload_str = str(body)

    # Common credential patterns to forbid outright.
    forbidden_substrings = (
        "Bearer ",
        "sk-",
        "pk-",
        "password=",
        "api_key=",
        "secret=",
    )
    for substring in forbidden_substrings:
        assert substring not in payload_str, (
            f"forbidden credential substring {substring!r} leaked into /capabilities response"
        )


async def test_capabilities_endpoint_is_idempotent(client: AsyncClient) -> None:
    """Two consecutive GETs return the same shape — the section is stateless / read-only.

    Spec C11 is explicitly "READ ONLY"; this guards against accidental caching of mutable state.
    """
    first = (await client.get("/capabilities")).json()
    second = (await client.get("/capabilities")).json()

    # Sections present + same keys (values like ``checked_at`` may differ between calls).
    assert set(first) == set(second)
    assert set(first["transport"]) == set(second["transport"])
    assert {row["name"] for row in first["providers"]} == {
        row["name"] for row in second["providers"]
    }


# ---- import-linter / module surface sanity ----------------------------------------------------


def test_capability_health_module_exports_the_three_builders() -> None:
    """The module surface is small and intentional — three builders, no extras."""
    from agentx_api import capability_health

    assert set(capability_health.__all__) == {
        "model_routing_status",
        "provider_reachability",
        "transport_status",
    }


# Touch the cached settings getter so any future change to ``Settings`` doesn't silently break
# these tests. The linter warns on unused imports otherwise.
_ = _get_settings_cached
