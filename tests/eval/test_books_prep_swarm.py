"""Books-prep swarm-style eval — drives the same loop as the lead-finder swarm but for the
books-prep pipeline.

This is a thinner analogue of ``test_swarm_end_to_end.py``: instead of a ``ScenarioPack`` (which
is lead-finder-shaped: company/lead/task), we drive the books-prep invoker with the golden
categorisation fixture and judge it against the same rubric (ledger-head accuracy). The
PromotionGate then BARS the synthetic-only run (caveats invariant #7 — no synthetic run may
promote a customer-facing version).

The full ``/commands/run-swarm`` API surface for books-prep is a separate workstream (it would
need a books-prep scenario pack + a books-prep sim registry + a books-prep-specific judge rubric
+ a new promptfoo evaluation file). This test proves the kernel-level loop works, which is the
build-time gate; the API surface waits for the next mandate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from agentx_contracts import CriterionResult, InstanceBinding, MandateType, Rubric, RubricCriterion, Scorecard
from agentx_contracts.trigger import DeadlineTrigger
from agentx_kernel.bootstrap import build_phase1_runinvoker
from agentx_mandate.library.books_prep import build_books_prep_type
from agentx_swarm import PromotionGate, PromotionGateInput
from agentx_syscall.registry import build_phase1_registry
from test_books_prep_golden_eval import run_golden_eval

NOW = datetime(2026, 6, 22, tzinfo=UTC)


def _instance() -> InstanceBinding:
    return InstanceBinding(
        instance_id="inst_books_swarm",
        type_ref="books-prep@0.1.0",
        ring="L1",
        heap_region_id="heap_books_swarm",
    )


def _books_prep_mandate() -> MandateType:
    mandate = build_books_prep_type()
    target = dict(mandate.charter.target or {})
    target["documents"] = ["swarm_run.pdf"]
    target["output_format"] = "xlsx"
    target["confidence_threshold"] = 0.8
    return mandate.model_copy(
        update={"charter": mandate.charter.model_copy(update={"target": target})}
    )


def _books_prep_rubric() -> Rubric:
    """Swarm-level rubric for a books-prep sim run."""
    return Rubric(
        name="books_prep_pipeline",
        pass_threshold=0.6,
        criteria=[
            RubricCriterion(
                id="ingest",
                description="Ingested the simulated document (sim-native transaction synthesis)",
                weight=0.4,
            ),
            RubricCriterion(
                id="categorize",
                description="Categorised transactions (claimed clean + queued low-conf)",
                weight=0.3,
            ),
            RubricCriterion(
                id="export",
                description="Emitted the export_ledger call and produced the deliverable",
                weight=0.3,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_books_prep_swarm_loop_runs_evaluates_and_gate_bars_synthetic(tmp_path: Path) -> None:
    """Same shape as the lead-finder swarm test: run sim → judge → gate.

    The judge here uses the golden-eval accuracy as the score (the rubric is satisfied if the
    ledger-head top-1 accuracy is ≥ the rubric's pass_threshold). The PromotionGate then BARS the
    synthetic-only scorecard from promoting a customer-facing version, regardless of score.
    """
    invoker = build_phase1_runinvoker(
        registry=build_phase1_registry(
            books_intake_dir=tmp_path / "in",
            books_output_dir=tmp_path / "out",
        ),
    )

    result = await invoker.invoke(
        mandate=_books_prep_mandate(),
        instance=_instance(),
        trigger=DeadlineTrigger(ts=NOW, reason="books-prep swarm proof", entity_id="inst_books_swarm:run"),
        mode="sim",
    )

    # --- run: the sim invocation produced a real trace ---
    assert result.state == "settled"
    assert any(
        event.kind == "thought" and "sim synthetic" in event.summary
        for event in result.trace.events
    )

    # --- judge: the golden-eval provides the rubric score (observational) ---
    metrics = run_golden_eval(threshold=0.8)
    rubric = _books_prep_rubric()
    score = metrics.ledger_head_top1_accuracy()
    scorecard = Scorecard(
        run_id=result.run_id,
        rubric_name=rubric.name,
        score=score,
        passed=score >= rubric.pass_threshold,
        origin="synthetic",
        criteria=[
            CriterionResult(
                criterion_id="ledger_head_accuracy",
                passed=score >= rubric.pass_threshold,
                score=score,
                comment="Ledger-head top-1 accuracy on the golden fixture (observational).",
            )
        ],
        failure_reasons=[] if score >= rubric.pass_threshold else [
            f"golden-eval accuracy {score:.1%} below rubric pass threshold {rubric.pass_threshold:.1%}"
        ],
    )

    # --- gate: synthetic-only evidence cannot promote customer-facing versions ---
    gate = PromotionGate(min_score=rubric.pass_threshold)
    blocked = gate.evaluate(PromotionGateInput(scorecards=[scorecard], human_approved=True))
    assert not blocked.allowed
    assert "synthetic-only evidence cannot promote customer-facing versions" in blocked.reasons

    # --- gate: real (CA-acceptance-run) evidence + human approval WOULD open it ---
    real_pass = Scorecard(
        run_id="ca_acceptance_run",
        rubric_name=rubric.name,
        score=score,
        passed=True,
        origin="real",
    )
    allowed = gate.evaluate(PromotionGateInput(scorecards=[scorecard, real_pass], human_approved=True))
    assert allowed.allowed
    assert allowed.live_ring == "L0"