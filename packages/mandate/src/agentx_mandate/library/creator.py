"""Phase-3 Creator mandate type (HERMES_BUILD_PLAN §Phase 3 — starts G10).

The Creator's MandateType composes four faculties (BLUEPRINT §5):
  - conversation: interviews the operator to elicit the brief (no fabrication).
  - scheduling: decides the cadence and emits the ``draft_candidate_type`` Call.
  - memory-craft: turns the brief + trace into probation facts so the human reviewer sees
    provenance for every draft.
  - escalation: fails safely (shared with lead-finder).

The Creator's run output is another ``MandateType`` (the candidate) — emitted via the
``draft_candidate_type`` syscall. The candidate is DRAFT-ONLY (invariant #7): the syscall
returns it for human review; promote to a real mandate_type is Phase 4.

Mirror of ``lead_finder.build_lead_finder_type()``.
"""

from __future__ import annotations

from agentx_contracts.faculty import FacultyBinding
from agentx_contracts.mandate import (
    Charter,
    Condition,
    DomainPackRef,
    MandateType,
    SettlementRules,
    VerificationSuite,
)
from agentx_contracts.verification import Rubric, RubricCriterion


def build_creator_type() -> MandateType:
    """The Creator mandate type — emits drafts of other mandate types.

    The postconditions are MACHINE-CHECKABLE on the drafted candidate (rules-rung, with an
    ``expr``). The Creator's own rules-verifier runs them when the creator run settles; the
    same postconditions ride along to the human reviewer so they can see at-a-glance what
    the rules engine thought of the candidate.
    """
    return MandateType(
        id="type_creator_v0",
        name="creator",
        version="0.1.0",
        charter=Charter(
            goal=(
                "Interview an operator about a desired mandate, draft a candidate "
                "MandateType from the brief, and stage it for human review. Promote is "
                "out of scope — that's Phase 4 (promote gate + canary)."
            ),
            postconditions=[
                Condition(
                    id="candidate_has_faculties",
                    description="The drafted candidate MandateType must bind ≥1 faculty.",
                    rung="rules",
                    expr="candidate.faculties >= 1",
                ),
                Condition(
                    id="candidate_has_charter_goal",
                    description="The drafted candidate MandateType must have a non-empty charter goal.",
                    rung="rules",
                    expr="candidate.charter.goal exists",
                ),
                Condition(
                    id="candidate_names_scenario_pack",
                    description=(
                        "The drafted candidate MandateType must name a scenario pack "
                        "(domain_pack ref) so the swarm can grade it."
                    ),
                    rung="rules",
                    expr="candidate.domain_pack.name exists",
                ),
            ],
            constraints=[
                "draft-only: the candidate is staged for review, never auto-promoted",
                "the Creator is a gated user (Phase 4 promote gate enforces real+human)",
            ],
            target={
                "icp": "qualified B2B prospects",
                "scenario_pack": "indian-smb-leads",
                "candidate_goal": "",
                "cadence_days": 7,
            },
        ),
        faculties=[
            FacultyBinding(faculty_name="conversation"),
            FacultyBinding(faculty_name="scheduling"),
            FacultyBinding(faculty_name="memory-craft"),
            FacultyBinding(faculty_name="escalation"),
        ],
        domain_pack=DomainPackRef(name="indian-smb-leads", version="0.1.0"),
        verification=VerificationSuite(
            ladder=["rules", "judge", "human", "reality"],
            rules=[],
            rubrics=[
                Rubric(
                    name="creator_quality",
                    pass_threshold=0.7,
                    criteria=[
                        RubricCriterion(
                            id="candidate_has_faculties",
                            description="Candidate binds at least one faculty (the §5 set).",
                            weight=0.5,
                        ),
                        RubricCriterion(
                            id="candidate_charter_complete",
                            description=(
                                "Candidate charter declares a goal and at least one "
                                "checkable postcondition."
                            ),
                            weight=0.3,
                        ),
                        RubricCriterion(
                            id="candidate_names_scenario_pack",
                            description="Candidate names a scenario pack / domain_pack ref.",
                            weight=0.2,
                        ),
                    ],
                ),
            ],
        ),
        settlement=SettlementRules(
            fact_commit_confidence=0.6,
            trust_on_success=1,
            trust_on_failure=-1,
            watch_window_hours=72,
        ),
        gym_ref="gym:creator",
        service_ports=["candidate_drafts"],
    )
