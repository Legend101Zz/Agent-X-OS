"""agentx_syscall — CODEX LANE (Session B).

The Adapter framework + capability registry + fulfillment-ladder resolution (with the
HumanTaskAdapter as the tail of EVERY ladder), health checks, and fixtures. Phase-1 adapters:
lead_research_batch, read_url, draft_email (draft mode only — no send), queue_manual_action,
mark_outcome. Any MCP server is wrapped BEHIND the gateway's ``Adapter`` interface — never raw.

Implements ``agentx_contracts.Adapter`` and ``agentx_contracts.SyscallRegistry``. Build against the
FROZEN contracts only. See AGENTS.md (lane + invariants) and BUILD-PLAN.md (task graph).
"""

from agentx_syscall.adapters import (
    DraftEmailAdapter,
    ExaResearchProvider,
    FirecrawlResearchProvider,
    HumanTaskAdapter,
    LeadResearchBatchAdapter,
    ManualTask,
    ManualTaskStore,
    MarkOutcomeAdapter,
    QueueManualActionAdapter,
    ReadUrlAdapter,
    ResearchLead,
    ResearchPage,
    ResearchProvider,
)
from agentx_syscall.registry import Phase1SyscallRegistry, build_phase1_registry

__all__ = [
    "DraftEmailAdapter",
    "ExaResearchProvider",
    "FirecrawlResearchProvider",
    "HumanTaskAdapter",
    "LeadResearchBatchAdapter",
    "ManualTask",
    "ManualTaskStore",
    "MarkOutcomeAdapter",
    "Phase1SyscallRegistry",
    "QueueManualActionAdapter",
    "ReadUrlAdapter",
    "ResearchLead",
    "ResearchPage",
    "ResearchProvider",
    "build_phase1_registry",
]
