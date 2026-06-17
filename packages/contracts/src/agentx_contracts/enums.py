"""Closed vocabularies for the seam.

Expressed as ``Literal`` aliases (not ``enum.Enum``) because they serialize as plain strings/ints,
give mypy exhaustiveness checking for free, and match the BUILD-KIT §3 seam style verbatim
(``Ring = Literal["L0",...]``).
"""

from typing import Literal, TypeAlias

# --- Authority --------------------------------------------------------------------------
# The trust ladder / protection rings. Phase 1 operates L0–L2 only; L3/L4 reserved.
Ring: TypeAlias = Literal["L0", "L1", "L2", "L3", "L4"]

# --- Run lifecycle (the durable continuation state machine; ARCHITECTURE Diagram 11) -----
RunState: TypeAlias = Literal["created", "running", "parked", "verifying", "settled", "crashed"]

# How a run was invoked. SIM means the swarm is driving the SAME loop with SimAdapters bound.
RunMode: TypeAlias = Literal["live", "sim"]

# --- Syscall / adapter vocabulary -------------------------------------------------------
# Adapter fulfillment maturity: 0=manual queue · 1=draft · 2=semi-auto · 3=full API.
MaturityLevel: TypeAlias = Literal[0, 1, 2, 3]

# Risk taxonomy for an effect. `money`/`irreversible` reserve the L4 + human-gate + API-only path
# (invariant #6) even though no money syscalls exist in Phase 1.
RiskClass: TypeAlias = Literal["read", "external_message", "reversible_write", "money", "irreversible"]

# Where the per-tenant credential comes from (for the adapter the gateway selects).
TenantAuth: TypeAlias = Literal["oauth", "api_key", "agent_owned", "manual"]

# Outcome status of a syscall as seen by the gateway/pod.
SyscallStatus: TypeAlias = Literal["ok", "parked", "error", "queued_manual"]

# Adapter health.
HealthStatus: TypeAlias = Literal["ok", "degraded", "down"]

# Deterministic rules-rung decision at the gateway.
RuleDecision: TypeAlias = Literal["allow", "park", "deny"]

# --- Verification -----------------------------------------------------------------------
# The verification ladder, cheapest rung first (BLUEPRINT §1 / MANDATE §4).
VerificationRung: TypeAlias = Literal["rules", "judge", "human", "reality"]

# A human's resolution of a parked approval.
ApprovalDecision: TypeAlias = Literal["approve", "edit", "reject"]

# --- Memory -----------------------------------------------------------------------------
# Provenance class of a heap fact (ARCHITECTURE Diagram 4 — "the three births of memory").
FactSource: TypeAlias = Literal["owner-stated", "owner-corrected", "agent-inferred", "outcome"]

# Heap-fact lifecycle: facts enter on probation and are promoted/retired by reality (the watch).
FactStatus: TypeAlias = Literal["probation", "promoted", "retired"]

# --- Faculties (BLUEPRINT §1 / §4.5) ----------------------------------------------------
# A faculty's preferred fulfillment, mirroring the syscall ladder: prefer the harness's strong
# native skill, fall back to our own implementation, or run a hybrid.
FulfillmentPreference: TypeAlias = Literal["prefer_harness_native", "prefer_own", "hybrid"]

# Which harness a faculty binds to (the swappable CPU below the adapter line, Model D).
HarnessKind: TypeAlias = Literal["hermes", "openclaw", "cheetahclaws", "own"]

# --- Triggers & journal -----------------------------------------------------------------
# What starts a run. `demand` (the internal market) is reserved for after Phase 1.
TriggerKind: TypeAlias = Literal["message", "deadline", "spawn", "demand"]

# --- Eval / gym -------------------------------------------------------------------------
# Origin of a graded case. SYNTHETIC (from the swarm) is BARRED from the promotion gate
# (invariant #7); only REAL settled cases can promote a customer-facing version.
CaseOrigin: TypeAlias = Literal["synthetic", "real"]

__all__ = [
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
]
