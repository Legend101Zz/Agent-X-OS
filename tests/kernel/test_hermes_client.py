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
