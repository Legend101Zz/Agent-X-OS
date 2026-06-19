"""Phase-1 syscall registry bootstrap."""

from collections.abc import Sequence

from agentx_contracts import Adapter, GatewayContext, SyscallRegistry, SyscallRequest

from agentx_syscall.adapters import (
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
) -> SyscallRegistry:
    """Build the live Phase-1 syscall ladder.

    ``send_email_adapters`` lets the bootstrap register ONE ``SendEmailAdapter`` PER INSTANCE so
    each instance's outbound sender identity (invariant #8) is honoured without ever sharing a
    global From across tenants. When no send_email adapter is configured (or none can_handle
    given its transport), the registry resolves ``send_email`` to ``human_task`` — invariant #5.
    """
    store = ManualTaskStore()
    providers = build_configured_research_providers()
    registry = Phase1SyscallRegistry(terminal_fallback=HumanTaskAdapter(store=store))
    registry.register(LeadResearchBatchAdapter(providers=providers))
    registry.register(ReadUrlAdapter(providers=providers))
    registry.register(DraftEmailAdapter())
    for send_adapter in send_email_adapters:
        registry.register(send_adapter)
    registry.register(QueueManualActionAdapter(store=store))
    registry.register(MarkOutcomeAdapter(store=store))
    return registry
