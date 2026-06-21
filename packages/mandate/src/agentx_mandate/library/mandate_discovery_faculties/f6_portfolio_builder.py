"""F6 — mandate-portfolio-builder faculty (the GATED Claim).

This is the ONE faculty in mandate-discovery that emits a Claim — and it
parks for human review at L1. The Claim carries provenance-stamped facts
that satisfy the charter postconditions:

  - fact:target_segment_specified        (precondition)
  - fact:read_only_invariance_holds      (pathcondition)
  - fact:pain_cluster_count              (postcondition #1)
  - fact:mandate_candidate_count         (postcondition #2)
  - fact:moat_pass_count                 (postcondition #3)
  - fact:buyer_source_manifest           (postcondition #4)
  - fact:mandate_portfolio               (postcondition #5 — the deliverable)

The Claim's facts are built by the playbook AFTER F1–F5 have all run, using
the deterministic gates in ``mandate_discovery_quality.py``. The faculty
itself is a Think action that signals the Claim will follow; the playbook
then yields the Claim with the assembled facts.

The atomic portfolio fact (``mandate_portfolio``) is the platform-consumable
deliverable: the roadmap board reads it; the lead-finder's spawn rules
reference it (on_condition: shortlist_approved).
"""

from __future__ import annotations

from typing import cast

from agentx_contracts.faculty import Faculty, HarnessAdapterSpec
from agentx_contracts.memory import Fact, Provenance

from agentx_mandate.harness import Claim, FacultyContext, HarnessAction, Think

FACULTY = Faculty(
    name="mandate_discovery_portfolio_builder",
    skill_pack="skill_pack:mandate-discovery/portfolio-builder@0.1.0",
    tool_manifest=[],
    eval_slice="gym:mandate-discovery/portfolio-builder",
    harness_adapter=HarnessAdapterSpec(
        harness="hermes",
        native_skills_enabled=["structured_synthesis", "portfolio_construction"],
        effectful_tools_to_gateway=True,
        memory_mode="per_run_scratch",
    ),
)


def build_portfolio_facts(
    ctx: FacultyContext,
    *,
    pain_cluster_count: int,
    mandate_candidate_count: int,
    moat_pass_count: int,
    buyer_mapped_count: int,
    shortlist_count: int,
    portfolio_committed: bool,
    portfolio_payload: dict[str, object] | None,
) -> list[Fact]:
    """The provenance-stamped facts F6 claims — one per charter condition.

    The postcondition predicates line up with the ``Condition.expr`` strings
    in ``build_mandate_discovery_type``: each ``fact:<predicate> exists`` is
    satisfied by one of the facts here. The facts are stamped with the run_id
    (invariant #1: no fact without provenance).
    """
    facts: list[Fact] = []
    # Precondition fact
    target_segment = str(ctx.target.get("segment", "")) if isinstance(ctx.target, dict) else ""
    if target_segment:
        facts.append(
            Fact(
                id=f"{ctx.run_id}:md:target_segment_specified",
                instance_id=ctx.instance_id,
                subject="mandate_discovery_run",
                predicate="target_segment_specified",
                object=target_segment,
                confidence=1.0,
                source="agent-inferred",
                provenance=Provenance(
                    run_id=ctx.run_id,
                    evidence=[f"target.segment:{target_segment}"],
                    note="The discovery run's target.segment was specified at trigger time.",
                ),
                status="probation",
                created_at=ctx.now,
            )
        )
    # Pathcondition fact
    facts.append(
        Fact(
            id=f"{ctx.run_id}:md:read_only_invariance_holds",
            instance_id=ctx.instance_id,
            subject="mandate_discovery_run",
            predicate="read_only_invariance_holds",
            object="true",
            confidence=1.0,
            source="agent-inferred",
            provenance=Provenance(
                run_id=ctx.run_id,
                evidence=["constraints:read_only"],
                note=(
                    "F1–F5 are all risk_class=read syscalls; F6 emits a Claim "
                    "but no effectful Call. The run is read-only by construction."
                ),
            ),
            status="probation",
            created_at=ctx.now,
        )
    )
    # Postcondition facts (the five gates the verifier checks)
    facts.append(
        Fact(
            id=f"{ctx.run_id}:md:pain_cluster_count",
            instance_id=ctx.instance_id,
            subject="mandate_discovery_run",
            predicate="pain_cluster_count",
            object=str(pain_cluster_count),
            confidence=0.7,
            source="agent-inferred",
            provenance=Provenance(
                run_id=ctx.run_id,
                evidence=[f"pain_clusters:survived:{pain_cluster_count}"],
                note=(
                    f"Surviving pain clusters after the F2 deterministic gate "
                    f"(severity>={3} AND frequency>={2} AND diversity>={2})."
                ),
            ),
            status="probation",
            created_at=ctx.now,
        )
    )
    facts.append(
        Fact(
            id=f"{ctx.run_id}:md:mandate_candidate_count",
            instance_id=ctx.instance_id,
            subject="mandate_discovery_run",
            predicate="mandate_candidate_count",
            object=str(mandate_candidate_count),
            confidence=0.7,
            source="agent-inferred",
            provenance=Provenance(
                run_id=ctx.run_id,
                evidence=[f"mandate_candidates:survived:{mandate_candidate_count}"],
                note=(
                    "Surviving mandate candidates after the F3 deterministic "
                    "gate (input!=output, recurring, pain>=0.4, not anti-portfolio)."
                ),
            ),
            status="probation",
            created_at=ctx.now,
        )
    )
    facts.append(
        Fact(
            id=f"{ctx.run_id}:md:moat_pass_count",
            instance_id=ctx.instance_id,
            subject="mandate_discovery_run",
            predicate="moat_pass_count",
            object=str(moat_pass_count),
            confidence=0.7,
            source="agent-inferred",
            provenance=Provenance(
                run_id=ctx.run_id,
                evidence=[f"moat_pass:survived:{moat_pass_count}"],
                note=(
                    "Candidates that survived the F4 moat gate "
                    "(NOT (saturation>0.7 AND defensibility<0.3))."
                ),
            ),
            status="probation",
            created_at=ctx.now,
        )
    )
    facts.append(
        Fact(
            id=f"{ctx.run_id}:md:buyer_source_manifest",
            instance_id=ctx.instance_id,
            subject="mandate_discovery_run",
            predicate="buyer_source_manifest",
            object=f"shortlist={shortlist_count};buyer_mapped={buyer_mapped_count}",
            confidence=0.7,
            source="agent-inferred",
            provenance=Provenance(
                run_id=ctx.run_id,
                evidence=[f"buyer_channels:mapped:{buyer_mapped_count}"],
                note=(
                    "Every shortlist item has at least one concrete buyer "
                    "channel with audience>0 AND a first-100-prospect query."
                ),
            ),
            status="probation",
            created_at=ctx.now,
        )
    )
    # The atomic portfolio fact — the platform-consumable deliverable.
    if portfolio_committed and isinstance(portfolio_payload, dict):
        deferred_list = cast(list[object], portfolio_payload.get("deferred", []))
        anti_list = cast(list[object], portfolio_payload.get("anti_portfolio", []))
        facts.append(
            Fact(
                id=f"{ctx.run_id}:md:mandate_portfolio",
                instance_id=ctx.instance_id,
                subject="mandate_discovery_run",
                predicate="mandate_portfolio",
                object=str(portfolio_payload.get("shortlist_count", shortlist_count)),
                confidence=0.6,
                source="agent-inferred",
                provenance=Provenance(
                    run_id=ctx.run_id,
                    evidence=[
                        f"portfolio.shortlist:{shortlist_count}",
                        f"portfolio.deferred:{len(deferred_list)}",
                        f"portfolio.anti_portfolio:{len(anti_list)}",
                        str(portfolio_payload.get("evidence_pack_url", "")),
                    ],
                    note=(
                        "The atomic mandate portfolio — consumed by the "
                        "roadmap board and the lead-finder spawn rules."
                    ),
                ),
                status="probation",
                created_at=ctx.now,
            )
        )
    return facts


def propose(ctx: FacultyContext) -> list[HarnessAction]:
    """Signal the F6 build + a placeholder Think.

    The actual Claim is yielded by the playbook AFTER all gates have run,
    using ``build_portfolio_facts``. This Think records that F6 has been
    invoked and the Claim will follow.
    """
    return [
        Think(
            summary="F6 portfolio-builder: assembling the atomic portfolio Claim",
            detail={
                "input_keys": ["pain_clusters", "mandate_candidates", "buyer_channels"],
                "output_key": "mandate_portfolio",
                "parks_for_human_review": True,
                "instance_id": ctx.instance_id,
                "run_id": ctx.run_id,
            },
        )
    ]


def claim_portfolio(
    ctx: FacultyContext,
    *,
    pain_cluster_count: int,
    mandate_candidate_count: int,
    moat_pass_count: int,
    buyer_mapped_count: int,
    shortlist_count: int,
    portfolio_committed: bool,
    portfolio_payload: dict[str, object] | None,
) -> Claim:
    """Build the Claim the playbook yields after F6's gates have all run."""
    facts = build_portfolio_facts(
        ctx,
        pain_cluster_count=pain_cluster_count,
        mandate_candidate_count=mandate_candidate_count,
        moat_pass_count=moat_pass_count,
        buyer_mapped_count=buyer_mapped_count,
        shortlist_count=shortlist_count,
        portfolio_committed=portfolio_committed,
        portfolio_payload=portfolio_payload,
    )
    return Claim(facts=facts)


__all__ = [
    "FACULTY",
    "propose",
    "build_portfolio_facts",
    "claim_portfolio",
]
