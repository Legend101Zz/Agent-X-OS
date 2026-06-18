"""Projection-backed catalog for durable mandate types and instances."""

from __future__ import annotations

import agentx_db.collections as c
from agentx_contracts.mandate import InstanceBinding, MandateInstance, MandateType

from .errors import (
    MandateInstanceConflict,
    MandateTypeConflict,
    UnknownMandateInstance,
    UnknownMandateType,
)
from .ports import ProjectionStore


class MandateRegistry:
    """Persist and resolve the long-lived Type -> Instance catalog layers."""

    def __init__(self, store: ProjectionStore) -> None:
        self._store = store

    async def register_type(self, mandate: MandateType) -> MandateType:
        existing_by_id = await self._store.get(c.MANDATE_TYPE, mandate.id)
        if existing_by_id is not None:
            existing = MandateType.model_validate(existing_by_id)
            if existing == mandate:
                return existing
            raise MandateTypeConflict(mandate.id)

        same_version = await self._store.find(
            c.MANDATE_TYPE,
            {"name": mandate.name, "version": mandate.version},
        )
        if same_version:
            existing = MandateType.model_validate(same_version[0])
            if existing == mandate:
                return existing
            raise MandateTypeConflict(type_ref(mandate))

        await self._store.upsert(
            c.MANDATE_TYPE,
            mandate.id,
            mandate.model_dump(mode="json"),
        )
        return mandate

    async def get_type(self, type_reference: str) -> MandateType | None:
        name, version = _split_type_ref(type_reference)
        docs = await self._store.find(c.MANDATE_TYPE, {"name": name, "version": version})
        if not docs:
            return None
        return MandateType.model_validate(docs[0])

    async def list_types(self) -> list[MandateType]:
        mandates = [
            MandateType.model_validate(document)
            for document in await self._store.find(c.MANDATE_TYPE, {})
        ]
        return sorted(mandates, key=lambda mandate: (mandate.name, mandate.version, mandate.id))

    async def instantiate(self, instance: MandateInstance) -> MandateInstance:
        if await self.get_type(instance.type_ref) is None:
            raise UnknownMandateType(instance.type_ref)
        existing_doc = await self._store.get(c.MANDATE_INSTANCE, instance.id)
        if existing_doc is not None:
            existing = MandateInstance.model_validate(existing_doc)
            if existing == instance:
                return existing
            raise MandateInstanceConflict(instance.id)

        await self._store.upsert(
            c.MANDATE_INSTANCE,
            instance.id,
            instance.model_dump(mode="json"),
        )
        return instance

    async def get_instance(self, instance_id: str) -> MandateInstance | None:
        document = await self._store.get(c.MANDATE_INSTANCE, instance_id)
        return MandateInstance.model_validate(document) if document is not None else None

    async def list_instances(self, *, customer_id: str | None = None) -> list[MandateInstance]:
        query: dict[str, object] = {}
        if customer_id is not None:
            query["customer_id"] = customer_id
        instances = [
            MandateInstance.model_validate(document)
            for document in await self._store.find(c.MANDATE_INSTANCE, query)
        ]
        return sorted(instances, key=lambda instance: instance.id)

    async def binding(self, instance_id: str) -> InstanceBinding:
        instance = await self.get_instance(instance_id)
        if instance is None:
            raise UnknownMandateInstance(instance_id)
        return InstanceBinding(
            instance_id=instance.id,
            type_ref=instance.type_ref,
            ring=instance.ring,
            heap_region_id=instance.heap_region_id,
            channel_binding=instance.channel_binding,
            overrides=list(instance.overrides),
        )


def type_ref(mandate: MandateType) -> str:
    return f"{mandate.name}@{mandate.version}"


def _split_type_ref(type_reference: str) -> tuple[str, str]:
    name, separator, version = type_reference.rpartition("@")
    if not separator or not name or not version:
        raise UnknownMandateType(type_reference)
    return name, version
