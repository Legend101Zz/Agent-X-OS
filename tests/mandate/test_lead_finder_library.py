"""P11 lead-finder MandateType library."""

from agentx_mandate.library.lead_finder import build_lead_finder_type


def test_build_lead_finder_type_assembles_phase1_faculties_and_checkable_rules() -> None:
    mandate = build_lead_finder_type()

    assert mandate.name == "lead-finder"
    assert [binding.faculty_name for binding in mandate.faculties] == [
        "research",
        "enrichment",
        "judgment",
        "memory-craft",
        "escalation",
    ]
    rules = [condition for condition in mandate.charter.postconditions if condition.rung == "rules"]
    assert [condition.expr for condition in rules] == [
        "claimed_facts >= 1",
        "fact:qualified_lead_score exists",
        "fact:actionable_lead exists",
    ]
    assert mandate.domain_pack.name == "indian-smb-leads"
