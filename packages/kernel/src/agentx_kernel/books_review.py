"""Per-row CA review resolution — the kernel-lane half of books-prep Flag #1.

Flagged transaction rows sit on the books-prep review queue as fire-and-forget ``queue_manual_action``
cards: they are readable but were never committed (the original run claims clean rows only) and have
no per-task resolution command. The only run-level approval is the single ``export_ledger`` park, which
is run-keyed — it cannot resolve one row out of many. Adding a per-row key to the parked-approval
events would require changing ``RunParked`` / ``ApprovalResolved`` / the command bodies, which live in
the FROZEN ``packages/contracts`` seam.

So we model a CA decision as a tiny triggered follow-up **micro-run**, not a per-row park (handoff §4,
"resolution-as-micro-run"). ``BooksReviewResolver.resolve`` reuses the existing settlement commit path
and the mandate fact-builder — all on the unchanged contracts:

- **approve** → commit the row as a ``ledger_transaction`` Fact (the original category), provenance-
  stamped, via ``SettlementCommitter`` (invariant #1: the Fact reaches the heap only through a
  ``RunSettled`` event).
- **edit** → apply the CA's corrected fields, then commit as above.
- **reject** → commit no Fact; the audit trail is preserved as a journaled ``ManagerAction``.
- in all cases → record the CA decision as a gym ``EvalCase(origin="real")`` (the spec's "CA
  corrections feed the gym"), written to the projection store like ``watch_maturation`` does.

Idempotency (handoff §5.5) reuses the journal's idempotency-key guard: the resolution is keyed by a
deterministic per-row run id, so resolving the same row twice raises ``DuplicateIdempotencyKey`` on the
guard append and short-circuits to a no-op — no double commit, no second eval case, no second audit row.

Lane-pure: kernel side only. No imports from ``agentx_syscall`` / ``agentx_swarm`` / ``pymongo``; the
mandate fact-builder is imported across the allowed kernel→mandate direction, and ``agentx_db`` is used
only for the projection collection-name constants (the established kernel pattern, see
``watch_maturation`` / ``control``).
"""

from __future__ import annotations

from datetime import datetime

import agentx_db.collections as c
from agentx_contracts import EvalCase, HydrationSnapshot, InstanceBinding, ManagerAction
from agentx_contracts.base import AgentXModel
from agentx_contracts.enums import ApprovalDecision
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.memory import Fact
from agentx_contracts.settlement import SettlementEvent, TrustDelta
from agentx_contracts.verification import Scorecard
from agentx_mandate.library.books_prep_review import (
    apply_edits,
    build_resolution_fact,
    dedupe_key_for,
)

from .errors import DuplicateIdempotencyKey
from .ports import JournalStore, ProjectionStore
from .projections import Projections
from .settlement import SettlementCommitter


class BooksReviewResolution(AgentXModel):
    """The typed outcome of resolving one flagged row — what the app's review screen reads back."""

    decision: ApprovalDecision
    dedupe_key: str
    run_id: str
    """The deterministic per-row resolution micro-run id."""
    committed_fact_id: str | None = None
    """The heap Fact id for approve/edit; ``None`` for reject."""
    eval_case_id: str
    already_resolved: bool = False
    """True when this row was already resolved (idempotent no-op — nothing was re-committed)."""


# Per-decision gym score: approve = the agent's prep was right; edit = right transaction, wrong
# categorisation (the CA corrected it); reject = the agent got this row wrong. These feed the gym as
# ground-truth (origin="real") signals.
_DECISION_SCORE: dict[ApprovalDecision, tuple[float, bool]] = {
    "approve": (1.0, True),
    "edit": (0.5, True),
    "reject": (0.0, False),
}


class BooksReviewResolver:
    """Resolve a single flagged books-prep row from a CA decision (approve / edit / reject)."""

    def __init__(self, *, journal: JournalStore, projection_store: ProjectionStore) -> None:
        self.journal = journal
        self.projection_store = projection_store
        self._projections = Projections(projection_store, journal)
        self._settlement = SettlementCommitter(journal=journal, projections=self._projections)

    async def resolve(
        self,
        *,
        instance: InstanceBinding,
        row: JsonObject,
        decision: ApprovalDecision,
        actor: str,
        now: datetime,
        edits: JsonObject | None = None,
    ) -> BooksReviewResolution:
        instance_id = instance.instance_id
        dedupe_key = dedupe_key_for(row)
        run_id = f"{instance_id}:ca_review:{dedupe_key}"
        eval_case_id = f"eval_ca_{run_id}"

        # Idempotency guard (handoff §5.5): the resolution audit row is keyed by a deterministic per-row
        # idempotency key. The FIRST resolution wins; a repeat append raises DuplicateIdempotencyKey and
        # we short-circuit — so a row can be resolved exactly once, regardless of the repeated decision.
        try:
            await self.journal.append(
                ManagerAction(
                    event_id=f"{run_id}:ca_review:{decision}",
                    seq=0,
                    ts=now,
                    instance_id=instance_id,
                    run_id=run_id,
                    actor=f"manager:{actor}",
                    action=f"ca_review:{decision}",
                    idempotency_key=f"{run_id}:resolved",
                    detail=self._audit_detail(row, decision, edits, dedupe_key),
                )
            )
        except DuplicateIdempotencyKey:
            return BooksReviewResolution(
                decision=decision,
                dedupe_key=dedupe_key,
                run_id=run_id,
                committed_fact_id=None,
                eval_case_id=eval_case_id,
                already_resolved=True,
            )

        committed_fact_id: str | None = None
        if decision in ("approve", "edit"):
            fact = build_resolution_fact(
                row,
                instance_id=instance_id,
                run_id=run_id,
                decision=decision,
                actor=actor,
                now=now,
                edits=edits,
            )
            await self._commit_fact(instance_id=instance_id, run_id=run_id, fact=fact, now=now)
            committed_fact_id = fact.id

        await self._write_eval_case(
            eval_case_id=eval_case_id,
            run_id=run_id,
            instance=instance,
            row=row,
            decision=decision,
            edits=edits,
            now=now,
        )

        return BooksReviewResolution(
            decision=decision,
            dedupe_key=dedupe_key,
            run_id=run_id,
            committed_fact_id=committed_fact_id,
            eval_case_id=eval_case_id,
            already_resolved=False,
        )

    async def _commit_fact(
        self, *, instance_id: str, run_id: str, fact: Fact, now: datetime
    ) -> None:
        """Commit one CA-resolved Fact through the same settlement path the run-loop uses.

        ``SettlementCommitter.commit`` appends ONE ``RunSettled`` event and fans it through the
        projections — the ``HeapProjector`` materialises the Fact to ``heap_fact`` (invariant #1: no
        other code path writes the heap). No watches/spawns: a CA decision is itself the human rung.
        """
        await self._settlement.commit(
            SettlementEvent(
                run_id=run_id,
                instance_id=instance_id,
                facts=[fact],
                trust=TrustDelta(
                    instance_id=instance_id,
                    delta=1,
                    reason="ca review resolution committed",
                ),
                settled_at=now,
            )
        )

    async def _write_eval_case(
        self,
        *,
        eval_case_id: str,
        run_id: str,
        instance: InstanceBinding,
        row: JsonObject,
        decision: ApprovalDecision,
        edits: JsonObject | None,
        now: datetime,
    ) -> None:
        """Record the CA decision as a REAL gym case (the "CA corrections feed the gym").

        Written directly to the ``eval_case`` projection — there is no ``EvalCaseCommitted`` journal
        event in the frozen Phase-1 set, so this mirrors ``watch_maturation``'s direct-write convention.
        ``origin="real"`` carries invariant #7: only reality-grade cases open the promotion gate.
        """
        score, passed = _DECISION_SCORE[decision]
        scorecard = Scorecard(
            run_id=run_id,
            rubric_name="ca_review",
            score=score,
            passed=passed,
            origin="real",
            judge_comments=[f"CA {decision}"],
        )
        resolved_row = apply_edits(row, edits) if decision == "edit" else dict(row)
        eval_case = EvalCase(
            id=eval_case_id,
            type_ref=instance.type_ref,
            origin="real",
            hydration=HydrationSnapshot(frozen_at=now),
            output={"decision": decision, "row": resolved_row, "edits": edits or {}},
            verification_result={"decision": decision},
            reality_outcome=decision,
            scorecard=scorecard,
            tags=["ca_review", decision],
        )
        doc = eval_case.model_dump(mode="json")
        # Mirror score/passed at the top level (the dashboard's mapEvalCases + the synthetic write path
        # both read these), matching watch_maturation's eval-case doc shape.
        doc["score"] = scorecard.score
        doc["passed"] = scorecard.passed
        await self.projection_store.upsert(c.EVAL_CASE, eval_case.id, doc)

    @staticmethod
    def _audit_detail(
        row: JsonObject, decision: ApprovalDecision, edits: JsonObject | None, dedupe_key: str
    ) -> JsonObject:
        return {
            "dedupe_key": dedupe_key,
            "decision": decision,
            "edits": edits or {},
            "original_ledger_head": row.get("ledger_head"),
            "original_gst_treatment": row.get("gst_treatment"),
            "queue_reason": row.get("queue_reason"),
        }


__all__ = ["BooksReviewResolution", "BooksReviewResolver"]
