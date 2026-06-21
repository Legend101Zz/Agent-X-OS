"""Phase-1 faculty library for mandate pods."""

from __future__ import annotations

from collections.abc import Callable

from agentx_contracts.faculty import Faculty

from agentx_mandate.harness import FacultyContext, HarnessAction
from agentx_mandate.library.mandate_discovery_faculties import (
    F1_COMMUNITY_SOURCE,
    F2_PAIN_EXTRACTION,
    F3_DEMAND_CLUSTERING,
    F4_COMPETITOR_STRESS,
    F5_BUYER_MAPPING,
    F6_PORTFOLIO_BUILDER,
)
from agentx_mandate.library.mandate_discovery_faculties.f1_community_source import propose as f1_propose
from agentx_mandate.library.mandate_discovery_faculties.f2_pain_extraction import propose as f2_propose
from agentx_mandate.library.mandate_discovery_faculties.f3_demand_clustering import propose as f3_propose
from agentx_mandate.library.mandate_discovery_faculties.f4_competitor_stress import propose as f4_propose
from agentx_mandate.library.mandate_discovery_faculties.f5_buyer_mapping import propose as f5_propose
from agentx_mandate.library.mandate_discovery_faculties.f6_portfolio_builder import propose as f6_propose

from . import (
    conversation,
    enrichment,
    escalation,
    judgment,
    memory_craft,
    research,
    scheduling,
)

Proposer = Callable[[FacultyContext], list[HarnessAction]]

FACULTY_LIBRARY: dict[str, Faculty] = {
    research.FACULTY.name: research.FACULTY,
    enrichment.FACULTY.name: enrichment.FACULTY,
    judgment.FACULTY.name: judgment.FACULTY,
    memory_craft.FACULTY.name: memory_craft.FACULTY,
    escalation.FACULTY.name: escalation.FACULTY,
    # Phase-3 (Creator, BLUEPRINT §5): interview + cadence — the kernel-side seams a Creator
    # needs to emit draft candidate MandateTypes. memory-craft + escalation are shared with the
    # lead-finder so the same escalation + provenance story holds for drafts too.
    conversation.FACULTY.name: conversation.FACULTY,
    scheduling.FACULTY.name: scheduling.FACULTY,
    # Phase-12 (mandate-discovery): the F1-F6 discovery faculties. The F7 escalation is
    # already in the library above (shared with lead-finder + creator). We re-export
    # the Faculty objects here so the mandate-discovery playbook's propose() lookups work.
    F1_COMMUNITY_SOURCE.name: F1_COMMUNITY_SOURCE,
    F2_PAIN_EXTRACTION.name: F2_PAIN_EXTRACTION,
    F3_DEMAND_CLUSTERING.name: F3_DEMAND_CLUSTERING,
    F4_COMPETITOR_STRESS.name: F4_COMPETITOR_STRESS,
    F5_BUYER_MAPPING.name: F5_BUYER_MAPPING,
    F6_PORTFOLIO_BUILDER.name: F6_PORTFOLIO_BUILDER,
}

_PROPOSERS: dict[str, Proposer] = {
    research.FACULTY.name: research.propose,
    enrichment.FACULTY.name: enrichment.propose,
    judgment.FACULTY.name: judgment.propose,
    memory_craft.FACULTY.name: memory_craft.propose,
    escalation.FACULTY.name: escalation.propose,
    conversation.FACULTY.name: conversation.propose,
    scheduling.FACULTY.name: scheduling.propose,
    F1_COMMUNITY_SOURCE.name: f1_propose,
    F2_PAIN_EXTRACTION.name: f2_propose,
    F3_DEMAND_CLUSTERING.name: f3_propose,
    F4_COMPETITOR_STRESS.name: f4_propose,
    F5_BUYER_MAPPING.name: f5_propose,
    F6_PORTFOLIO_BUILDER.name: f6_propose,
}


def get_faculty(name: str) -> Faculty:
    return FACULTY_LIBRARY[name]


def propose(name: str, ctx: FacultyContext) -> list[HarnessAction]:
    return _PROPOSERS[name](ctx)


__all__ = ["FACULTY_LIBRARY", "get_faculty", "propose"]

