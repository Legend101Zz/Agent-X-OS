"""Phase-1 syscall registry bootstrap."""

from agentx_contracts import Adapter, GatewayContext, SyscallRegistry, SyscallRequest

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


def build_phase1_registry() -> SyscallRegistry:
    """Build the live Phase-1 syscall ladder."""

    store = ManualTaskStore()
    providers = build_configured_research_providers()
    registry = Phase1SyscallRegistry(terminal_fallback=HumanTaskAdapter(store=store))
    registry.register(LeadResearchBatchAdapter(providers=providers))
    registry.register(ReadUrlAdapter(providers=providers))
    registry.register(DraftEmailAdapter())
    registry.register(QueueManualActionAdapter(store=store))
    registry.register(MarkOutcomeAdapter(store=store))
    return registry
