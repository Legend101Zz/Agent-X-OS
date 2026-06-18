"""Memory-craft faculty — turns scratch conclusions into probationary fact claims."""

from __future__ import annotations

from agentx_contracts.faculty import Faculty, HarnessAdapterSpec
from agentx_contracts.memory import Fact, Provenance

from agentx_mandate.harness import Claim, FacultyContext, HarnessAction
from agentx_mandate.lead_quality import is_actionable_lead

FACULTY = Faculty(
    name="memory-craft",
    skill_pack="skill_pack:lead-finder/memory-craft@0.1.0",
    tool_manifest=[],
    eval_slice="gym:lead-finder/memory-craft",
    harness_adapter=HarnessAdapterSpec(
        harness="hermes",
        native_skills_enabled=["structured_memory"],
        effectful_tools_to_gateway=True,
        memory_mode="per_run_scratch",
    ),
)


def _lead_id(lead: object) -> str | None:
    if not isinstance(lead, dict):
        return None
    value = lead.get("id")
    return value if isinstance(value, str) else None


def _company(lead: object, lead_id: str) -> str:
    if not isinstance(lead, dict):
        return lead_id
    value = lead.get("company")
    return value if isinstance(value, str) else lead_id


def _evidence(lead: object, ctx: FacultyContext, lead_id: str) -> list[str]:
    if isinstance(lead, dict):
        raw = lead.get("evidence")
        if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
            return raw
    return [f"scratchpad:{ctx.run_id}:{lead_id}"]


def _score(scores: object, lead_id: str) -> tuple[float, str]:
    if not isinstance(scores, dict):
        return 0.5, "unscored candidate"
    raw_entry = scores.get(lead_id)
    if not isinstance(raw_entry, dict):
        return 0.5, "unscored candidate"
    raw_score = raw_entry.get("score")
    score = raw_score if isinstance(raw_score, int | float) else 0.5
    raw_reason = raw_entry.get("reason")
    reason = raw_reason if isinstance(raw_reason, str) else "scored candidate"
    return max(0.0, min(float(score), 1.0)), reason


def propose(ctx: FacultyContext) -> list[HarnessAction]:
    raw_leads = ctx.scratchpad.get("leads")
    if not isinstance(raw_leads, list):
        return []

    facts: list[Fact] = []
    scores = ctx.scratchpad.get("scores")
    for lead in raw_leads:
        lead_id = _lead_id(lead)
        if lead_id is None or not is_actionable_lead(lead):
            continue
        confidence, reason = _score(scores, lead_id)
        facts.append(
            Fact(
                id=f"{ctx.run_id}:{lead_id}:lead_score",
                instance_id=ctx.instance_id,
                subject=lead_id,
                predicate="qualified_lead_score",
                object=str(confidence),
                confidence=confidence,
                source="agent-inferred",
                provenance=Provenance(
                    run_id=ctx.run_id,
                    evidence=_evidence(lead, ctx, lead_id),
                    note=f"{_company(lead, lead_id)}: {reason}",
                ),
                status="probation",
                created_at=ctx.now,
            )
        )
        facts.append(
            Fact(
                id=f"{ctx.run_id}:{lead_id}:actionable",
                instance_id=ctx.instance_id,
                subject=lead_id,
                predicate="actionable_lead",
                object=_company(lead, lead_id),
                confidence=confidence,
                source="agent-inferred",
                provenance=Provenance(
                    run_id=ctx.run_id,
                    evidence=_evidence(lead, ctx, lead_id),
                    note=f"{_company(lead, lead_id)} passed the actionable-lead gate",
                ),
                status="probation",
                created_at=ctx.now,
            )
        )
    return [Claim(facts=facts)] if facts else []
