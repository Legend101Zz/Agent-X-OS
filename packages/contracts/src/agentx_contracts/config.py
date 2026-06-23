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

    # --- Optional Gemini transport (OFF by default) ---
    # Gemini exposes an OpenAI-compatible chat endpoint, and Hermes already drives an OpenAI-compatible
    # transport, so flipping these is a transport SWAP at construction time (no runner rewrite). Default
    # off → MiniMax → nothing changes. ``build_faculty_transport`` reads these (kernel bootstrap).
    use_gemini: bool = False
    gemini_api_key: SecretStr | None = None
    gemini_model_id: str = "gemini-2.5-flash"
    gemini_base_url: str = ""  # Gemini's OpenAI-compatible base, e.g. https://generativelanguage.googleapis.com/v1beta/openai/

    # --- Research provider (Codex lane) — set at least one ---
    exa_api_key: SecretStr | None = None  # semantic/neural search (good for discovery)
    brave_api_key: SecretStr | None = None  # Brave Search API (fast, cheap web search)
    firecrawl_api_key: SecretStr | None = None  # search + scrape (page reads)

    # --- Eval / judge / gate (Codex lane) ---
    promptfoo_api_key: SecretStr | None = None

    # --- Email send (Phase 1 — Gmail SMTP via the operator's App Password) ---
    # `email_transports.py` reads these directly via its own dotenv dance (the SMTP path was added
    # in a later session and predates the Settings widening). We declare them here too so the
    # typed loader sees them and `get_settings()` is the single source of truth.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr | None = None
    email_from: str = ""
    email_from_name: str = ""
    run_live_email: bool = False  # gated master switch for real outbound send

    # --- API runtime controls (read by api/app.py via os.getenv OR get_settings()) ---
    agentx_api_allow_fixtures: bool = False  # if True, dashboard may fall back to fake data
    agentx_cors_origins: str = ""  # comma-separated; empty = same-origin only (browser will block cross-origin)
    agentx_operator_token: SecretStr | None = None  # bearer required for /commands/*

    # --- books-prep shared storage (product app shares these dirs with the engine) ---
    # Empty string → adapters fall back to their None default (cwd for output; no
    # intake resolution for bare doc_ids). Set both to absolute paths in production.
    books_intake_dir: str = ""
    books_output_dir: str = ""

    # --- Runtime ---
    agentx_env: Literal["dev", "test", "prod"] = "dev"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide ``Settings`` (cached). Reads ``.env`` once on first call."""
    return Settings()
