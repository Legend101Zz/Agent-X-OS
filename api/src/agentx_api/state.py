"""Dashboard state composes the lifespan-owned ``OperatorRuntime`` and exposes read-side projections.

The runtime owns every stateful kernel piece. ``state.py`` only:
- decides the backend (Mongo vs memory) based on settings + env;
- builds the OperatorRuntime once via ``build_runtime``;
- exposes typed read helpers that return ``dict`` payloads shaped for the dashboard;
- wires the long-lived ``SchedulerWorker`` into a background task on ``start()``.

This file is the *only* place the API state is constructed; FastAPI just calls ``create_state()``
and stores the result on ``app.state``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import agentx_db.collections as c
from agentx_contracts.config import get_settings
from agentx_contracts.enums import RunState
from agentx_contracts.journal import (
    JournalEvent,
    RunCreated,
    RunHydrated,
    RunSettled,
    RunVerified,
    SyscallAttempted,
)
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.mandate import MandateInstance
from agentx_contracts.memory import Fact, Provenance

# Re-export so the API endpoints can construct deadlines without an extra import.
from agentx_contracts.trigger import DeadlineTrigger  # noqa: F401
from agentx_db.setup import ensure_indexes

from .operator import OperatorRuntime, build_runtime

BackendKind = Literal["memory", "mongo"]


@dataclass
class DashboardState:
    """The lifespan-owned composition that FastAPI holds on ``app.state.dashboard``."""

    runtime: OperatorRuntime
    backend: BackendKind
    seed_demo: bool
    database: Any | None
    client: Any | None
    # Phase-1 test hook: when ``None`` the runtime reads env (RUN_LIVE_EMAIL=1 + RESEND_API_KEY) and
    # only registers a SendEmailAdapter when both are present; when a transport is supplied the
    # runtime uses it directly (test fake) and registers the SendEmailAdapter unconditionally. In
    # either case, when the runtime has zero channel_binding instances, no SendEmailAdapter is
    # registered and the human_task tail takes over (invariant #5).
    send_email_transport: Any | None = None

    # ---- convenience accessors so endpoint code is short -------------------------------
    @property
    def journal(self) -> Any:
        return self.runtime.journal

    @property
    def store(self) -> Any:
        return self.runtime.projection_store

    @property
    def projections(self) -> Any:
        return self.runtime.projections

    @property
    def control(self) -> Any:
        return self.runtime.control

    @property
    def registry(self) -> Any:
        return self.runtime.registry

    @property
    def manual_tasks(self) -> Any:
        return self.runtime.manual_tasks

    # ---- lifecycle ---------------------------------------------------------------------
    async def start(self) -> None:
        if self.database is not None:
            await ensure_indexes(self.database)
        if self.seed_demo:
            await _maybe_seed_demo(self)

    async def close(self) -> None:
        await self.runtime.close()

    # ---- generic store helpers ---------------------------------------------------------
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
        events: list[JournalEvent] = []
        if run_id is not None:
            events = await self.journal.read_run(run_id)
        elif instance_id is not None:
            events = await self.journal.read_instance(instance_id)
        else:
            instances = await self.collection(c.MANDATE_INSTANCE)
            for instance in instances:
                raw_id = instance.get("id")
                if isinstance(raw_id, str):
                    events.extend(await self.journal.read_instance(raw_id))
            # Normalise tz-awareness before sorting: BSON datetimes from Mongo are UTC-aware, but
            # in-memory JournalEvent.ts values created via datetime.now() are naive. Mixing the two
            # in a sort key raises `TypeError: can't compare offset-naive and offset-aware datetimes`
            # (real-world bug — surfaced the moment the API went live with mixed sources).
            def _sort_key(event: JournalEvent) -> tuple[Any, str, int]:
                ts = event.ts
                if isinstance(ts, datetime) and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                return (ts, event.instance_id, event.seq)

            events.sort(key=_sort_key)
        if kind is not None:
            events = [event for event in events if event.kind == kind]
        return events[-limit:]

def create_state(
    *,
    use_mongo: bool | None,
    seed_demo: bool,
    send_email_transport: Any | None = None,
) -> DashboardState:
    """Build a DashboardState from settings + optional env flag.

    ``use_mongo=False`` forces memory even when ``MONGODB_URI`` is set (used by tests).
    ``use_mongo=None`` honours ``MONGODB_URI`` presence.
    """
    settings = get_settings()
    uri = settings.mongodb_uri.get_secret_value() if settings.mongodb_uri is not None else ""
    should_use_mongo = bool(uri.strip()) if use_mongo is None else use_mongo
    database: Any | None = None
    client: Any | None = None
    if should_use_mongo:
        from pymongo import AsyncMongoClient

        client = AsyncMongoClient(uri)
        database = client[settings.mongodb_db_name]
    runtime = build_runtime(
        settings=settings,
        database=database,
        client=client,
        send_email_transport=send_email_transport,
    )
    return DashboardState(
        runtime=runtime,
        backend="mongo" if should_use_mongo else "memory",
        seed_demo=seed_demo,
        database=database,
        client=client,
        send_email_transport=send_email_transport,
    )


# ---- Optional demo seed (memory mode only) ---------------------------------------------


async def _maybe_seed_demo(state: DashboardState) -> None:
    """Seed the demo instance + one parked approval card when memory mode + seed_demo."""
    if state.backend != "memory":
        return
    existing = await state.collection(c.MANDATE_INSTANCE)
    if existing:
        return
    now = datetime(2026, 6, 18, 9, 30, tzinfo=UTC)
    from agentx_mandate.library.lead_finder import build_lead_finder_type

    mandate = build_lead_finder_type()
    await state.control.register_mandate_type(mandate)
    instance = MandateInstance(
        id="inst_demo",
        type_ref="lead-finder@0.1.0",
        customer_id="Orbit Dental Co",
        ring="L1",
        heap_region_id="heap_demo",
    )
    await state.control.instantiate_mandate(instance)

    settled_trigger = DeadlineTrigger(
        ts=now - _td(hours=6), reason="morning lead sweep", entity_id="lead_orbit"
    )
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
            ts=settled_trigger.ts + _td(seconds=3),
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
        created_at=settled_trigger.ts + _td(minutes=4),
    )
    await _append_and_project(
        state,
        RunVerified(
            event_id="run_demo_settled:verified",
            seq=0,
            ts=settled_trigger.ts + _td(minutes=5),
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
            ts=settled_trigger.ts + _td(minutes=6),
            instance_id=instance.id,
            run_id="run_demo_settled",
            facts=[fact],
            billing_amount=250.0,
            trust_delta=1,
            watch_ids=["watch_demo_reply"],
        ),
    )

    parked_trigger = DeadlineTrigger(
        ts=now - _td(minutes=20), reason="draft outreach", entity_id="lead_nova"
    )
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
            ts=parked_trigger.ts + _td(seconds=2),
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
            ts=parked_trigger.ts + _td(minutes=1),
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
    from agentx_contracts.journal import ManagerAction, RunParked

    await _append_and_project(
        state,
        RunParked(
            event_id="run_demo_parked:parked",
            seq=0,
            ts=parked_trigger.ts + _td(minutes=2),
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
            ts=now - _td(minutes=10),
            instance_id=instance.id,
            actor="manager:seed",
            action="set_ring",
            detail={"ring": "L1"},
        ),
    )

    # Seed one open manual task to demonstrate the durable queue endpoint.
    from agentx_contracts import SyscallRequest as _SyscallRequest

    state.manual_tasks.enqueue(
        _SyscallRequest(
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


def _td(**kwargs: int) -> Any:
    from datetime import timedelta

    return timedelta(**kwargs)


async def _append_and_project(state: DashboardState, event: JournalEvent) -> JournalEvent:
    stamped: JournalEvent = await state.journal.append(event)
    await state.projections.apply(stamped)
    return stamped


# ---- Read-side projections -------------------------------------------------------------


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


async def instance_memory(state: DashboardState, instance_id: str) -> dict[str, Any]:
    """Read-side projection for the Inspector's Memory tab (BLUEPRINT §8 row 1).

    Returns the instance's committed heap facts in a UI-ready envelope:

        {"instance_id": "...", "facts": [{"id": "...", "subject": "...", "predicate": "...",
                                           "object": "...", "confidence": 0.0..1.0,
                                           "status": "probation"|"promoted"|"retired",
                                           "source": "agent-inferred"|...,
                                           "provenance": {"run_id": "...", "evidence": [...], "note": ...},
                                           "created_at": "ISO-8601", "updated_at": "ISO-8601 | None"},
                                          ...]}

    Status semantics (per ``agentx_contracts.enums.FactStatus``):
      - ``probation``: just settled; not yet verified by reality.
      - ``promoted``: verified by reality (the deferred-settlement watch fired confirming it).
        This is what the spec calls "verified".
      - ``retired``: reality contradicted the fact; it's been removed from the working set.

    Returns the *missing* envelope (``{"missing": True, "instance_id": ..., "facts": []}``)
    when:
      - the instance does not exist at all, OR
      - the instance exists but the projection store has no ``heap_fact`` docs yet.

    The route layer translates this envelope into HTTP 404 — the reader itself never raises
    for these conditions, so a partial system (instance present, no settled runs yet) can
    render an EmptyState instead of a 500.
    """
    instance = await state.get_doc(c.MANDATE_INSTANCE, instance_id)
    raw_facts = await state.collection(c.HEAP_FACT, {"instance_id": instance_id})
    if instance is None and not raw_facts:
        return {"missing": True, "instance_id": instance_id, "facts": []}
    if not raw_facts:
        return {"missing": True, "instance_id": instance_id, "facts": []}
    facts = [_memory_fact(doc) for doc in raw_facts]
    return {"instance_id": instance_id, "facts": facts}


def _memory_fact(doc: dict[str, Any]) -> dict[str, Any]:
    """Project one ``heap_fact`` doc into the UI-ready Memory tab shape.

    The contract ``Fact`` model already serializes to a stable JSON shape via
    ``HeapProjector`` (``fact.model_dump(mode="json")``), so this projection is mostly a
    pass-through with one deliberate omission: ``decay_at`` is internal GC bookkeeping and
    leaks implementation details into the public API, so it is dropped here. ``instance_id``
    is also dropped because the route is per-instance — repeating it on every fact is noise
    on the wire and in the Memory tab UI.
    """
    provenance_raw = doc.get("provenance") or {}
    provenance = {
        "run_id": provenance_raw.get("run_id", ""),
        "evidence": list(provenance_raw.get("evidence") or []),
    }
    if provenance_raw.get("note") is not None:
        provenance["note"] = provenance_raw["note"]
    return {
        "id": doc.get("id", ""),
        "subject": doc.get("subject", ""),
        "predicate": doc.get("predicate", ""),
        "object": doc.get("object", ""),
        "confidence": _float(doc.get("confidence"), 0.0),
        "status": doc.get("status", "probation"),
        "source": doc.get("source", "agent-inferred"),
        "provenance": provenance,
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


async def scheduler_work_list(
    state: DashboardState,
    *,
    status: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Read-side projection for the Kernel view's Scheduler tab (BLUEPRINT §8 row 3).

    Returns the scheduler store's current work rows in a UI-ready envelope:

        {"work": [{"work_id": "...", "kind": "trigger"|"approval",
                   "status": "pending"|"claimed"|"completed"|"failed",
                   "attempts": int, "available_at": "ISO-8601",
                   "run_id": "...|null", "instance_id": "...|null", "type_ref": "...|null",
                   "updated_at": "ISO-8601"},
                  ...],
         "count": int}

    The reader is a thin projection over ``SchedulerStore.list_statuses`` — it doesn't
    mutate the queue and doesn't touch contracts. ``status`` is an optional filter on
    the row's status field (``pending``, ``claimed``, ``completed``, ``failed``); an
    invalid value is rejected here, before the store ever sees it, so a typo returns a
    clean 400 instead of a silent empty list. ``limit`` caps the page size; the route
    layer enforces the FastAPI Query bounds (1..1000) and we clamp again here as a
    safety net.

    An empty store returns ``{"work": [], "count": 0}`` — never raises — so the Kernel
    view can render an EmptyState on a cold install.
    """
    allowed_statuses = {"pending", "claimed", "completed", "failed"}
    if status is not None and status not in allowed_statuses:
        # Surface as a ValueError; the route layer translates to HTTP 400.
        raise ValueError(
            f"invalid status filter: {status!r}; must be one of {sorted(allowed_statuses)}"
        )
    safe_limit = max(1, min(int(limit), 1000))
    rows = await state.runtime.scheduler_store.list_statuses(
        status=status, limit=safe_limit
    )
    return {
        "work": [row.model_dump(mode="json") for row in rows],
        "count": len(rows),
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
    """First-class /approvals view: parked approval cards, NOT manual-queue tasks.

    The dashboard now uses ``approvalCards`` separately from ``manualQueue`` so the UI never mixes
    "needs manager approval" with "the human-task adapter queued this because no API exists yet".
    """
    cards: list[dict[str, Any]] = []
    instances = (
        [instance_id]
        if instance_id is not None
        else [
            str(instance.get("id"))
            for instance in await state.collection(c.MANDATE_INSTANCE)
            if instance.get("id")
        ]
    )
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


# ---- helpers ----------------------------------------------------------------------------


def _ring_for_instance_sync(resume_doc: dict[str, Any] | None, default: str) -> str:
    if resume_doc is not None and isinstance(resume_doc.get("ring"), str):
        return str(resume_doc["ring"])
    return default


async def _ring_for_instance(state: DashboardState, instance_doc: dict[str, Any]) -> str:
    instance_id = str(instance_doc.get("id", ""))
    if not instance_id:
        return "L0"
    resume_doc = await state.get_doc(c.RESUME, instance_id)
    return _ring_for_instance_sync(resume_doc, str(instance_doc.get("ring", "L0")))


def _latest_run(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return rows[0] if rows else None


def _drafted_effect(events: list[JournalEvent]) -> JsonObject:
    """Recover the drafted effect args from a journal sequence if the approval card is missing."""
    for event in reversed(events):
        if isinstance(event, SyscallAttempted):
            return {
                "syscall": event.syscall,
                "args": event.args,
                "idempotency_key": event.event_id.removesuffix(":attempt"),
            }
    return {}


def _summarize_run(run_id: str, events: list[JournalEvent]) -> JsonObject:
    state_value = "created"
    type_ref = ""
    instance_id = ""
    trigger_kind = ""
    last_ts = datetime.fromtimestamp(0, tz=UTC)
    settled: RunSettled | None = None
    parked_reason: str | None = None
    required_ring: str | None = None
    for event in events:
        # Normalise naive datetimes to UTC-aware so we don't crash on BSON-vs-memory mixes.
        ts = event.ts
        if isinstance(ts, datetime) and ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        last_ts = max(last_ts, ts)
        instance_id = event.instance_id or instance_id
        if isinstance(event, RunCreated):
            state_value = "running"
            type_ref = event.type_ref
            trigger_kind = event.trigger.kind
        elif isinstance(event, RunSettled):
            state_value = "settled"
            settled = event
        elif event.kind == "run_parked":
            state_value = "parked"
            parked_reason = getattr(event, "reason", None)
            required_ring = getattr(event, "required_ring", None)
        elif event.kind == "approval_resolved":
            state_value = "approved_pending_resume"
    return {
        "run_id": run_id,
        "instance_id": instance_id,
        "type_ref": type_ref,
        "trigger_kind": trigger_kind,
        "state": state_value,
        "park_reason": parked_reason,
        "required_ring": required_ring,
        "event_count": len(events),
        "created_at": events[0].ts.isoformat() if events else None,
        "updated_at": last_ts.isoformat(),
        "settled": settled.model_dump(mode="json") if settled else None,
    }


def _timeline_event(event: JournalEvent) -> dict[str, Any]:
    summary = _event_summary(event)
    payload = event.model_dump(mode="json")
    return {
        "kind": event.kind,
        "ts": event.ts.isoformat(),
        "actor": event.actor,
        "summary": summary,
        "event": payload,
    }


def _event_summary(event: JournalEvent) -> str:
    kind = event.kind
    if kind == "manager_action":
        action = getattr(event, "action", "")
        detail = getattr(event, "detail", {}) or {}
        return f"manager: {action} {detail}"
    if kind == "approval_resolved":
        decision = getattr(event, "decision", "")
        return f"approval: {decision}"
    if kind == "run_parked":
        reason = getattr(event, "reason", "")
        return f"parked: {reason}"
    if kind == "syscall_attempted":
        return f"syscall: {getattr(event, 'syscall', '')}"
    if kind == "syscall_settled":
        return f"settled: {getattr(event, 'syscall', '')} status={getattr(event, 'status', '')}"
    return kind


def _int(value: Any, default: int = 0) -> int:
    return value if isinstance(value, int) else default


def _float(value: Any, default: float = 0.0) -> float:
    return value if isinstance(value, (int, float)) else default


def _json_doc(doc: dict[str, Any]) -> dict[str, Any]:
    clean = dict(doc)
    clean.pop("_id", None)
    return clean


__all__ = [
    "BackendKind",
    "DashboardState",
    "approval_cards",
    "capability_rows",
    "create_state",
    "instance_detail",
    "instance_memory",
    "instance_rows",
    "manual_queue",
    "run_detail",
    "run_summaries",
    "scheduler_work_list",
    "system_overview",
]
