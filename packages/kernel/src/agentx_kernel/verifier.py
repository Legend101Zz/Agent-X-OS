"""K4 verifier: deterministic rules rung and human approval parking.

The judge rung is a separate seam. This module owns the live-kernel-safe checks: simple rules that
run as code, and the human approval rung represented as parked/resolved journal events.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from agentx_contracts.enums import Ring, VerificationRung
from agentx_contracts.journal import ApprovalResolved, RunParked
from agentx_contracts.mandate import Condition, MandateType
from agentx_contracts.memory import Fact

from .ports import JournalStore


@dataclass(frozen=True)
class RulesVerificationResult:
    passed: bool
    passed_condition_ids: list[str]
    failed_condition_ids: list[str]
    reasons: list[str]
    rungs_passed: list[VerificationRung]


class RulesVerifier:
    """Evaluates the charter postconditions assigned to the deterministic ``rules`` rung."""

    def verify_postconditions(
        self,
        mandate: MandateType,
        *,
        claimed_facts: Sequence[Fact],
    ) -> RulesVerificationResult:
        passed_ids: list[str] = []
        failed_ids: list[str] = []
        reasons: list[str] = []

        rule_conditions = [c for c in mandate.charter.postconditions if c.rung == "rules"]
        for condition in rule_conditions:
            ok, reason = self._evaluate(condition, claimed_facts)
            if ok:
                passed_ids.append(condition.id)
            else:
                failed_ids.append(condition.id)
                reasons.append(f"{condition.id}: {reason}")

        passed = not failed_ids
        return RulesVerificationResult(
            passed=passed,
            passed_condition_ids=passed_ids,
            failed_condition_ids=failed_ids,
            reasons=reasons,
            rungs_passed=["rules"] if rule_conditions and passed else [],
        )

    def _evaluate(self, condition: Condition, claimed_facts: Sequence[Fact]) -> tuple[bool, str]:
        expr = condition.expr.strip() if condition.expr is not None else ""
        if not expr:
            return False, "rules condition has no expression"

        count_result = _evaluate_claimed_facts_count(expr, len(claimed_facts))
        if count_result is not None:
            return count_result, "ok" if count_result else f"expected {expr}"

        predicate = _parse_fact_exists(expr)
        if predicate is not None:
            ok = any(fact.predicate == predicate for fact in claimed_facts)
            return ok, "ok" if ok else f"missing fact predicate {predicate!r}"

        return False, f"unsupported rule expression: {expr}"


def _evaluate_claimed_facts_count(expr: str, count: int) -> bool | None:
    parts = expr.split()
    if len(parts) != 3 or parts[0] != "claimed_facts":
        return None
    op, raw_expected = parts[1], parts[2]
    if not raw_expected.isdigit():
        return None
    expected = int(raw_expected)
    if op == ">=":
        return count >= expected
    if op == ">":
        return count > expected
    if op == "==":
        return count == expected
    if op == "<=":
        return count <= expected
    if op == "<":
        return count < expected
    return None


def _parse_fact_exists(expr: str) -> str | None:
    prefix = "fact:"
    suffix = " exists"
    if not expr.startswith(prefix) or not expr.endswith(suffix):
        return None
    predicate = expr[len(prefix) : -len(suffix)].strip()
    return predicate or None


class HumanApprovalGate:
    """The human rung: park the run and resume when an ``ApprovalResolved`` event appears."""

    def __init__(self, journal: JournalStore) -> None:
        self._journal = journal

    async def park_for_approval(
        self,
        *,
        instance_id: str,
        run_id: str,
        reason: str,
        required_ring: Ring | None,
        now: datetime,
    ) -> RunParked:
        parked = await self._journal.append(
            RunParked(
                event_id=f"{run_id}:park:human_approval",
                seq=0,
                ts=now,
                instance_id=instance_id,
                run_id=run_id,
                reason=reason,
                awaiting="human_approval",
                required_ring=required_ring,
            )
        )
        return cast(RunParked, parked)

    async def resolution(self, *, run_id: str) -> ApprovalResolved | None:
        events = await self._journal.read_run(run_id)
        for event in reversed(events):
            if isinstance(event, ApprovalResolved):
                return event
        return None
