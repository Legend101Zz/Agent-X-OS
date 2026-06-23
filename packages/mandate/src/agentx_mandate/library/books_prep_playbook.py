"""The books-prep PLAYBOOK + deterministic categoriser — the sim-mode trajectory the ``own`` double
follows, and the reference categorisation logic the live Hermes path is guided to reproduce.

Flow: plan → (extraction faculty emits one ``ingest_document`` read per doc; the run-loop fulfils it and
stashes parsed rows on ``ctx.scratchpad['transactions']``) → categorise every row (ledger head + GST
treatment + confidence + the feed-forward fields) → CLAIM the clean rows as ``ledger_transaction`` facts,
QUEUE the low-confidence / extraction-suspect ones to the CA review queue → EXPORT the clean .xlsx.

Cross-batch dedup (caveats P0-2): a row whose heap dedupe key already exists in this instance's heap
(visible via the hydration snapshot) is reconciled/skipped, not re-committed.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from agentx_contracts.faculty import Faculty
from agentx_contracts.jsontypes import JsonObject, JsonValue
from agentx_contracts.memory import Fact, Provenance
from agentx_contracts.syscall import SyscallRequest

from agentx_mandate.faculties import propose
from agentx_mandate.harness import Call, Claim, FacultyContext, Finish, HarnessAction, Think
from agentx_mandate.library.books_prep import DEFAULT_CONFIDENCE_THRESHOLD
from agentx_mandate.library.indian_smb_books import (
    CREDIT_HEAD_RULES,
    LEDGER_HEAD_RULES,
    gstin_from_narration,
    is_non_supply_head,
    state_from_gstin,
    vendor_from_narration,
)


def _num(value: object) -> float:
    """Coerce a JSON-typed cell to a float (non-numeric → 0.0); keeps mypy honest over JsonValue."""
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


_RECONCILE_TOLERANCE = 0.01
# Fields carried straight through from the ingest adapter's transaction shape onto the ledger row.
_PASS_THROUGH = (
    "date",
    "narration",
    "debit",
    "credit",
    "balance",
    "ref",
    "source",
    "account_id",
    "statement_period",
    "extraction_confidence",
    "extraction_suspect",
)


def books_prep_playbook(ctx: FacultyContext, faculties: list[Faculty]) -> Iterator[HarnessAction]:
    """Yield the books-prep trajectory one action at a time (ingest reads suspend for fulfilment)."""
    documents = ctx.target.get("documents")
    yield Think(
        summary="Plan the books-prep run: ingest each document, categorize, queue the doubtful, export.",
        detail={
            "documents": len(documents) if isinstance(documents, list) else 0,
            "confidence_threshold": ctx.target.get("confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD),
        },
    )
    for faculty in faculties:
        yield from propose(faculty.name, ctx)  # extraction → ingest_document reads; others → no-ops here

    rows = categorize_transactions(ctx)
    facts = build_transaction_facts(ctx, rows)
    if facts:
        yield Claim(facts=facts)
    for index, row in enumerate(rows, start=1):
        if row.get("queued"):
            yield _queue_call(ctx, row, index)
    yield _export_call(ctx, rows)
    yield Finish(
        output={
            "transactions": len(rows),
            "clean": len(facts),
            "queued": sum(1 for row in rows if row.get("queued")),
        }
    )


# --- categorisation ---------------------------------------------------------------------


def categorize_transactions(ctx: FacultyContext) -> list[JsonObject]:
    """Categorise the ingested transactions; stash + return the ledger rows (with queued flags)."""
    threshold = _threshold(ctx.target)
    raw = ctx.scratchpad.get("transactions")
    txns = [t for t in raw if isinstance(t, dict)] if isinstance(raw, list) else []
    existing_keys = _heap_dedupe_keys(ctx)
    seen_keys: set[str] = set()
    series_prev: dict[tuple[str, str], JsonObject] = {}
    rows: list[JsonObject] = []
    for txn in txns:
        dedupe_key = str(txn.get("dedupe_key") or _fallback_dedupe_key(txn))
        if dedupe_key in existing_keys:
            continue  # cross-batch duplicate → reconciled/skipped (P0-2), not re-committed
        duplicate_in_batch = dedupe_key in seen_keys
        seen_keys.add(dedupe_key)

        row = _categorize_row(txn, dedupe_key)
        series_key = (str(row.get("account_id", "")), str(row.get("statement_period", "")))
        row["balance_break"] = _is_balance_break(series_prev.get(series_key), row)
        series_prev[series_key] = row

        confidence = float(row["confidence"]) if isinstance(row["confidence"], (int, float)) else 0.0
        queued = confidence < threshold or bool(txn.get("extraction_suspect")) or duplicate_in_batch
        row["queued"] = queued
        if queued:
            row["queue_reason"] = _queue_reason(row, txn, duplicate_in_batch, threshold)
        rows.append(row)
    ctx.scratchpad["ledger_rows"] = rows
    ctx.scratchpad["coverage"] = _coverage(rows)
    return rows


def _categorize_row(txn: JsonObject, dedupe_key: str) -> JsonObject:
    narration = str(txn.get("narration", ""))
    debit = _num(txn.get("debit"))
    credit = _num(txn.get("credit"))
    is_credit = credit > 0 and debit <= 0
    head, gst_treatment, confidence = _match_head(narration, is_credit=is_credit)
    gstin = gstin_from_narration(narration)
    vendor = vendor_from_narration(narration)
    state = state_from_gstin(gstin)
    # missing_supporting_doc: a taxable-looking expense (debit) whose GST is indeterminate and that is
    # not a clearly non-supply head — the hand-off signal to the future gst-recon mandate (P0-1).
    missing_supporting_doc = (
        not is_credit and gst_treatment == "indeterminate_from_source" and not is_non_supply_head(head)
    )
    row: JsonObject = {key: txn.get(key) for key in _PASS_THROUGH}
    row.update(
        {
            "dedupe_key": dedupe_key,
            "ledger_head": head,
            "gst_treatment": gst_treatment,
            "confidence": confidence,
            "vendor": vendor,
            "gstin": gstin,
            "state": state,
            "receivable_payable": "receivable" if is_credit else "payable",
            "missing_supporting_doc": missing_supporting_doc,
        }
    )
    return row


def _match_head(narration: str, *, is_credit: bool) -> tuple[str, str, float]:
    lowered = narration.lower()
    rules = CREDIT_HEAD_RULES if is_credit else []
    for keywords, head, gst, confidence in [*rules, *LEDGER_HEAD_RULES]:
        if any(keyword in lowered for keyword in keywords):
            return head, gst, confidence
    # No pattern matched → low-confidence default that routes to the queue.
    if is_credit:
        return "Sales", "indeterminate_from_source", 0.55
    return "Suspense", "indeterminate_from_source", 0.4


def _is_balance_break(prev: JsonObject | None, row: JsonObject) -> bool:
    """A break is when this row's balance doesn't follow from the prior one in the same series."""
    if prev is None:
        return False
    prev_balance = prev.get("balance")
    balance = row.get("balance")
    if not isinstance(prev_balance, (int, float)) or not isinstance(balance, (int, float)):
        return False
    expected = float(prev_balance) - _num(row.get("debit")) + _num(row.get("credit"))
    return abs(expected - float(balance)) > _RECONCILE_TOLERANCE


def _queue_reason(row: JsonObject, txn: JsonObject, duplicate_in_batch: bool, threshold: float) -> str:
    if bool(txn.get("extraction_suspect")):
        return "extraction_suspect: row failed balance reconciliation (re-check the parse)"
    if duplicate_in_batch:
        return "duplicate transaction within this batch"
    return f"low categorisation confidence (< {threshold}); ledger head '{row.get('ledger_head')}' is uncertain"


# --- claiming clean transactions as facts ----------------------------------------------


def build_transaction_facts(ctx: FacultyContext, rows: list[JsonObject]) -> list[Fact]:
    """Build a ``ledger_transaction`` Fact per CLEAN row (queued rows are not committed)."""
    facts: list[Fact] = []
    for row in rows:
        if row.get("queued"):
            continue
        dedupe_key = str(row.get("dedupe_key", ""))
        confidence = float(row["confidence"]) if isinstance(row["confidence"], (int, float)) else 0.0
        facts.append(
            Fact(
                id=f"{ctx.run_id}:txn:{dedupe_key}",
                instance_id=ctx.instance_id,
                subject=dedupe_key,
                predicate="ledger_transaction",
                object=json.dumps(row, sort_keys=True, default=str),
                confidence=max(0.0, min(confidence, 1.0)),
                source="agent-inferred",
                provenance=Provenance(
                    run_id=ctx.run_id,
                    evidence=[_source_citation(row)],
                    note=f"{row.get('ledger_head')} ({row.get('gst_treatment')})",
                ),
                status="probation",
                created_at=ctx.now,
            )
        )
    return facts


# --- effectful calls --------------------------------------------------------------------


def _queue_call(ctx: FacultyContext, row: JsonObject, index: int) -> Call:
    transaction: JsonValue = dict(row)
    return Call(
        request=SyscallRequest(
            name="queue_manual_action",
            args={
                "action": "review_transaction",
                "reason": str(row.get("queue_reason", "needs CA review")),
                "transaction": transaction,
            },
            instance_id=ctx.instance_id,
            run_id=ctx.run_id,
            idempotency_key=f"{ctx.run_id}:queue_manual_action:{index}",
            ring=ctx.ring,
            risk_class="reversible_write",
        )
    )


def _export_call(ctx: FacultyContext, rows: list[JsonObject]) -> Call:
    output_format = str(ctx.target.get("output_format", "xlsx"))
    filename = f"ledger_{ctx.instance_id}_{ctx.run_id}.{output_format}".replace(":", "_")
    rows_json: list[JsonValue] = list(rows)
    return Call(
        request=SyscallRequest(
            name="export_ledger",
            args={"filename": filename, "rows": rows_json},
            instance_id=ctx.instance_id,
            run_id=ctx.run_id,
            idempotency_key=f"{ctx.run_id}:export_ledger",
            ring=ctx.ring,
            risk_class="reversible_write",
        )
    )


# --- helpers ----------------------------------------------------------------------------


def _threshold(target: JsonObject) -> float:
    raw = target.get("confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD)
    return float(raw) if isinstance(raw, (int, float)) else DEFAULT_CONFIDENCE_THRESHOLD


def _heap_dedupe_keys(ctx: FacultyContext) -> set[str]:
    keys: set[str] = set()
    for fact in ctx.snapshot.facts:
        if fact.predicate == "ledger_transaction" and fact.subject:
            keys.add(fact.subject)
    return keys


def _fallback_dedupe_key(txn: JsonObject) -> str:
    import hashlib

    basis = "|".join(
        str(txn.get(key, "")) for key in ("account_id", "date", "debit", "credit", "balance", "ref", "narration")
    )
    return "txn_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def _source_citation(row: JsonObject) -> str:
    source = row.get("source")
    if isinstance(source, dict):
        return f"doc:{source.get('doc_id', '')} p{source.get('page', '')}/l{source.get('line', '')}"
    return f"doc:{row.get('account_id', '')}"


def _coverage(rows: list[JsonObject]) -> JsonObject:
    total = len(rows)

    def pct(key: str) -> float:
        if total == 0:
            return 0.0
        return round(100.0 * sum(1 for row in rows if row.get(key)) / total, 1)

    return {
        "transactions": total,
        "queued_for_review": sum(1 for row in rows if row.get("queued")),
        "gstin_coverage": pct("gstin"),
        "vendor_coverage": pct("vendor"),
        "receivable_payable_coverage": pct("receivable_payable"),
        "missing_supporting_doc_count": sum(1 for row in rows if row.get("missing_supporting_doc")),
    }
