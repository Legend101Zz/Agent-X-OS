"""Kernel-side Hermes/Minimax live client boundary.

MiniMax exposes an OpenAI-compatible ``/v1/chat/completions`` API. This client stays in the kernel
because it holds API credentials; mandate pods never import it.
"""

from __future__ import annotations

import asyncio
import json
import urllib.request
from typing import Any

from agentx_contracts.config import Settings, get_settings
from pydantic import SecretStr

from .errors import ConfigError


class HermesClient:
    """Minimal async wrapper over the MiniMax OpenAI-compatible chat completions endpoint."""

    def __init__(self, *, base_url: str, api_key: SecretStr, model_id: str) -> None:
        if not base_url:
            raise ConfigError("FACULTY_MODEL_BASE_URL is required for Hermes")
        if not model_id:
            raise ConfigError("FACULTY_MODEL_ID is required for Hermes")
        if not api_key.get_secret_value():
            raise ConfigError("MINIMAX_API_KEY is required for Hermes")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model_id = model_id

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> HermesClient:
        loaded = settings or get_settings()
        if loaded.minimax_api_key is None:
            raise ConfigError("MINIMAX_API_KEY is required for Hermes")
        return cls(
            base_url=loaded.faculty_model_base_url,
            api_key=loaded.minimax_api_key,
            model_id=loaded.faculty_model_id,
        )

    @property
    def chat_completions_url(self) -> str:
        return f"{self._base_url}/chat/completions"

    def payload(self, prompt: str) -> dict[str, object]:
        return {
            "model": self._model_id,
            "messages": [{"role": "user", "content": prompt}],
        }

    async def complete(self, prompt: str) -> str:
        response = await asyncio.to_thread(self._post, self.payload(prompt))
        return _extract_content(response)

    def _post(self, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.chat_completions_url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise RuntimeError("Hermes response was not a JSON object")
        return parsed


def _extract_content(response: dict[str, object]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("Hermes response did not include choices")
    first: Any = choices[0]
    if not isinstance(first, dict):
        raise RuntimeError("Hermes choice was not an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("Hermes choice did not include a message")
    content = message.get("content")
    if not isinstance(content, str):
        raise RuntimeError("Hermes message did not include text content")
    return content
