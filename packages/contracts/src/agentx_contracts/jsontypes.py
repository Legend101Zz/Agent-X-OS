"""Precise JSON typing — the answer to "no untyped dicts".

Many payloads in the system are *genuinely* schema-less at the contract layer: syscall arguments,
charter targets, JSON-Schema documents, manager-action details. We never type those as bare ``dict``.
Instead we use Pydantic's recursive ``JsonValue`` (a fully-typed JSON tree) so mypy and Pydantic both
understand the shape while staying honest that the *content* is dynamic.
"""

from typing import TypeAlias

from pydantic import JsonValue

# A JSON object: keys are strings, values are any JSON value (recursively typed).
JsonObject: TypeAlias = dict[str, JsonValue]

# A JSON-Schema document is itself just JSON (used by Adapter.input_schema / output_schema).
JsonSchema: TypeAlias = dict[str, JsonValue]

__all__ = ["JsonValue", "JsonObject", "JsonSchema"]
