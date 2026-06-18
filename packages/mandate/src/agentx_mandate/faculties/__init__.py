"""Phase-1 faculty library for mandate pods."""

from __future__ import annotations

from collections.abc import Callable

from agentx_contracts.faculty import Faculty

from agentx_mandate.harness import FacultyContext, HarnessAction

from . import enrichment, escalation, judgment, memory_craft, research

Proposer = Callable[[FacultyContext], list[HarnessAction]]

FACULTY_LIBRARY: dict[str, Faculty] = {
    research.FACULTY.name: research.FACULTY,
    enrichment.FACULTY.name: enrichment.FACULTY,
    judgment.FACULTY.name: judgment.FACULTY,
    memory_craft.FACULTY.name: memory_craft.FACULTY,
    escalation.FACULTY.name: escalation.FACULTY,
}

_PROPOSERS: dict[str, Proposer] = {
    research.FACULTY.name: research.propose,
    enrichment.FACULTY.name: enrichment.propose,
    judgment.FACULTY.name: judgment.propose,
    memory_craft.FACULTY.name: memory_craft.propose,
    escalation.FACULTY.name: escalation.propose,
}


def get_faculty(name: str) -> Faculty:
    return FACULTY_LIBRARY[name]


def propose(name: str, ctx: FacultyContext) -> list[HarnessAction]:
    return _PROPOSERS[name](ctx)


__all__ = ["FACULTY_LIBRARY", "get_faculty", "propose"]
