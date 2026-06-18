"""P10 typed command/query API over kernel projections and journal."""

from datetime import UTC, datetime

from agentx_contracts.journal import SyscallAttempted
from agentx_contracts.mandate import MandateInstance
from agentx_kernel.control import KernelControl
from agentx_kernel.projections import Projections
from agentx_kernel.stores.memory import InMemoryJournalStore, InMemoryProjectionStore
from agentx_kernel.verifier import HumanApprovalGate
from agentx_mandate.library.lead_finder import build_lead_finder_type

NOW = datetime(2026, 6, 17, tzinfo=UTC)


async def _control() -> tuple[KernelControl, InMemoryProjectionStore]:
    journal = InMemoryJournalStore()
    projection_store = InMemoryProjectionStore()
    projections = Projections(projection_store, journal)
    return KernelControl(journal=journal, projections=projections, projection_store=projection_store), projection_store


async def test_approval_inbox_lists_unresolved_human_approval_and_approve_resolves_it() -> None:
    control, _projection_store = await _control()
    await control.journal.append(
        SyscallAttempted(
            event_id="idem-draft:attempt",
            seq=0,
            ts=NOW,
            instance_id="inst_a",
            run_id="run_1",
            syscall="draft_email",
            args={"to": "owner@example.com", "subject": "Lead", "body": "Real draft body"},
            ring_required="L2",
        )
    )
    await HumanApprovalGate(control.journal).park_for_approval(
        instance_id="inst_a",
        run_id="run_1",
        reason="draft_email requires L2",
        required_ring="L2",
        now=NOW,
    )

    inbox = await control.approval_inbox(instance_id="inst_a")
    assert len(inbox.items) == 1
    assert inbox.items[0].run_id == "run_1"
    assert inbox.items[0].approval_card == {
        "syscall": "draft_email",
        "args": {"to": "owner@example.com", "subject": "Lead", "body": "Real draft body"},
        "idempotency_key": "idem-draft",
    }

    action = await control.approve(
        instance_id="inst_a",
        run_id="run_1",
        actor="manager:founder",
        now=NOW,
    )

    assert action.action == "approve"
    assert await control.approval_inbox(instance_id="inst_a") == inbox.model_copy(update={"items": []})


async def test_set_ring_is_journaled_and_updates_instance_file_resume_projection() -> None:
    control, _projection_store = await _control()

    action = await control.set_ring(instance_id="inst_a", ring="L2", actor="manager:founder", now=NOW)
    instance_file = await control.instance_file(instance_id="inst_a")
    floor = await control.floor(instance_id="inst_a")

    assert action.action == "set_ring"
    assert instance_file.resume is not None
    assert instance_file.resume["ring"] == "L2"
    assert floor.ring == "L2"


async def test_control_registers_and_instantiates_catalog_entries() -> None:
    control, _projection_store = await _control()
    mandate = build_lead_finder_type()
    instance = MandateInstance(
        id="inst_catalog",
        type_ref="lead-finder@0.1.0",
        customer_id="Catalog Dental",
        ring="L1",
        heap_region_id="tenant_catalog",
    )

    await control.register_mandate_type(mandate)
    await control.instantiate_mandate(instance)

    assert await control.list_mandate_types() == [mandate]
    assert await control.list_mandate_instances() == [instance]
    assert (await control.instance_binding(instance.id)).instance_id == instance.id
