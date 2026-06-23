"""Per-row CA review resolution — the mandate-lane half of books-prep Flag #1.

When a CA approves / edits a single flagged transaction row from the review queue, the engine commits
that row into the client's books as a ``ledger_transaction`` Fact. This module is the PURE builder
that turns ``(flagged row, CA decision, optional edits)`` into that Fact — the same encoding
``books_prep_playbook.build_transaction_facts`` produces for clean rows, so the verifier's
universal-quantifier rules and every downstream reader see one consistent shape.

It is deliberately effect-free (invariant #2): it imports only the frozen ``agentx_contracts``
submodules and never touches a store, the journal, or a credential. The KERNEL-side
``BooksReviewResolver`` drives this builder through the settlement commit path (so the Fact reaches
the heap only via a ``RunSettled`` event — invariant #1) and records the CA decision as a gym case.

A CA decision is the **human verification rung** of the v0 ladder ("human (the CA review queue) →
reality (CA accept/correct)"): an approved/edited row is human-confirmed, so the committed Fact is
``status="promoted"`` (not the agent flow's ``probation``), and its source is ``owner-corrected`` for
an edit or ``agent-inferred`` (CA-confirmed) for a plain approve.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from agentx_contracts.enums import ApprovalDecision, FactSource
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.memory import Fact, Provenance

# The fields a CA may correct on a flagged row. Kept narrow on purpose: a CA review fixes the
# CATEGORISATION (which ledger head, which GST treatment), never the underlying bank fact (date /
# amount / narration come from the source document and are immutable).
EDITABLE_FIELDS = ("ledger_head", "gst_treatment")


def apply_edits(row: JsonObject, edits: JsonObject | None) -> JsonObject:
    """Return a copy of ``row`` with the CA's corrected categorisation fields applied.

    Only ``EDITABLE_FIELDS`` are honoured — any other key in ``edits`` is ignored, so a CA edit can
    never rewrite the source-of-truth bank columns.
    """
    resolved = dict(row)
    if edits:
        for field in EDITABLE_FIELDS:
            if field in edits:
                resolved[field] = edits[field]
    return resolved


def dedupe_key_for(row: JsonObject) -> str:
    """The row's heap dedupe key — explicit if present, else a deterministic hash of the bank columns.

    Mirrors ``books_prep_playbook._fallback_dedupe_key`` so a row resolved off the queue keys to the
    SAME heap subject the playbook would have used, keeping cross-batch dedup coherent.
    """
    explicit = row.get("dedupe_key")
    if isinstance(explicit, str) and explicit:
        return explicit
    basis = "|".join(
        str(row.get(key, ""))
        for key in ("account_id", "date", "debit", "credit", "balance", "ref", "narration")
    )
    return "txn_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def build_resolution_fact(
    row: JsonObject,
    *,
    instance_id: str,
    run_id: str,
    decision: ApprovalDecision,
    actor: str,
    now: datetime,
    edits: JsonObject | None = None,
) -> Fact:
    """Build the ``ledger_transaction`` Fact for an approved/edited flagged row.

    Only ``decision in {"approve", "edit"}`` reaches here (a ``reject`` commits no Fact). The Fact id
    is deterministic in ``run_id`` (the resolver derives ``run_id`` deterministically from
    ``instance_id`` + dedupe key, so re-resolving the same row upserts the same heap doc — the
    idempotency guard). Provenance carries the resolution ``run_id``, a source citation, and the CA
    decision note, satisfying ``settlement._validated_fact`` and invariant #1.
    """
    resolved = apply_edits(row, edits) if decision == "edit" else dict(row)
    dedupe_key = dedupe_key_for(resolved)
    confidence = _confidence(resolved)
    source: FactSource = "owner-corrected" if decision == "edit" else "agent-inferred"
    return Fact(
        id=f"{run_id}:txn:{dedupe_key}",
        instance_id=instance_id,
        subject=dedupe_key,
        predicate="ledger_transaction",
        object=json.dumps(resolved, sort_keys=True, default=str),
        confidence=max(0.0, min(confidence, 1.0)),
        source=source,
        provenance=Provenance(
            run_id=run_id,
            evidence=[_source_citation(resolved), f"ca_review:{actor}"],
            note=(
                f"CA {decision} by {actor}: "
                f"{resolved.get('ledger_head')} ({resolved.get('gst_treatment')})"
            ),
        ),
        # The CA review IS the human verification rung — an approved/edited row is human-confirmed.
        status="promoted",
        created_at=now,
    )


def _confidence(row: JsonObject) -> float:
    raw = row.get("confidence")
    return float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else 0.0


def _source_citation(row: JsonObject) -> str:
    source = row.get("source")
    if isinstance(source, dict):
        return f"doc:{source.get('doc_id', '')} p{source.get('page', '')}/l{source.get('line', '')}"
    return f"doc:{row.get('account_id', '')}"
