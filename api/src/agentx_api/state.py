from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

import agentx_db.collections as c
from agentx_contracts.config import get_settings
from agentx_contracts.enums import RunState
from agentx_contracts.journal import (
    ApprovalResolved,
    JournalEvent,
    ManagerAction,
    RunCreated,
    RunHydrated,
    RunParked,
    RunSettled,
    RunVerified,
    SyscallAttempted,
)
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.mandate import MandateInstance
from agentx_contracts.memory import Fact, Provenance
from agentx_contracts.syscall import SyscallRequest
from agentx_contracts.trigger import DeadlineTrigger
from agentx_db.setup import ensure_indexes
from agentx_kernel.control import KernelControl
from agentx_kernel.ports import JournalStore, ProjectionStore
from agentx_kernel.projections import Projections
from agentx_kernel.stores.memory import InMemoryJournalStore, InMemoryProjectionStore
from agentx_kernel.stores.mongo import MongoJournalStore, MongoProjectionStore
from agentx_mandate.library.lead_finder import build_lead_finder_type
from agentx_syscall.adapters import (
    DraftEmailAdapter,
    HumanTaskAdapter,
    LeadResearchBatchAdapter,
    ManualTaskStore,
    MarkOutcomeAdapter,
    QueueManualActionAdapter,
    ReadUrlAdapter,
    build_configured_research_providers,
)
from agentx_syscall.registry import Phase1SyscallRegistry

BackendKind = Literal["memory", "mongo"]


@dataclass
class DashboardState:
    journal: JournalStore
    store: ProjectionStore
    projections: Projections
    control: KernelControl
    registry: Phase1SyscallRegistry
    manual_tasks: ManualTaskStore
    backend: BackendKind
    seed_demo: bool
    database: Any | None = None
    client: Any | None = None
    _ready: bool = False

    async def ready(self) -> None:
        if self._ready:
            return
        if self.database is not None:
            await ensure_indexes(self.database)
        if self.seed_demo:
            await seed_demo_state(self)
        self._ready = True

    async def close(self) -> None:
        close = getattr(self.client, "close", None)
        if callable(close):
            close()

    async def collection(self, collection: str, query: JsonObject | None = None) -> list[dict[str, Any]]:
        docs = await self.store.find(collection, dict(query or {}))
        return [_json_doc(doc) for doc in docs]

    async def get_doc(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        doc = await self.store.get(collection, doc_id)
        return _json_doc(doc) if doc is not None else None

    async def journal_events(
        self,
        *,
        instance_id: str | None = None,
        run_id: str | None = None,
        kind: str | None = None,
        limit: int = 100,
    ) -> list[JournalEvent]:
        if run_id is not None:
            events = await self.journal.read_run(run_id)
        elif instance_id is not None:
            events = await self.journal.read_instance(instance_id)
        else:
            instances = await self.collection(c.MANDATE_INSTANCE)
            events = []
            for instance in instances:
                raw_id = instance.get("id")
                if isinstance(raw_id, str):
                    events.extend(await self.journal.read_instance(raw_id))
            events.sort(key=lambda event: (event.ts, event.instance_id, event.seq))
        if kind is not None:
            events = [event for event in events if event.kind == kind]
        return events[-limit:]


def create_state(*, use_mongo: bool | None, seed_demo: bool) -> DashboardState:
    settings = get_settings()
    uri = settings.mongodb_uri.get_secret_value()
    should_use_mongo = bool(uri) if use_mongo is None else use_mongo
    registry, manual_store = _build_registry()

    if should_use_mongo:
        from pymongo import AsyncMongoClient

        client: Any = AsyncMongoClient(uri)
        database = client[settings.mongodb_db_name]
        journal: JournalStore = MongoJournalStore(database)
        store: ProjectionStore = MongoProjectionStore(database)
        projections = Projections(store, journal)
        return DashboardState(
            journal=journal,
            store=store,
            projections=projections,
            control=KernelControl(journal=journal, projections=projections, projection_store=store),
            registry=registry,
            manual_tasks=manual_store,
            backend="mongo",
            seed_demo=seed_demo,
            database=database,
            client=client,
        )

    journal = InMemoryJournalStore()
    store = InMemoryProjectionStore()
    projections = Projections(store, journal)
    return DashboardState(
        journal=journal,
        store=store,
        projections=projections,
        control=KernelControl(journal=journal, projections=projections, projection_store=store),
        registry=registry,
        manual_tasks=manual_store,
        backend="memory",
        seed_demo=seed_demo,
    )


async def seed_demo_state(state: DashboardState) -> None:
    existing = await state.collection(c.MANDATE_INSTANCE)
    if existing:
        return

    now = datetime(2026, 6, 18, 9, 30, tzinfo=UTC)
    mandate_type = build_lead_finder_type()
    await state.store.upsert(c.MANDATE_TYPE, mandate_type.id, mandate_type.model_dump(mode="json"))
    instance = MandateInstance(
        id="inst_demo",
        type_ref="lead-finder@0.1.0",
        customer_id="Orbit Dental Co",
        ring="L1",
        heap_region_id="heap_demo",
    )
    await state.store.upsert(c.MANDATE_INSTANCE, instance.id, instance.model_dump(mode="json"))

    settled_trigger = DeadlineTrigger(ts=now - timedelta(hours=6), reason="morning lead sweep", entity_id="lead_orbit")
    await _append_and_project(
        state,
        RunCreated(
            event_id="run_demo_settled:created",
            seq=0,
            ts=settled_trigger.ts,
            instance_id=instance.id,
            run_id="run_demo_settled",
            type_ref=instance.type_ref,
            trigger=settled_trigger,
        ),
    )
    await _append_and_project(
        state,
        RunHydrated(
            event_id="run_demo_settled:hydrated",
            seq=0,
            ts=settled_trigger.ts + timedelta(seconds=3),
            instance_id=instance.id,
            run_id="run_demo_settled",
            fact_count=2,
            thread_id=f"{instance.id}:lead_orbit",
        ),
    )
    fact = Fact(
        id="fact_demo_lead_score",
        instance_id=instance.id,
        subject="lead_orbit",
        predicate="qualified_lead_score",
        object="0.82",
        confidence=0.82,
        source="agent-inferred",
        provenance=Provenance(
            run_id="run_demo_settled",
            evidence=["https://orbit.example/careers", "syscall_trace:lead_research_batch"],
            note="Demo fixture: lead matched clinic ICP and expansion signal.",
        ),
        created_at=settled_trigger.ts + timedelta(minutes=4),
    )
    await _append_and_project(
        state,
        RunVerified(
            event_id="run_demo_settled:verified",
            seq=0,
            ts=settled_trigger.ts + timedelta(minutes=5),
            instance_id=instance.id,
            run_id="run_demo_settled",
            rungs_passed=["rules", "human"],
        ),
    )
    await _append_and_project(
        state,
        RunSettled(
            event_id="run_demo_settled:settled",
            seq=0,
            ts=settled_trigger.ts + timedelta(minutes=6),
            instance_id=instance.id,
            run_id="run_demo_settled",
            facts=[fact],
            billing_amount=250.0,
            trust_delta=1,
            watch_ids=["watch_demo_reply"],
        ),
    )

    parked_trigger = DeadlineTrigger(ts=now - timedelta(minutes=20), reason="draft outreach", entity_id="lead_nova")
    await _append_and_project(
        state,
        RunCreated(
            event_id="run_demo_parked:created",
            seq=0,
            ts=parked_trigger.ts,
            instance_id=instance.id,
            run_id="run_demo_parked",
            type_ref=instance.type_ref,
            trigger=parked_trigger,
        ),
    )
    await _append_and_project(
        state,
        RunHydrated(
            event_id="run_demo_parked:hydrated",
            seq=0,
            ts=parked_trigger.ts + timedelta(seconds=2),
            instance_id=instance.id,
            run_id="run_demo_parked",
            fact_count=1,
            thread_id=f"{instance.id}:lead_nova",
        ),
    )
    await _append_and_project(
        state,
        SyscallAttempted(
            event_id="run_demo_parked:syscall:draft_email",
            seq=0,
            ts=parked_trigger.ts + timedelta(minutes=1),
            instance_id=instance.id,
            run_id="run_demo_parked",
            syscall="draft_email",
            args={
                "to": "founder-review@agent-x.local",
                "subject": "Draft outreach: Nova Care Clinics",
                "body": (
                    "Draft only. Candidate: Nova Care Clinics. Evidence: hiring ops lead; "
                    "multi-location expansion."
                ),
                "sent": False,
            },
            ring_required="L2",
        ),
    )
    await _append_and_project(
        state,
        RunParked(
            event_id="run_demo_parked:parked",
            seq=0,
            ts=parked_trigger.ts + timedelta(minutes=2),
            instance_id=instance.id,
            run_id="run_demo_parked",
            reason="draft_email requires L2; instance currently runs at L1",
            awaiting="human_approval",
            required_ring="L2",
        ),
    )
    await _append_and_project(
        state,
        ManagerAction(
            event_id="inst_demo:manager:set_ring:L1",
            seq=0,
            ts=now - timedelta(minutes=10),
            instance_id=instance.id,
            actor="manager:seed",
            action="set_ring",
            detail={"ring": "L1"},
        ),
    )

    state.manual_tasks.enqueue(
        SyscallRequest(
            name="queue_manual_action",
            args={"action": "review_lead", "lead_id": "lead_nova", "reason": "Need owner context before outreach."},
            instance_id=instance.id,
            run_id="run_demo_parked",
            idempotency_key="manual-demo-review-lead",
            ring="L1",
            risk_class="reversible_write",
        ),
        source_adapter="queue_manual_action",
    )

    await state.store.upsert(
        c.EVAL_CASE,
        "eval_demo_synth",
        {
            "id": "eval_demo_synth",
            "type_ref": "lead-finder@0.1.0",
            "origin": "synthetic",
            "score": 0.74,
            "passed": True,
            "tags": ["indian_b2b_leads_v1"],
        },
    )


async def system_overview(state: DashboardState) -> dict[str, Any]:
    instances = await state.collection(c.MANDATE_INSTANCE)
    runs = await run_summaries(state)
    billing = await state.collection(c.BILLING_LINE)
    total = sum(_float(doc.get("amount")) for doc in billing)
    rings: Counter[str] = Counter()
    for instance in instances:
        ring = await _ring_for_instance(state, instance)
        rings[ring] += 1
    return {
        "backend": state.backend,
        "counts": {
            "instances": len(instances),
            "live_runs": sum(1 for run in runs if run["state"] in {"created", "running", "verifying"}),
            "parked_awaiting_approval": sum(1 for run in runs if run["state"] == "parked"),
            "settled": sum(1 for run in runs if run["state"] == "settled"),
            "manual_queue": len(state.manual_tasks.list_open()),
        },
        "rings": dict(rings),
        "pnl": {"total": total, "currency": "INR"},
        "recent_events": [event.model_dump(mode="json") for event in await state.journal_events(limit=12)],
    }


async def instance_rows(state: DashboardState) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for instance in await state.collection(c.MANDATE_INSTANCE):
        instance_id = str(instance.get("id", ""))
        inbox = await state.control.approval_inbox(instance_id=instance_id)
        resume = await state.get_doc(c.RESUME, instance_id)
        billing = await state.collection(c.BILLING_LINE, {"instance_id": instance_id})
        rows.append(
            {
                "instance": instance,
                "resume": resume,
                "approval_count": len(inbox.items),
                "billing_total": sum(_float(doc.get("amount")) for doc in billing),
                "latest_run": _latest_run(await run_summaries(state, instance_id=instance_id)),
            }
        )
    return rows


async def instance_detail(state: DashboardState, instance_id: str) -> dict[str, Any]:
    instance = await state.get_doc(c.MANDATE_INSTANCE, instance_id)
    if instance is None:
        return {"missing": True, "instance_id": instance_id}
    facts = await state.collection(c.HEAP_FACT, {"instance_id": instance_id})
    resume = await state.get_doc(c.RESUME, instance_id)
    threads = await state.collection(c.THREAD, {"instance_id": instance_id})
    billing = await state.collection(c.BILLING_LINE, {"instance_id": instance_id})
    approvals = await approval_cards(state, instance_id=instance_id)
    return {
        "instance": instance,
        "facts": facts,
        "resume": resume,
        "threads": threads,
        "runs": await run_summaries(state, instance_id=instance_id),
        "billing": {"lines": billing, "total": sum(_float(doc.get("amount")) for doc in billing), "currency": "INR"},
        "approvals": approvals,
        "journal_head": await state.journal.max_seq(instance_id),
    }


async def run_summaries(
    state: DashboardState,
    *,
    state_filter: RunState | None = None,
    instance_id: str | None = None,
) -> list[JsonObject]:
    events = await state.journal_events(instance_id=instance_id, limit=1000)
    by_run: dict[str, list[JournalEvent]] = {}
    for event in events:
        if event.run_id is not None:
            by_run.setdefault(event.run_id, []).append(event)
    summaries = [_summarize_run(run_id, run_events) for run_id, run_events in by_run.items()]
    summaries.sort(key=lambda run: str(run.get("updated_at", "")), reverse=True)
    if state_filter is not None:
        summaries = [run for run in summaries if run["state"] == state_filter]
    return summaries


async def run_detail(state: DashboardState, run_id: str) -> dict[str, Any]:
    events = await state.journal_events(run_id=run_id, limit=1000)
    if not events:
        return {"missing": True, "run_id": run_id}
    trace_docs = await state.collection(c.SYSCALL_TRACE, {"run_id": run_id})
    settlement = next((event for event in events if isinstance(event, RunSettled)), None)
    hydrated = next((event for event in events if isinstance(event, RunHydrated)), None)
    return {
        "run": _summarize_run(run_id, events),
        "timeline": [_timeline_event(event) for event in events],
        "hydration_snapshot": hydrated.model_dump(mode="json") if hydrated is not None else None,
        "claimed_facts": [fact.model_dump(mode="json") for fact in settlement.facts] if settlement else [],
        "settlement": settlement.model_dump(mode="json") if settlement is not None else None,
        "syscall_trace": trace_docs,
    }


async def approval_cards(state: DashboardState, *, instance_id: str | None = None) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    instances = [instance_id] if instance_id is not None else [
        str(instance.get("id")) for instance in await state.collection(c.MANDATE_INSTANCE) if instance.get("id")
    ]
    for current_instance_id in instances:
        inbox = await state.control.approval_inbox(instance_id=current_instance_id)
        for item in inbox.items:
            events = await state.journal.read_run(item.run_id)
            cards.append(
                {
                    **item.model_dump(mode="json"),
                    "instance_id": current_instance_id,
                    "drafted_effect": item.approval_card or _drafted_effect(events),
                    "timeline": [_timeline_event(event) for event in events],
                }
            )
    cards.sort(key=lambda card: _int(card.get("seq")), reverse=True)
    return cards


async def capability_rows(state: DashboardState) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    open_tasks = state.manual_tasks.list_open()
    for adapter in state.registry.adapters():
        health = await adapter.health_check()
        queue_volume = sum(
            1 for task in open_tasks if task.source_adapter == adapter.name or task.request_name == adapter.name
        )
        rows.append(
            {
                "name": adapter.name,
                "category": adapter.category,
                "maturity_level": adapter.maturity_level,
                "risk_class": adapter.risk_class,
                "required_ring": adapter.required_ring,
                "tenant_auth": adapter.tenant_auth,
                "is_terminal_fallback": adapter.is_terminal_fallback,
                "fixtures": [fixture.model_dump(mode="json") for fixture in adapter.fixtures],
                "health": health.model_dump(mode="json"),
                "queue_volume": queue_volume,
            }
        )
    return rows


def manual_queue(state: DashboardState) -> list[dict[str, Any]]:
    return [task.to_json() for task in state.manual_tasks.list_open()]


def _build_registry() -> tuple[Phase1SyscallRegistry, ManualTaskStore]:
    store = ManualTaskStore()
    providers = build_configured_research_providers()
    registry = Phase1SyscallRegistry(terminal_fallback=HumanTaskAdapter(store=store))
    registry.register(LeadResearchBatchAdapter(providers=providers))
    registry.register(ReadUrlAdapter(providers=providers))
    registry.register(DraftEmailAdapter())
    registry.register(QueueManualActionAdapter(store=store))
    registry.register(MarkOutcomeAdapter(store=store))
    return registry, store


async def _append_and_project(state: DashboardState, event: JournalEvent) -> JournalEvent:
    stamped = await state.journal.append(event)
    await state.projections.apply(stamped)
    return stamped


def _summarize_run(run_id: str, events: list[JournalEvent]) -> dict[str, Any]:
    events = sorted(events, key=lambda event: event.seq)
    created = next((event for event in events if isinstance(event, RunCreated)), None)
    parked = next((event for event in reversed(events) if isinstance(event, RunParked)), None)
    resolved = next((event for event in reversed(events) if isinstance(event, ApprovalResolved)), None)
    settled = next((event for event in reversed(events) if isinstance(event, RunSettled)), None)
    verified = next((event for event in reversed(events) if isinstance(event, RunVerified)), None)
    state: RunState = "running"
    if settled is not None:
        state = "settled"
    elif parked is not None and resolved is None:
        state = "parked"
    elif verified is not None:
        state = "verifying"
    elif created is not None:
        state = "running"
    latest = events[-1]
    return {
        "run_id": run_id,
        "instance_id": latest.instance_id,
        "type_ref": created.type_ref if created is not None else None,
        "state": state,
        "created_at": created.ts.isoformat() if created is not None else latest.ts.isoformat(),
        "updated_at": latest.ts.isoformat(),
        "event_count": len(events),
        "park": parked.model_dump(mode="json") if parked is not None and resolved is None else None,
        "settled": settled.model_dump(mode="json") if settled is not None else None,
    }


def _timeline_event(event: JournalEvent) -> dict[str, Any]:
    return {
        "seq": event.seq,
        "ts": event.ts.isoformat(),
        "kind": event.kind,
        "actor": event.actor,
        "run_id": event.run_id,
        "summary": _event_summary(event),
        "event": event.model_dump(mode="json"),
    }


def _event_summary(event: JournalEvent) -> str:
    if isinstance(event, RunCreated):
        return f"created from {event.trigger.kind}"
    if isinstance(event, RunHydrated):
        return f"hydrated {event.fact_count} facts"
    if isinstance(event, SyscallAttempted):
        return f"syscall intent: {event.syscall}"
    if isinstance(event, RunParked):
        return event.reason
    if isinstance(event, ApprovalResolved):
        return f"approval {event.decision}"
    if isinstance(event, RunVerified):
        return f"verified via {', '.join(event.rungs_passed) or 'rules'}"
    if isinstance(event, RunSettled):
        return f"settled {len(event.facts)} facts"
    if isinstance(event, ManagerAction):
        return f"manager action: {event.action}"
    return event.kind


def _drafted_effect(events: list[JournalEvent]) -> dict[str, Any] | None:
    for event in reversed(events):
        if isinstance(event, SyscallAttempted):
            return {"syscall": event.syscall, "args": event.args, "required_ring": event.ring_required}
    return None


async def _ring_for_instance(state: DashboardState, instance: dict[str, Any]) -> str:
    instance_id = instance.get("id")
    if isinstance(instance_id, str):
        resume = await state.get_doc(c.RESUME, instance_id)
        if resume is not None and isinstance(resume.get("ring"), str):
            return str(resume["ring"])
    ring = instance.get("ring")
    return ring if isinstance(ring, str) else "L0"


def _latest_run(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    return runs[0] if runs else None


def _float(value: object) -> float:
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _int(value: object) -> int:
    return value if isinstance(value, int) else 0


def _json_doc(doc: dict[str, object]) -> dict[str, Any]:
    value = _to_json_value(doc)
    return cast(dict[str, Any], value)


def _to_json_value(value: object) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_json_value(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)
