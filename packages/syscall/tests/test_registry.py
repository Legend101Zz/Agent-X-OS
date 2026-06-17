from datetime import UTC, datetime

import pytest
from agentx_contracts import GatewayContext, SyscallRequest
from agentx_syscall.adapters import DraftEmailAdapter, HumanTaskAdapter, ManualTaskStore
from agentx_syscall.registry import Phase1SyscallRegistry, build_phase1_registry


def _ctx() -> GatewayContext:
    return GatewayContext(
        instance_id="inst_1",
        run_id="run_1",
        tenant_id="tenant_1",
        ring="L1",
        now=datetime.now(UTC),
    )


def _req(name: str) -> SyscallRequest:
    return SyscallRequest(
        name=name,
        args={"to": "ops@example.com", "subject": "Draft", "body": "Hello"},
        instance_id="inst_1",
        run_id="run_1",
        idempotency_key=f"idem_{name}",
        ring="L1",
    )


def test_resolve_returns_specific_adapter_before_human_tail() -> None:
    store = ManualTaskStore()
    registry = Phase1SyscallRegistry(terminal_fallback=HumanTaskAdapter(store=store))
    registry.register(DraftEmailAdapter())

    adapter = registry.resolve(_req("draft_email"), _ctx())

    assert adapter.name == "draft_email"
    assert adapter.is_terminal_fallback is False


def test_resolve_unknown_syscall_returns_human_tail() -> None:
    registry = build_phase1_registry()

    adapter = registry.resolve(_req("unsupported_phase1_intent"), _ctx())

    assert adapter.name == "human_task"
    assert adapter.is_terminal_fallback is True


def test_registry_has_exactly_one_terminal_fallback() -> None:
    registry = build_phase1_registry()

    terminal = [adapter for adapter in registry.adapters() if adapter.is_terminal_fallback]

    assert [adapter.name for adapter in terminal] == ["human_task"]


def test_rejects_second_terminal_fallback() -> None:
    registry = Phase1SyscallRegistry()

    with pytest.raises(ValueError, match="terminal fallback"):
        registry.register(HumanTaskAdapter(store=ManualTaskStore()))
