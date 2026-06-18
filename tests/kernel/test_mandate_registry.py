import pytest
from agentx_contracts.mandate import MandateInstance
from agentx_kernel.errors import MandateInstanceConflict, MandateTypeConflict, UnknownMandateType
from agentx_kernel.registry import MandateRegistry
from agentx_kernel.stores.memory import InMemoryProjectionStore
from agentx_mandate.library.lead_finder import build_lead_finder_type


def _instance(*, instance_id: str = "inst_real", ring: str = "L1") -> MandateInstance:
    return MandateInstance(
        id=instance_id,
        type_ref="lead-finder@0.1.0",
        customer_id="Acme Dental",
        ring=ring,  # type: ignore[arg-type]
        heap_region_id=f"tenant_{instance_id}",
    )


async def test_register_type_is_idempotent_and_rejects_conflicting_identity() -> None:
    registry = MandateRegistry(InMemoryProjectionStore())
    mandate = build_lead_finder_type()

    assert await registry.register_type(mandate) == mandate
    assert await registry.register_type(mandate.model_copy(deep=True)) == mandate
    assert await registry.get_type("lead-finder@0.1.0") == mandate
    assert await registry.list_types() == [mandate]

    conflicting = mandate.model_copy(deep=True)
    conflicting.charter.goal = "A different immutable type definition."
    with pytest.raises(MandateTypeConflict):
        await registry.register_type(conflicting)


async def test_instantiate_get_list_and_binding_are_idempotent_and_typed() -> None:
    registry = MandateRegistry(InMemoryProjectionStore())
    mandate = build_lead_finder_type()
    instance = _instance()
    await registry.register_type(mandate)

    assert await registry.instantiate(instance) == instance
    assert await registry.instantiate(instance.model_copy(deep=True)) == instance
    assert await registry.get_instance(instance.id) == instance
    assert await registry.list_instances() == [instance]
    assert await registry.list_instances(customer_id="Acme Dental") == [instance]

    binding = await registry.binding(instance.id)
    assert binding.instance_id == instance.id
    assert binding.type_ref == instance.type_ref
    assert binding.ring == "L1"
    assert binding.heap_region_id == instance.heap_region_id

    with pytest.raises(MandateInstanceConflict):
        await registry.instantiate(_instance(ring="L2"))


async def test_instantiate_requires_registered_type() -> None:
    registry = MandateRegistry(InMemoryProjectionStore())

    with pytest.raises(UnknownMandateType):
        await registry.instantiate(_instance())
