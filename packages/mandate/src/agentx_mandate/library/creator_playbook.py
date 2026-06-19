"""The Creator's PLAYBOOK — the deterministic trajectory the ``own`` harness drives (sim mode).

The Creator's run claims provenance-stamped facts about the candidate it drafted, so the
rules-verifier can check the Creator's charter postconditions. The claims are the
"structural evidence" that the candidate has ≥1 faculty (the §5 set) and names a scenario pack
— the same predicates the rules-engine can evaluate (``fact:<predicate> exists``).

Like ``lead_finder_playbook`` (G1 sim harness double), this is the GENERATOR the ``own``
harness iterates. The kernel run-loop still disposes each yielded ``Call`` through the
gateway (ring-check, journal, adapter execute).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

from agentx_contracts.faculty import Faculty
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.memory import Fact, Provenance

from agentx_mandate.faculties import propose
from agentx_mandate.harness import Claim, FacultyContext, Finish, HarnessAction, Think


def _candidate_claims(ctx: FacultyContext, receipt: dict[str, object]) -> list[Fact]:
    """Build provenance-stamped facts about the drafted candidate.

    The Creator's charter postconditions look for these facts:
      - ``creator_drafted_faculty_count`` — the candidate binds ≥1 faculty (the §5 set).
      - ``creator_drafted_scenario_pack`` — the candidate names a scenario pack (swarm
        grader).
      - ``creator_drafted_goal`` — the candidate has a non-empty charter goal (the §1
        Charter organ).
      - ``creator_drafted`` — generic marker the run produced a draft.

    The facts are stamped with provenance (run_id + evidence) so invariant #1 holds.
    """
    candidate_dict = receipt.get("candidate", {})
    faculties = candidate_dict.get("faculties", []) if isinstance(candidate_dict, dict) else []
    faculty_count = len(faculties) if isinstance(faculties, list) else 0
    domain_pack = candidate_dict.get("domain_pack", {}) if isinstance(candidate_dict, dict) else {}
    scenario_pack = domain_pack.get("name", "") if isinstance(domain_pack, dict) else ""
    charter = candidate_dict.get("charter", {}) if isinstance(candidate_dict, dict) else {}
    goal = charter.get("goal", "") if isinstance(charter, dict) else ""

    facts: list[Fact] = [
        Fact(
            id=f"{ctx.run_id}:creator_drafted:mandate_type",
            instance_id=ctx.instance_id,
            subject="creator_draft",
            predicate="creator_drafted",
            object=candidate_dict.get("name", "") if isinstance(candidate_dict, dict) else "",
            confidence=0.7,
            source="agent-inferred",
            provenance=Provenance(
                run_id=ctx.run_id,
                evidence=[f"draft_candidate_type:{ctx.run_id}"],
                note="Creator drafted a candidate MandateType (invariant #7 — staged, not registered).",
            ),
            status="probation",
            created_at=ctx.now,
        ),
        Fact(
            id=f"{ctx.run_id}:creator_drafted:faculty_count",
            instance_id=ctx.instance_id,
            subject="creator_draft",
            predicate="creator_drafted_faculty_count",
            object=str(faculty_count),
            confidence=0.7,
            source="agent-inferred",
            provenance=Provenance(
                run_id=ctx.run_id,
                evidence=[f"draft_candidate_type:faculties:{faculty_count}"],
                note=f"Candidate binds {faculty_count} faculty/faculties (the §5 set).",
            ),
            status="probation",
            created_at=ctx.now,
        ),
        Fact(
            id=f"{ctx.run_id}:creator_drafted:scenario_pack",
            instance_id=ctx.instance_id,
            subject="creator_draft",
            predicate="creator_drafted_scenario_pack",
            object=str(scenario_pack),
            confidence=0.7,
            source="agent-inferred",
            provenance=Provenance(
                run_id=ctx.run_id,
                evidence=[f"draft_candidate_type:scenario_pack:{scenario_pack}"],
                note=f"Candidate names scenario pack {scenario_pack!r} (swarm grader hook).",
            ),
            status="probation",
            created_at=ctx.now,
        ),
        Fact(
            id=f"{ctx.run_id}:creator_drafted:goal",
            instance_id=ctx.instance_id,
            subject="creator_draft",
            predicate="creator_drafted_goal",
            object=str(goal),
            confidence=0.7,
            source="agent-inferred",
            provenance=Provenance(
                run_id=ctx.run_id,
                evidence=[f"draft_candidate_type:charter:goal:{len(str(goal))}"],
                note=f"Candidate has a charter goal ({len(str(goal))} chars).",
            ),
            status="probation",
            created_at=ctx.now,
        ),
    ]
    return facts


def creator_playbook(ctx: FacultyContext, faculties: list[Faculty]) -> Iterator[HarnessAction]:
    """Yield the Creator trajectory one action at a time.

    Shape:
      1. Think — a single "interview captured" marker (this is what ``conversation`` emits).
      2. Each faculty's proposal (conversation, scheduling). ``scheduling`` yields the
         ``draft_candidate_type`` Call — that's the heartbeat of the Creator.
      3. The ``draft_candidate_type`` Call suspends for gateway disposal; the gateway writes
         the result into ``ctx.scratchpad['last_receipt']`` (the Creator's run-loop path).
         On resume, the playbook yields a ``Claim`` for the provenance-stamped facts about the
         drafted candidate.
      4. Finish — the Creator's rules-verifier checks the charter postconditions against the
         claimed facts; if any fail, the run escalates.
    """
    target = dict(ctx.target)
    yield Think(
        summary="Creator: capture the brief from the operator.",
        detail=cast(
            JsonObject,
            {"target_keys": sorted(target.keys()), "icp": target.get("icp", "")},
        ),
    )
    for faculty in faculties:
        yield from propose(faculty.name, ctx)

    # After all faculties have proposed, the gateway has disposed the draft_candidate_type
    # Call and stored the result in ``ctx.scratchpad['last_receipt']``. The Creator's
    # memory-craft faculty would claim the facts — we do it inline here because the
    # faculty generic ``memory_craft.propose`` knows about lead-finder claims, not creator
    # claims. (Phase 3 keeps the Creator's claim shape narrow; Phase 4 promote reads the
    # receipt + the claimed facts together.)
    receipt = ctx.scratchpad.get("last_receipt")
    if isinstance(receipt, dict):
        claims = _candidate_claims(ctx, receipt)
        if claims:
            yield Claim(facts=claims)

    yield Finish(output={"action": "drafted_candidate", "park_for_review": True})


__all__ = ["creator_playbook"]
