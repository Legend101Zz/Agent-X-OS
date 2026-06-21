"""The F1–F6 mandate-discovery faculties (plus F7 escalation which is shared).

Each mandate-discovery faculty is a faculty in the agentx_mandate sense:
``FACULTY`` data (name, skill_pack ref, tool_manifest, eval_slice, harness_adapter)
plus a ``propose(ctx) -> list[HarnessAction]`` function the playbook drives.

The F1 community-source faculty proposes a READ intent — ``community_source_sample``
— that the gateway fulfils via the read adapters (Reddit / HN / X / Discord /
forum / IndieHackers / G2 / ProductHunt). The playbook then yields a Claim
that commits the sampled posts as provenance-stamped facts.

F2 / F3 / F6 are LLM-on-scratchpad faculties — the LLM proposes structured
JSON (pain signals, mandate candidates, portfolio), and the deterministic
``mandate_discovery_quality`` module applies the gates.

F4 / F5 are read intents (competitor search, channel discovery) that the
gateway fulfils.

F7 is the standard ``escalation`` faculty (shared with lead-finder + creator).
"""

from agentx_mandate.faculties.escalation import FACULTY as _SHARED_ESCALATION

# F1 — community-source
from .f1_community_source import FACULTY as F1_COMMUNITY_SOURCE
from .f1_community_source import propose as f1_propose

# F2 — pain-extraction
from .f2_pain_extraction import FACULTY as F2_PAIN_EXTRACTION
from .f2_pain_extraction import propose as f2_propose

# F3 — demand-clustering
from .f3_demand_clustering import FACULTY as F3_DEMAND_CLUSTERING
from .f3_demand_clustering import propose as f3_propose

# F4 — competitor-stress-test
from .f4_competitor_stress import FACULTY as F4_COMPETITOR_STRESS
from .f4_competitor_stress import propose as f4_propose

# F5 — buyer-mapping
from .f5_buyer_mapping import FACULTY as F5_BUYER_MAPPING
from .f5_buyer_mapping import propose as f5_propose

# F6 — mandate-portfolio-builder (the gated Claim)
from .f6_portfolio_builder import FACULTY as F6_PORTFOLIO_BUILDER
from .f6_portfolio_builder import propose as f6_propose

# F7 — escalation (re-exported from the shared library; the playbook imports from here
# for symmetry with F1–F6 even though it's not a discovery-specific faculty)
F7_ESCALATION = _SHARED_ESCALATION

__all__ = [
    "F1_COMMUNITY_SOURCE",
    "F2_PAIN_EXTRACTION",
    "F3_DEMAND_CLUSTERING",
    "F4_COMPETITOR_STRESS",
    "F5_BUYER_MAPPING",
    "F6_PORTFOLIO_BUILDER",
    "F7_ESCALATION",
    "f1_propose",
    "f2_propose",
    "f3_propose",
    "f4_propose",
    "f5_propose",
    "f6_propose",
]
