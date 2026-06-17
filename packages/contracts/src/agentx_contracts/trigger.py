"""Triggers — what starts a run (BLUEPRINT §2 step 1).

A discriminated union on ``kind`` so the kernel can pattern-match exhaustively and mypy can check it.
``demand`` (the internal market) is reserved for after Phase 1 and is intentionally not modelled yet.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from .base import AgentXModel
from .jsontypes import JsonObject


class _TriggerBase(AgentXModel):
    ts: datetime
    entity_id: str | None = None
    """The counterparty this trigger concerns (lead/patient/conversation), when applicable."""


class MessageTrigger(_TriggerBase):
    """An inbound message arrived on a channel."""

    kind: Literal["message"] = "message"
    channel: str
    text: str


class DeadlineTrigger(_TriggerBase):
    """A scheduled time/deadline fired (e.g. a follow-up window opened)."""

    kind: Literal["deadline"] = "deadline"
    reason: str


class SpawnTrigger(_TriggerBase):
    """A parent run spawned this child. Spawn is the call; the heap is the return path (no message channel)."""

    kind: Literal["spawn"] = "spawn"
    parent_run_id: str
    spawn_reason: str
    params: JsonObject = Field(default_factory=dict)


# The Trigger seam type (used by RunInvoker, SEAM 2). Discriminated on ``kind``.
Trigger = Annotated[
    MessageTrigger | DeadlineTrigger | SpawnTrigger,
    Field(discriminator="kind"),
]
