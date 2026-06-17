"""THE SEAM PROOF — the end-to-end integration target for Session B.

This test is DESIGNED TO FAIL in Session A with a clear "not implemented", documenting exactly what
the two halves must join into. It *passes* only when both lanes are built against the frozen
contracts and snap together:

    candidate lead-finder MandateType
      -> kernel RunInvoker.invoke(mode="sim")   hydrates a frozen snapshot from the heap
      -> a faculty proposes a syscall (intent)  via its tool_manifest
      -> the GATEWAY ring-checks; at L1 it PARKS for a human approval card
      -> approval resumes the run; the effect executes (idempotent) + is journaled
      -> SETTLEMENT commits ONE atomic RunSettled event (facts w/ provenance, trust, billing, watch)
      -> the swarm's promptfoo Judge grades the trace into a Scorecard

The first half (RunInvoker, gateway, settlement) is Claude's; the syscall adapters + SimAdapter +
Judge are Codex's. Both build ONLY against ``agentx_contracts``.
"""

from datetime import UTC, datetime

import pytest
from agentx_contracts import (
    Charter,
    Condition,
    DeadlineTrigger,
    DomainPackRef,
    FacultyBinding,
    InstanceBinding,
    MandateType,
    SettlementRules,
    SpawnRule,
    VerificationSuite,
)
from agentx_kernel.bootstrap import build_phase1_runinvoker
from agentx_swarm.judge import build_promptfoo_judge
from agentx_syscall.registry import build_phase1_registry


def _candidate_lead_finder() -> MandateType:
    """The Phase-1 candidate mandate, assembled from library faculties (BLUEPRINT §7).

    Doubles as a worked example that the contracts compose into a real MandateType.
    """
    return MandateType(
        id="type_lead_finder_v0",
        name="lead-finder",
        version="0.1.0",
        charter=Charter(
            goal="Find and score qualified leads for an ICP, with evidence for each.",
            postconditions=[
                Condition(
                    id="leads_scored",
                    description="Each returned lead has a fit score and cited evidence.",
                    rung="judge",
                ),
                Condition(
                    id="no_existing_customers",
                    description="Never surface an existing customer as a new lead.",
                    rung="rules",
                    expr="lead.id not in instance.customers",
                ),
            ],
            constraints=["read-only research only", "draft email only — never send (Phase 1)"],
            target={"quantity": 10, "fit_threshold": 0.7},
        ),
        faculties=[
            FacultyBinding(faculty_name="research"),
            FacultyBinding(faculty_name="judgment"),
            FacultyBinding(faculty_name="memory-craft"),
            FacultyBinding(faculty_name="escalation"),
        ],
        domain_pack=DomainPackRef(name="indian-smb-leads", version="0.1.0"),
        verification=VerificationSuite(),
        settlement=SettlementRules(
            spawn_rules=[
                SpawnRule(on_condition="lead_warm_but_unbooked", child_type_ref="follow-up@0.1.0")
            ],
        ),
        service_ports=["qualified_leads"],
    )


def _sharma_binding() -> InstanceBinding:
    """An instance at ring L1 — so an effectful syscall (draft_email) PARKS for approval."""
    return InstanceBinding(
        instance_id="inst_sharma_dental",
        type_ref="lead-finder@0.1.0",
        ring="L1",
        heap_region_id="heap_sharma",
    )


@pytest.mark.asyncio
async def test_phase1_seam_proof() -> None:
    mandate = _candidate_lead_finder()
    binding = _sharma_binding()
    trigger = DeadlineTrigger(ts=datetime.now(UTC), reason="daily lead sweep")

    # The contracts already compose — these construct and validate cleanly in Session A:
    assert mandate.name == "lead-finder"
    assert {b.faculty_name for b in mandate.faculties} == {
        "research",
        "judgment",
        "memory-craft",
        "escalation",
    }
    assert binding.ring == "L1"
    # Codex's lane entry points exist (filled in Session B):
    assert callable(build_phase1_registry)
    assert callable(build_promptfoo_judge)

    # --- The seam itself is the Session-B integration target (fails "not implemented" now) ---
    invoker = build_phase1_runinvoker()  # raises NotImplementedError(SEAM_PROOF_TODO) in Session A
    result = await invoker.invoke(
        mandate=mandate, instance=binding, trigger=trigger, mode="sim"
    )

    # Intended Session-B assertions (unreachable until the seam is implemented):
    assert result.state in {"settled", "parked"}
    assert result.trace.run_id == result.run_id
    if result.state == "parked":
        assert result.park is not None and result.park.awaiting == "human_approval"
    if result.settlement is not None:
        # invariant #1: every committed fact carries provenance.
        assert all(f.provenance.run_id for f in result.settlement.facts)
