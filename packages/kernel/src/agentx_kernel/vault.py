"""Config-backed credential vault — the real ``Vault`` (invariant #2).

The gateway asks the vault for a credential at call time (``vault://{tenant_id}/{adapter_name}``) and
hands it ONLY to ``Adapter.execute``. It never enters a pod, a hydration snapshot, the journal, or the
heap. This is the seam where a per-tenant secret manager plugs in later; Phase-1 sources secrets from
kernel ``Settings``.

Phase-1 mapping: the keyed research adapters (``lead_research_batch`` / ``read_url``) resolve to the
configured research-provider key; every other adapter is draft-only or the human-task tail and needs
no secret, so it gets a ``manual`` handle (the injection point stays exercised end-to-end).
"""

from __future__ import annotations

from agentx_contracts.config import Settings, get_settings
from agentx_contracts.security import Credential
from pydantic import SecretStr

# Adapter names whose effect consumes a keyed research provider.
_RESEARCH_ADAPTERS: frozenset[str] = frozenset({"lead_research_batch", "read_url"})


class ConfigVault:
    """Resolve non-secret vault refs into injectable ``Credential`` handles from kernel ``Settings``."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def get(self, ref: str, tenant_id: str) -> Credential | None:
        if _adapter_name(ref) in _RESEARCH_ADAPTERS:
            material = self._research_key()
            if material is not None:
                return Credential(ref=ref, kind="api_key", material=material)
        # No secret required (draft-only, manual, or the human-task tail).
        return Credential(ref=ref, kind="manual", material=None)

    def _research_key(self) -> SecretStr | None:
        # Prefer Exa, then Firecrawl — matching build_configured_research_providers() ordering.
        for key in (self._settings.exa_api_key, self._settings.firecrawl_api_key):
            if key is not None and key.get_secret_value().strip():
                return key
        return None


def _adapter_name(ref: str) -> str:
    """Extract the adapter segment from a ``vault://{tenant_id}/{adapter_name}`` ref."""
    return ref.rsplit("/", 1)[-1] if "/" in ref else ref
