"""T4 — the config-backed credential vault (invariant #2: the pod never holds a secret).

The gateway resolves ``vault://{tenant_id}/{adapter_name}`` at call time and injects the result ONLY
into ``Adapter.execute``. ConfigVault sources real secrets from kernel Settings — never from a pod.
"""

from agentx_contracts.config import Settings
from agentx_contracts.security import Credential
from agentx_kernel.vault import ConfigVault
from pydantic import SecretStr

# _env_file=None keeps these hermetic (they ignore any real .env on the machine).


async def test_research_ref_resolves_real_api_key_credential() -> None:
    vault = ConfigVault(Settings(_env_file=None, exa_api_key=SecretStr("test-exa-key")))

    cred = await vault.get(ref="vault://tenant_inst_a/lead_research_batch", tenant_id="tenant_inst_a")

    assert isinstance(cred, Credential)
    assert cred.kind == "api_key"
    assert cred.material is not None
    assert cred.material.get_secret_value() == "test-exa-key"
    assert cred.ref == "vault://tenant_inst_a/lead_research_batch"


async def test_research_ref_prefers_exa_then_firecrawl() -> None:
    vault = ConfigVault(Settings(_env_file=None, firecrawl_api_key=SecretStr("fc-key")))

    cred = await vault.get(ref="vault://t/read_url", tenant_id="t")

    assert cred is not None and cred.kind == "api_key"
    assert cred.material is not None and cred.material.get_secret_value() == "fc-key"


async def test_non_keyed_adapter_gets_manual_credential_without_secret() -> None:
    vault = ConfigVault(Settings(_env_file=None, exa_api_key=SecretStr("test-exa-key")))

    cred = await vault.get(ref="vault://t/draft_email", tenant_id="t")

    assert cred is not None
    assert cred.kind == "manual"
    assert cred.material is None


async def test_research_ref_without_configured_key_falls_back_to_manual() -> None:
    vault = ConfigVault(Settings(_env_file=None))  # no exa/firecrawl keys

    cred = await vault.get(ref="vault://t/lead_research_batch", tenant_id="t")

    assert cred is not None and cred.kind == "manual" and cred.material is None
