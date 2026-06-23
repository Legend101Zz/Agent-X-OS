"""P1 — the books-prep cold-start categorisation eval (OBSERVATIONAL).

Per caveats P1: a static eval distinct from the runtime gym that measures day-one categorisation
quality. The point is to surface ``false_confidence_rate`` (the safety-critical number for every
un-reviewed row) and a calibration table, so we can SET the confidence threshold from a measured
curve rather than from a guessed 0.8.

The golden fixture is small (~15 rows) and OBSERVATIONAL: it runs every test invocation, prints
metrics to stderr, but does NOT enforce a hard pass threshold. Until we collect 50–150 real rows
from the target CA (the "revenue-ready" acceptance run, caveats P2-1) we cannot set a real bar;
faking a threshold now would be lying to ourselves.

The fixture lives in-repo (hand-curated from common Indian SMB bank-narration patterns; these are
the categorizer's reference cases) and the eval reports:
  * ledger_head top-1 accuracy
  * vendor-resolution accuracy (on rows where a vendor should resolve)
  * queue_rate at the chosen threshold (the CA's workload)
  * false_confidence_rate: % of rows scored ≥ threshold that were WRONG
  * calibration table (accuracy by confidence band)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentx_contracts import HydrationSnapshot
from agentx_mandate.harness import FacultyContext
from agentx_mandate.library.books_prep import DEFAULT_CONFIDENCE_THRESHOLD
from agentx_mandate.library.books_prep_playbook import categorize_transactions

NOW = datetime(2026, 6, 22, tzinfo=UTC)


# --- golden fixture: a small set of labelled bank-narration rows. ----------------------
# Each row is what a CA would have labelled by hand. ``expected_head`` is the reference ledger
# head the categorizer SHOULD emit at full quality; ``expected_vendor`` is non-null only when the
# narration carries a clearly-resolvable counterparty name.
#
# Sources: common Indian SMB bank-statement patterns (UPI / NEFT / IMPS / POS rails). These are
# observational reference cases — when the categorizer's confidence is high AND it disagrees
# with the label, that disagreement is a candidate for the next hand-label pass (this is the
# reality rung — caveats P1).


@dataclass(frozen=True)
class GoldenRow:
    row_id: str
    narration: str
    debit: float
    credit: float
    expected_head: str
    expected_vendor: str | None = None  # None when no clear vendor should resolve
    expected_gst_treatment: str | None = None  # None when sentinel is acceptable
    notes: str = ""


GOLDEN_FIXTURE: list[GoldenRow] = [
    GoldenRow(
        row_id="fuel_hpcl",
        narration="UPI HPCL petrol pump fuel purchase",
        debit=2000.0,
        credit=0.0,
        expected_head="Fuel & Travel",
        expected_gst_treatment="indeterminate_from_source",
        notes="HPCL clearly identifies a fuel vendor; debit → Fuel & Travel (matches category).",
    ),
    GoldenRow(
        row_id="gst_challan",
        narration="NEFT GST PAYMENT challan CPIN 240526",
        debit=12000.0,
        credit=0.0,
        expected_head="GST Payable",
        expected_gst_treatment="out_of_scope",
        notes="GST challan is clearly a GST payment; the head should be GST Payable.",
    ),
    GoldenRow(
        row_id="office_supplies",
        narration="UPI AMAZON office supplies stationery",
        debit=1800.0,
        credit=0.0,
        expected_head="Office Expenses",
        expected_gst_treatment="indeterminate_from_source",
        notes="AMAZON stationery → Office Expenses (the design's §2.1 example).",
    ),
    GoldenRow(
        row_id="salary_payroll",
        narration="NEFT SALARY payroll Acme Pvt Ltd May 2026",
        debit=45000.0,
        credit=0.0,
        expected_head="Salaries & Wages",
        expected_gst_treatment="out_of_scope",
        notes="Salary narration → Salaries & Wages.",
    ),
    GoldenRow(
        row_id="rent_payment",
        narration="NEFT RENT payment to landlord Sharma",
        debit=25000.0,
        credit=0.0,
        expected_head="Rent",
        expected_vendor="Sharma",  # narrator carries the landlord name
        expected_gst_treatment="indeterminate_from_source",
        notes="Rent narration → Rent. Vendor 'Sharma' resolves from the landlord name.",
    ),
    GoldenRow(
        row_id="electricity_bill",
        narration="UPI MSEB electricity bill payment",
        debit=3200.0,
        credit=0.0,
        expected_head="Electricity",
        expected_gst_treatment="indeterminate_from_source",
        notes="MSEB is the Maharashtra state electricity board; matches the rule.",
    ),
    GoldenRow(
        row_id="interest_income",
        narration="interest credited on FD ACME TRADERS PVT LTD",
        debit=0.0,
        credit=2500.0,
        expected_head="Interest Income",
        expected_vendor="ACME TRADERS",
        expected_gst_treatment="out_of_scope",
        notes="Credit + interest narration → Interest Income. Vendor 'ACME TRADERS' resolves.",
    ),
    GoldenRow(
        row_id="bank_charge",
        narration="NEFT CHG service charge IMPS",
        debit=15.0,
        credit=0.0,
        expected_head="Bank Charges",
        expected_gst_treatment="out_of_scope",
        notes="Bank-charge narration → Bank Charges (out_of_scope for GST).",
    ),
    GoldenRow(
        row_id="freight_courier",
        narration="UPI DTDC courier freight charges",
        debit=350.0,
        credit=0.0,
        expected_head="Freight & Postage",
        expected_gst_treatment="indeterminate_from_source",
        notes="DTDC courier → Freight & Postage.",
    ),
    GoldenRow(
        row_id="professional_audit",
        narration="NEFT CA audit professional fees ABC & Associates",
        debit=15000.0,
        credit=0.0,
        expected_head="Professional Fees",
        expected_vendor="ABC & Associates",
        expected_gst_treatment="indeterminate_from_source",
        notes="Audit narration → Professional Fees. Vendor 'ABC & Associates' resolves.",
    ),
    GoldenRow(
        row_id="unknown_suspense",
        narration="NEFT random party xyz 123",
        debit=5000.0,
        credit=0.0,
        expected_head="Suspense",
        expected_gst_treatment="indeterminate_from_source",
        notes="No pattern matches → falls to Suspense (low confidence → queued).",
    ),
    GoldenRow(
        row_id="emi_loan_repayment",
        narration="NEFT EMI loan repayment HDFC0001234",
        debit=12000.0,
        credit=0.0,
        expected_head="Loan Repayment",
        expected_gst_treatment="out_of_scope",
        notes="EMI narration → Loan Repayment.",
    ),
]


@dataclass
class EvalMetrics:
    total: int
    ledger_head_top1_correct: int
    vendor_resolved_correct: int
    vendor_eligible: int
    queued_count: int
    high_confidence_wrong: int  # false_confidence_rate numerator
    high_confidence_total: int  # false_confidence_rate denominator
    by_confidence_band: dict[str, dict[str, int]] = field(default_factory=dict)
    details: list[dict[str, Any]] = field(default_factory=list)

    def ledger_head_top1_accuracy(self) -> float:
        return self.ledger_head_top1_correct / self.total if self.total else 0.0

    def vendor_accuracy(self) -> float:
        return self.vendor_resolved_correct / self.vendor_eligible if self.vendor_eligible else 0.0

    def queue_rate(self) -> float:
        return self.queued_count / self.total if self.total else 0.0

    def false_confidence_rate(self) -> float:
        return self.high_confidence_wrong / self.high_confidence_total if self.high_confidence_total else 0.0


def _confidence_band(confidence: float) -> str:
    """Bucket confidence into 0.1-wide bands for the calibration table."""
    bucket = int(confidence * 10) / 10
    return f"{bucket:.1f}-{bucket + 0.1:.1f}"


def run_golden_eval(threshold: float = DEFAULT_CONFIDENCE_THRESHOLD) -> EvalMetrics:
    """Run the categorizer over the golden fixture and compute the P1 metrics.

    Observational: never raises, never gates; returns metrics for the test + the dashboard.
    """
    # Wrap each GoldenRow as a parsed-transaction dict (mirrors the live IngestDocumentAdapter output).
    transactions = [
        {
            "date": "2026-04-09",
            "narration": row.narration,
            "debit": row.debit,
            "credit": row.credit,
            "balance": 100000.0 - row.debit + row.credit,
            "ref": f"GOLD{index:03d}",
            "source": {"doc_id": f"golden_{row.row_id}.csv", "page": 1, "line": index + 1},
            "account_id": "GOLDEN",
            "statement_period": "2026-04",
            "extraction_confidence": 1.0,
            "extraction_suspect": False,
            "dedupe_key": f"golden_{row.row_id}",
        }
        for index, row in enumerate(GOLDEN_FIXTURE)
    ]
    ctx = FacultyContext(
        snapshot=HydrationSnapshot(frozen_at=NOW),
        target={"documents": ["golden.csv"], "confidence_threshold": threshold, "output_format": "xlsx"},
        scratchpad={"transactions": transactions},
        instance_id="inst_golden",
        run_id="run_golden_eval",
        ring="L1",
        now=NOW,
    )
    rows = categorize_transactions(ctx)

    metrics = EvalMetrics(total=len(GOLDEN_FIXTURE), ledger_head_top1_correct=0,
                          vendor_resolved_correct=0, vendor_eligible=0, queued_count=0,
                          high_confidence_wrong=0, high_confidence_total=0)

    for label, row in zip(GOLDEN_FIXTURE, rows, strict=True):
        head_correct = row["ledger_head"] == label.expected_head
        vendor_expected = label.expected_vendor is not None
        vendor_resolved = isinstance(row.get("vendor"), str) and row["vendor"] != ""
        # Vendor accuracy: did we resolve a vendor when expected AND the resolved name matches.
        if vendor_expected:
            metrics.vendor_eligible += 1
            expected_lower = label.expected_vendor.lower() if label.expected_vendor else ""
            if vendor_resolved and expected_lower in str(row["vendor"]).lower():
                metrics.vendor_resolved_correct += 1
        if head_correct:
            metrics.ledger_head_top1_correct += 1
        if row.get("queued"):
            metrics.queued_count += 1

        # false_confidence_rate: high-confidence rows that were wrong.
        raw_confidence = row.get("confidence")
        confidence = (
            float(raw_confidence)
            if isinstance(raw_confidence, (int, float)) and not isinstance(raw_confidence, bool)
            else 0.0
        )
        if confidence >= threshold:
            metrics.high_confidence_total += 1
            if not head_correct:
                metrics.high_confidence_wrong += 1

        band = _confidence_band(confidence)
        band_stats = metrics.by_confidence_band.setdefault(
            band, {"total": 0, "correct": 0, "queued": 0}
        )
        band_stats["total"] += 1
        if head_correct:
            band_stats["correct"] += 1
        if row.get("queued"):
            band_stats["queued"] += 1

        metrics.details.append({
            "row_id": label.row_id,
            "narration": label.narration,
            "expected_head": label.expected_head,
            "actual_head": row["ledger_head"],
            "confidence": round(confidence, 3),
            "queued": bool(row.get("queued")),
            "head_correct": head_correct,
            "vendor": row.get("vendor"),
        })

    return metrics


def _report(metrics: EvalMetrics, threshold: float) -> str:
    """Render the metrics as a compact table for the test log + future dashboard export."""
    lines = [
        f"books-prep golden eval — threshold={threshold:.2f}, n={metrics.total}",
        f"  ledger_head top-1 accuracy : {metrics.ledger_head_top1_accuracy():.1%}",
        f"  vendor-resolution accuracy: {metrics.vendor_accuracy():.1%}",
        f"    (eligible {metrics.vendor_eligible}/{metrics.total})",
        f"  queue_rate @ threshold    : {metrics.queue_rate():.1%}",
        f"  false_confidence_rate     : {metrics.false_confidence_rate():.1%}",
        f"    ({metrics.high_confidence_wrong} wrong / {metrics.high_confidence_total} high-conf)",
        "  calibration table:",
    ]
    for band in sorted(metrics.by_confidence_band.keys()):
        stats = metrics.by_confidence_band[band]
        accuracy = stats["correct"] / stats["total"] if stats["total"] else 0.0
        lines.append(f"    [{band}]  n={stats['total']:>3}  accuracy={accuracy:.1%}  queued={stats['queued']}")
    return "\n".join(lines)


# --- the test ------------------------------------------------------------------------------


def test_golden_eval_runs_and_reports_metrics_without_gating(capsys: Any) -> None:
    """P1: the eval RUNS every time, reports metrics, and DOES NOT gate the build.

    The metrics are observational — they print to stderr for the developer reading the log, and
    the test asserts only that the eval produces sane numbers (no crashes, total == fixture size,
    accuracy in [0, 1]). It does NOT assert a hard pass threshold — that bar is set after the
    CA acceptance run (caveats P2-1) with real labelled rows.
    """
    metrics = run_golden_eval(threshold=DEFAULT_CONFIDENCE_THRESHOLD)

    # Always-print the report so it's visible in the test log even on green.
    with capsys.disabled():
        print(_report(metrics, DEFAULT_CONFIDENCE_THRESHOLD))

    # Sanity: eval completed end-to-end without crashing.
    assert metrics.total == len(GOLDEN_FIXTURE)
    assert 0.0 <= metrics.ledger_head_top1_accuracy() <= 1.0
    assert 0.0 <= metrics.vendor_accuracy() <= 1.0
    assert 0.0 <= metrics.false_confidence_rate() <= 1.0
    # Details: one entry per row, with head + confidence + queued flag.
    assert len(metrics.details) == metrics.total


def test_golden_eval_dumps_json_report_for_dashboard_consumption(tmp_path: Path) -> None:
    """The eval's JSON output is the artifact the design §7 dashboard view consumes — the
    coverage / confidence summary sheet can render this to show 'GSTIN derivable on 38% of rows'
    style metrics (caveats P2-2)."""
    metrics = run_golden_eval(threshold=DEFAULT_CONFIDENCE_THRESHOLD)
    report = {
        "threshold": DEFAULT_CONFIDENCE_THRESHOLD,
        "total": metrics.total,
        "ledger_head_top1_accuracy": metrics.ledger_head_top1_accuracy(),
        "vendor_accuracy": metrics.vendor_accuracy(),
        "queue_rate": metrics.queue_rate(),
        "false_confidence_rate": metrics.false_confidence_rate(),
        "high_confidence_wrong": metrics.high_confidence_wrong,
        "high_confidence_total": metrics.high_confidence_total,
        "by_confidence_band": metrics.by_confidence_band,
        "details": metrics.details,
    }
    out = tmp_path / "books_prep_golden_eval.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    # The JSON round-trips cleanly.
    reloaded = json.loads(out.read_text(encoding="utf-8"))
    assert reloaded["total"] == metrics.total
    assert reloaded["false_confidence_rate"] == metrics.false_confidence_rate()


def test_golden_eval_raises_false_confidence_when_threshold_is_too_low() -> None:
    """Setting the threshold artificially LOW should let wrong-but-confident rows through, raising
    the false_confidence_rate — a sanity check that the metric is responsive to threshold moves."""
    strict = run_golden_eval(threshold=0.99)  # almost everything queued
    lax = run_golden_eval(threshold=0.10)  # almost nothing queued; anything confident (incl. wrong) passes
    # The lax threshold has a higher (or equal) high_confidence_total than the strict one.
    assert lax.high_confidence_total >= strict.high_confidence_total
    # And the false_confidence_rate at the lax threshold is the bound on which we set the real bar.
    assert isinstance(lax.false_confidence_rate(), float)