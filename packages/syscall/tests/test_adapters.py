from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest
from agentx_contracts import GatewayContext, SyscallRequest
from agentx_syscall.adapters import (
    DraftEmailAdapter,
    HumanTaskAdapter,
    LeadResearchBatchAdapter,
    ManualTaskStore,
    MarkOutcomeAdapter,
    QueueManualActionAdapter,
    ReadUrlAdapter,
    ResearchLead,
    ResearchPage,
    ResearchProvider,
)


class FakeResearchProvider:
    name = "fake_research"

    async def health_check(self) -> bool:
        return True

    async def search_leads(self, criteria: Mapping[str, Any], count: int) -> list[ResearchLead]:
        return [
            ResearchLead(
                id=f"lead_{idx}",
                name=f"Clinic {idx}",
                url=f"https://clinic{idx}.example",
                evidence=[f"matches {criteria['segment']}"],
                fit_score=0.9,
            )
            for idx in range(1, count + 1)
        ]

    async def read_url(self, url: str) -> ResearchPage:
        return ResearchPage(
            url=url,
            title="Example Clinic",
            markdown="# Example Clinic\nAccepting bookings.",
            evidence=["Accepting bookings"],
        )


def _ctx() -> GatewayContext:
    return GatewayContext(
        instance_id="inst_1",
        run_id="run_1",
        tenant_id="tenant_1",
        ring="L1",
        now=datetime.now(UTC),
    )


def _req(name: str, args: dict[str, Any] | None = None) -> SyscallRequest:
    return SyscallRequest(
        name=name,
        args=args or {},
        instance_id="inst_1",
        run_id="run_1",
        idempotency_key=f"idem_{name}",
        ring="L1",
    )


@pytest.mark.asyncio
async def test_lead_research_batch_uses_provider_and_has_fixture_health() -> None:
    provider: ResearchProvider = FakeResearchProvider()
    adapter = LeadResearchBatchAdapter(providers=[provider])

    result = await adapter.execute(
        _req("lead_research_batch", {"criteria": {"segment": "dental"}, "count": 2}),
        cred=None,
    )
    health = await adapter.health_check()

    assert result.status == "ok"
    assert result.fulfilled_by == "lead_research_batch"
    assert result.output["provider"] == "fake_research"
    leads = result.output["leads"]
    assert isinstance(leads, list)
    assert len(leads) == 2
    assert health.status == "ok"
    assert adapter.fixtures[0].expect_status == "ok"


@pytest.mark.asyncio
async def test_read_url_uses_provider() -> None:
    provider: ResearchProvider = FakeResearchProvider()
    adapter = ReadUrlAdapter(providers=[provider])

    result = await adapter.execute(_req("read_url", {"url": "https://clinic.example"}), cred=None)

    assert result.status == "ok"
    assert result.output["url"] == "https://clinic.example"
    assert "Accepting bookings" in str(result.output["markdown"])


@pytest.mark.asyncio
async def test_draft_email_never_sends() -> None:
    adapter = DraftEmailAdapter()

    result = await adapter.execute(
        _req(
            "draft_email",
            {
                "to": "founder@example.com",
                "subject": "Lead idea",
                "body": "Draft only.",
            },
        ),
        cred=None,
    )

    assert result.status == "ok"
    assert result.output["mode"] == "draft"
    assert result.output["sent"] is False


@pytest.mark.asyncio
async def test_queue_manual_action_and_mark_outcome_share_store() -> None:
    store = ManualTaskStore()
    queue = QueueManualActionAdapter(store=store)
    marker = MarkOutcomeAdapter(store=store)

    queued = await queue.execute(
        _req("queue_manual_action", {"action": "review_lead", "lead_id": "lead_1"}),
        cred=None,
    )
    task_id = str(queued.output["task_id"])
    marked = await marker.execute(
        _req("mark_outcome", {"task_id": task_id, "outcome": "booked"}),
        cred=None,
    )

    assert queued.status == "queued_manual"
    assert marked.status == "ok"
    assert store.get(task_id).outcome == "booked"


@pytest.mark.asyncio
async def test_human_task_adapter_is_bottom_rung_for_every_intent() -> None:
    store = ManualTaskStore()
    adapter = HumanTaskAdapter(store=store)
    request = _req("anything_future", {"payload": "preserved"})

    assert adapter.can_handle(request, _ctx()) is True
    result = await adapter.execute(request, cred=None)

    assert result.status == "queued_manual"
    assert result.fulfilled_by == "human_task"
    assert result.output["task_id"] in {task.id for task in store.list_open()}
