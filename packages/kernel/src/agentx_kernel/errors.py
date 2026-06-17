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


class ConfigError(KernelError):
    """A required setting (e.g. a connection string, a faculty model id) is missing at startup."""
