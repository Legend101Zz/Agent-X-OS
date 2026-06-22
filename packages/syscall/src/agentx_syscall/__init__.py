"""agentx_syscall — CODEX LANE (Session B).

The Adapter framework + capability registry + fulfillment-ladder resolution (with the
HumanTaskAdapter as the tail of EVERY ladder), health checks, and fixtures. Phase-1 adapters:
lead_research_batch, read_url, draft_email (draft mode only — no send), queue_manual_action,
mark_outcome. Any MCP server is wrapped BEHIND the gateway's ``Adapter`` interface — never raw.

Implements ``agentx_contracts.Adapter`` and ``agentx_contracts.SyscallRegistry``. Build against the
FROZEN contracts only. See AGENTS.md (lane + invariants) and BUILD-PLAN.md (task graph).
"""

from agentx_syscall.adapters import (
    BraveSearchProvider,
    DraftCandidateTypeAdapter,
    DraftEmailAdapter,
    EmailTransport,
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
    ResearchResult,
    SendEmailAdapter,
    SentEmailReceipt,
)
from agentx_syscall.deep_research_adapter import DeepResearchAdapter
from agentx_syscall.email_transports import (
    ResendEmailTransport,
    build_configured_email_transport,
)
from agentx_syscall.manual_tasks import (
    InMemoryManualTaskRepository,
    ManualTaskRepository,
    MongoManualTaskRepository,
    make_in_memory_manual_task_repository,
    make_mongo_manual_task_repository,
)
from agentx_syscall.registry import Phase1SyscallRegistry, build_phase1_registry

__all__ = [
    "BraveSearchProvider",
    "DeepResearchAdapter",
    "DraftCandidateTypeAdapter",
    "DraftEmailAdapter",
    "EmailTransport",
    "ExaResearchProvider",
    "FirecrawlResearchProvider",
    "HumanTaskAdapter",
    "InMemoryManualTaskRepository",
    "LeadResearchBatchAdapter",
    "ManualTask",
    "ManualTaskRepository",
    "ManualTaskStore",
    "MarkOutcomeAdapter",
    "MongoManualTaskRepository",
    "Phase1SyscallRegistry",
    "QueueManualActionAdapter",
    "ReadUrlAdapter",
    "ResearchLead",
    "ResearchPage",
    "ResearchProvider",
    "ResearchResult",
    "ResendEmailTransport",
    "SendEmailAdapter",
    "SentEmailReceipt",
    "build_configured_email_transport",
    "build_phase1_registry",
    "make_in_memory_manual_task_repository",
    "make_mongo_manual_task_repository",
]  # noqa: E501
