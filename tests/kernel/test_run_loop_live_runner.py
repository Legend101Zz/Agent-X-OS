"""Flag #2 — mode-aware runner selection on ``Phase1RunInvoker``.

The api never wired a model-driven runner, so a ``mode="live"`` run silently used the deterministic
``OwnHarness`` playbook and called no model. The fix adds a SEPARATE ``live_runner`` slot consulted
ONLY for live runs, leaving the existing ``runner=`` slot's "always used if set" semantics intact
(so the parked-resume / discovery tests that inject ``runner=`` keep working).

These tests pin the 3-way precedence directly on ``_runner`` plus one behavioral proof through
``invoke`` that a live run drives the injected ``live_runner`` while a sim run does not.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from agentx_contracts.faculty import FacultyBinding
from agentx_contracts.mandate import (
    Charter,
    DomainPackRef,
    InstanceBinding,
    MandateType,
    SettlementRules,
    VerificationSuite,
)
from agentx_contracts.trigger import DeadlineTrigger
from agentx_kernel.gateway import Gateway
from agentx_kernel.hydration import HydrationLoader
from agentx_kernel.projections import Projections
from agentx_kernel.run_loop import Phase1RunInvoker
from agentx_kernel.settlement import SettlementCommitter
from agentx_kernel.stores.memory import (
    InMemoryJournalStore,
    InMemoryProjectionStore,
    InMemoryRunContinuationStore,
    InMemorySyscallReceiptStore,
    InMemoryVault,
)
from agentx_kernel.verifier import RulesVerifier
from agentx_mandate.harness import Finish, OwnHarness

NOW = datetime(2026, 6, 23, tzinfo=UTC)


class _RecordingSession:
    """A trivial harness session that finishes immediately and records nothing else."""

    cursor: int = 0

    async def step(self, observation: object) -> Finish:
        return Finish()


class RecordingRunner:
    """A fake model-driven runner: records that it was started, then finishes the run."""

    name = "hermes"

    def __init__(self) -> None:
        self.started = False

    def start(
        self, *, context: object, faculties: object, cursor: int = 0, mandate: object = None
    ) -> _RecordingSession:
        self.started = True
        return _RecordingSession()


def _mandate() -> MandateType:
    """Minimal mandate with NO rules postconditions, so a no-fact Finish settles cleanly."""
    return MandateType(
        id="flag2-v0",
        name="flag2-mandate",
        version="0.1.0",
        charter=Charter(goal="prove runner selection", postconditions=[]),
        faculties=[FacultyBinding(faculty_name="memory-craft")],
        domain_pack=DomainPackRef(name="test", version="0.1.0"),
        verification=VerificationSuite(),
        settlement=SettlementRules(),
    )


def _instance() -> InstanceBinding:
    return InstanceBinding(
        instance_id="inst_flag2",
        type_ref="flag2-mandate@0.1.0",
        ring="L1",
        heap_region_id="tenant_flag2",
    )


def _invoker(*, runner: object = None, live_runner: object = None) -> Phase1RunInvoker:
    journal = InMemoryJournalStore()
    store = InMemoryProjectionStore()
    projections = Projections(store, journal)
    return Phase1RunInvoker(
        journal=journal,
        projections=projections,
        hydration=HydrationLoader(store, journal),
        gateway=Gateway(
            journal=journal,
            vault=InMemoryVault(),
            registry=None,
            receipts=InMemorySyscallReceiptStore(),
        ),
        settlement=SettlementCommitter(journal=journal, projections=projections),
        verifier=RulesVerifier(),
        continuations=InMemoryRunContinuationStore(),
        runner=runner,  # type: ignore[arg-type]
        live_runner=live_runner,  # type: ignore[arg-type]
        run_log_dir="",
    )


# --- _runner precedence (the unit of logic) ---------------------------------------------


def test_live_mode_uses_live_runner_when_set() -> None:
    live = RecordingRunner()
    invoker = _invoker(runner=None, live_runner=live)
    assert invoker._runner(_mandate(), "live") is cast(object, live)


def test_sim_mode_never_uses_live_runner() -> None:
    live = RecordingRunner()
    invoker = _invoker(runner=None, live_runner=live)
    chosen = invoker._runner(_mandate(), "sim")
    assert chosen is not cast(object, live)
    assert isinstance(chosen, OwnHarness)


def test_injected_runner_is_used_for_both_modes_when_live_runner_absent() -> None:
    """Back-compat: callers that set runner= (parked-resume/discovery tests) are unaffected."""
    injected = OwnHarness(recorded=[Finish()])
    invoker = _invoker(runner=injected, live_runner=None)
    assert invoker._runner(_mandate(), "live") is injected
    assert invoker._runner(_mandate(), "sim") is injected


def test_live_runner_takes_precedence_over_injected_runner_only_in_live() -> None:
    injected = OwnHarness(recorded=[Finish()])
    live = RecordingRunner()
    invoker = _invoker(runner=injected, live_runner=live)
    assert invoker._runner(_mandate(), "live") is cast(object, live)
    assert invoker._runner(_mandate(), "sim") is injected


# --- behavioral proof through invoke ----------------------------------------------------


async def test_invoke_live_drives_live_runner_and_settles() -> None:
    live = RecordingRunner()
    invoker = _invoker(runner=None, live_runner=live)
    result = await invoker.invoke(
        mandate=_mandate(),
        instance=_instance(),
        trigger=DeadlineTrigger(ts=NOW, reason="live", entity_id="inst_flag2:live"),
        mode="live",
    )
    assert live.started is True
    assert result.state == "settled"


async def test_invoke_sim_does_not_touch_live_runner() -> None:
    live = RecordingRunner()
    invoker = _invoker(runner=None, live_runner=live)
    await invoker.invoke(
        mandate=_mandate(),
        instance=_instance(),
        trigger=DeadlineTrigger(ts=NOW, reason="sim", entity_id="inst_flag2:sim"),
        mode="sim",
    )
    assert live.started is False
