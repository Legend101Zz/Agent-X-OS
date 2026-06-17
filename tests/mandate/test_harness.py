"""M1 — the faculties-framework harness seam, exercised through the ``own`` test double.

The harness is where a faculty's reasoning runs. In sim we bind the deterministic ``own`` double
(canned reasoning) so runs are fast and reproducible. The double must:
  - surface effectful proposals (draft_email) to the run-loop so the gateway can gate them;
  - fulfil READ intents natively (borrow the muscle) — they never reach the gateway in sim;
  - be a durable continuation: rebuildable + resumable at a saved cursor (Temporal-style replay).

The pod holds NO credentials and NO durable state — this module imports only the pure contracts seam.
"""

from datetime import UTC, datetime

from agentx_contracts import Fact, HydrationSnapshot, Provenance, SyscallRequest
from agentx_mandate.harness import Call, Claim, FacultyContext, Finish, OwnHarness, Think

NOW = datetime(2026, 6, 17, tzinfo=UTC)


def _ctx() -> FacultyContext:
    return FacultyContext(
        snapshot=HydrationSnapshot(frozen_at=NOW), target={}, scratchpad={},
        instance_id="inst_a", run_id="run_1", ring="L1", now=NOW,
    )


def _req(name: str, risk: str, idem: str) -> SyscallRequest:
    return SyscallRequest(
        name=name, instance_id="inst_a", run_id="run_1", idempotency_key=idem,
        ring="L1", risk_class=risk,  # type: ignore[arg-type]
    )


def _read_call() -> Call:
    return Call(request=_req("lead_research_batch", "read", "idem-read"))


def _draft_call() -> Call:
    return Call(request=_req("draft_email", "external_message", "idem-draft"))


async def _session(actions: list[object]):
    harness = OwnHarness(recorded=actions)  # type: ignore[arg-type]
    return harness.start(context=_ctx(), faculties=[])


async def test_own_double_yields_surfaced_actions_in_order() -> None:
    session = await _session([Think(summary="planning"), _draft_call()])
    a1 = await session.step(None)
    a2 = await session.step(None)
    assert isinstance(a1, Think)
    assert isinstance(a2, Call) and a2.request.name == "draft_email"


async def test_read_intents_are_fulfilled_natively_not_surfaced() -> None:
    # A read Call must NOT surface to the run-loop in sim — only the effectful draft_email does.
    session = await _session([Think(summary="research"), _read_call(), _draft_call()])
    surfaced: list[object] = []
    for _ in range(2):
        surfaced.append(await session.step(None))
    assert [type(a).__name__ for a in surfaced] == ["Think", "Call"]
    assert isinstance(surfaced[1], Call) and surfaced[1].request.name == "draft_email"


async def test_exhausted_session_returns_finish() -> None:
    session = await _session([Think(summary="only")])
    await session.step(None)  # Think
    done = await session.step(None)
    assert isinstance(done, Finish)


async def test_session_is_resumable_at_a_saved_cursor() -> None:
    # Drive to the draft_email, "park", then rebuild + resume at the parked cursor (deterministic replay).
    actions = [Think(summary="plan"), _draft_call()]
    session = await _session(actions)
    await session.step(None)  # Think  -> cursor 1
    parked = await session.step(None)  # draft_email -> cursor 2
    assert isinstance(parked, Call)
    resume_cursor = session.cursor - 1  # re-execute the parked call on resume

    harness = OwnHarness(recorded=actions)  # type: ignore[arg-type]
    resumed = harness.start(context=_ctx(), faculties=[], cursor=resume_cursor)
    again = await resumed.step(None)
    assert isinstance(again, Call) and again.request.name == "draft_email"


async def test_claim_action_carries_facts_with_provenance() -> None:
    fact = Fact(
        id="f1", instance_id="inst_a", subject="lead_1", predicate="interested_in", object="cleaning",
        confidence=0.6, source="agent-inferred", provenance=Provenance(run_id="run_1"), created_at=NOW,
    )
    session = await _session([Claim(facts=[fact])])
    action = await session.step(None)
    assert isinstance(action, Claim)
    assert action.facts[0].provenance.run_id == "run_1"
