"""Typed config loader (pydantic-settings) — reads ``.env``.

Holds SECRETS, so like ``security.py`` it is quarantined: NOT re-exported from
``agentx_contracts.__init__`` and forbidden to ``agentx_mandate`` (a user-space pod must not be able
to reach a connection string or an API key). Import explicitly:
``from agentx_contracts.config import get_settings``.

Defaults are empty so importing/constructing never fails when ``.env`` is absent (CI, mypy, tests);
the kernel validates that required secrets are present at startup, not at import time.
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All Phase-1 environment variables, typed. Field names map to UPPER_SNAKE env vars (case-insensitive)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database (kernel) ---
    mongodb_uri: SecretStr = SecretStr("")
    mongodb_db_name: str = "agentx"

    # --- Faculties: the Hermes harness drives Minimax DIRECTLY (your Minimax API key) ---
    minimax_api_key: SecretStr | None = None
    faculty_model_base_url: str = ""  # Minimax OpenAI-compatible endpoint, e.g. https://api.minimax.io/v1 (confirm)
    faculty_model_id: str = ""  # e.g. "MiniMax-M2"
    hermes_endpoint: str | None = None  # how the kernel reaches Hermes (if a service); build agent confirms

    # --- promptfoo JUDGE: via OpenRouter (one key, any model) — a DIFFERENT model than the faculties ---
    openrouter_api_key: SecretStr | None = None
    judge_model_id: str = ""  # OpenRouter slug, e.g. "anthropic/claude-sonnet-4"

    # Optional: a direct GLM/Zhipu key, if you swap the faculty model off Minimax.
    zhipu_api_key: SecretStr | None = None

    # --- Research provider (Codex lane) — set at least one ---
    exa_api_key: SecretStr | None = None
    firecrawl_api_key: SecretStr | None = None

    # --- Eval / judge / gate (Codex lane) ---
    promptfoo_api_key: SecretStr | None = None

    # --- Runtime ---
    agentx_env: Literal["dev", "test", "prod"] = "dev"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide ``Settings`` (cached). Reads ``.env`` once on first call."""
    return Settings()
