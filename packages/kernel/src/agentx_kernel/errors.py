"""Kernel error types — deterministic, typed failures the run-loop and gateway can catch.

The kernel never lets an exception decide policy implicitly; these are the explicit, named failure
modes (idempotency collisions, missing config, unresolvable fulfillment) the deterministic code
matches on.
"""

from __future__ import annotations


class KernelError(Exception):
    """Base class for every kernel-raised error."""


class DuplicateIdempotencyKey(KernelError):
    """An effectful journal event with an already-seen ``idempotency_key`` was appended again.

    The journal enforces at-most-once: the gateway catches this on a retry and returns the prior
    result instead of executing the effect twice (BLUEPRINT §3 — "LLMs retry; never double-do").
    """

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"duplicate idempotency_key: {key!r}")


class IdempotencyRequestConflict(KernelError):
    """An idempotency key was reused for a different logical syscall request."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"idempotency key belongs to a different syscall request: {key!r}")


class MissingSyscallReceipt(KernelError):
    """A legacy settled syscall cannot be replayed because its output receipt is absent."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"settled syscall has no durable output receipt: {key!r}")


class JournalSeqContention(KernelError):
    """Per-instance ``seq`` assignment kept colliding under concurrency past the retry budget.

    The journal assigns ``seq = max_seq + 1`` then inserts under a UNIQUE ``(instance_id, seq)`` index.
    A concurrent appender can win the seq between the read and the insert; the store retries with a
    freshly recomputed ``seq``. This is raised only if every retry lost the race (extreme contention).
    """

    def __init__(self, instance_id: str) -> None:
        self.instance_id = instance_id
        super().__init__(f"journal seq contention exhausted for instance {instance_id!r}")


class ConfigError(KernelError):
    """A required setting (e.g. a connection string, a faculty model id) is missing at startup."""


class MandateTypeConflict(KernelError):
    """A catalog type identity was reused with different immutable content."""

    def __init__(self, identity: str) -> None:
        self.identity = identity
        super().__init__(f"mandate type conflicts with registered identity: {identity!r}")


class MandateInstanceConflict(KernelError):
    """An instance id was reused with different customer-private state."""

    def __init__(self, instance_id: str) -> None:
        self.instance_id = instance_id
        super().__init__(f"mandate instance conflicts with registered id: {instance_id!r}")


class UnknownMandateType(KernelError):
    """An instance references a type+version that is not registered."""

    def __init__(self, type_ref: str) -> None:
        self.type_ref = type_ref
        super().__init__(f"mandate type is not registered: {type_ref!r}")


class UnknownMandateInstance(KernelError):
    """A requested instance id is not registered."""

    def __init__(self, instance_id: str) -> None:
        self.instance_id = instance_id
        super().__init__(f"mandate instance is not registered: {instance_id!r}")
