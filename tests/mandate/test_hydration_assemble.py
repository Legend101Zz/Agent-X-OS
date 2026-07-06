"""P4 pure hydration: rank heap facts and freeze the run snapshot."""

from datetime import UTC, datetime, timedelta

from agentx_contracts.mandate import DomainPackRef
from agentx_contracts.memory import Fact, Provenance, Thread
from agentx_mandate.hydration import assemble

NOW = datetime(2026, 6, 17, tzinfo=UTC)


def _fact(
    fid: str,
    *,
    subject: str,
    confidence: float,
    created_at: datetime,
) -> Fact:
    return Fact(
        id=fid,
        instance_id="inst_a",
        subject=subject,
        predicate="matches_icp",
        object="true",
        confidence=confidence,
        source="agent-inferred",
        provenance=Provenance(run_id="run_prior", evidence=[f"trace:{fid}"]),
        created_at=created_at,
    )


def _thread() -> Thread:
    return Thread(
        id="inst_a:lead_1",
        instance_id="inst_a",
        entity_id="lead_1",
        state="engaged",
        history=[{"turn": "owner approved outreach"}],
        updated_at=NOW,
    )


def test_assemble_ranks_facts_by_relevance_confidence_and_recency() -> None:
    fresh_relevant = _fact("fresh_relevant", subject="lead_1", confidence=0.8, created_at=NOW)
    fresh_irrelevant = _fact("fresh_irrelevant", subject="lead_2", confidence=0.95, created_at=NOW)
    stale_relevant = _fact("stale_relevant", subject="lead_1", confidence=0.99, created_at=NOW - timedelta(days=60))

    snapshot = assemble(
        facts=[stale_relevant, fresh_irrelevant, fresh_relevant],
        thread=_thread(),
        recent_journal=[],
        skill_pack_refs=["skill_pack:lead-finder/research@0.1.0"],
        domain_pack=DomainPackRef(name="dental", version="0.1.0"),
        now=NOW,
    )

    assert [fact.id for fact in snapshot.facts] == ["fresh_relevant", "fresh_irrelevant", "stale_relevant"]


def test_assemble_handles_naive_fact_timestamps() -> None:
    """Facts reloaded from Mongo come back tz-naive; ranking must not crash on them."""
    naive = _fact("naive", subject="lead_1", confidence=0.8, created_at=datetime(2026, 6, 1))
    aware = _fact("aware", subject="lead_1", confidence=0.8, created_at=NOW)

    snapshot = assemble(
        facts=[naive, aware],
        thread=_thread(),
        recent_journal=[],
        skill_pack_refs=["skill_pack:lead-finder/research@0.1.0"],
        domain_pack=DomainPackRef(name="dental", version="0.1.0"),
        now=NOW,
    )

    # The aware/fresh fact outranks the naive/older one (naive treated as UTC).
    assert [fact.id for fact in snapshot.facts] == ["aware", "naive"]


def test_assemble_freezes_snapshot_and_deep_copies_inputs() -> None:
    fact = _fact("f1", subject="lead_1", confidence=0.8, created_at=NOW)
    thread = _thread()

    snapshot = assemble(
        facts=[fact],
        thread=thread,
        recent_journal=[],
        skill_pack_refs=["skill_pack:lead-finder/research@0.1.0"],
        domain_pack=DomainPackRef(name="dental", version="0.1.0"),
        now=NOW,
    )
    fact.object = "mutated"
    thread.state = "mutated"

    assert snapshot.frozen_at == NOW
    assert snapshot.facts[0].object == "true"
    assert snapshot.thread is not None and snapshot.thread.state == "engaged"
    assert snapshot.skill_pack_refs == ["skill_pack:lead-finder/research@0.1.0"]
    assert snapshot.domain_pack == DomainPackRef(name="dental", version="0.1.0")
