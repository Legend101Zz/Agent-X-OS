"""K4 verifier: deterministic rules rung and human approval parking.

The judge rung is a separate seam. This module owns the live-kernel-safe checks: simple rules that
run as code, and the human approval rung represented as parked/resolved journal events.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from agentx_contracts.enums import Ring, VerificationRung
from agentx_contracts.journal import ApprovalResolved, RunParked
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.mandate import Condition, MandateType
from agentx_contracts.memory import Fact

from .ports import JournalStore

_RECONCILE_TOLERANCE = 0.01
_DEFAULT_CONFIDENCE_THRESHOLD = 0.8


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

        target = mandate.charter.target
        rule_conditions = [c for c in mandate.charter.postconditions if c.rung == "rules"]
        for condition in rule_conditions:
            ok, reason = self._evaluate(condition, claimed_facts, target)
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

    def _evaluate(
        self, condition: Condition, claimed_facts: Sequence[Fact], target: JsonObject
    ) -> tuple[bool, str]:
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

        # books-prep universal-quantifier rules over the claimed ``ledger_transaction`` facts.
        books_result = _evaluate_books_rule(expr, claimed_facts, target)
        if books_result is not None:
            return books_result

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


# --- books-prep rules: universal checks over the claimed ``ledger_transaction`` facts ----------------
# A clean transaction is committed as a Fact with ``predicate="ledger_transaction"``, ``subject=dedupe
# key``, ``object=JSON(row)``, ``confidence=categorisation confidence`` and a source citation in
# ``provenance.evidence``. These checks read that encoding — they are deterministic and live-kernel-safe.


def _evaluate_books_rule(
    expr: str, claimed_facts: Sequence[Fact], target: JsonObject
) -> tuple[bool, str] | None:
    txns = [fact for fact in claimed_facts if fact.predicate == "ledger_transaction"]
    if expr.startswith("every ledger_transaction "):
        return _check_every_transaction(expr[len("every ledger_transaction ") :].strip(), txns, target)
    if expr == "unique ledger_transaction dedupe_key":
        keys = [fact.subject for fact in txns]
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        return (not duplicates), ("ok" if not duplicates else f"duplicate dedupe keys: {duplicates}")
    return None


def _check_every_transaction(
    check: str, txns: list[Fact], target: JsonObject
) -> tuple[bool, str] | None:
    if check == "has source":
        for fact in txns:
            payload = _txn_payload(fact)
            source = payload.get("source")
            cited = bool(fact.provenance.evidence) and isinstance(source, dict) and bool(source.get("doc_id"))
            if not cited:
                return False, f"transaction {fact.subject} is missing a source citation"
        return True, "ok"
    if check == "has ledger_head":
        for fact in txns:
            head = _txn_payload(fact).get("ledger_head")
            if not (isinstance(head, str) and head) or not (0.0 < fact.confidence <= 1.0):
                return False, f"transaction {fact.subject} is missing a ledger head or confidence"
        return True, "ok"
    if check == "has gst_treatment":
        for fact in txns:
            gst = _txn_payload(fact).get("gst_treatment")
            if not (isinstance(gst, str) and gst):
                return False, f"transaction {fact.subject} is missing gst_treatment"
        return True, "ok"
    if check == "confidence_ge_threshold":
        threshold = _target_threshold(target)
        for fact in txns:
            if fact.confidence < threshold:
                return False, (
                    f"transaction {fact.subject} confidence {fact.confidence} < threshold {threshold} "
                    "(should have been queued)"
                )
        return True, "ok"
    if check == "balance_continuity":
        return _check_balance_continuity(txns)
    return None


def _check_balance_continuity(txns: list[Fact]) -> tuple[bool, str]:
    """Within each (account_id, statement_period) series, consecutive balances reconcile OR the break
    is flagged (``balance_break=true``). A break that is NOT flagged fails the rule."""
    groups: dict[tuple[str, str], list[tuple[int, JsonObject]]] = {}
    for fact in txns:
        payload = _txn_payload(fact)
        source = payload.get("source")
        source_line = source.get("line") if isinstance(source, dict) else None
        line = int(source_line) if isinstance(source_line, int) and not isinstance(source_line, bool) else 0
        key = (str(payload.get("account_id", "")), str(payload.get("statement_period", "")))
        groups.setdefault(key, []).append((line, payload))
    for key, items in groups.items():
        items.sort(key=lambda item: item[0])
        prev: JsonObject | None = None
        for _line, payload in items:
            if prev is not None:
                prev_balance = prev.get("balance")
                balance = payload.get("balance")
                if isinstance(prev_balance, (int, float)) and isinstance(balance, (int, float)):
                    debit = _num_or_zero(payload.get("debit"))
                    credit = _num_or_zero(payload.get("credit"))
                    expected = float(prev_balance) - debit + credit
                    if abs(expected - float(balance)) > _RECONCILE_TOLERANCE and not payload.get("balance_break"):
                        return False, f"unflagged balance break in series {key}"
            prev = payload
    return True, "ok"


def _txn_payload(fact: Fact) -> JsonObject:
    try:
        parsed = json.loads(fact.object)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _target_threshold(target: JsonObject) -> float:
    raw = target.get("confidence_threshold", _DEFAULT_CONFIDENCE_THRESHOLD)
    return float(raw) if isinstance(raw, (int, float)) else _DEFAULT_CONFIDENCE_THRESHOLD


def _num_or_zero(value: object) -> float:
    """Coerce an arbitrary JSON cell to a float (non-numeric → 0.0); keeps mypy honest."""
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


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
