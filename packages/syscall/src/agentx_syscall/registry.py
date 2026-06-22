"""Phase-1 syscall registry bootstrap."""

from collections.abc import Sequence
from pathlib import Path

from agentx_contracts import Adapter, GatewayContext, SyscallRegistry, SyscallRequest

from agentx_syscall.adapters import (
    DraftCandidateTypeAdapter,
    DraftEmailAdapter,
    HumanTaskAdapter,
    LeadResearchBatchAdapter,
    ManualTaskStore,
    MarkOutcomeAdapter,
    QueueManualActionAdapter,
    ReadUrlAdapter,
    SendEmailAdapter,
    build_configured_research_providers,
)
from agentx_syscall.books import ExportLedgerAdapter, IngestDocumentAdapter
from agentx_syscall.deep_research_adapter import DeepResearchAdapter


class Phase1SyscallRegistry:
    """Fulfillment-ladder resolver with a guaranteed human-task tail."""

    def __init__(self, *, terminal_fallback: Adapter | None = None) -> None:
        self._adapters: list[Adapter] = []
        self._terminal_fallback: Adapter = terminal_fallback or HumanTaskAdapter()
        if not self._terminal_fallback.is_terminal_fallback:
            raise ValueError("terminal fallback adapter must set is_terminal_fallback=True")
        if self._terminal_fallback.name != "human_task":
            raise ValueError("terminal fallback adapter must be human_task")

    def register(self, adapter: Adapter) -> None:
        if adapter.is_terminal_fallback:
            raise ValueError("registry already has a terminal fallback adapter")
        self._adapters.append(adapter)

    def adapters(self) -> list[Adapter]:
        return [*self._adapters, self._terminal_fallback]

    def resolve(self, req: SyscallRequest, ctx: GatewayContext) -> Adapter:
        capable = [adapter for adapter in self._adapters if adapter.can_handle(req, ctx)]
        if capable:
            return sorted(capable, key=lambda adapter: adapter.maturity_level, reverse=True)[0]
        return self._terminal_fallback


def build_phase1_registry(
    *,
    send_email_adapters: Sequence[SendEmailAdapter] = (),
    discovery_adapters: Sequence[Adapter] = (),
    books_intake_dir: str | Path | None = None,
    books_output_dir: str | Path | None = None,
) -> SyscallRegistry:
    """Build the live Phase-1 syscall ladder.

    ``send_email_adapters`` lets the bootstrap register ONE ``SendEmailAdapter`` PER INSTANCE so
    each instance's outbound sender identity (invariant #8) is honoured without ever sharing a
    global From across tenants. When no send_email adapter is configured (or none can_handle
    given its transport), the registry resolves ``send_email`` to ``human_task`` — invariant #5.

    ``discovery_adapters`` lets the bootstrap register the Phase-12 mandate-discovery read
    adapters (``community_source_sample``, ``competitor_search``, ``buyer_channel_discovery``).
    When omitted, the mandate-discovery run parks at L1 awaiting the F1/F4/F5 read fulfilment
    (the manual queue is the human-task fallback for un-implemented read intents).

    ``books_intake_dir`` / ``books_output_dir`` wire the books-prep deterministic document I/O
    adapters (no LLM, no network). ``ingest_document`` is READ (fulfilled natively in sim; via
    ``IngestDocumentAdapter`` in live); ``export_ledger`` is REVERSIBLE_WRITE and parks at L1.
    """
    store = ManualTaskStore()
    providers = build_configured_research_providers()
    registry = Phase1SyscallRegistry(terminal_fallback=HumanTaskAdapter(store=store))
    registry.register(LeadResearchBatchAdapter(providers=providers))
    registry.register(ReadUrlAdapter(providers=providers))
    # In-OS deep research: bounded multi-hop fan-out over the configured providers
    # (Exa + Brave + Firecrawl). Read-class, L0 — no LLM, returns a cited pack.
    registry.register(DeepResearchAdapter(providers=providers))
    registry.register(DraftEmailAdapter())
    # Phase-3 (HERMES_BUILD_PLAN §Phase 3 — G10): Creator's draft_candidate_type syscall.
    # Draft-only; never registers a mandate_type (invariant #7 — promote is Phase 4).
    registry.register(DraftCandidateTypeAdapter())
    for send_adapter in send_email_adapters:
        registry.register(send_adapter)
    # Phase-12 (HERMES_BUILD_PLAN §Phase 12): mandate-discovery read adapters.
    # The caller is responsible for instantiating with the right API key; if no
    # discovery_adapters are passed, the F1/F4/F5 Calls fall to the human-task
    # terminal fallback (the run parks for human fulfilment).
    for discovery_adapter in discovery_adapters:
        registry.register(discovery_adapter)
    registry.register(QueueManualActionAdapter(store=store))
    registry.register(MarkOutcomeAdapter(store=store))
    # books-prep deterministic document I/O (no LLM, no network). ingest_document is READ (fulfilled
    # natively in sim; via this adapter in live); export_ledger is REVERSIBLE_WRITE and parks at L1.
    registry.register(IngestDocumentAdapter(intake_dir=books_intake_dir))
    registry.register(ExportLedgerAdapter(output_dir=books_output_dir))
    return registry
