"""Durable syscall result receipts used for faithful idempotency replay."""

from __future__ import annotations

from agentx_contracts.base import AgentXModel
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.syscall import SyscallRequest, SyscallResult


class SyscallReceipt(AgentXModel):
    """The complete result and request identity for one globally unique idempotency key."""

    idempotency_key: str
    instance_id: str
    run_id: str
    syscall: str
    args: JsonObject
    result: SyscallResult

    @classmethod
    def from_execution(cls, req: SyscallRequest, result: SyscallResult) -> SyscallReceipt:
        return cls(
            idempotency_key=req.idempotency_key,
            instance_id=req.instance_id,
            run_id=req.run_id,
            syscall=req.name,
            args=req.args,
            result=result,
        )

    def matches(self, req: SyscallRequest) -> bool:
        return (
            self.instance_id == req.instance_id
            and self.run_id == req.run_id
            and self.syscall == req.name
            and self.args == req.args
        )
