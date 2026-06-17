"""Phase-1 syscall adapters.

Adapters are actuators behind the kernel gateway. They receive intent-shaped
``SyscallRequest`` objects and an optional credential injected by the gateway;
they never make autonomous decisions outside that request.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import import_module
from typing import Any, Protocol, cast

from agentx_contracts import (
    GatewayContext,
    Health,
    JsonObject,
    JsonSchema,
    MaturityLevel,
    Ring,
    SyscallRequest,
    SyscallResult,
    SyscallTestCase,
    TenantAuth,
    VerifyOutcome,
)
from agentx_contracts.security import Credential

_OPEN_OBJECT_SCHEMA: JsonSchema = {"type": "object", "additionalProperties": True}


@dataclass(frozen=True)
class ResearchLead:
    """Normalized lead record returned by research providers."""

    id: str
    name: str
    url: str
    evidence: list[str]
    fit_score: float
    metadata: JsonObject = field(default_factory=dict)

    def to_json(self) -> JsonObject:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "evidence": list(self.evidence),
            "fit_score": self.fit_score,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ResearchPage:
    """Normalized page content returned by read-side providers."""

    url: str
    title: str | None
    markdown: str
    evidence: list[str]
    metadata: JsonObject = field(default_factory=dict)

    def to_json(self) -> JsonObject:
        return {
            "url": self.url,
            "title": self.title,
            "markdown": self.markdown,
            "evidence": list(self.evidence),
            "metadata": dict(self.metadata),
        }


class ResearchProvider(Protocol):
    """Small provider seam behind the Agent-X Adapter interface."""

    name: str

    async def health_check(self) -> bool:
        """Return whether the provider is usable now."""
        ...

    async def search_leads(self, criteria: Mapping[str, Any], count: int) -> list[ResearchLead]:
        """Return normalized lead records for a lead-research intent."""
        ...

    async def read_url(self, url: str) -> ResearchPage:
        """Return normalized page content for a known URL."""
        ...


@dataclass
class ManualTask:
    """One manual-projection task queued for the operator surface."""

    id: str
    request_name: str
    args: JsonObject
    instance_id: str
    run_id: str
    idempotency_key: str
    source_adapter: str
    created_at: datetime
    outcome: str | None = None
    outcome_detail: JsonObject = field(default_factory=dict)

    def to_json(self) -> JsonObject:
        return {
            "id": self.id,
            "request_name": self.request_name,
            "args": dict(self.args),
            "instance_id": self.instance_id,
            "run_id": self.run_id,
            "idempotency_key": self.idempotency_key,
            "source_adapter": self.source_adapter,
            "created_at": self.created_at.isoformat(),
            "outcome": self.outcome,
            "outcome_detail": dict(self.outcome_detail),
        }


class ManualTaskStore:
    """In-memory queue backing the Phase-1 manual-projection path.

    The kernel can replace this with a DB-backed queue later without changing the
    syscall contract. For Phase 1 it gives adapters a deterministic fixtureable
    queue and keeps every unsupported intent fulfillable by a human.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, ManualTask] = {}
        self._order: list[str] = []

    def enqueue(self, req: SyscallRequest, *, source_adapter: str) -> ManualTask:
        existing = self._find_by_idempotency(req.idempotency_key)
        if existing is not None:
            return existing

        task_id = f"manual_{len(self._order) + 1}"
        task = ManualTask(
            id=task_id,
            request_name=req.name,
            args=dict(req.args),
            instance_id=req.instance_id,
            run_id=req.run_id,
            idempotency_key=req.idempotency_key,
            source_adapter=source_adapter,
            created_at=datetime.now(UTC),
        )
        self._tasks[task.id] = task
        self._order.append(task.id)
        return task

    def mark_outcome(self, task_id: str, outcome: str, detail: JsonObject | None = None) -> ManualTask:
        task = self._tasks[task_id]
        task.outcome = outcome
        task.outcome_detail = dict(detail or {})
        return task

    def get(self, task_id: str) -> ManualTask:
        return self._tasks[task_id]

    def list_open(self) -> list[ManualTask]:
        return [self._tasks[task_id] for task_id in self._order if self._tasks[task_id].outcome is None]

    def _find_by_idempotency(self, idempotency_key: str) -> ManualTask | None:
        for task in self._tasks.values():
            if task.idempotency_key == idempotency_key:
                return task
        return None


class _AdapterBase:
    name: str
    category: str
    maturity_level: MaturityLevel
    risk_class: str
    required_ring: Ring
    tenant_auth: TenantAuth
    input_schema: JsonSchema
    output_schema: JsonSchema
    fixtures: list[SyscallTestCase]
    is_terminal_fallback: bool = False

    def __init__(
        self,
        *,
        name: str,
        category: str,
        maturity_level: MaturityLevel,
        risk_class: str,
        required_ring: Ring,
        tenant_auth: TenantAuth,
        input_schema: JsonSchema | None = None,
        output_schema: JsonSchema | None = None,
        fixtures: list[SyscallTestCase] | None = None,
    ) -> None:
        self.name = name
        self.category = category
        self.maturity_level = maturity_level
        self.risk_class = risk_class
        self.required_ring = required_ring
        self.tenant_auth = tenant_auth
        self.input_schema = dict(input_schema or _OPEN_OBJECT_SCHEMA)
        self.output_schema = dict(output_schema or _OPEN_OBJECT_SCHEMA)
        self.fixtures = list(fixtures or [])

    def can_handle(self, req: SyscallRequest, ctx: GatewayContext) -> bool:
        return req.name == self.name

    async def dry_run(self, req: SyscallRequest) -> SyscallResult:
        return SyscallResult(
            status="ok",
            output={"dry_run": True, "intent": req.name},
            idempotency_key=req.idempotency_key,
            fulfilled_by=self.name,
            maturity_used=self.maturity_level,
        )

    async def verify(self, result: SyscallResult) -> VerifyOutcome:
        return VerifyOutcome(
            ok=result.status in {"ok", "queued_manual"},
            reason=result.error or "",
            checks=[f"{self.name}:status:{result.status}"],
        )

    async def health_check(self) -> Health:
        return Health(status="ok", detail=f"{self.name} ready", checked_at=datetime.now(UTC))


class LeadResearchBatchAdapter(_AdapterBase):
    """Batch lead research through Exa/Firecrawl-style read providers."""

    def __init__(self, *, providers: Sequence[ResearchProvider] | None = None) -> None:
        self._providers = list(providers or [])
        super().__init__(
            name="lead_research_batch",
            category="research",
            maturity_level=3,
            risk_class="read",
            required_ring="L0",
            tenant_auth="api_key",
            fixtures=[
                SyscallTestCase(
                    name="lead_research_batch_smoke",
                    input={"criteria": {"segment": "dental clinics", "region": "Bengaluru"}, "count": 3},
                    expect_status="ok",
                    expect_output_contains={"provider": "configured"},
                )
            ],
        )

    def can_handle(self, req: SyscallRequest, ctx: GatewayContext) -> bool:
        return super().can_handle(req, ctx) and bool(self._providers)

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        if not self._providers:
            return _error_result(req, self.name, self.maturity_level, "no research provider configured")
        criteria = _mapping_arg(req.args, "criteria", default={})
        count = max(1, min(_int_arg(req.args, "count", default=10), 30))
        provider = self._providers[0]
        leads = await provider.search_leads(criteria, count)
        return SyscallResult(
            status="ok",
            output={
                "provider": provider.name,
                "credential_ref": cred.ref if cred is not None else None,
                "leads": [lead.to_json() for lead in leads],
            },
            idempotency_key=req.idempotency_key,
            fulfilled_by=self.name,
            maturity_used=self.maturity_level,
        )

    async def health_check(self) -> Health:
        if not self._providers:
            return Health(
                status="degraded",
                detail="no Exa or Firecrawl provider configured; registry will fall back to human_task",
                checked_at=datetime.now(UTC),
            )
        healthy: list[str] = []
        for provider in self._providers:
            if await provider.health_check():
                healthy.append(provider.name)
        if healthy:
            return Health(
                status="ok",
                detail=f"research providers ready: {', '.join(healthy)}",
                checked_at=datetime.now(UTC),
            )
        return Health(
            status="down",
            detail="configured research providers failed health checks",
            checked_at=datetime.now(UTC),
        )


class ReadUrlAdapter(_AdapterBase):
    """Read a known URL through the configured read providers."""

    def __init__(self, *, providers: Sequence[ResearchProvider] | None = None) -> None:
        self._providers = list(providers or [])
        super().__init__(
            name="read_url",
            category="research",
            maturity_level=3,
            risk_class="read",
            required_ring="L0",
            tenant_auth="api_key",
            fixtures=[
                SyscallTestCase(
                    name="read_url_smoke",
                    input={"url": "https://example.com"},
                    expect_status="ok",
                    expect_output_contains={"url": "https://example.com"},
                )
            ],
        )

    def can_handle(self, req: SyscallRequest, ctx: GatewayContext) -> bool:
        return super().can_handle(req, ctx) and bool(self._providers)

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        if not self._providers:
            return _error_result(req, self.name, self.maturity_level, "no read provider configured")
        url = _str_arg(req.args, "url")
        provider = self._providers[0]
        page = await provider.read_url(url)
        return SyscallResult(
            status="ok",
            output={
                "provider": provider.name,
                "credential_ref": cred.ref if cred is not None else None,
                **page.to_json(),
            },
            idempotency_key=req.idempotency_key,
            fulfilled_by=self.name,
            maturity_used=self.maturity_level,
        )

    async def health_check(self) -> Health:
        if not self._providers:
            return Health(
                status="degraded",
                detail="no Exa or Firecrawl provider configured; registry will fall back to human_task",
                checked_at=datetime.now(UTC),
            )
        healthy = [provider.name for provider in self._providers if await provider.health_check()]
        if healthy:
            return Health(
                status="ok",
                detail=f"read providers ready: {', '.join(healthy)}",
                checked_at=datetime.now(UTC),
            )
        return Health(
            status="down",
            detail="configured read providers failed health checks",
            checked_at=datetime.now(UTC),
        )


class DraftEmailAdapter(_AdapterBase):
    """Create an email draft only. It never sends mail in Phase 1."""

    def __init__(self) -> None:
        super().__init__(
            name="draft_email",
            category="communication",
            maturity_level=1,
            risk_class="external_message",
            required_ring="L1",
            tenant_auth="manual",
            fixtures=[
                SyscallTestCase(
                    name="draft_email_smoke",
                    input={"to": "owner@example.com", "subject": "Lead", "body": "Draft copy."},
                    expect_status="ok",
                    expect_output_contains={"mode": "draft", "sent": False},
                )
            ],
        )

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        to = _str_arg(req.args, "to")
        subject = _str_arg(req.args, "subject")
        body = _str_arg(req.args, "body")
        draft_id = f"draft_{req.idempotency_key}"
        return SyscallResult(
            status="ok",
            output={
                "draft_id": draft_id,
                "to": to,
                "subject": subject,
                "body": body,
                "mode": "draft",
                "sent": False,
                "credential_ref": cred.ref if cred is not None else None,
            },
            idempotency_key=req.idempotency_key,
            fulfilled_by=self.name,
            maturity_used=self.maturity_level,
        )


class QueueManualActionAdapter(_AdapterBase):
    """Explicit manual-projection syscall."""

    def __init__(self, *, store: ManualTaskStore) -> None:
        self._store = store
        super().__init__(
            name="queue_manual_action",
            category="manual",
            maturity_level=0,
            risk_class="reversible_write",
            required_ring="L0",
            tenant_auth="manual",
            fixtures=[
                SyscallTestCase(
                    name="queue_manual_action_smoke",
                    input={"action": "review_lead", "lead_id": "lead_1"},
                    expect_status="queued_manual",
                    expect_output_contains={"queue": "manual_projection"},
                )
            ],
        )

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        task = self._store.enqueue(req, source_adapter=self.name)
        return _manual_result(req=req, task=task, fulfilled_by=self.name)


class MarkOutcomeAdapter(_AdapterBase):
    """Record the operator/reality outcome for a manual task."""

    def __init__(self, *, store: ManualTaskStore) -> None:
        self._store = store
        super().__init__(
            name="mark_outcome",
            category="outcome",
            maturity_level=0,
            risk_class="read",
            required_ring="L0",
            tenant_auth="manual",
            fixtures=[
                SyscallTestCase(
                    name="mark_outcome_smoke",
                    input={"task_id": "manual_1", "outcome": "booked"},
                    expect_status="ok",
                    expect_output_contains={"outcome": "booked"},
                )
            ],
        )

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        task_id = _str_arg(req.args, "task_id")
        outcome = _str_arg(req.args, "outcome")
        detail = _mapping_arg(req.args, "detail", default={})
        try:
            task = self._store.mark_outcome(task_id, outcome, dict(detail))
        except KeyError:
            return _error_result(req, self.name, self.maturity_level, f"manual task not found: {task_id}")
        return SyscallResult(
            status="ok",
            output={"task_id": task.id, "outcome": task.outcome, "task": task.to_json()},
            idempotency_key=req.idempotency_key,
            fulfilled_by=self.name,
            maturity_used=self.maturity_level,
        )


class HumanTaskAdapter(_AdapterBase):
    """Terminal fallback for every ladder."""

    is_terminal_fallback = True

    def __init__(self, *, store: ManualTaskStore | None = None) -> None:
        self._store = store or ManualTaskStore()
        super().__init__(
            name="human_task",
            category="manual",
            maturity_level=0,
            risk_class="reversible_write",
            required_ring="L0",
            tenant_auth="manual",
            fixtures=[
                SyscallTestCase(
                    name="human_task_tail_smoke",
                    input={"intent": "unsupported_phase1_intent"},
                    expect_status="queued_manual",
                    expect_output_contains={"queue": "manual_projection"},
                )
            ],
        )
        self.is_terminal_fallback = True

    def can_handle(self, req: SyscallRequest, ctx: GatewayContext) -> bool:
        return True

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        task = self._store.enqueue(req, source_adapter=self.name)
        return _manual_result(req=req, task=task, fulfilled_by=self.name)

    async def dry_run(self, req: SyscallRequest) -> SyscallResult:
        task = self._store.enqueue(req, source_adapter=self.name)
        return _manual_result(req=req, task=task, fulfilled_by=self.name)


class ExaResearchProvider:
    """Thin Exa SDK wrapper.

    Current Exa Python docs recommend ``Exa.search(..., type="auto",
    contents={"highlights": True})`` for first integrations and
    ``get_contents`` for known URLs.
    """

    name = "exa"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def health_check(self) -> bool:
        return bool(self._api_key)

    async def search_leads(self, criteria: Mapping[str, Any], count: int) -> list[ResearchLead]:
        exa_module = import_module("exa_py")
        client_cls = exa_module.Exa
        client = client_cls(api_key=self._api_key)
        query = _criteria_to_query(criteria)
        response = client.search(query, type="auto", num_results=count, contents={"highlights": True})
        return _parse_search_results(response, provider=self.name, count=count)

    async def read_url(self, url: str) -> ResearchPage:
        exa_module = import_module("exa_py")
        client_cls = exa_module.Exa
        client = client_cls(api_key=self._api_key)
        response = client.get_contents([url], text=True, highlights=True)
        return _parse_page(response, url=url, provider=self.name)


class FirecrawlResearchProvider:
    """Thin Firecrawl SDK wrapper.

    Current Firecrawl Python docs use ``Firecrawl.search(query, limit=...)``
    and ``Firecrawl.scrape(url)``.
    """

    name = "firecrawl"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def health_check(self) -> bool:
        return bool(self._api_key)

    async def search_leads(self, criteria: Mapping[str, Any], count: int) -> list[ResearchLead]:
        firecrawl_module = import_module("firecrawl")
        client_cls = firecrawl_module.Firecrawl
        client = client_cls(api_key=self._api_key)
        response = client.search(_criteria_to_query(criteria), limit=count)
        return _parse_search_results(response, provider=self.name, count=count)

    async def read_url(self, url: str) -> ResearchPage:
        firecrawl_module = import_module("firecrawl")
        client_cls = firecrawl_module.Firecrawl
        client = client_cls(api_key=self._api_key)
        response = client.scrape(url)
        return _parse_page(response, url=url, provider=self.name)


def build_configured_research_providers() -> list[ResearchProvider]:
    """Build live provider wrappers from settings without importing provider SDKs at module import."""

    from agentx_contracts.config import get_settings

    settings = get_settings()
    providers: list[ResearchProvider] = []
    exa_key = settings.exa_api_key.get_secret_value() if settings.exa_api_key is not None else ""
    firecrawl_key = (
        settings.firecrawl_api_key.get_secret_value() if settings.firecrawl_api_key is not None else ""
    )
    if exa_key:
        providers.append(ExaResearchProvider(exa_key))
    if firecrawl_key:
        providers.append(FirecrawlResearchProvider(firecrawl_key))
    return providers


def _manual_result(*, req: SyscallRequest, task: ManualTask, fulfilled_by: str) -> SyscallResult:
    return SyscallResult(
        status="queued_manual",
        output={"queue": "manual_projection", "task_id": task.id, "task": task.to_json()},
        idempotency_key=req.idempotency_key,
        fulfilled_by=fulfilled_by,
        maturity_used=0,
    )


def _error_result(req: SyscallRequest, fulfilled_by: str, maturity: MaturityLevel, error: str) -> SyscallResult:
    return SyscallResult(
        status="error",
        output={},
        idempotency_key=req.idempotency_key,
        fulfilled_by=fulfilled_by,
        maturity_used=maturity,
        error=error,
    )


def _str_arg(args: Mapping[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing string arg: {key}")
    return value


def _int_arg(args: Mapping[str, Any], key: str, *, default: int) -> int:
    value = args.get(key, default)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return default


def _mapping_arg(args: Mapping[str, Any], key: str, *, default: Mapping[str, Any]) -> Mapping[str, Any]:
    value = args.get(key, default)
    if isinstance(value, Mapping):
        return value
    return default


def _criteria_to_query(criteria: Mapping[str, Any]) -> str:
    if not criteria:
        return "qualified B2B leads with evidence"
    parts = [f"{key}: {value}" for key, value in sorted(criteria.items())]
    return "Find qualified leads with evidence. " + "; ".join(parts)


def _parse_search_results(response: object, *, provider: str, count: int) -> list[ResearchLead]:
    raw_results = _raw_results(response)
    leads: list[ResearchLead] = []
    for idx, item in enumerate(raw_results[:count], start=1):
        mapping = _to_mapping(item)
        title = str(mapping.get("title") or mapping.get("name") or f"Lead {idx}")
        url = str(mapping.get("url") or mapping.get("link") or "")
        lead_id = str(mapping.get("id") or f"{provider}_{idx}")
        highlights = _string_list(mapping.get("highlights"))
        snippet = str(mapping.get("snippet") or mapping.get("description") or "")
        evidence = highlights or ([snippet] if snippet else [f"{provider} result {idx}"])
        leads.append(
            ResearchLead(
                id=lead_id,
                name=title,
                url=url,
                evidence=evidence,
                fit_score=0.75,
                metadata={"provider": provider},
            )
        )
    return leads


def _parse_page(response: object, *, url: str, provider: str) -> ResearchPage:
    mapping = _first_mapping(response)
    markdown = str(mapping.get("markdown") or mapping.get("text") or mapping.get("content") or "")
    title = mapping.get("title")
    metadata = _to_mapping(mapping.get("metadata"))
    metadata_json = cast(JsonObject, dict(metadata))
    return ResearchPage(
        url=str(mapping.get("url") or url),
        title=str(title) if title is not None else None,
        markdown=markdown,
        evidence=[markdown[:240]] if markdown else [f"{provider} read_url completed"],
        metadata={"provider": provider, **metadata_json},
    )


def _raw_results(response: object) -> list[object]:
    mapping = _to_mapping(response)
    for key in ("results", "web", "data"):
        value = mapping.get(key)
        if isinstance(value, Sequence) and not isinstance(value, str):
            return list(value)
    if isinstance(response, Sequence) and not isinstance(response, str):
        return list(response)
    return []


def _first_mapping(response: object) -> Mapping[str, Any]:
    mapping = _to_mapping(response)
    if mapping:
        results = _raw_results(response)
        if results:
            return _to_mapping(results[0])
        return mapping
    return {}


def _to_mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return cast(Mapping[str, Any], value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return cast(Mapping[str, Any], dumped)
    attrs: dict[str, Any] = {}
    for key in ("id", "title", "name", "url", "link", "highlights", "snippet", "markdown", "text", "metadata"):
        if hasattr(value, key):
            attrs[key] = getattr(value, key)
    return attrs


def _string_list(value: object) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [value]
    return []
