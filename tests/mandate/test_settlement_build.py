"""P8 pure settlement: build the atomic commit fan-out without I/O."""

from datetime import UTC, datetime, timedelta

import pytest
from agentx_contracts.mandate import MandateRun, SettlementRules, SpawnRule
from agentx_contracts.memory import Fact, Provenance
from agentx_contracts.trigger import DeadlineTrigger
from agentx_mandate.settlement import build_settlement

NOW = datetime(2026, 6, 17, tzinfo=UTC)


def _run() -> MandateRun:
    return MandateRun(
        id="run_1",
        instance_id="inst_a",
        type_ref="lead-finder@0.1.0",
        trigger=DeadlineTrigger(ts=NOW, reason="sweep", entity_id="lead_1"),
        created_at=NOW,
    )


def _fact(*, run_id: str = "run_1", evidence: list[str] | None = None) -> Fact:
    return Fact(
        id="f1",
        instance_id="inst_a",
        subject="lead_1",
        predicate="qualified_lead_score",
        object="0.8",
        confidence=0.8,
        source="agent-inferred",
        provenance=Provenance(run_id=run_id, evidence=evidence or ["trace:1"]),
        created_at=NOW,
    )


def test_build_settlement_creates_trust_billing_watch_spawn_and_thread_update() -> None:
    settlement = build_settlement(
        run=_run(),
        rules=SettlementRules(
            trust_on_success=2,
            billing_per_run=49.0,
            watch_window_hours=72,
            spawn_rules=[
                SpawnRule(
                    on_condition="lead_warm_but_unbooked",
                    child_type_ref="follow-up@0.1.0",
                    params={"cadence": "gentle"},
                    inherit_authority=False,
                )
            ],
        ),
        verified_facts=[_fact()],
        trigger_ctx={
            "success": True,
            "satisfied_conditions": ["lead_warm_but_unbooked"],
            "thread_state": "qualified",
        },
        now=NOW,
    )

    assert settlement.run_id == "run_1"
    assert settlement.instance_id == "inst_a"
    assert settlement.facts[0].provenance.run_id == "run_1"
    assert settlement.trust is not None and settlement.trust.delta == 2
    assert settlement.billing is not None and settlement.billing.amount == 49.0
    assert settlement.watches[0].deadline == NOW + timedelta(hours=72)
    assert settlement.spawns[0].child_type_ref == "follow-up@0.1.0"
    assert settlement.thread_update is not None
    assert settlement.thread_update.entity_id == "lead_1"
    assert settlement.thread_update.new_state == "qualified"


def test_build_settlement_refuses_facts_without_run_provenance_or_evidence() -> None:
    with pytest.raises(ValueError, match="provenance"):
        build_settlement(
            run=_run(),
            rules=SettlementRules(),
            verified_facts=[_fact(run_id="", evidence=[])],
            trigger_ctx={"success": True},
            now=NOW,
        )
