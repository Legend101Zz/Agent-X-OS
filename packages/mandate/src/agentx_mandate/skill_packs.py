"""Skill-pack prompt fragments — the per-faculty prompt text the generalized runner composes.

A ``Faculty.skill_pack`` is a versioned REF (a string), not raw prompt text. This module resolves a
ref → its prompt fragment so the kernel's ``PromptComposer`` can build a mandate's system prompt from
``charter.goal`` + constraints + the faculties' fragments + the target (the GENERIC prompt path used by
every mandate except lead-finder, which is regression-locked to its legacy renderer).

Fragments are versioned DATA, never credentials — so the kernel may import this module (kernel→mandate
is allowed; mandate→kernel is forbidden). Unknown refs resolve to ``""`` so a mandate with no fragment
text still composes a valid (if terse) prompt.
"""

from __future__ import annotations

# Keyed by the exact ``Faculty.skill_pack`` ref (the books-specific faculties; the shared faculties —
# judgment/enrichment/memory-craft/escalation — keep their lead-finder refs and contribute no books text,
# so the categorisation conventions live in the DOMAIN-PACK fragment below instead).
SKILL_PACK_FRAGMENTS: dict[str, str] = {
    "skill_pack:books-prep/extraction@0.1.0": (
        "Extraction: call ingest_document once for EACH provided document ref. The adapter parses the "
        "file deterministically and returns transaction rows with a per-row source citation — never "
        "invent or guess a row. If a document returns an error (scanned/no-text or structurally broken), "
        "do not fabricate its rows; it routes to the human queue."
    ),
    "skill_pack:books-prep/ledger-export@0.1.0": (
        "Routing + export: any transaction below the confidence threshold OR flagged extraction-suspect "
        "goes to queue_manual_action with a clear reason (the CA review queue) — never finalize a doubtful "
        "row. Claim the clean rows, then call export_ledger to write the .xlsx. You prepare books for a CA "
        "to review; you never finalize them."
    ),
}

# Keyed by ``DomainPackRef.name`` — versioned categorisation conventions for the GENERIC prompt path.
# This is where the books-specific judgment guidance lives (the judgment faculty is shared, so its skill
# pack stays lead-finder's).
DOMAIN_PACK_FRAGMENTS: dict[str, str] = {
    "indian-smb-books": (
        "Categorisation (indian-smb-books): for each extracted transaction assign an Indian SMB ledger "
        "head and a confidence in 0..1, citing the narration text you used (common heads: Sales, "
        "Purchases, Salaries & Wages, Rent, GST Payable, TDS Payable, Bank Charges, Professional Fees, "
        "Office Expenses, Fuel & Travel). GST treatment usually CANNOT be determined from a bank statement "
        "alone — emit the sentinel 'indeterminate_from_source' rather than guessing HSN / place-of-supply "
        "/ RCM. Where derivable, also emit vendor, GSTIN, state, a missing_supporting_doc flag, and a "
        "receivable/payable tag — these feed the future gst-recon and collections mandates and are NOT "
        "gated (a row missing a derivable GSTIN still passes)."
    ),
}


def skill_pack_fragment(ref: str) -> str:
    """Return the prompt fragment for a skill-pack ref, or ``""`` if none is registered."""
    return SKILL_PACK_FRAGMENTS.get(ref, "")


def domain_pack_fragment(name: str) -> str:
    """Return the prompt fragment for a domain-pack name, or ``""`` if none is registered."""
    return DOMAIN_PACK_FRAGMENTS.get(name, "")
