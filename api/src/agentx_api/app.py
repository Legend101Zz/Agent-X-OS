from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast

import agentx_db.collections as c
from agentx_contracts.enums import Ring, RunState
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .gaps import CORE_GAPS, gap_by_id
from .state import (
    DashboardState,
    approval_cards,
    capability_rows,
    create_state,
    instance_detail,
    instance_rows,
    manual_queue,
    run_detail,
    run_summaries,
    system_overview,
)


class ApproveCommand(BaseModel):
    instance_id: str
    run_id: str
    actor: str = "manager:dashboard"


class SetRingCommand(BaseModel):
    instance_id: str
    ring: Ring
    actor: str = "manager:dashboard"


class UnsupportedCommand(BaseModel):
    payload: dict[str, object] = Field(default_factory=dict)


def create_app(*, use_mongo: bool | None = None, seed_demo: bool = False) -> FastAPI:
    state = create_state(use_mongo=use_mongo, seed_demo=seed_demo)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.dashboard = state
        await state.ready()
        try:
            yield
        finally:
            await state.close()

    app = FastAPI(
        title="Agent-X Operator API",
        version="0.0.1",
        description="Thin HTTP face over existing Agent-X kernel query/command surfaces.",
        lifespan=lifespan,
    )
    app.state.dashboard = state
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def ensure_ready(request: Request, call_next):  # type: ignore[no-untyped-def]
        await _state(request).ready()
        return await call_next(request)

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        dashboard = _state(request)
        return {"ok": True, "backend": dashboard.backend, "ts": datetime.now(UTC).isoformat()}

    @app.get("/system/overview")
    async def get_overview(request: Request) -> dict[str, Any]:
        return {"system": "agent-x-os", **await system_overview(_state(request))}

    @app.get("/instances")
    async def get_instances(request: Request) -> dict[str, Any]:
        return {"instances": await instance_rows(_state(request))}

    @app.get("/instances/{instance_id}")
    async def get_instance(instance_id: str, request: Request) -> dict[str, Any]:
        return await instance_detail(_state(request), instance_id)

    @app.get("/runs")
    async def get_runs(
        request: Request,
        state: RunState | None = None,
        instance_id: str | None = None,
    ) -> dict[str, Any]:
        return {"runs": await run_summaries(_state(request), state_filter=state, instance_id=instance_id)}

    @app.get("/runs/{run_id}")
    async def get_run(run_id: str, request: Request) -> dict[str, Any]:
        return await run_detail(_state(request), run_id)

    @app.get("/approvals")
    async def get_approvals(request: Request, instance_id: str | None = None) -> dict[str, Any]:
        return {"items": await approval_cards(_state(request), instance_id=instance_id)}

    @app.get("/mandate-types")
    async def get_mandate_types(request: Request) -> dict[str, Any]:
        return {"mandate_types": await _state(request).collection(c.MANDATE_TYPE)}

    @app.get("/journal")
    async def get_journal(
        request: Request,
        instance_id: str | None = None,
        run_id: str | None = None,
        kind: str | None = None,
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> dict[str, Any]:
        events = await _state(request).journal_events(instance_id=instance_id, run_id=run_id, kind=kind, limit=limit)
        return {"events": [event.model_dump(mode="json") for event in events]}

    @app.get("/events")
    async def stream_events(request: Request) -> StreamingResponse:
        async def events() -> AsyncIterator[str]:
            recent = await _state(request).journal_events(limit=50)
            yield "event: journal\n"
            yield f"data: {json.dumps([event.model_dump(mode='json') for event in recent])}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/capabilities")
    async def get_capabilities(request: Request) -> dict[str, Any]:
        return {"capabilities": await capability_rows(_state(request))}

    @app.get("/eval-cases")
    async def get_eval_cases(request: Request) -> dict[str, Any]:
        return {"eval_cases": await _state(request).collection(c.EVAL_CASE)}

    @app.get("/manual-queue")
    async def get_manual_queue(request: Request) -> dict[str, Any]:
        return {"items": manual_queue(_state(request))}

    @app.get("/core-gaps")
    async def get_core_gaps() -> dict[str, Any]:
        return {"gaps": CORE_GAPS}

    @app.post("/commands/approve")
    async def approve(command: ApproveCommand, request: Request) -> dict[str, Any]:
        action = await _state(request).control.approve(
            instance_id=command.instance_id,
            run_id=command.run_id,
            actor=command.actor,
            now=datetime.now(UTC),
        )
        return {"supported": True, "action": action.model_dump(mode="json")}

    @app.post("/commands/set-ring")
    async def set_ring(command: SetRingCommand, request: Request) -> dict[str, Any]:
        action = await _state(request).control.set_ring(
            instance_id=command.instance_id,
            ring=command.ring,
            actor=command.actor,
            now=datetime.now(UTC),
        )
        return {"supported": True, "action": action.model_dump(mode="json")}

    _unsupported_routes = {
        "/commands/edit": "command.edit_approval",
        "/commands/reject": "command.reject_approval",
        "/commands/instantiate": "command.instantiate",
        "/commands/trigger-run": "command.trigger_run",
        "/commands/run-swarm": "command.run_swarm",
        "/commands/promote": "command.promote",
    }
    for route_path, gap_id in _unsupported_routes.items():
        app.add_api_route(
            route_path,
            _unsupported_handler(gap_id),
            methods=["POST"],
            response_class=JSONResponse,
        )

    return app


def _unsupported_handler(gap_id: str):  # type: ignore[no-untyped-def]
    async def handler(command: UnsupportedCommand | None = None) -> JSONResponse:
        return JSONResponse(
            status_code=501,
            content={"supported": False, "gap": gap_by_id(gap_id), "received": command.model_dump() if command else {}},
        )

    return handler


def _state(request: Request) -> DashboardState:
    return cast(DashboardState, request.app.state.dashboard)


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


app = create_app(seed_demo=_env_flag("AGENTX_API_SEED_DEMO"))
