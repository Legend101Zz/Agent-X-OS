"""Phase-1 syscall adapters.

Adapters are actuators behind the kernel gateway. They receive intent-shaped
``SyscallRequest`` objects and an optional credential injected by the gateway;
they never make autonomous decisions outside that request.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
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
from agentx_contracts.mandate import MandateType
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
        lead_id = req.args.get("lead_id")
        return SyscallResult(
            status="ok",
            output={
                "provider": provider.name,
                "credential_ref": cred.ref if cred is not None else None,
                "lead_id": lead_id if isinstance(lead_id, str) else None,
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
            required_ring="L2",
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


class EmailTransport(Protocol):
    """A pluggable outbound email transport (Resend / AgentMail / SMTP / fake).

    The transport is the boundary that actually talks to the world; the adapter NEVER holds the
    secret (the credential arrives via ``execute(req, cred)`` from the gateway, and the transport
    receives its API key through the SAME gateway/vault seam). Mirrors ``ResearchProvider`` for
    symmetry: a small provider seam behind the Agent-X Adapter interface.
    """

    name: str

    async def send(
        self,
        *,
        from_addr: str,
        to: str,
        subject: str,
        body: str,
        headers: Mapping[str, str] | None = None,
    ) -> SentEmailReceipt:
        """Send one email and return a transport receipt (message_id, accepted)."""
        ...


@dataclass(frozen=True)
class SentEmailReceipt:
    """What an email transport returns: the upstream provider's message id + acceptance flag."""

    message_id: str
    to: str
    from_addr: str
    subject: str
    accepted: bool = True


class SendEmailAdapter(_AdapterBase):
    """Send an approved email really — the gated real-send rung (HERMES_BUILD_PLAN §Phase 1).

    This is the rung that converts a parked ``draft_email`` (L2 + human approval) into an outbound
    email. It enforces:

    - **Invariant #2:** the transport secret arrives ONLY via ``cred`` at execute time. The adapter
      constructor takes a transport object whose secret was already injected by the gateway when the
      transport was built (or a test-supplied fake); the adapter itself never imports credential
      roots.
    - **Invariant #8 (per-instance sender identity):** the ``From``/sender identity MUST equal the
      instance's own ``ChannelBinding.sender_identity``. The adapter refuses requests whose
      ``sender_identity`` arg doesn't match what the resolver returns for the instance — no
      shared/global sender, no spoofing across instances.
    - **Invariant #5 (terminal fallback):** if no transport is configured (``can_handle`` returns
      False), the registry's ladder resolves to ``human_task``; ``resolve`` never returns None.
    - **Idempotency / no double-send:** the adapter remembers the idempotency_key -> receipt mapping
      for the lifetime of the adapter and replays it without calling ``transport.send`` again,
      independent of (and on top of) the gateway's journal/receipt idempotency.
    - **Live gating:** ``RUN_LIVE_EMAIL=1`` is the only gate that allows a real outbound send in
      live mode; otherwise the configured transport is replaced with a no-op so unit tests and
      unconfigured deployments stay deterministic.

    The adapter is registered ONCE per process; it resolves the per-instance sender on each
    ``execute(req)`` via ``instance_sender_resolver(req.instance_id)``. The kernel run-loop ALSO
    stamps ``req.args["sender_identity"]`` from the instance's ``ChannelBinding`` (belt and
    suspenders), so the adapter's check sees a stamped value that the resolver should agree with.
    """

    def __init__(
        self,
        *,
        transport: EmailTransport | None,
        instance_sender: str | None = None,
        instance_sender_resolver: Callable[[str], str | Awaitable[str | None] | None] | None = None,
        transport_factory: Callable[[], EmailTransport | None] | None = None,
    ) -> None:
        self._transport = transport
        # At least one of instance_sender / instance_sender_resolver must be supplied. When only a
        # fixed ``instance_sender`` is given, the adapter is bound to ONE instance; when a resolver
        # is given, one adapter serves ALL instances (per-instance sender looked up per request).
        if instance_sender is None and instance_sender_resolver is None:
            raise ValueError("SendEmailAdapter requires instance_sender or instance_sender_resolver")
        self._fixed_sender: str | None = instance_sender
        self._sender_resolver: Callable[[str], str | Awaitable[str | None] | None] | None = instance_sender_resolver
        self._transport_factory = transport_factory
        self._sent_receipts: dict[str, SentEmailReceipt] = {}
        super().__init__(
            name="send_email",
            category="communication",
            maturity_level=2,
            risk_class="external_message",
            required_ring="L2",
            tenant_auth="api_key",
            fixtures=[
                SyscallTestCase(
                    name="send_email_smoke",
                    input={
                        "to": "founder@example.com",
                        "subject": "Lead intro",
                        "body": "Body text.",
                        "sender_identity": instance_sender or "",
                    },
                    expect_status="ok",
                    expect_output_contains={"mode": "sent", "sent": True},
                )
            ],
        )

    def _resolve_sender(self, instance_id: str) -> str | None:
        if self._sender_resolver is None:
            return self._fixed_sender
        # Resolvers may be sync or async; callers that need to await must use
        # ``_resolve_sender_async``. The sync path is for fixed-sender + test-fake-resolver only
        # (the resolver returns a plain str); async resolvers are rejected here.
        result = self._sender_resolver(instance_id)
        if isinstance(result, str):
            return result
        return None

    async def _resolve_sender_async(self, instance_id: str) -> str | None:
        if self._sender_resolver is None:
            return self._fixed_sender
        import inspect

        result = self._sender_resolver(instance_id)
        if inspect.isawaitable(result):
            return await result
        if isinstance(result, str):
            return result
        return None

    def can_handle(self, req: SyscallRequest, ctx: GatewayContext) -> bool:
        if not super().can_handle(req, ctx):
            return False
        transport = self._live_transport()
        return transport is not None

    def _live_transport(self) -> EmailTransport | None:
        """Resolve the live transport, honoring ``RUN_LIVE_EMAIL=1`` and re-evaluating the factory.

        If a factory was supplied (e.g. live mode reads env each call), re-evaluate it now; otherwise
        fall back to the constructor-supplied transport. ``None`` means "not configured" — and
        ``can_handle`` will report False, sending the request down the human_task tail.
        """
        if self._transport_factory is not None:
            return self._transport_factory()
        return self._transport

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        # Idempotency replay (defense-in-depth on top of the gateway's own receipt replay).
        prior = self._sent_receipts.get(req.idempotency_key)
        if prior is not None:
            return SyscallResult(
                status="ok",
                output={
                    "mode": "sent",
                    "sent": True,
                    "message_id": prior.message_id,
                    "to": prior.to,
                    "subject": prior.subject,
                    "from": prior.from_addr,
                    "idempotent_replay": True,
                    "credential_ref": cred.ref if cred is not None else None,
                },
                idempotency_key=req.idempotency_key,
                fulfilled_by=self.name,
                maturity_used=self.maturity_level,
            )

        # Invariant #8: the sender identity MUST be the instance's own — refuse spoofing.
        requested_sender = _str_arg(req.args, "sender_identity")
        instance_sender = await self._resolve_sender_async(req.instance_id)
        if instance_sender is None:
            return _error_result(
                req,
                self.name,
                self.maturity_level,
                f"no instance sender bound for instance_id={req.instance_id!r}",
            )
        if requested_sender != instance_sender:
            return _error_result(
                req,
                self.name,
                self.maturity_level,
                (
                    f"sender_identity mismatch: request claims {requested_sender!r} "
                    f"but instance sender is {instance_sender!r}"
                ),
            )

        to = _str_arg(req.args, "to")
        subject = _str_arg(req.args, "subject")
        body = _str_arg(req.args, "body")

        transport = self._live_transport()
        if transport is None:
            # can_handle should have rejected this; surface as a clear error if reached.
            return _error_result(req, self.name, self.maturity_level, "send_email transport not configured")

        # The credential is injected by the gateway (invariant #2). The pod/adapter caller never
        # holds the secret. The transport received its key from the SAME gateway at construction
        # time (or a test-supplied fake); here we just attach the vault ref to the receipt/journal
        # for traceability, never the material.
        receipt = await transport.send(
            from_addr=instance_sender,
            to=to,
            subject=subject,
            body=body,
        )
        self._sent_receipts[req.idempotency_key] = receipt
        return SyscallResult(
            status="ok",
            output={
                "mode": "sent",
                "sent": True,
                "message_id": receipt.message_id,
                "to": receipt.to,
                "subject": receipt.subject,
                "from": receipt.from_addr,
                "transport": transport.name,
                "credential_ref": cred.ref if cred is not None else None,
            },
            idempotency_key=req.idempotency_key,
            fulfilled_by=self.name,
            maturity_used=self.maturity_level,
        )

    async def health_check(self) -> Health:
        transport = self._live_transport()
        if transport is None:
            return Health(
                status="degraded",
                detail="no email transport configured; registry will fall back to human_task",
                checked_at=datetime.now(UTC),
            )
        return Health(
            status="ok",
            detail=f"email transport ready: {transport.name}",
            checked_at=datetime.now(UTC),
        )


class DraftCandidateTypeAdapter(_AdapterBase):
    """Phase-3 draft-only creator adapter (HERMES_BUILD_PLAN §Phase 3 — G10).

    The Creator emits candidate ``MandateType`` drafts through this adapter. Crucially:
    ``execute`` stages the candidate as run output ONLY — it does NOT register the type. The
    adapter has no catalog / projection-store dependency, so structurally it cannot promote. Phase
    4 (promote gate + canary) is the ONLY path that takes a candidate to a registered
    ``mandate_type`` doc; that path also enforces real+human (invariant #7).

    Invariants honoured:
      - **#2 (no credential in user space):** the adapter imports zero credential roots; no
        catalog / projection writes; only ``agentx_contracts.mandate``.
      - **#5 (terminal fallback):** when not resolvable, the registry falls back to ``human_task``
        (the adapter never returns None).
      - **#7 (no synthetic case promotes):** the candidate IS a ``MandateType`` (typed), and the
        output marks ``drafted=True, registered=False``. The adapter has no write path.
      - **#4 (no brain in the live kernel):** the adapter is a pure transformer (dict → typed
        MandateType). It does not run an autonomous loop.

    The adapter registers at ``required_ring='L0'`` (a canary rung — same as ``read_url`` and
    ``lead_research_batch``). The draft has NO live customer effect: the adapter has no catalog
    write paths, no network calls, and the resulting candidate stays in the receipt until Phase 4's
    promote gate escalates it to L2/L3 (which is the irreversible step).
    Risk class is ``reversible_write`` — a draft that gets rejected by the promote gate is just
    discarded, no customer-facing effect to undo.
    """

    def __init__(self) -> None:
        self._drafts: dict[str, MandateType] = {}
        super().__init__(
            name="draft_candidate_type",
            category="mandate_meta",
            maturity_level=1,
            risk_class="reversible_write",
            required_ring="L0",
            tenant_auth="manual",
            fixtures=[
                SyscallTestCase(
                    name="draft_candidate_type_smoke",
                    input={
                        "goal": "Find and qualify leads.",
                        "icp": "test icp",
                        "scenario_pack": "indian-smb-leads",
                        "cadence_days": 7,
                        "faculties": ["research", "judgment", "memory-craft", "escalation"],
                    },
                    expect_status="ok",
                    expect_output_contains={"mode": "draft", "drafted": True, "registered": False},
                )
            ],
        )

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        # Idempotent: the same idempotency_key returns the same draft (no re-materialisation).
        prior = self._drafts.get(req.idempotency_key)
        if prior is not None:
            return _draft_result(req=req, candidate=prior, idempotent_replay=True)

        candidate = _materialise_candidate(req.args)
        self._drafts[req.idempotency_key] = candidate
        return _draft_result(req=req, candidate=candidate, idempotent_replay=False)

    async def health_check(self) -> Health:
        return Health(
            status="ok",
            detail="draft_candidate_type: stages MandateType drafts for human review; no live registration",
            checked_at=datetime.now(UTC),
        )


def _materialise_candidate(args: Mapping[str, Any]) -> MandateType:
    """Convert the Creator's structured brief (``req.args``) into a typed ``MandateType``.

    The Creator's ``scheduling`` faculty emits args shaped as:
      ``{goal, icp, scenario_pack, cadence_days, faculties, target_schema, ...}``

    We translate that into a minimal but well-formed ``MandateType`` so the human reviewer sees
    the SAME contract shape the catalog uses — no bespoke ``candidate`` shape.
    """
    from agentx_contracts.faculty import FacultyBinding as _FacultyBinding
    from agentx_contracts.mandate import (
        Charter as _Charter,
    )
    from agentx_contracts.mandate import (
        Condition as _Condition,
    )
    from agentx_contracts.mandate import (
        DomainPackRef as _DomainPackRef,
    )
    from agentx_contracts.mandate import (
        MandateType as _MandateType,
    )
    from agentx_contracts.mandate import (
        SettlementRules as _SettlementRules,
    )
    from agentx_contracts.mandate import (
        VerificationSuite as _VerificationSuite,
    )
    from agentx_contracts.verification import Rubric as _Rubric
    from agentx_contracts.verification import RubricCriterion as _RubricCriterion

    def _opt(args: Mapping[str, Any], key: str, default: str) -> str:
        raw = args.get(key)
        return raw if isinstance(raw, str) and raw else default

    goal = _opt(args, "goal", "Find and qualify leads.")
    icp = _opt(args, "icp", "qualified B2B prospects")
    scenario_pack = _opt(args, "scenario_pack", "indian-smb-leads")
    pack_version = _opt(args, "scenario_pack_version", "0.1.0")
    name = _opt(args, "candidate_name", "") or _slugify(goal)
    raw_cadence = args.get("cadence_days")
    cadence_days = raw_cadence if isinstance(raw_cadence, int) and raw_cadence > 0 else 7

    faculties_raw = args.get("faculties")
    faculty_names: list[str] = []
    if isinstance(faculties_raw, list):
        for fname in faculties_raw:
            if isinstance(fname, str) and fname:
                faculty_names.append(fname)
    if not faculty_names:
        # Empty / wrong-type / non-string-only list — fall back to the §5 default set so the
        # human reviewer ALWAYS sees a candidate with real faculties (no empty-binding drafts).
        faculty_names = ["research", "judgment", "memory-craft", "escalation"]

    return _MandateType(
        id=f"type_{name}_v0",
        name=name,
        version="0.1.0",
        charter=_Charter(
            goal=goal,
            postconditions=[
                _Condition(
                    id="has_claimed_facts",
                    description="At least one lead fact was claimed.",
                    rung="rules",
                    expr="claimed_facts >= 1",
                ),
                _Condition(
                    id="has_lead_score",
                    description="A qualified lead score fact exists.",
                    rung="rules",
                    expr="fact:qualified_lead_score exists",
                ),
            ],
            constraints=["read-only research first", "draft email only; never send in Phase 1"],
            target={"icp": icp, "cadence_days": cadence_days},
        ),
        faculties=[_FacultyBinding(faculty_name=fname) for fname in faculty_names],
        domain_pack=_DomainPackRef(name=scenario_pack, version=pack_version),
        verification=_VerificationSuite(
            ladder=["rules", "judge", "human", "reality"],
            rules=[],
            rubrics=[
                _Rubric(
                    name="lead_quality",
                    pass_threshold=0.7,
                    criteria=[
                        _RubricCriterion(
                            id="fit",
                            description="Finds a right-fit lead.",
                            weight=0.7,
                        ),
                        _RubricCriterion(
                            id="safety",
                            description="Keeps effects behind approval.",
                            weight=0.3,
                        ),
                    ],
                ),
            ],
        ),
        settlement=_SettlementRules(watch_window_hours=72),
        gym_ref=f"gym:{scenario_pack}",
        service_ports=["qualified_leads"],
    )


def _draft_result(
    *, req: SyscallRequest, candidate: MandateType, idempotent_replay: bool
) -> SyscallResult:
    """Build the success-result envelope for a draft.

    The ``mode='draft'`` + ``drafted=True`` + ``registered=False`` triple is the structural
    proof of invariant #7 in the syscall lane: the Creator emits CANDIDATES only.

    The candidate is dumped to a JSON dict so the result travels through the journal cleanly.
    Phase-4 promote + the human reviewer's UI read the dump and re-hydrate via
    ``MandateType.model_validate(candidate_dict)`` — the same pattern the catalog read uses.
    """
    candidate_dump = candidate.model_dump(mode="json")
    return SyscallResult(
        status="ok",
        output={
            "mode": "draft",
            "drafted": True,
            "registered": False,
            "sent": False,  # never sends; mirrors draft_email's `sent: false` shape
            "candidate_id": candidate.id,
            "candidate_type_ref": f"{candidate.name}@{candidate.version}",
            "candidate_name": candidate.name,
            "candidate_version": candidate.version,
            "creator_instance_id": req.instance_id,
            "creator_run_id": req.run_id,
            "idempotent_replay": idempotent_replay,
            "candidate": candidate_dump,
            "credential_ref": None,  # no credential needed for a draft (manual / human-gated)
        },
        idempotency_key=req.idempotency_key,
        fulfilled_by="draft_candidate_type",
        maturity_used=cast(MaturityLevel, self_maturity_used_for_drafts()),
    )


def self_maturity_used_for_drafts() -> int:
    # Local sentinel — MaturityLevel is a Literal[0,1,2,3], int-typed; using 1 directly here
    # would be a magic number. We expose it through a helper so the rung is named, not magic.
    return 1


def _slugify(value: str, *, default: str = "candidate") -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return default
    # ASCII-only slug; drop non-alphanumeric, collapse separators.
    chars: list[str] = []
    for char in raw:
        if char.isalnum():
            chars.append(char)
        elif char in {" ", "_", "-"}:
            chars.append("-")
    slug = "".join(chars).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or default


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
        excluded = criteria.get("exclude_domains")
        exclude_domains = [str(item) for item in excluded] if isinstance(excluded, list) else None
        response = client.search(
            _criteria_to_query(criteria),
            limit=count,
            exclude_domains=exclude_domains,
            timeout=60_000,
        )
        return _parse_search_results(response, provider=self.name, count=count)

    async def read_url(self, url: str) -> ResearchPage:
        firecrawl_module = import_module("firecrawl")
        client_cls = firecrawl_module.Firecrawl
        client = client_cls(api_key=self._api_key)
        response = client.scrape(
            url,
            formats=["markdown", "links"],
            only_main_content=True,
            timeout=60_000,
        )
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
    explicit = criteria.get("query")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    if not criteria:
        return "qualified B2B leads with evidence"
    parts = [f"{key}: {value}" for key, value in sorted(criteria.items())]
    return "Find qualified leads with evidence. " + "; ".join(parts)


def _parse_search_results(response: object, *, provider: str, count: int) -> list[ResearchLead]:
    raw_results = _raw_results(response)
    leads: list[ResearchLead] = []
    for idx, item in enumerate(raw_results[:count], start=1):
        mapping = _to_mapping(item)
        metadata = _to_mapping(mapping.get("metadata"))
        title = str(mapping.get("title") or mapping.get("name") or metadata.get("title") or f"Lead {idx}")
        url = str(
            mapping.get("url")
            or mapping.get("link")
            or metadata.get("sourceURL")
            or metadata.get("url")
            or metadata.get("ogUrl")
            or ""
        )
        lead_id = str(mapping.get("id") or f"{provider}_{idx}")
        highlights = _string_list(mapping.get("highlights"))
        snippet = str(
            mapping.get("snippet")
            or mapping.get("description")
            or metadata.get("description")
            or metadata.get("ogDescription")
            or ""
        )
        markdown = str(mapping.get("markdown") or "")
        evidence = highlights or ([snippet] if snippet else [])
        if markdown:
            evidence.append(markdown[:500])
        if not evidence:
            evidence = [f"{provider} result {idx}"]
        leads.append(
            ResearchLead(
                id=lead_id,
                name=title,
                url=url,
                evidence=evidence,
                fit_score=0.75,
                metadata={"provider": provider, **cast(JsonObject, dict(metadata))},
            )
        )
    return leads


def _parse_page(response: object, *, url: str, provider: str) -> ResearchPage:
    mapping = _first_mapping(response)
    markdown = str(mapping.get("markdown") or mapping.get("text") or mapping.get("content") or "")
    metadata = _to_mapping(mapping.get("metadata"))
    title = mapping.get("title") or metadata.get("title") or metadata.get("ogTitle")
    page_url = (
        mapping.get("url")
        or metadata.get("sourceURL")
        or metadata.get("url")
        or metadata.get("ogUrl")
        or url
    )
    metadata_json = cast(JsonObject, dict(metadata))
    return ResearchPage(
        url=str(page_url),
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
