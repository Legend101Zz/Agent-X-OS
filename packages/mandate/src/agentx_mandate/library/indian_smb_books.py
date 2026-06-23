"""``indian-smb-books`` domain pack — versioned categorisation priors (data, not prompt text).

Chart-of-accounts conventions + narration→ledger-head / vendor / GST-treatment patterns for an Indian
SMB's bank statement. Deliberately small and rule-based for v0 (the gym + CA corrections grow it). The
deterministic ``books_prep_playbook`` categoriser consumes this; the live Hermes path is GUIDED by the
books skill-pack prompt that paraphrases these conventions.
"""

from __future__ import annotations

import re

# gst_treatment is a DETERMINED value only where a bank narration alone makes it unambiguous; everything
# else stays ``indeterminate_from_source`` (caveats P0-1 — a bank statement cannot yield HSN/place-of-
# supply/RCM, which live on the invoice v0 does not ingest).
_IND = "indeterminate_from_source"
_OOS = "out_of_scope"

# (keyword tuple, ledger_head, gst_treatment, base_confidence). First match wins; order = specificity.
LEDGER_HEAD_RULES: list[tuple[tuple[str, ...], str, str, float]] = [
    (("gst", "cgst", "sgst", "igst", "challan", "cpin"), "GST Payable", _OOS, 0.9),
    (("tds", "tcs"), "TDS Payable", _OOS, 0.88),
    (("salary", "payroll", "wages", "stipend"), "Salaries & Wages", _OOS, 0.9),
    (("rent",), "Rent", _IND, 0.85),
    (("electricity", "power bill", "mseb", "bescom"), "Electricity", _IND, 0.85),
    (("internet", "broadband", "airtel", "jio", "vodafone", "bsnl"), "Telephone & Internet", _IND, 0.82),
    (("interest", "int.pd", "int paid"), "Interest Expense", _OOS, 0.82),
    (("bank charge", "service charge", "chg", "amc", "neft chg", "imps chg"), "Bank Charges", _OOS, 0.85),
    (("emi", "loan", "repayment"), "Loan Repayment", _OOS, 0.8),
    (("petrol", "diesel", "fuel", "hpcl", "iocl", "bharat petroleum"), "Fuel & Travel", _IND, 0.8),
    (("stationery", "printing", "office supplies", "amazon", "flipkart"), "Office Expenses", _IND, 0.7),
    (("freight", "transport", "courier", "logistics", "dtdc", "bluedart"), "Freight & Postage", _IND, 0.78),
    (("professional", "consultancy", "audit", "legal", "ca "), "Professional Fees", _IND, 0.78),
    (("purchase", "vendor", "supplier", "trading", "traders", "enterprises"), "Purchases", _IND, 0.6),
]

# Inward (credit) narration cues → revenue side.
CREDIT_HEAD_RULES: list[tuple[tuple[str, ...], str, str, float]] = [
    (("refund", "reversal", "cashback"), "Refunds Received", _OOS, 0.8),
    (("interest", "int.cr", "int credited"), "Interest Income", _OOS, 0.82),
    (("sales", "invoice", "inv", "payment received", "received from"), "Sales", _IND, 0.7),
]

# Narration prefixes that carry a counterparty name (UPI/IMPS/NEFT/POS rails).
_VENDOR_PATTERNS = [
    re.compile(r"\b(?:NEFT|IMPS|RTGS)[\s:/-]+(?:[A-Z0-9]+[\s:/-]+)?([A-Za-z][A-Za-z &.]{2,40})", re.I),
    re.compile(r"\bUPI[\s:/-]+([A-Za-z][A-Za-z0-9 &.]{2,40})", re.I),
    re.compile(r"\bPOS[\s:/-]+([A-Za-z][A-Za-z0-9 &.]{2,40})", re.I),
    re.compile(r"\b(?:to|from|received from|paid to)\s+([A-Z][A-Za-z &.]{2,40})", re.I),
]

_GSTIN_PATTERN = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d]Z[A-Z\d])\b")

# GST state code (first two GSTIN digits) → state name (subset; enough for v0 vendor/state feed-forward).
_GST_STATE_CODES = {
    "27": "Maharashtra",
    "29": "Karnataka",
    "07": "Delhi",
    "33": "Tamil Nadu",
    "24": "Gujarat",
    "06": "Haryana",
    "09": "Uttar Pradesh",
    "19": "West Bengal",
    "36": "Telangana",
    "32": "Kerala",
}

# Heads that are clearly NOT a taxable inward supply (so an indeterminate GST treatment on them does
# NOT raise missing_supporting_doc).
_NON_SUPPLY_HEADS = {
    "GST Payable",
    "TDS Payable",
    "Salaries & Wages",
    "Interest Expense",
    "Bank Charges",
    "Loan Repayment",
    "Interest Income",
    "Refunds Received",
}


def vendor_from_narration(narration: str) -> str:
    for pattern in _VENDOR_PATTERNS:
        match = pattern.search(narration)
        if match:
            return " ".join(match.group(1).split()).strip(" .&").title()
    return ""


def gstin_from_narration(narration: str) -> str:
    match = _GSTIN_PATTERN.search(narration.upper())
    return match.group(1) if match else ""


def state_from_gstin(gstin: str) -> str:
    return _GST_STATE_CODES.get(gstin[:2], "") if len(gstin) >= 2 else ""


def is_non_supply_head(head: str) -> bool:
    return head in _NON_SUPPLY_HEADS
