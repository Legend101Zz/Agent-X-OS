"""books-prep MandateType — mandate #2: a messy financial-document dump → a clean, categorized,
source-cited Excel ledger ready for CA review, with low-confidence/ambiguous lines pushed to a queue.

It is an ASSISTANT that PREPARES books for a CA to review — never an autopilot that finalizes them.
Charter uses the REVISED postconditions from the caveats doc (not design §4.1): GST treatment is
emitted-not-gated (P0-1), extraction-suspect rows route independently (P0-3), balance continuity is
scoped per (account, period) (P2-3), and cross-batch duplicate commits are blocked (P0-2). The
vendor/gstin/state, missing_supporting_doc, receivable/payable fields are EMITTED, not gated.
"""

from __future__ import annotations

from agentx_contracts.faculty import FacultyBinding
from agentx_contracts.mandate import (
    Charter,
    Condition,
    DomainPackRef,
    MandateType,
    SettlementRules,
    SpawnRule,
    VerificationSuite,
)

# v0 default — PROVISIONAL, not a calibrated bar. The P1 golden eval reports the calibration curve +
# false_confidence_rate; the threshold is set WITH the CA from that curve, not assumed here.
DEFAULT_CONFIDENCE_THRESHOLD = 0.8


def build_books_prep_type() -> MandateType:
    return MandateType(
        id="type_books_prep_v0",
        name="books-prep",
        version="0.1.0",
        charter=Charter(
            goal=(
                "Turn a business's raw financial-document dump into a clean, categorized, source-cited "
                "transaction ledger ready for CA review. Prepare the books for a CA to review and finalize "
                "— never finalize them yourself."
            ),
            postconditions=[
                Condition(
                    id="has_transactions",
                    description="At least one transaction was claimed.",
                    rung="rules",
                    expr="claimed_facts >= 1",
                ),
                Condition(
                    id="every_txn_has_source",
                    description="Every claimed transaction cites its source (doc id + page/line).",
                    rung="rules",
                    expr="every ledger_transaction has source",
                ),
                Condition(
                    id="every_txn_has_ledger_head_and_confidence",
                    description="Every transaction has a ledger head + a confidence (GST treatment NOT gated).",
                    rung="rules",
                    expr="every ledger_transaction has ledger_head",
                ),
                Condition(
                    id="gst_treatment_emitted",
                    description=(
                        "Every transaction carries a gst_treatment — a determined value OR the explicit "
                        "sentinel 'indeterminate_from_source' (a valid pass; a bank statement cannot yield GST)."
                    ),
                    rung="rules",
                    expr="every ledger_transaction has gst_treatment",
                ),
                Condition(
                    id="low_confidence_queued",
                    description=(
                        "No claimed transaction is below the confidence threshold or extraction-suspect "
                        "(those route to the CA review queue, never finalized silently)."
                    ),
                    rung="rules",
                    expr="every ledger_transaction confidence_ge_threshold",
                ),
                Condition(
                    id="balance_continuity",
                    description=(
                        "Running balance holds within each (account, statement period); "
                        "any break is flagged per series."
                    ),
                    rung="rules",
                    expr="every ledger_transaction balance_continuity",
                ),
                Condition(
                    id="no_duplicate_commit",
                    description=(
                        "No two claimed transactions share a heap dedupe key "
                        "(cross-batch dedup guards the rest)."
                    ),
                    rung="rules",
                    expr="unique ledger_transaction dedupe_key",
                ),
            ],
            constraints=[
                "never invent a transaction with no source document",
                "read-only on source documents; never moves money (books only)",
                "low-confidence or ambiguous lines go to the CA review queue, never finalized silently",
            ],
            target={
                "documents": [],
                "output_format": "xlsx",
                "confidence_threshold": DEFAULT_CONFIDENCE_THRESHOLD,
            },
        ),
        faculties=[
            FacultyBinding(faculty_name="extraction"),
            FacultyBinding(faculty_name="judgment"),
            FacultyBinding(faculty_name="enrichment"),
            FacultyBinding(faculty_name="memory-craft"),
            FacultyBinding(faculty_name="escalation"),
            FacultyBinding(faculty_name="ledger-export"),
        ],
        domain_pack=DomainPackRef(name="indian-smb-books", version="0.1.0"),
        verification=VerificationSuite(),
        settlement=SettlementRules(
            watch_window_hours=72,
            # Deferred composition edge (declared, not implemented in v0): a settled books-prep run
            # seeds the future gst-recon mandate.
            spawn_rules=[
                SpawnRule(on_condition="books_ready", child_type_ref="gst-recon@0.1.0"),
            ],
        ),
        service_ports=["clean_ledger"],
    )
