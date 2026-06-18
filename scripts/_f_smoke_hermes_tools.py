"""Session F smoke: one live MiniMax tool-calling turn — validate the response shape before the
multi-step money-spending ICP runs. Prints the assistant message (content + tool_calls)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from agentx_contracts.config import Settings
from agentx_contracts.mandate import HydrationSnapshot
from agentx_kernel.hermes import HermesClient
from agentx_kernel.hermes_runner import _TOOLS, _system_prompt, _user_prompt
from agentx_mandate.harness import FacultyContext


async def main() -> int:
    settings = Settings()
    client = HermesClient.from_settings(settings)
    ctx = FacultyContext(
        snapshot=HydrationSnapshot(frozen_at=datetime.now(UTC)),
        target={"icp": "independent dental clinics", "location": "Pune", "count": 1},
        scratchpad={},
        instance_id="smoke",
        run_id="smoke_run",
        ring="L1",
        now=datetime.now(UTC),
    )
    messages = [
        {"role": "system", "content": _system_prompt(ctx)},
        {"role": "user", "content": _user_prompt(ctx)},
    ]
    response = await client.complete_chat(messages=messages, tools=_TOOLS)
    choices = response.get("choices")
    message = choices[0]["message"] if isinstance(choices, list) and choices else {}
    print("HAS_TOOL_CALLS=", bool(isinstance(message, dict) and message.get("tool_calls")))
    print("CONTENT=", json.dumps(message.get("content"))[:400] if isinstance(message, dict) else None)
    if isinstance(message, dict) and message.get("tool_calls"):
        tc = message["tool_calls"][0]
        print("TOOL_NAME=", tc["function"]["name"])
        print("TOOL_ARGS=", tc["function"]["arguments"][:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
