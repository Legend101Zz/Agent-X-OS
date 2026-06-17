"""K3 loader half of hydration: read projections and build a frozen mandate snapshot."""

from datetime import UTC, datetime

from agentx_contracts.journal import RunCreated
from agentx_contracts.mandate import DomainPackRef
from agentx_contracts.memory import Fact, Provenance, Thread
from agentx_contracts.trigger import DeadlineTrigger
from agentx_kernel.hydration import HydrationLoader
from agentx_kernel.stores.memory import InMemoryJournalStore, InMemoryProjectionStore

NOW = datetime(2026, 6, 17, tzinfo=UTC)


def _fact(fid: str, subject: str) -> Fact:
    return Fact(
        id=fid,
        instance_id="inst_a",
        subject=subject,
        predicate="matches_icp",
        object="true",
        confidence=0.8,
        source="agent-inferred",
        provenance=Provenance(run_id="run_prior", evidence=[f"trace:{fid}"]),
        created_at=NOW,
    )


def _thread() -> Thread:
    return Thread(
        id="inst_a:lead_1",
        instance_id="inst_a",
        entity_id="lead_1",
        state="engaged",
        history=[],
        updated_at=NOW,
    )


async def test_hydration_loader_reads_projections_and_journal_then_assembles_snapshot() -> None:
    projection = InMemoryProjectionStore()
    journal = InMemoryJournalStore()
    await projection.upsert("heap_fact", "f1", _fact("f1", "lead_1").model_dump(mode="json"))
    await projection.upsert("heap_fact", "f2", _fact("f2", "lead_2").model_dump(mode="json"))
    await projection.upsert("thread", "inst_a:lead_1", _thread().model_dump(mode="json"))
    await journal.append(
        RunCreated(
            event_id="rc1",
            seq=0,
            ts=NOW,
            instance_id="inst_a",
            run_id="run_1",
            type_ref="lead-finder@0.1.0",
            trigger=DeadlineTrigger(ts=NOW, reason="sweep", entity_id="lead_1"),
        )
    )

    snapshot = await HydrationLoader(projection, journal).hydrate(
        instance_id="inst_a",
        entity_id="lead_1",
        skill_pack_refs=["skill_pack:lead-finder/research@0.1.0"],
        domain_pack=DomainPackRef(name="dental", version="0.1.0"),
        now=NOW,
    )

    assert [fact.id for fact in snapshot.facts] == ["f1", "f2"]
    assert snapshot.thread is not None and snapshot.thread.id == "inst_a:lead_1"
    assert len(snapshot.recent_journal) == 1
    assert snapshot.skill_pack_refs == ["skill_pack:lead-finder/research@0.1.0"]
    assert snapshot.domain_pack == DomainPackRef(name="dental", version="0.1.0")
