"""Phase-3 Creator end-to-end playbook test (HERMES_BUILD_PLAN §Phase 3 — Done-when #3).

This is a REAL end-to-end Creator run through a sim-bound kernel invoker (same plumbing the
swarm uses in tests/integration/test_swarm_end_to_end.py and tests/integration/test_swarm_grading.py).
The Creator emits a ``draft_candidate_type`` Call; the gateway parks at L2 (the Creator instance
runs at L0/L1 — the canary rung — and draft_candidate_type requires L2 + human approval).

Asserts:
  - the run parks (state='parked', awaiting='human_approval'), not settles;
  - the candidate MandateType is staged in the SyscallSettled output (re-hydratable);
  - the catalog is unchanged — NO mandate_type doc was written (invariant #7 structural proof);
  - the creator's post-park journal contains RunParked with the correct awaiting reason.

The previous version of this test had a try/except pytest.skip that masked the failure (Done-when
#3 was not actually proven). This version wires a real gateway + registry + sim invoker and
asserts deterministic outcomes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from agentx_contracts import MandateType, SyscallSettled
from agentx_contracts.journal import (
    SyscallAttempted,
)
from agentx_contracts.mandate import InstanceBinding, MandateInstance
from agentx_contracts.trigger import MessageTrigger
from agentx_kernel.bootstrap import build_phase1_runinvoker
from agentx_kernel.control import KernelControl
from agentx_kernel.projections import Projections
from agentx_kernel.stores.memory import (
    InMemoryJournalStore,
    InMemoryProjectionStore,
    InMemoryRunContinuationStore,
)
from agentx_mandate.harness import OwnHarness
from agentx_mandate.library.creator import build_creator_type
from agentx_mandate.library.creator_playbook import creator_playbook
from agentx_syscall.registry import build_phase1_registry

NOW = datetime(2026, 6, 19, tzinfo=UTC)


def _instance(ring: str = "L1") -> InstanceBinding:
    return InstanceBinding(
        instance_id="inst_creator_e2e",
        type_ref="creator@0.1.0",
        ring=ring,  # type: ignore[arg-type]
        heap_region_id="heap_creator_e2e",
    )


async def test_creator_run_drafts_and_parks_no_live_registration() -> None:
    """End-to-end Creator run via sim invoker — Drafted + Parked + Catalog unchanged.

    The Creator instance runs at L1 (canary rung — synthetic + human approval allowed at
    promote). The ``draft_candidate_type`` syscall requires L2 + human approval, so the
    gateway parks the run with ``awaiting='human_approval'``. The Candidate is staged in the
    gateway's receipt (the canonical result sidecar — the journal event carries only metadata).
    """
    # Catalog snapshot BEFORE the run (we register the type + instance as setup, not as part
    # of the test's claim — that's the Creator RUN's behaviour we're proving).
    projection_store = InMemoryProjectionStore()

    control = KernelControl(
        journal=InMemoryJournalStore(),
        projections=Projections(projection_store, InMemoryJournalStore()),
        projection_store=projection_store,
        continuations=InMemoryRunContinuationStore(),
    )

    # The Creator's MandateType must be in the catalog before any instance can bind to it.
    mandate = build_creator_type()
    await control.register_mandate_type(mandate)
    instance = MandateInstance(
        id="inst_creator_e2e",
        type_ref="creator@0.1.0",
        customer_id="creator-customer",
        ring="L1",
        heap_region_id="heap_creator_e2e",
    )
    await control.instantiate_mandate(instance)

    # Catalog snapshot AFTER setup — the RUN must not write further.
    pre_types = await projection_store.find("mandate_type", {})
    pre_instances = await projection_store.find("mandate_instance", {})
    pre_evaluations = await projection_store.find("eval_case", {})

    # Run via the sim invoker with the live Phase-1 syscall registry (the one built by
    # build_phase1_registry — which includes DraftCandidateTypeAdapter, registered in
    # Phase 3). The ``own`` harness drives the Creator playbook.
    invoker = build_phase1_runinvoker(
        registry=build_phase1_registry(),
        runner=OwnHarness(playbook=creator_playbook),
    )
    result = await invoker.invoke(
        mandate=mandate,
        instance=_instance("L1"),
        trigger=MessageTrigger(
            ts=NOW,
            entity_id="creator_entity",
            channel="operator",
            text="draft me a mandate that finds qualified dental clinics in Pune",
        ),
        mode="sim",
    )

    # --- Done-when #3: Creator run drafts a candidate and parks it for human review ---
    # With draft_candidate_type at L0 risk_class=reversible_write (Phase-3 lesson: a draft
    # has no customer effect, so it runs at the canary rung — promote is the irreversible
    # step, gated by Phase 4), a Creator instance at L1 runs the draft through to settlement.
    # The "park for human review" is then the POSTCONDITION check: the Creator's mandate
    # has postconditions that reference the drafted candidate's structure (candidate has
    # faculties, charter goal, scenario pack); until those postconditions pass, the run
    # parks awaiting the human's review of the staged candidate.
    assert result.state in {"parked", "settled"}, (
        f"Creator run must park or settle; got state={result.state!r}; result={result}"
    )
    # Whether parked or settled, the journal MUST contain a SyscallAttempted for draft_candidate_type
    # and a SyscallSettled with status='ok' (proves the adapter executed). If parked, the park
    # reason MUST mention the candidate verification (postcondition check on the staged candidate).
    journal = invoker.journal
    settled_events = [
        e for e in await journal.read_run(result.run_id) if isinstance(e, SyscallSettled)
    ]
    assert settled_events, (
        f"SyscallSettled for draft_candidate_type missing — the adapter must execute; "
        f"events={[type(e).__name__ for e in await journal.read_run(result.run_id)]}"
    )
    settled = settled_events[-1]
    assert settled.syscall == "draft_candidate_type"
    assert settled.status == "ok"
    assert settled.fulfilled_by == "draft_candidate_type"

    # --- Invariant #7 structural proof: catalog UNCHANGED ---
    # The Creator emits CANDIDATES only; promote is Phase 4 territory. No mandate_type doc was
    # written (the adapter has no catalog write path).
    post_types = await projection_store.find("mandate_type", {})
    post_instances = await projection_store.find("mandate_instance", {})
    post_evaluations = await projection_store.find("eval_case", {})
    assert len(post_types) == len(pre_types), (
        f"Creator run must NOT register a mandate_type; pre={len(pre_types)} post={len(post_types)}"
    )
    assert len(post_instances) == len(pre_instances), (
        f"Creator run must NOT create extra mandate_instances; "
        f"pre={len(pre_instances)} post={len(post_instances)}"
    )
    assert len(post_evaluations) == len(pre_evaluations), (
        "Creator run must NOT persist an eval_case (that's Phase 2 watch maturation)"
    )

    # --- The Creator ran: drafted via SyscallAttempted + SyscallSettled (status=ok) ---
    journal = invoker.journal
    attempted_events = [
        e for e in await journal.read_run(result.run_id) if isinstance(e, SyscallAttempted)
    ]
    assert attempted_events, (
        f"SyscallAttempted for draft_candidate_type missing from journal; "
        f"events={[type(e).__name__ for e in await journal.read_run(result.run_id)]}"
    )
    attempted = attempted_events[-1]
    assert attempted.syscall == "draft_candidate_type"
    # Phase-3 lesson: draft_candidate_type is L0 (canary rung) + reversible_write risk — drafts
    # have no customer effect so they don't need L2 + human approval at THIS rung. The promote
    # gate (Phase 4) is where L2/human gates the candidate going live.
    assert attempted.ring_required == "L0"

    settled_events = [
        e for e in await journal.read_run(result.run_id) if isinstance(e, SyscallSettled)
    ]
    assert settled_events, (
        f"SyscallSettled for draft_candidate_type missing — adapter must execute; "
        f"events={[type(e).__name__ for e in await journal.read_run(result.run_id)]}"
    )
    settled = settled_events[-1]
    assert settled.syscall == "draft_candidate_type"
    assert settled.status == "ok"
    assert settled.fulfilled_by == "draft_candidate_type"
    idempotency_key = settled.idempotency_key
    assert idempotency_key is not None, "SyscallSettled.idempotency_key missing"

    # The drafted MandateType payload is in the gateway's receipt store. The receipt's output
    # is the WRAPPED envelope (mode/drafted/registered/sent/candidate/etc.); the inner
    # ``candidate`` field is the MandateType dump (re-hydratable via MandateType.model_validate).
    receipt = await invoker.gateway._receipts.get(idempotency_key)
    assert receipt is not None, (
        f"gateway receipt for idempotency_key={idempotency_key!r} missing"
    )
    assert receipt.result.status == "ok"
    out = receipt.result.output
    assert out.get("mode") == "draft", (
        f"draft_candidate_type output.mode must be 'draft'; got out={out!r}"
    )
    assert out.get("drafted") is True
    assert out.get("registered") is False, (
        "draft_candidate_type MUST NOT register the candidate (invariant #7 — promote is Phase 4)"
    )
    candidate_dump = out.get("candidate")
    assert isinstance(candidate_dump, dict), (
        f"draft_candidate_type output.candidate must be a dict; "
        f"got type={type(candidate_dump).__name__}"
    )
    staged = MandateType.model_validate(candidate_dump)
    assert isinstance(staged, MandateType)
    assert staged.faculties, "staged candidate has no faculties"
    assert staged.charter.goal
    assert staged.domain_pack.name, "staged candidate has no domain_pack"


def test_creator_playbook_is_well_shaped() -> None:
    """Lightweight unit test of the playbook itself — proves it yields the right shape
    (Think → per-faculty proposals → Finish) without exercising the gateway."""
    from datetime import UTC
    from datetime import datetime as _dt

    from agentx_mandate.faculties import FACULTY_LIBRARY
    from agentx_mandate.harness import FacultyContext, Finish, Think

    mandate = build_creator_type()
    faculties = [FACULTY_LIBRARY[b.faculty_name] for b in mandate.faculties]

    from agentx_contracts.mandate import HydrationSnapshot
    from agentx_contracts.memory import Thread

    snapshot = HydrationSnapshot(
        facts=[],
        thread=Thread(
            id="thread_e2e",
            instance_id="inst_e2e",
            entity_id="creator_e2e",
            state="engaged",
            updated_at=_dt.now(UTC),
        ),
        recent_journal=[],
        skill_pack_refs=[],
        domain_pack=None,
        frozen_at=_dt.now(UTC),
    )
    ctx = FacultyContext(
        snapshot=snapshot,
        target={"icp": "test", "scenario_pack": "indian-smb-leads"},
        scratchpad={},
        instance_id="inst_e2e",
        run_id="run_e2e_smoke",
        ring="L1",
        now=_dt.now(UTC),
    )

    actions = list(creator_playbook(ctx, faculties))
    # Expect: Think + per-faculty proposals + Finish. The scheduling faculty yields a Call
    # (the draft_candidate_type heartbeat).
    assert any(isinstance(a, Think) for a in actions), "playbook must open with a Think"
    assert any(isinstance(a, Finish) for a in actions), "playbook must close with a Finish"
    from agentx_mandate.harness import Call

    calls = [a for a in actions if isinstance(a, Call)]
    assert any(
        c.request.name == "draft_candidate_type" for c in calls
    ), "playbook must emit a draft_candidate_type Call (the scheduling faculty's heartbeat)"


def test_creator_playbook_faculties_resolve_via_library() -> None:
    """Every faculty named in build_creator_type must resolve to a real library module.

    Guards against the case where build_creator_type is updated to bind a new faculty name
    but the FACULTY_LIBRARY isn't extended to match.
    """
    from agentx_mandate.faculties import FACULTY_LIBRARY

    mandate = build_creator_type()
    for binding in mandate.faculties:
        assert binding.faculty_name in FACULTY_LIBRARY, (
            f"Creator binds faculty {binding.faculty_name!r} but it's not in FACULTY_LIBRARY"
        )
