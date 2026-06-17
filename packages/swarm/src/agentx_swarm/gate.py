"""Promotion gate for keeping synthetic wins out of customer-facing promotion."""

from __future__ import annotations

from agentx_contracts import AgentXModel, CaseOrigin, EvalCase, Ring, Scorecard
from pydantic import Field


class PromotionGateInput(AgentXModel):
    """Evidence supplied to the Phase-1 promotion gate."""

    scorecards: list[Scorecard] = Field(default_factory=list)
    eval_cases: list[EvalCase] = Field(default_factory=list)
    human_approved: bool = False
    requested_ring: Ring = "L0"


class PromotionDecision(AgentXModel):
    """Promotion gate result."""

    allowed: bool
    reasons: list[str] = Field(default_factory=list)
    live_ring: Ring | None = None


class PromotionGate:
    """Blocks promotion unless real evidence and human approval are present."""

    def __init__(self, *, min_score: float = 0.7, allow_rings: set[Ring] | None = None) -> None:
        self._min_score = min_score
        self._allow_rings = allow_rings or {"L0", "L1"}

    def evaluate(self, evidence: PromotionGateInput) -> PromotionDecision:
        reasons: list[str] = []
        if not evidence.human_approved:
            reasons.append("human approval is required")
        if evidence.requested_ring not in self._allow_rings:
            reasons.append(f"requested ring {evidence.requested_ring} is not allowed for Phase 1")

        passed_scorecards = [
            scorecard
            for scorecard in evidence.scorecards
            if scorecard.passed and scorecard.score >= self._min_score
        ]
        passed_eval_case_origins = [
            eval_case.origin
            for eval_case in evidence.eval_cases
            if eval_case.scorecard is not None
            and eval_case.scorecard.passed
            and eval_case.scorecard.score >= self._min_score
        ]
        origins = [scorecard.origin for scorecard in passed_scorecards] + passed_eval_case_origins

        if not origins:
            reasons.append("no passing scorecard evidence")
        elif "real" not in origins:
            reasons.append("synthetic-only evidence cannot promote customer-facing versions")
        if any(origin == "synthetic" for origin in origins) and "real" not in origins:
            reasons.append("Scorecard.origin/EvalCase.origin synthetic cases are barred from promotion")

        allowed = not reasons
        return PromotionDecision(
            allowed=allowed,
            reasons=reasons,
            live_ring=evidence.requested_ring if allowed else None,
        )


def case_origin_is_promotable(origin: CaseOrigin) -> bool:
    """Small helper for callers that need to pre-filter eval case origins."""

    return origin == "real"
