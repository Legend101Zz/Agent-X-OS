"""P8 kernel settlement commit: one RunSettled event, then projections."""

from datetime import UTC, datetime, timedelta

from agentx_contracts.memory import Fact, Provenance
from agentx_contracts.settlement import SettlementEvent, TrustDelta, Watch
from agentx_kernel.projections import Projections
from agentx_kernel.settlement import SettlementCommitter
from agentx_kernel.stores.memory import InMemoryJournalStore, InMemoryProjectionStore

NOW = datetime(2026, 6, 17, tzinfo=UTC)


def _fact() -> Fact:
    return Fact(
        id="f1",
        instance_id="inst_a",
        subject="lead_1",
        predicate="qualified_lead_score",
        object="0.8",
        confidence=0.8,
        source="agent-inferred",
        provenance=Provenance(run_id="run_1", evidence=["trace:1"]),
        created_at=NOW,
    )


async def test_commit_appends_one_runsettled_and_projects_facts_to_heap() -> None:
    journal = InMemoryJournalStore()
    projection_store = InMemoryProjectionStore()
    projections = Projections(projection_store, journal)
    settlement = SettlementEvent(
        run_id="run_1",
        instance_id="inst_a",
        facts=[_fact()],
        trust=TrustDelta(instance_id="inst_a", delta=1, reason="rules passed"),
        settled_at=NOW,
    )

    event = await SettlementCommitter(journal=journal, projections=projections).commit(settlement)

    assert event.kind == "run_settled"
    assert event.trust_delta == 1
    events = await journal.read_run("run_1")
    assert [item.kind for item in events] == ["run_settled"]
    heap_doc = await projection_store.get("heap_fact", "f1")
    assert heap_doc is not None
    provenance = heap_doc["provenance"]
    assert isinstance(provenance, dict)
    assert provenance["run_id"] == "run_1"


async def test_commit_registers_and_projects_settlement_watches() -> None:
    journal = InMemoryJournalStore()
    projection_store = InMemoryProjectionStore()
    projections = Projections(projection_store, journal)
    deadline = NOW + timedelta(hours=72)
    settlement = SettlementEvent(
        run_id="run_1",
        instance_id="inst_a",
        watches=[
            Watch(
                id="watch_1",
                run_id="run_1",
                instance_id="inst_a",
                condition="lead_replied",
                deadline=deadline,
            )
        ],
        settled_at=NOW,
    )

    await SettlementCommitter(journal=journal, projections=projections).commit(settlement)

    events = await journal.read_run("run_1")
    assert [item.kind for item in events] == ["run_settled", "watch_registered"]
    watch_doc = await projection_store.get("watch", "watch_1")
    assert watch_doc is not None
    assert watch_doc["condition"] == "lead_replied"
    assert watch_doc["deadline"] == deadline.isoformat()
    assert watch_doc["status"] == "pending"
