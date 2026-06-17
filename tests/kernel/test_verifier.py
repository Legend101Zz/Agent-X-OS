"""P6 verifier: deterministic rules rung plus human approval parking."""

from datetime import UTC, datetime

from agentx_contracts.journal import ApprovalResolved
from agentx_contracts.mandate import (
    Charter,
    Condition,
    DomainPackRef,
    MandateType,
    SettlementRules,
    VerificationSuite,
)
from agentx_contracts.memory import Fact, Provenance
from agentx_kernel.stores.memory import InMemoryJournalStore
from agentx_kernel.verifier import HumanApprovalGate, RulesVerifier

NOW = datetime(2026, 6, 17, tzinfo=UTC)


def _fact(predicate: str = "qualified_lead_score") -> Fact:
    return Fact(
        id="f1",
        instance_id="inst_a",
        subject="lead_1",
        predicate=predicate,
        object="0.8",
        confidence=0.8,
        source="agent-inferred",
        provenance=Provenance(run_id="run_1", evidence=["trace:1"]),
        created_at=NOW,
    )


def _mandate() -> MandateType:
    return MandateType(
        id="type_lead_finder_v0",
        name="lead-finder",
        version="0.1.0",
        charter=Charter(
            goal="Find qualified leads.",
            postconditions=[
                Condition(
                    id="has_claimed_facts",
                    description="At least one fact was claimed.",
                    rung="rules",
                    expr="claimed_facts >= 1",
                ),
                Condition(
                    id="has_lead_score",
                    description="A lead score fact exists.",
                    rung="rules",
                    expr="fact:qualified_lead_score exists",
                ),
                Condition(id="judge_quality", description="Judge checks quality.", rung="judge"),
            ],
        ),
        faculties=[],
        domain_pack=DomainPackRef(name="test", version="0.1.0"),
        verification=VerificationSuite(),
        settlement=SettlementRules(),
    )


def test_rules_verifier_passes_supported_rules_postconditions() -> None:
    result = RulesVerifier().verify_postconditions(_mandate(), claimed_facts=[_fact()])

    assert result.passed is True
    assert result.rungs_passed == ["rules"]
    assert result.passed_condition_ids == ["has_claimed_facts", "has_lead_score"]
    assert result.failed_condition_ids == []


def test_rules_verifier_fails_missing_or_unsupported_rules_postconditions() -> None:
    mandate = _mandate().model_copy(
        update={
            "charter": Charter(
                goal="Find qualified leads.",
                postconditions=[
                    Condition(
                        id="has_claimed_facts",
                        description="At least one fact was claimed.",
                        rung="rules",
                        expr="claimed_facts >= 1",
                    ),
                    Condition(
                        id="unknown_rule",
                        description="Unsupported expression fails closed.",
                        rung="rules",
                        expr="lead.id not in instance.customers",
                    ),
                ],
            )
        }
    )

    result = RulesVerifier().verify_postconditions(mandate, claimed_facts=[])

    assert result.passed is False
    assert result.failed_condition_ids == ["has_claimed_facts", "unknown_rule"]
    assert "unsupported rule expression" in result.reasons[-1]


async def test_human_approval_gate_parks_and_resumes_from_approval_resolved_event() -> None:
    journal = InMemoryJournalStore()
    gate = HumanApprovalGate(journal)

    parked = await gate.park_for_approval(
        instance_id="inst_a",
        run_id="run_1",
        reason="draft_email requires L2",
        required_ring="L2",
        now=NOW,
    )

    assert parked.awaiting == "human_approval"
    assert parked.required_ring == "L2"
    assert await gate.resolution(run_id="run_1") is None

    await journal.append(
        ApprovalResolved(
            event_id="approval_1",
            seq=0,
            ts=NOW,
            instance_id="inst_a",
            run_id="run_1",
            decision="approve",
        )
    )

    resolution = await gate.resolution(run_id="run_1")
    assert resolution is not None
    assert resolution.decision == "approve"
