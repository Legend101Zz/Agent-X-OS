"""Per-row CA review resolution (books-prep Flag #1) — the §5 done-when spec, test-first.

A CA approves / edits / rejects a SINGLE flagged transaction row from the books-prep review queue.
Resolution is modelled as a tiny triggered follow-up "micro-run" (``BooksReviewResolver``) that reuses
the kernel settlement commit path + the mandate fact-builder — it NEVER touches the frozen
``packages/contracts`` seam and stays inside the kernel + mandate lane.

These tests encode BEHAVIOUR, not implementation:

1. approve  → a ``ledger_transaction`` Fact for the row's dedupe_key is committed to the instance heap,
   provenance-stamped, with the ORIGINAL category.
2. edit     → the committed Fact carries the CORRECTED fields (ledger_head / gst_treatment).
3. reject   → NO ``ledger_transaction`` Fact is committed, but the rejection is journaled (audit intact).
4. every approve/edit/reject is recorded as a gym ``EvalCase`` (the "CA corrections feed the gym").
5. idempotency: resolving the same row twice does not double-commit.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import agentx_db.collections as c
import pytest
from agentx_contracts import InstanceBinding, JsonObject, ManagerAction
from agentx_kernel.books_review import BooksReviewResolver
from agentx_kernel.stores.memory import InMemoryJournalStore, InMemoryProjectionStore

NOW = datetime(2026, 6, 24, tzinfo=UTC)


def _instance() -> InstanceBinding:
    return InstanceBinding(
        instance_id="inst_books_review",
        type_ref="books-prep@0.1.0",
        ring="L1",
        heap_region_id="heap_books_review",
    )


def _flagged_row() -> JsonObject:
    """A row as it sits on the CA review queue (low-confidence, never committed by the original run)."""
    return {
        "dedupe_key": "txn_review_1",
        "date": "2026-04-05",
        "narration": "UPI/AMAZON/office stationery purchase",
        "debit": 1800.0,
        "credit": 0.0,
        "balance": 98200.0,
        "ref": "SIM0002",
        "source": {"doc_id": "april-statement.pdf", "page": 1, "line": 3},
        "account_id": "XXXX1234",
        "statement_period": "2026-04",
        "ledger_head": "Suspense",
        "gst_treatment": "indeterminate_from_source",
        "confidence": 0.4,
        "vendor": "AMAZON",
        "gstin": "",
        "state": "",
        "receivable_payable": "payable",
        "missing_supporting_doc": True,
        "queued": True,
        "queue_reason": "low categorisation confidence (< 0.8); ledger head 'Suspense' is uncertain",
    }


def _resolver() -> BooksReviewResolver:
    return BooksReviewResolver(
        journal=InMemoryJournalStore(),
        projection_store=InMemoryProjectionStore(),
    )


async def _heap_txn_facts(resolver: BooksReviewResolver, *, dedupe_key: str) -> list[dict[str, object]]:
    return await resolver.projection_store.find(
        c.HEAP_FACT,
        {
            "instance_id": "inst_books_review",
            "subject": dedupe_key,
            "predicate": "ledger_transaction",
        },
    )


# --- 1. approve commits the row, provenance-stamped, original category ------------------


@pytest.mark.asyncio
async def test_approve_commits_a_provenance_stamped_ledger_transaction_fact() -> None:
    resolver = _resolver()
    row = _flagged_row()

    resolution = await resolver.resolve(
        instance=_instance(), row=row, decision="approve", actor="ca_priya", now=NOW
    )

    assert resolution.decision == "approve"
    assert resolution.already_resolved is False
    assert resolution.committed_fact_id is not None

    facts = await _heap_txn_facts(resolver, dedupe_key="txn_review_1")
    assert len(facts) == 1, facts
    fact = facts[0]
    # Provenance-stamped (invariant #1: no fact without a commit).
    provenance = fact["provenance"]
    assert isinstance(provenance, dict)
    assert provenance["run_id"]  # the resolution micro-run id
    assert provenance["evidence"]  # cites the source doc
    # Approve keeps the ORIGINAL category.
    payload = json.loads(str(fact["object"]))
    assert payload["ledger_head"] == "Suspense"
    assert payload["gst_treatment"] == "indeterminate_from_source"


# --- 2. edit commits the corrected fields ----------------------------------------------


@pytest.mark.asyncio
async def test_edit_commits_the_corrected_fields() -> None:
    resolver = _resolver()
    row = _flagged_row()

    resolution = await resolver.resolve(
        instance=_instance(),
        row=row,
        decision="edit",
        edits={"ledger_head": "Office Supplies", "gst_treatment": "input_tax_credit"},
        actor="ca_priya",
        now=NOW,
    )

    assert resolution.decision == "edit"
    assert resolution.committed_fact_id is not None

    facts = await _heap_txn_facts(resolver, dedupe_key="txn_review_1")
    assert len(facts) == 1
    payload = json.loads(str(facts[0]["object"]))
    # The committed Fact carries the CA's corrected fields, not the original ones.
    assert payload["ledger_head"] == "Office Supplies"
    assert payload["gst_treatment"] == "input_tax_credit"


# --- 3. reject commits no fact but journals the rejection ------------------------------


@pytest.mark.asyncio
async def test_reject_commits_no_fact_but_journals_the_rejection() -> None:
    resolver = _resolver()
    row = _flagged_row()

    resolution = await resolver.resolve(
        instance=_instance(), row=row, decision="reject", actor="ca_priya", now=NOW
    )

    assert resolution.decision == "reject"
    assert resolution.committed_fact_id is None

    # No ledger_transaction fact reached the heap.
    facts = await _heap_txn_facts(resolver, dedupe_key="txn_review_1")
    assert facts == []

    # The rejection IS journaled (audit trail intact).
    events = await resolver.journal.read_instance("inst_books_review")
    rejections = [
        e
        for e in events
        if isinstance(e, ManagerAction)
        and "reject" in e.action
        and e.detail.get("dedupe_key") == "txn_review_1"
    ]
    assert len(rejections) == 1


# --- 4. every decision is recorded as a gym eval case ----------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["approve", "edit", "reject"])
async def test_every_decision_writes_a_real_gym_eval_case(decision: str) -> None:
    resolver = _resolver()
    edits: JsonObject | None = {"ledger_head": "Office Supplies"} if decision == "edit" else None

    resolution = await resolver.resolve(
        instance=_instance(),
        row=_flagged_row(),
        decision=decision,  # type: ignore[arg-type]
        edits=edits,
        actor="ca_priya",
        now=NOW,
    )

    cases = await resolver.projection_store.find(c.EVAL_CASE, {"id": resolution.eval_case_id})
    assert len(cases) == 1
    case = cases[0]
    # CA corrections feed the gym as REAL (origin="real") cases — invariant #7.
    assert case["origin"] == "real"
    assert case["reality_outcome"] == decision
    tags = case["tags"]
    assert isinstance(tags, list)
    assert "ca_review" in tags and decision in tags


# --- 5. idempotency: resolving the same row twice does not double-commit ----------------


@pytest.mark.asyncio
async def test_resolving_the_same_row_twice_does_not_double_commit() -> None:
    resolver = _resolver()
    row = _flagged_row()

    first = await resolver.resolve(
        instance=_instance(), row=row, decision="approve", actor="ca_priya", now=NOW
    )
    second = await resolver.resolve(
        instance=_instance(), row=row, decision="approve", actor="ca_priya", now=NOW
    )

    assert first.already_resolved is False
    assert second.already_resolved is True

    # Exactly one committed fact, one eval case, one resolution audit row.
    facts = await _heap_txn_facts(resolver, dedupe_key="txn_review_1")
    assert len(facts) == 1

    cases = await resolver.projection_store.find(c.EVAL_CASE, {})
    assert len(cases) == 1

    events = await resolver.journal.read_instance("inst_books_review")
    resolution_actions = [
        e for e in events if isinstance(e, ManagerAction) and e.action.startswith("ca_review:")
    ]
    assert len(resolution_actions) == 1


# --- bootstrap wiring ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_resolver_shares_injected_stores() -> None:
    """``build_books_review_resolver`` wires the resolver to the SAME stores the kernel uses, so a
    committed Fact lands in the injected projection store (the heap the rest of the kernel reads)."""
    from agentx_kernel.bootstrap import build_books_review_resolver

    journal = InMemoryJournalStore()
    store = InMemoryProjectionStore()
    resolver = build_books_review_resolver(journal=journal, projection_store=store)
    assert resolver.journal is journal
    assert resolver.projection_store is store

    await resolver.resolve(
        instance=_instance(), row=_flagged_row(), decision="approve", actor="ca_priya", now=NOW
    )
    committed = await store.find(c.HEAP_FACT, {"subject": "txn_review_1"})
    assert len(committed) == 1
