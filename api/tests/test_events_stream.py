from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, cast

from agentx_contracts.journal import ManagerAction
from fastapi import Request
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute

from agentx_api.app import create_app


async def _next_frame(iterator: AsyncIterator[Any], *, timeout: float = 2.0) -> dict[str, Any]:
    chunks: list[str] = []
    while True:
        chunk = await asyncio.wait_for(anext(iterator), timeout=timeout)
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        chunks.append(text)
        joined = "".join(chunks)
        if "\n\n" not in joined:
            continue
        data_lines = [
            line.removeprefix("data:").strip()
            for line in joined.splitlines()
            if line.startswith("data:")
        ]
        return cast(dict[str, Any], json.loads("\n".join(data_lines)))


async def test_events_stream_tails_new_events_and_stops_on_disconnect() -> None:
    app = create_app(use_mongo=False, seed_demo=True, start_worker=False)
    state = app.state.dashboard
    await state.start()
    existing = await state.journal_events(limit=50)
    disconnected = False

    async def receive() -> dict[str, Any]:
        if disconnected:
            return {"type": "http.disconnect"}
        return {"type": "http.request", "body": b"", "more_body": True}

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/events",
        "raw_path": b"/events",
        "query_string": b"",
        "headers": [],
        "app": app,
        "scheme": "http",
        "server": ("test", 80),
        "client": ("test", 123),
        "root_path": "",
        "http_version": "1.1",
    }
    request = Request(scope, receive=receive)
    route = cast(
        APIRoute,
        next(route for route in app.routes if getattr(route, "path", None) == "/events"),
    )
    response = await route.endpoint(request)
    assert isinstance(response, StreamingResponse)
    iterator = cast(AsyncIterator[Any], response.body_iterator.__aiter__())

    initial_frames = [await _next_frame(iterator) for _ in existing]
    assert [frame["event_id"] for frame in initial_frames] == [event.event_id for event in existing]

    previous_seq = max(event.seq for event in existing if event.instance_id == "inst_demo")
    appended = await state.journal.append(
        ManagerAction(
            event_id="manager:sse-test",
            seq=0,
            ts=datetime.now(UTC),
            instance_id="inst_demo",
            actor="manager:test",
            action="sse_test",
            detail={},
        )
    )
    new_frame = await _next_frame(iterator)

    assert new_frame["event_id"] == appended.event_id
    assert new_frame["seq"] > previous_seq

    disconnected = True
    try:
        await asyncio.wait_for(anext(iterator), timeout=2.0)
    except StopAsyncIteration:
        pass
    else:
        raise AssertionError("SSE iterator did not terminate after client disconnect")

    await state.close()
