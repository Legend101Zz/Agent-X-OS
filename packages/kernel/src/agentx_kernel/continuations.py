"""Kernel-owned durable payload for resuming a parked run."""

from __future__ import annotations

from agentx_contracts.base import AgentXModel
from agentx_contracts.enums import RunMode
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.mandate import HydrationSnapshot, InstanceBinding, MandateType
from agentx_contracts.memory import Fact
from agentx_contracts.syscall import SyscallRequest
from agentx_contracts.verification import Trace
from pydantic import Field, model_validator


class RunContinuation(AgentXModel):
    """Payload-faithful sidecar needed to continue a parked run without replaying reasoning."""

    run_id: str
    instance: InstanceBinding
    mandate: MandateType
    mode: RunMode
    snapshot: HydrationSnapshot
    """The run-start hydration snapshot, captured once and treated as frozen continuation input."""
    scratchpad: JsonObject = Field(default_factory=dict)
    trace: Trace
    claimed_facts: list[Fact] = Field(default_factory=list)
    harness_cursor: int = Field(default=0, ge=0)
    harness_state: JsonObject = Field(default_factory=dict)
    pending_call: SyscallRequest

    @model_validator(mode="after")
    def validate_bindings(self) -> RunContinuation:
        """Reject a sidecar that could resume one run or tenant with another run's payload."""
        if self.trace.run_id != self.run_id:
            raise ValueError("trace run_id does not match continuation run_id")
        if self.pending_call.run_id != self.run_id:
            raise ValueError("pending_call run_id does not match continuation run_id")
        if self.pending_call.instance_id != self.instance.instance_id:
            raise ValueError("pending_call instance_id does not match continuation instance")
        return self
