"""Phase-1 lead-finder mandate type."""

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


def build_lead_finder_type() -> MandateType:
    return MandateType(
        id="type_lead_finder_v0",
        name="lead-finder",
        version="0.1.0",
        charter=Charter(
            goal="Find and score qualified leads for an ICP, with evidence for each.",
            postconditions=[
                Condition(
                    id="has_claimed_facts",
                    description="At least one lead fact was claimed.",
                    rung="rules",
                    expr="claimed_facts >= 1",
                ),
                Condition(
                    id="has_lead_score",
                    description="A qualified lead score fact exists.",
                    rung="rules",
                    expr="fact:qualified_lead_score exists",
                ),
                Condition(
                    id="has_actionable_lead",
                    description="At least one lead has organization, role, contact path, and cited signal.",
                    rung="rules",
                    expr="fact:actionable_lead exists",
                ),
            ],
            constraints=["read-only research first", "draft email only; never send in Phase 1"],
            target={"icp": "independent dental clinics", "location": "Pune", "count": 1},
        ),
        faculties=[
            FacultyBinding(faculty_name="research"),
            FacultyBinding(faculty_name="enrichment"),
            FacultyBinding(faculty_name="judgment"),
            FacultyBinding(faculty_name="memory-craft"),
            FacultyBinding(faculty_name="escalation"),
        ],
        domain_pack=DomainPackRef(name="indian-smb-leads", version="0.1.0"),
        verification=VerificationSuite(),
        settlement=SettlementRules(watch_window_hours=72),
        service_ports=["qualified_leads"],
    )
