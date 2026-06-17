"""P8 kernel settlement commit: one RunSettled event, then projections."""

from datetime import UTC, datetime

from agentx_contracts.memory import Fact, Provenance
from agentx_contracts.settlement import SettlementEvent, TrustDelta
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
    assert heap_doc["provenance"]["run_id"] == "run_1"
