"""Kernel-side Hermes/Minimax live client boundary.

MiniMax exposes an OpenAI-compatible ``/v1/chat/completions`` API, and Gemini exposes the same shape
on its own OpenAI-compat base. Either backend satisfies the runner's ``ChatTransport`` Protocol
(same request/response schema), so the toggle is just a transport/model swap at construction time —
no runner rewrite. This module keeps the factory: ``build_faculty_transport(settings)`` returns a
``HermesClient`` pointing at Gemini when ``use_gemini`` is true AND a key is present, otherwise the
canonical MiniMax client (default off → nothing changes).

The client stays in the kernel because it holds API credentials; mandate pods never import it.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Any, cast

from agentx_contracts.config import Settings, get_settings
from agentx_contracts.jsontypes import JsonObject
from pydantic import SecretStr

from .errors import ConfigError


class HermesClient:
    """Minimal async wrapper over an OpenAI-compatible chat completions endpoint (Minimax OR Gemini).

    The constructor is deliberately backend-agnostic — the only things that change between MiniMax
    and Gemini are the ``base_url``, ``api_key``, and ``model_id`` (the request/response shape and
    the ``complete_chat`` semantics are identical). The factory ``build_faculty_transport`` resolves
    those three fields from ``Settings`` based on the ``use_gemini`` toggle.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        model_id: str,
        provider: str = "minimax",
    ) -> None:
        if not base_url:
            raise ConfigError("FACULTY_MODEL_BASE_URL is required for Hermes")
        if not model_id:
            raise ConfigError("FACULTY_MODEL_ID is required for Hermes")
        if not api_key.get_secret_value():
            raise ConfigError("model API key is required for Hermes")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model_id = model_id
        self._provider = provider

    @property
    def provider(self) -> str:
        """``"minimax"`` or ``"gemini"`` — useful for logs/health, not for behaviour."""
        return self._provider

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> HermesClient:
        """Backwards-compatible factory — routes to Gemini when ``use_gemini`` is true, else Minimax.

        Existing call sites (``HermesClient.from_settings()``) keep working unchanged: with
        ``use_gemini=False`` (the default) the behaviour is identical to the legacy MiniMax-only
        client. Use ``build_faculty_transport`` directly when the caller wants the new explicit name.
        """
        return build_faculty_transport(settings)

    @property
    def chat_completions_url(self) -> str:
        return f"{self._base_url}/chat/completions"

    def payload(self, prompt: str) -> dict[str, object]:
        return {
            "model": self._model_id,
            "messages": [{"role": "user", "content": prompt}],
        }

    def chat_payload(
        self, *, messages: list[JsonObject], tools: list[JsonObject]
    ) -> dict[str, object]:
        """The OpenAI tool-calling body for MiniMax-M3 (research-confirmed params; see findings.md)."""
        return {
            "model": self._model_id,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 1.0,
            "top_p": 0.95,
            # Headroom so a long tool-call (e.g. a full draft_email body) plus the
            # model's interleaved reasoning don't truncate mid-arguments — a
            # truncated arguments JSON makes the next turn fail with HTTP 400.
            "max_tokens": 8192,
            "stream": False,
        }

    async def complete(self, prompt: str) -> str:
        response = await asyncio.to_thread(self._post, self.payload(prompt))
        return _extract_content(response)

    async def complete_chat(self, *, messages: list[JsonObject], tools: list[JsonObject]) -> JsonObject:
        """Drive one tool-calling turn; return the raw chat-completion response (the runner parses it).

        M3 tool-calling gets slow as the page-markdown history grows; retry once on a transient network
        error so a single slow turn does not abort a multi-step agentic run.
        """
        payload = self.chat_payload(messages=messages, tools=tools)
        last_exc: Exception | None = None
        for _ in range(2):
            try:
                return cast(JsonObject, await asyncio.to_thread(self._post, payload))
            except urllib.error.HTTPError as exc:
                # A 4xx is a malformed/oversized request — retrying sends the same
                # bad body and wastes a call. Surface MiniMax's error body (which
                # explains WHY: max-context exceeded, invalid param, etc.) and stop.
                detail = _read_http_error_body(exc)
                raise RuntimeError(f"Hermes chat call failed: HTTP {exc.code} {exc.reason}: {detail}") from exc
            except (TimeoutError, urllib.error.URLError, OSError) as exc:
                last_exc = exc
        raise RuntimeError(f"Hermes chat call failed after retries: {last_exc}")

    def _post(self, payload: dict[str, object], timeout: int = 180) -> dict[str, object]:
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
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise RuntimeError("Hermes response was not a JSON object")
        return parsed


def _read_http_error_body(exc: urllib.error.HTTPError) -> str:
    """Read the response body off an HTTPError (MiniMax returns a JSON reason there).

    ``urllib`` raises before the caller can read the body; the body is the single
    most useful diagnostic for a 400 (it names the bad parameter or "context
    length exceeded"). Best-effort, clipped so a giant body doesn't flood logs.
    """
    try:
        raw = exc.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return "(no response body)"
    return raw[:800]


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


def build_faculty_transport(settings: Settings | None = None) -> HermesClient:
    """The kernel-side factory: build the faculty-model transport from ``Settings``.

    Routes by ``settings.use_gemini`` (added in step 1 of the books-prep build, design §5):
      * ``use_gemini=True`` AND ``gemini_api_key`` AND ``gemini_base_url`` AND ``gemini_model_id``
        → ``HermesClient`` pointed at Gemini's OpenAI-compat endpoint.
      * Anything else (default) → the canonical MiniMax client (no behaviour change).

    This is the one switch a future CLI flag / env var flips to satisfy the hackathon's
    "≥1 Gemini call in production" requirement. Multimodal (scanned docs) is a FUTURE transport
    extension (image parts) — out of v0 scope; the interface today is text-only.
    """
    loaded = settings or get_settings()
    if loaded.use_gemini and loaded.gemini_api_key and loaded.gemini_base_url and loaded.gemini_model_id:
        return HermesClient(
            base_url=loaded.gemini_base_url,
            api_key=loaded.gemini_api_key,
            model_id=loaded.gemini_model_id,
            provider="gemini",
        )
    if loaded.minimax_api_key is None:
        raise ConfigError("MINIMAX_API_KEY is required for Hermes (Gemini toggle is off or incomplete)")
    return HermesClient(
        base_url=loaded.faculty_model_base_url,
        api_key=loaded.minimax_api_key,
        model_id=loaded.faculty_model_id,
        provider="minimax",
    )
