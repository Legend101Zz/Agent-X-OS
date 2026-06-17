"""Credential types — INVARIANT #2: NOT importable from ``agentx_mandate`` (pods hold no creds).

This module is deliberately quarantined. It is NOT re-exported from ``agentx_contracts.__init__``;
it must be imported explicitly (``from agentx_contracts.security import Credential``), and the build
forbids ``agentx_mandate`` from importing it at all — enforced by ``.importlinter`` AND
``tests/test_credential_boundary.py``.

The ONLY place a ``Credential`` is ever passed is ``Adapter.execute(req, cred)``: the kernel gateway
injects it from the vault at call time. It never enters a user-space pod, a hydration snapshot, the
journal, or the heap.
"""

from pydantic import ConfigDict, SecretStr

from .base import AgentXModel
from .enums import TenantAuth


class Credential(AgentXModel):
    """An opaque, injected credential handle. Secret material is a ``SecretStr`` (redacted in logs).

    Frozen: a credential is never mutated after the gateway injects it. ``material`` is ``None`` for
    the ``manual`` auth path (the human-task tail needs no secret).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str
    """Non-secret vault handle / lookup key (safe to log and journal)."""
    kind: TenantAuth
    material: SecretStr | None = None
    """The injected secret, redacted in ``repr``/logs. Read via ``.get_secret_value()`` at call time only."""
