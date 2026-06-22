"""P12 live Hermes/Minimax client boundary."""

import os

import pytest
from agentx_contracts.config import Settings
from agentx_kernel.hermes import HermesClient
from pydantic import SecretStr


def test_hermes_client_builds_openai_compatible_payload_and_endpoint() -> None:
    client = HermesClient(base_url="https://api.minimax.io/v1/", api_key=SecretStr("secret"), model_id="MiniMax-M3")

    assert client.chat_completions_url == "https://api.minimax.io/v1/chat/completions"
    assert client.payload("hello") == {
        "model": "MiniMax-M3",
        "messages": [{"role": "user", "content": "hello"}],
    }


def test_hermes_client_builds_tool_calling_chat_payload() -> None:
    client = HermesClient(base_url="https://api.minimax.io/v1", api_key=SecretStr("secret"), model_id="MiniMax-M3")

    payload = client.chat_payload(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "think"}}],
    )

    assert payload["model"] == "MiniMax-M3"
    assert payload["tool_choice"] == "auto"
    assert payload["stream"] is False
    assert payload["messages"] == [{"role": "user", "content": "hi"}]
    tools = payload["tools"]
    assert isinstance(tools, list)
    assert tools[0]["function"]["name"] == "think"


def test_hermes_client_from_settings_requires_key_base_url_and_model() -> None:
    settings = Settings(
        minimax_api_key=SecretStr("secret"),
        faculty_model_base_url="https://api.minimax.io/v1",
        faculty_model_id="MiniMax-M3",
    )

    client = HermesClient.from_settings(settings)

    assert client.chat_completions_url == "https://api.minimax.io/v1/chat/completions"


@pytest.mark.live
async def test_live_hermes_chat_completion() -> None:
    if os.getenv("RUN_LIVE_HERMES") != "1":
        pytest.skip("set RUN_LIVE_HERMES=1 with MINIMAX_API_KEY/FACULTY_MODEL_* to run")

    client = HermesClient.from_settings(Settings())
    text = await client.complete("Reply with the single word: ok")

    assert text.strip()


# --- Gemini toggle (design §5 / step 6) ----------------------------------------
# The toggle is *just* a transport/model swap at construction time: Gemini exposes the same
# OpenAI-compat chat-completions shape as MiniMax, so the runner needs no rewrite.


def test_build_faculty_transport_defaults_to_minimax_when_use_gemini_false() -> None:
    from agentx_kernel.hermes import build_faculty_transport

    settings = Settings(
        minimax_api_key=SecretStr("minimax-secret"),
        faculty_model_base_url="https://api.minimax.io/v1",
        faculty_model_id="MiniMax-M3",
        # use_gemini is False by default
        gemini_api_key=SecretStr("gemini-secret"),
        gemini_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        gemini_model_id="gemini-2.5-flash",
    )

    client = build_faculty_transport(settings)

    assert client.provider == "minimax"
    assert client.chat_completions_url == "https://api.minimax.io/v1/chat/completions"


def test_build_faculty_transport_routes_to_gemini_when_fully_configured() -> None:
    from agentx_kernel.hermes import build_faculty_transport

    settings = Settings(
        minimax_api_key=SecretStr("minimax-secret"),
        faculty_model_base_url="https://api.minimax.io/v1",
        faculty_model_id="MiniMax-M3",
        use_gemini=True,
        gemini_api_key=SecretStr("gemini-secret"),
        gemini_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        gemini_model_id="gemini-2.5-flash",
    )

    client = build_faculty_transport(settings)

    assert client.provider == "gemini"
    assert (
        client.chat_completions_url
        == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    )
    # The OpenAI-compat body shape is identical between providers — the same request works.
    payload = client.payload("hello")
    assert payload["model"] == "gemini-2.5-flash"


def test_build_faculty_transport_partial_gemini_config_falls_back_to_minimax() -> None:
    """If the operator flips use_gemini but forgets one of key/base_url/model_id, we MUST keep
    working on the canonical MiniMax transport rather than 500 the runner. Better safe than sorry.
    """
    from agentx_kernel.hermes import build_faculty_transport

    settings = Settings(
        minimax_api_key=SecretStr("minimax-secret"),
        faculty_model_base_url="https://api.minimax.io/v1",
        faculty_model_id="MiniMax-M3",
        use_gemini=True,
        # gemini_api_key missing → falls back
        gemini_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        gemini_model_id="gemini-2.5-flash",
    )

    client = build_faculty_transport(settings)

    assert client.provider == "minimax"


def test_build_faculty_transport_requires_minimax_key_when_neither_is_usable() -> None:
    from agentx_kernel.errors import ConfigError
    from agentx_kernel.hermes import build_faculty_transport

    settings = Settings(
        minimax_api_key=None,
        faculty_model_base_url="https://api.minimax.io/v1",
        faculty_model_id="MiniMax-M3",
    )

    with pytest.raises(ConfigError):
        build_faculty_transport(settings)


def test_hermes_client_from_settings_is_backwards_compatible_alias() -> None:
    """The legacy ``HermesClient.from_settings()`` call sites (scripts/, tests/, dogfood) keep
    working byte-for-byte: it now delegates to ``build_faculty_transport`` so the toggle applies,
    but with the default Settings it produces the same Minimax-pointed client as before."""
    settings = Settings(
        minimax_api_key=SecretStr("minimax-secret"),
        faculty_model_base_url="https://api.minimax.io/v1",
        faculty_model_id="MiniMax-M3",
    )

    client = HermesClient.from_settings(settings)

    assert client.provider == "minimax"
    assert client.chat_completions_url == "https://api.minimax.io/v1/chat/completions"
