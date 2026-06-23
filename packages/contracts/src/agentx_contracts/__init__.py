"""agentx_contracts — THE SEAM both build agents depend on (frozen after Session A).

Pydantic v2 domain + memory models and ``typing.Protocol`` interfaces. This ``__init__`` re-exports
the PURE seam only. The credential-bearing modules are intentionally NOT re-exported and must be
imported explicitly (and are forbidden to ``agentx_mandate`` — invariant #2):

    from agentx_contracts.security import Credential      # gateway/adapters only
    from agentx_contracts.config import get_settings      # kernel/infra only

If a Protocol or model here is wrong, fixing it is a STOP-AND-COORDINATE event (BUILD-PLAN.md):
edit contracts, both agents re-pull, then resume. No agent edits the other's package.
"""

from .base import AgentXModel
from .enums import (
    ApprovalDecision,
    CaseOrigin,
    FactSource,
    FactStatus,
    FulfillmentPreference,
    HarnessKind,
    HealthStatus,
    MaturityLevel,
    Ring,
    RiskClass,
    RuleDecision,
    RunMode,
    RunState,
    SyscallStatus,
    TenantAuth,
    TriggerKind,
    VerificationRung,
)
from .faculty import Faculty, FacultyBinding, HarnessAdapterSpec, RoutingHint
from .gym import EvalCase
from .journal import (
    ApprovalResolved,
    DeferredSettled,
    JournalEvent,
    ManagerAction,
    RunCreated,
    RunHydrated,
    RunParked,
    RunSettled,
    RunVerified,
    SyscallAttempted,
    SyscallSettled,
    WatchFired,
    WatchRegistered,
)
from .jsontypes import JsonObject, JsonSchema, JsonValue
from .mandate import (
    ChannelBinding,
    Charter,
    Condition,
    DomainPackRef,
    ExecutionProfile,
    HydrationSnapshot,
    InstanceBinding,
    MandateInstance,
    MandateRun,
    MandateType,
    Override,
    RoutingEntry,
    SettlementRules,
    SpawnRule,
    VerificationSuite,
)
from .memory import Fact, Provenance, Resume, Thread
from .protocols import Adapter, Judge, RuleCheck, RunInvoker, SyscallRegistry
from .run import ParkInfo, RunResult
from .settlement import (
    BillingLine,
    SettlementEvent,
    SpawnInstruction,
    ThreadUpdate,
    TrustDelta,
    Watch,
)
from .syscall import (
    ChannelRule,
    GatewayContext,
    Health,
    RuleVerdict,
    SyscallRequest,
    SyscallResult,
    SyscallTestCase,
    VerifyOutcome,
)
from .toolschema import TOOL_SCHEMAS, ToolSchema, tool_schema_for
from .trigger import DeadlineTrigger, MessageTrigger, SpawnTrigger, Trigger
from .verification import (
    CriterionResult,
    Rubric,
    RubricCriterion,
    Scorecard,
    Trace,
    TraceEvent,
)

__all__ = [
    # base + json
    "AgentXModel",
    "JsonObject",
    "JsonSchema",
    "JsonValue",
    # enums
    "ApprovalDecision",
    "CaseOrigin",
    "FactSource",
    "FactStatus",
    "FulfillmentPreference",
    "HarnessKind",
    "HealthStatus",
    "MaturityLevel",
    "Ring",
    "RiskClass",
    "RuleDecision",
    "RunMode",
    "RunState",
    "SyscallStatus",
    "TenantAuth",
    "TriggerKind",
    "VerificationRung",
    # memory
    "Fact",
    "Provenance",
    "Resume",
    "Thread",
    # verification
    "CriterionResult",
    "Rubric",
    "RubricCriterion",
    "Scorecard",
    "Trace",
    "TraceEvent",
    # faculty
    "Faculty",
    "FacultyBinding",
    "HarnessAdapterSpec",
    "RoutingHint",
    # trigger
    "DeadlineTrigger",
    "MessageTrigger",
    "SpawnTrigger",
    "Trigger",
    # journal (event-sourced source of truth)
    "ApprovalResolved",
    "DeferredSettled",
    "JournalEvent",
    "ManagerAction",
    "RunCreated",
    "RunHydrated",
    "RunParked",
    "RunSettled",
    "RunVerified",
    "SyscallAttempted",
    "SyscallSettled",
    "WatchFired",
    "WatchRegistered",
    # syscall boundary
    "ChannelRule",
    "GatewayContext",
    "Health",
    "RuleVerdict",
    "SyscallRequest",
    "SyscallResult",
    "SyscallTestCase",
    "VerifyOutcome",
    # tool-schema registry (harness generalization seam)
    "TOOL_SCHEMAS",
    "ToolSchema",
    "tool_schema_for",
    # mandate
    "Charter",
    "ChannelBinding",
    "Condition",
    "DomainPackRef",
    "ExecutionProfile",
    "HydrationSnapshot",
    "InstanceBinding",
    "MandateInstance",
    "MandateRun",
    "MandateType",
    "Override",
    "RoutingEntry",
    "SettlementRules",
    "SpawnRule",
    "VerificationSuite",
    # settlement
    "BillingLine",
    "SettlementEvent",
    "SpawnInstruction",
    "ThreadUpdate",
    "TrustDelta",
    "Watch",
    # gym
    "EvalCase",
    # run result
    "ParkInfo",
    "RunResult",
    # protocols (the three seams)
    "Adapter",
    "Judge",
    "RuleCheck",
    "RunInvoker",
    "SyscallRegistry",
]
