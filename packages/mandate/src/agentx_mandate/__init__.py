"""agentx_mandate — CLAUDE LANE (Session B).

MandateType/Instance/Run as data, the seven organs, the FACULTIES FRAMEWORK (each faculty's
harness_adapter enables the harness's native skills, re-points effectful tools to the gateway, and
treats harness memory as per-run scratch), the MEMORY LAYER, HYDRATION, and the SETTLEMENT engine.
Phase-1 faculties: research, judgment, memory-craft, escalation. Phase-3 (Creator) added:
conversation, scheduling. Phase-12 (mandate-discovery) added: 6 discovery-specific faculties
(F1 community-source, F2 pain-extraction, F3 demand-clustering, F4 competitor-stress-test,
F5 buyer-mapping, F6 mandate-portfolio-builder) plus the deterministic quality gates.

INVARIANT #2 (enforced by .importlinter + tests/test_credential_boundary.py): this package depends
ONLY on the PURE seam of ``agentx_contracts``. It must NEVER import ``agentx_contracts.security``
(Credential) or ``agentx_contracts.config`` (Settings), nor any credentialed package — pods hold no
credentials and no durable state below the adapter line.
"""

from agentx_mandate.library import (
    build_creator_type,
    build_lead_finder_type,
    build_mandate_discovery_type,
)

__all__ = [
    "build_creator_type",
    "build_lead_finder_type",
    "build_mandate_discovery_type",
]

