"""Phase-1 faculty library for mandate pods."""

from __future__ import annotations

from collections.abc import Callable

from agentx_contracts.faculty import Faculty

from agentx_mandate.harness import FacultyContext, HarnessAction

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
}

_PROPOSERS: dict[str, Proposer] = {
    research.FACULTY.name: research.propose,
    enrichment.FACULTY.name: enrichment.propose,
    judgment.FACULTY.name: judgment.propose,
    memory_craft.FACULTY.name: memory_craft.propose,
    escalation.FACULTY.name: escalation.propose,
    conversation.FACULTY.name: conversation.propose,
    scheduling.FACULTY.name: scheduling.propose,
}


def get_faculty(name: str) -> Faculty:
    return FACULTY_LIBRARY[name]


def propose(name: str, ctx: FacultyContext) -> list[HarnessAction]:
    return _PROPOSERS[name](ctx)


__all__ = ["FACULTY_LIBRARY", "get_faculty", "propose"]

