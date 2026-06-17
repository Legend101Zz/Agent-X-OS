"""Shared Pydantic base for every Agent-X contract model.

The seam validates *LLM/agent output at runtime* — that is the whole reason the contracts are
Pydantic models and not bare dataclasses or TS types (which erase at runtime). Every model therefore
``extra="forbid"``: malformed or hallucinated fields are rejected at the boundary instead of being
silently absorbed into the kernel's trusted state.
"""

from pydantic import BaseModel, ConfigDict


class AgentXModel(BaseModel):
    """Strict base: validates assignment, forbids unknown fields.

    Subclass this for all domain/memory/seam models so the whole contract surface rejects
    unexpected input uniformly. Models that must be immutable (e.g. credentials) override
    ``model_config`` to add ``frozen=True``.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)
