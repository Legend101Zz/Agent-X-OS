"""The Agent-X Operator API: thin FastAPI surface over the lifespan-owned OperatorRuntime.

Endpoints (Phase 1 dashboard operability):

  Read:
    GET  /health
    GET  /system/overview
    GET  /instances
    GET  /instances/{id}
    GET  /runs?state=&instance_id=
    GET  /runs/{run_id}
    GET  /approvals?instance_id=
    GET  /manual-queue
    GET  /mandate-types
    GET  /journal?instance_id=&run_id=&kind=&limit=
    GET  /events                                  (SSE stream)
    GET  /capabilities
    GET  /eval-cases
    GET  /core-gaps
    GET  /scheduler-work/{work_id}
    GET  /system/info                             (auth: CORS + token visibility)

  Commands (all require ``Authorization: Bearer <AGENTX_OPERATOR_TOKEN>`` when set):
    POST /commands/instantiate
    POST /commands/trigger-run
    POST /commands/approve
    POST /commands/reject
    POST /commands/set-ring

Lifespan:
  - Compose OperatorRuntime once via ``build_runtime``.
  - Start the in-process scheduler worker in ``startup``.
  - Stop it and close the Mongo client in ``shutdown``.

Security posture:
  - Bearer token auth on command routes only (read routes are open; the API is local/internal).
  - CORS restricted to ``AGENTX_CORS_ORIGINS`` (comma-separated); empty = same-origin only.
  - Fixture/demo mode requires the explicit ``AGENTX_API_ALLOW_FIXTURES=1`` env flag. Without it,
    live mode fails closed: a missing Mongo surfaces a ``disconnected`` health state instead of
    fixture substitution.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast

import agentx_db.collections as c
from agentx_contracts.enums import ApprovalDecision, Ring, RunMode, RunState
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.mandate import MandateType
from agentx_contracts.trigger import DeadlineTrigger
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
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


async def _ensure_canonical_mandate_registered(state: DashboardState) -> None:
    """Memory-mode helper: register the canonical lead-finder if the catalog is empty.

    Live mode (Mongo) keeps whatever the operator has registered; we don't want to silently
    register types on first connect. The seed_demo flag still injects the legacy fixture; this
    helper covers the test / sim path where we want one mandate present without the demo state.
    """
    if state.seed_demo:
        return
    existing = await state.collection(c.MANDATE_TYPE)
    if existing:
        return
    from agentx_mandate.library.lead_finder import build_lead_finder_type

    await state.control.register_mandate_type(build_lead_finder_type())

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------


class InstantiateCommand(BaseModel):
    type_ref: str
    customer_id: str = Field(min_length=1)
    business_name: str = Field(min_length=1)
    ring: Ring = "L0"
    target_override: JsonObject | None = None
    # The per-instance outbound sender identity (invariant #8). When set, the instance gets an email
    # ChannelBinding so the gated send_email rung can send as THIS sender (and never a shared global).
    sender_identity: str | None = None
    actor: str = "manager:dashboard"


class TriggerRunCommand(BaseModel):
    instance_id: str
    target: JsonObject | None = None
    mode: RunMode = "sim"
    actor: str = "manager:dashboard"


class ApprovalCommand(BaseModel):
    instance_id: str
    run_id: str
    actor: str = "manager:dashboard"
    edited: bool = False


class SetRingCommand(BaseModel):
    instance_id: str
    ring: Ring
    actor: str = "manager:dashboard"


class RunSwarmCommand(BaseModel):
    type_ref: str = "lead-finder@0.1.0"
    pack_id: str = "indian_b2b_leads_v1"
    ring: Ring = "L2"
    judge_live: bool = False
    actor: str = "manager:dashboard"


class PromoteCommand(BaseModel):
    """Phase-4 promote body — the candidate→live bridge.

    The only client-supplied inputs are:
      - candidate_id  (server looks up the draft + gathers eval_cases by type_ref)
      - ring          (validated to {L0, L1} for the canary path; L2+ for the strict gate)
      - human_approved (the operator's confirmation)
      - actor         (audit trail)

    Client-supplied eval_case_ids / scorecards are NOT accepted — the server gathers by
    type_ref to defeat operator cherry-picking.
    """

    candidate_id: str = Field(min_length=1)
    ring: Ring = "L0"
    human_approved: bool = False
    actor: str = "manager:dashboard"


# ---------------------------------------------------------------------------
# Auth + CORS + env helpers
# ---------------------------------------------------------------------------


def _env_flag(name: str) -> bool:
    """Read a bool flag. Prefers ``get_settings()`` (pydantic-settings, reads .env) so this works
    whether or not the start script manually exported the var into the process env. Falls back to
    ``os.getenv`` for the rare case where the Settings field doesn't exist yet (test fixtures)."""
    try:
        from agentx_contracts.config import get_settings

        settings_map = {
            "AGENTX_API_ALLOW_FIXTURES": "agentx_api_allow_fixtures",
            "RUN_LIVE_EMAIL": "run_live_email",
        }
        attr = settings_map.get(name)
        if attr is not None:
            return bool(getattr(get_settings(), attr, False))
    except Exception:  # noqa: BLE001 - never fail flag reads (settings may be uninitialised)
        pass
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str) -> list[str]:
    """Read a comma-separated list. Prefers ``get_settings()`` (typed .env loader) over
    ``os.getenv`` so the start script doesn't have to manually export .env into the process env."""
    try:
        from agentx_contracts.config import get_settings

        settings_map = {"AGENTX_CORS_ORIGINS": "agentx_cors_origins"}
        attr = settings_map.get(name)
        if attr is not None:
            raw = str(getattr(get_settings(), attr, "") or "")
            return [item.strip() for item in raw.split(",") if item.strip()]
    except Exception:  # noqa: BLE001
        pass
    raw = os.getenv(name, "").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _operator_token() -> str:
    """Return the configured operator token, or empty string if none is set.

    When the env var is unset the API still works but every command route returns 401 — fail
    closed until the operator explicitly opts into the local-only trust boundary by setting a
    token. Prefers ``get_settings()`` (reads .env) over ``os.getenv`` so the start script doesn't
    have to manually export the var.
    """
    try:
        from agentx_contracts.config import get_settings

        tok = getattr(get_settings(), "agentx_operator_token", None)
        if tok is not None:
            secret = tok.get_secret_value() if hasattr(tok, "get_secret_value") else str(tok)
            if secret.strip():
                return secret.strip()
    except Exception:  # noqa: BLE001
        pass
    return os.getenv("AGENTX_OPERATOR_TOKEN", "").strip()


def _require_command_auth(request: Request) -> None:
    """FastAPI dependency that enforces the bearer token on every command route."""
    expected = _operator_token()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="AGENTX_OPERATOR_TOKEN is not configured; command routes are disabled.",
        )
    raw_header = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if not raw_header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token.",
            headers={"WWW-Authenticate": 'Bearer realm="agentx"'},
        )
    presented = raw_header.split(" ", 1)[1].strip()
    if not secrets.compare_digest(presented, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid bearer token.",
        )


# ---------------------------------------------------------------------------
# Phase-4 promote helpers (candidate→live bridge).
# ---------------------------------------------------------------------------


def _canary_gate(
    *,
    eval_cases: list[Any],
    human_approved: bool,
    ring: str,
) -> tuple[list[str], bool]:
    """The L0/L1 canary gate — distinct from the swarm's strict PromotionGate.

    A canary rung accepts EITHER synthetic OR real evidence (Phase-4 design: synthetic
    is the bridge that lets a freshly-Creator-drafted candidate reach a canary rung
    before any real run). It still requires:
      - human_approved
      - at least one passing scorecard on the eval_cases (origin can be synthetic OR real)

    Returns (reasons, allowed). When allowed=True, reasons is [].
    """
    reasons: list[str] = []
    if not human_approved:
        reasons.append("canary promote requires human_approved=true")
    passing = [
        case
        for case in eval_cases
        if case.scorecard is not None
        and case.scorecard.passed
        and case.scorecard.score >= 0.5
    ]
    if not passing:
        reasons.append(
            "canary promote requires at least one eval_case with a passing scorecard "
            "(swarm-smoke-passed)"
        )
    if not reasons:
        return [], True
    return reasons, False


def _promote_barred(*, reasons: list[str], ring: str) -> JSONResponse:
    """Uniform 422 envelope for a barred promote — caller-friendly + machine-readable."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "status": "barred",
            "ring_requested": ring,
            "reasons": reasons,
        },
    )


# ---------------------------------------------------------------------------
# App factory + lifespan
# ---------------------------------------------------------------------------


def create_app(
    *,
    use_mongo: bool | None = None,
    seed_demo: bool = False,
    operator_token: str | None = None,
    cors_origins: list[str] | None = None,
    start_worker: bool = True,
    send_email_transport: Any | None = None,
) -> FastAPI:
    """Build the FastAPI app. ``operator_token`` overrides ``AGENTX_OPERATOR_TOKEN`` (test hook).

    ``send_email_transport`` is a Phase-1 test hook: when ``None`` the runtime reads
    ``RUN_LIVE_EMAIL=1`` + ``RESEND_API_KEY`` and registers a live Resend transport if both are
    present; otherwise no SendEmailAdapter is registered (the human_task tail handles send_email,
    invariant #5). When supplied (a test fake), the runtime uses it instead and registers exactly
    one SendEmailAdapter at the per-instance sender supplied via MandateInstance.channel_binding.
    """
    state = create_state(
        use_mongo=use_mongo,
        seed_demo=seed_demo,
        send_email_transport=send_email_transport,
    )
    if operator_token is not None:
        os.environ["AGENTX_OPERATOR_TOKEN"] = operator_token
    if cors_origins is not None:
        os.environ["AGENTX_CORS_ORIGINS"] = ",".join(cors_origins)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.dashboard = state
        await state.start()
        if start_worker:
            await state.runtime.start_worker()
        try:
            yield
        finally:
            await state.close()

    app = FastAPI(
        title="Agent-X Operator API",
        version="0.1.0",
        description="Thin FastAPI control surface over the lifespan-owned OperatorRuntime.",
        lifespan=lifespan,
    )
    app.state.dashboard = state
    _install_cors(app)

    @app.middleware("http")
    async def ensure_startup(request: Request, call_next):  # type: ignore[no-untyped-def]
        try:
            await state.start()
            await _ensure_canonical_mandate_registered(state)
        except Exception:  # noqa: BLE001
            logger.exception("dashboard state startup failed")
            return JSONResponse(
                status_code=503,
                content={"ok": False, "state": "disconnected", "error": "startup failed"},
            )
        if start_worker:
            try:
                await state.runtime.start_worker()
            except RuntimeError:
                pass  # already running
        return await call_next(request)

    _install_routes(app)
    return app


def _install_cors(app: FastAPI) -> None:
    origins = _env_list("AGENTX_CORS_ORIGINS")
    if not origins:
        # Same-origin only: do NOT add CORSMiddleware at all. FastAPI defaults to no CORS headers.
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
        allow_credentials=False,
    )


# ---------------------------------------------------------------------------
# Route installation
# ---------------------------------------------------------------------------


def _install_routes(app: FastAPI) -> None:
    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        state = _state(request)
        try:
            await state.start()
            backend = state.backend
            db_ok = True
        except Exception:  # noqa: BLE001
            backend = state.backend
            db_ok = False
        return {
            "ok": db_ok,
            "backend": backend,
            "ts": datetime.now(UTC).isoformat(),
            "mode": "live" if db_ok else "disconnected",
            "fixtures_allowed": _env_flag("AGENTX_API_ALLOW_FIXTURES"),
            "command_auth_configured": bool(_operator_token()),
        }

    @app.get("/system/info")
    async def system_info(request: Request) -> dict[str, Any]:
        state = _state(request)
        return {
            "service": "agentx-operator-api",
            "version": "0.1.0",
            "internal_only": True,
            "posture": "local-only; do NOT expose to the public internet.",
            "cors_origins": _env_list("AGENTX_CORS_ORIGINS"),
            "fixtures_allowed": _env_flag("AGENTX_API_ALLOW_FIXTURES"),
            "command_auth_configured": bool(_operator_token()),
            "backend": state.backend,
        }

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
        """First-class approval inbox endpoint (separate from /manual-queue)."""
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
        events = await _state(request).journal_events(
            instance_id=instance_id, run_id=run_id, kind=kind, limit=limit
        )
        return {"events": [event.model_dump(mode="json") for event in events]}

    @app.get("/events")
    async def stream_events(request: Request) -> StreamingResponse:
        from asyncio import sleep

        async def events() -> AsyncIterator[str]:
            state = _state(request)
            last_seq_by_instance: dict[str, int] = {}
            recent = await _state(request).journal_events(limit=50)
            for event in recent:
                last_seq_by_instance[event.instance_id] = max(
                    last_seq_by_instance.get(event.instance_id, 0),
                    event.seq,
                )
                yield "event: journal\n"
                yield f"data: {json.dumps(event.model_dump(mode='json'))}\n\n"

            idle_seconds = 0
            while idle_seconds < 300:
                if await request.is_disconnected():
                    return
                current = await state.journal_events(limit=1000)
                unseen = [
                    event
                    for event in current
                    if event.seq > last_seq_by_instance.get(event.instance_id, 0)
                ]
                if unseen:
                    idle_seconds = 0
                    for event in unseen:
                        last_seq_by_instance[event.instance_id] = event.seq
                        yield "event: journal\n"
                        yield f"data: {json.dumps(event.model_dump(mode='json'))}\n\n"
                    continue
                idle_seconds += 1
                if idle_seconds % 15 == 0:
                    yield ": heartbeat\n\n"
                await sleep(1)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

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

    @app.get("/scheduler-work/{work_id}")
    async def get_scheduler_work(work_id: str, request: Request) -> dict[str, Any]:
        state = _state(request)
        status_row = await state.runtime.scheduler_store.status(work_id)
        if status_row is None:
            raise HTTPException(status_code=404, detail=f"scheduler work not found: {work_id}")
        return {"work": status_row.model_dump(mode="json")}

    # ------------------------- Commands (auth required) ------------------------

    @app.post(
        "/commands/instantiate",
        dependencies=[Depends(_require_command_auth)],
        status_code=status.HTTP_201_CREATED,
    )
    async def instantiate(command: InstantiateCommand, request: Request) -> dict[str, Any]:
        state = _state(request)
        from agentx_contracts.mandate import MandateInstance

        mandate = await state.control._registry.get_type(command.type_ref)
        if mandate is None:
            raise HTTPException(status_code=404, detail=f"unknown type_ref: {command.type_ref}")
        # The dashboard can submit an explicit JSON target_override (typed mandate fields are
        # captured in that JSON: ``icp``, ``location``, ``count``, etc.). The override is
        # attached to a per-instance type id so re-registering doesn't collide with the canonical
        # type on every trigger.
        target_override: JsonObject = dict(command.target_override or {})
        instance_id = _derive_instance_id(command.business_name)
        mandate_with_override: Any = mandate
        if target_override:
            mandate_with_override = mandate.model_copy(
                update={
                    "id": f"type_{instance_id}",
                    "charter": mandate.charter.model_copy(update={"target": target_override}),
                }
            )
        channel_binding = None
        if command.sender_identity and command.sender_identity.strip():
            from agentx_contracts.mandate import ChannelBinding

            channel_binding = ChannelBinding(
                channel="email",
                sender_identity=command.sender_identity.strip(),
                opt_in=True,
            )
        instance = MandateInstance(
            id=instance_id,
            type_ref=(
                f"{mandate_with_override.name}@{mandate_with_override.version}"
                if target_override
                else f"{mandate.name}@{mandate.version}"
            ),
            customer_id=command.business_name,
            ring=command.ring,
            heap_region_id=f"tenant_{instance_id}",
            channel_binding=channel_binding,
        )
        try:
            persisted = await state.control.instantiate_mandate(instance)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        # Register the target-overridden variant under a per-instance type id so trigger_run
        # can resolve it directly without rewriting the registry mid-flight.
        if target_override:
            try:
                await state.control.register_mandate_type(mandate_with_override)
            except Exception as exc:  # noqa: BLE001
                # Conflict on the per-instance type id means a previous trigger_run re-registered
                # with the same target; that is safe and we just keep the existing variant.
                from agentx_kernel.errors import MandateTypeConflict

                if not isinstance(exc, MandateTypeConflict):
                    raise HTTPException(status_code=409, detail=str(exc)) from exc
        await _append_manager_action(
            state,
            instance_id=instance_id,
            actor=command.actor,
            action="instantiate",
            detail={
                "type_ref": instance.type_ref,
                "ring": command.ring,
                "target_override": target_override or None,
            },
            run_id=None,
        )
        return {
            "supported": True,
            "instance": persisted.model_dump(mode="json"),
            "mandate_id": mandate_with_override.id,
        }

    @app.post(
        "/commands/trigger-run",
        dependencies=[Depends(_require_command_auth)],
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def trigger_run(command: TriggerRunCommand, request: Request) -> dict[str, Any]:
        state = _state(request)
        from agentx_contracts.mandate import MandateType

        instance_doc = await state.get_doc(c.MANDATE_INSTANCE, command.instance_id)
        if instance_doc is None:
            raise HTTPException(status_code=404, detail=f"unknown instance_id: {command.instance_id}")
        mandate_doc = next(
            (
                doc
                for doc in await state.collection(c.MANDATE_TYPE)
                if f"{doc.get('name')}@{doc.get('version')}" == instance_doc.get("type_ref")
            ),
            None,
        )
        if mandate_doc is None:
            raise HTTPException(
                status_code=404,
                detail=f"unknown type_ref: {instance_doc.get('type_ref')}",
            )
        mandate = MandateType.model_validate(mandate_doc)
        target: JsonObject = dict(mandate.charter.target or {})
        if command.target is not None:
            target.update(command.target)
        mandate = mandate.model_copy(
            update={"charter": mandate.charter.model_copy(update={"target": target})}
        )
        # Re-register the mandate with the merged target so the worker sees it.
        await state.control.register_mandate_type(mandate)
        trigger = DeadlineTrigger(
            ts=datetime.now(UTC),
            reason="dashboard:trigger_run",
            entity_id=f"{command.instance_id}:target",
        )
        now = datetime.now(UTC)
        action = await state.control.enqueue_trigger(
            instance_id=command.instance_id,
            mandate=mandate,
            trigger=trigger,
            mode=command.mode,
            actor=command.actor,
            now=now,
        )
        await _append_manager_action(
            state,
            instance_id=command.instance_id,
            actor=command.actor,
            action="trigger_run",
            detail={"type_ref": mandate.id, "mode": command.mode, "trigger": trigger.model_dump(mode="json")},
            run_id=None,
        )
        from agentx_kernel.scheduler import TriggerWork

        # The work_id is deterministic; the scheduler stores it on enqueue. We mirror the kernel
        # formula so the client can poll without re-fetching from the scheduler.
        work = TriggerWork.schedule(
            mandate=mandate,
            instance=await state.control.instance_binding(command.instance_id),
            trigger=trigger,
            mode=command.mode,
        )
        return {
            "supported": True,
            "work_id": work.work_id,
            "manager_action": action.model_dump(mode="json"),
            "instance_id": command.instance_id,
            "mode": command.mode,
            "status": "queued",
        }

    @app.post(
        "/commands/approve",
        dependencies=[Depends(_require_command_auth)],
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def approve(command: ApprovalCommand, request: Request) -> dict[str, Any]:
        return await _resolve(request, command, decision="approve")

    @app.post(
        "/commands/reject",
        dependencies=[Depends(_require_command_auth)],
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def reject(command: ApprovalCommand, request: Request) -> dict[str, Any]:
        return await _resolve(request, command, decision="reject")

    @app.post(
        "/commands/set-ring",
        dependencies=[Depends(_require_command_auth)],
        status_code=status.HTTP_200_OK,
    )
    async def set_ring(command: SetRingCommand, request: Request) -> dict[str, Any]:
        state = _state(request)
        action = await state.control.set_ring(
            instance_id=command.instance_id,
            ring=command.ring,
            actor=command.actor,
            now=datetime.now(UTC),
        )
        return {"supported": True, "action": action.model_dump(mode="json")}

    # ------------------------- Edit still 501 (gap, intentional) -------------------

    @app.post("/commands/edit")
    async def edit_unavailable() -> JSONResponse:
        return JSONResponse(
            status_code=501,
            content={
                "supported": False,
                "gap": gap_by_id("command.edit_approval"),
                "received": {},
            },
        )

    @app.post(
        "/commands/run-swarm",
        dependencies=[Depends(_require_command_auth)],
        status_code=status.HTTP_200_OK,
    )
    async def run_swarm(command: RunSwarmCommand, request: Request) -> dict[str, Any]:
        """Drive a sim swarm run on the kernel, grade + gate it, persist a synthetic EvalCase.

        The run executes on a SECOND, sim-bound invoker (inside SwarmRunner) so the live registry
        and journal are never touched. EVAL_CASE has no projector, so the graded case is written
        directly; a single ManagerAction(action="run_swarm") records the audit trail.
        """
        state = _state(request)
        # Resolve the candidate MandateType from the catalog; fall back to the canonical lead-finder.
        mandate = await state.control._registry.get_type(command.type_ref)
        if mandate is None:
            from agentx_mandate.library.lead_finder import build_lead_finder_type

            mandate = build_lead_finder_type()

        report = await state.runtime.swarm_runner.run(
            mandate=mandate,
            pack_id=command.pack_id,
            ring=command.ring,
            judge_enabled=True if command.judge_live else None,
        )

        from agentx_contracts.gym import EvalCase

        eval_case = EvalCase(
            id=f"eval_{report.run_id}",
            type_ref=report.type_ref,
            origin="synthetic",
            hydration=report.hydration,
            output=report.output,
            verification_result=report.scorecard.model_dump(mode="json"),
            scorecard=report.scorecard,
            tags=[command.pack_id, "swarm"],
        )
        eval_doc = eval_case.model_dump(mode="json")
        # Mirror score/passed at the top level so the dashboard's mapEvalCases renders the score bar
        # (the seed fixture uses the same shape). EVAL_CASE has no projector — deliberate direct write.
        eval_doc["score"] = report.scorecard.score
        eval_doc["passed"] = report.scorecard.passed
        await state.store.upsert(c.EVAL_CASE, eval_case.id, eval_doc)

        await _append_manager_action(
            state,
            instance_id="foundry",
            actor=command.actor,
            action="run_swarm",
            detail={
                "pack_id": command.pack_id,
                "type_ref": report.type_ref,
                "score": report.scorecard.score,
                "passed": report.scorecard.passed,
                "gate_allowed": report.gate_decision.allowed,
            },
            run_id=report.run_id,
        )

        return {
            "supported": True,
            "run_id": report.run_id,
            "type_ref": report.type_ref,
            "pack_id": report.pack_id,
            "trace": report.trace_payload,
            "scorecard": report.scorecard.model_dump(mode="json"),
            "gate_decision": report.gate_decision.model_dump(mode="json"),
            "eval_case_id": eval_case.id,
        }

    @app.post(
        "/commands/promote",
        dependencies=[Depends(_require_command_auth)],
    )
    async def promote(command: PromoteCommand, request: Request) -> JSONResponse:
        """Phase-4 promote handler — the candidate→live bridge.

        RING-AWARE:

        - L0/L1 (canary): requires human_approved + at least one passing scorecard
          (origin can be synthetic OR real — synthetic is the bridge that lets a
          Creator candidate reach a canary rung before any real run).
        - L2/L3/L4 (autonomous): requires human_approved + real-origin evidence via
          PromotionGate (synthetic-only is barred; invariant #7).

        The server gathers eval_cases by the candidate's type_ref — never accepts
        client-supplied eval_case_ids (that would let an operator cherry-pick favorable
        evidence and defeat the gate).
        """
        state = _state(request)
        from agentx_swarm import PromotionGate, PromotionGateInput

        # 1. Ring validation: must be in {L0, L1, L2, L3, L4} (Pydantic Literal already enforced;
        #    this is the post-validation rejection reason for the gate output).
        if command.ring not in {"L0", "L1", "L2", "L3", "L4"}:
            return _promote_barred(
                reasons=[f"requested ring {command.ring} is not a valid Ring value"],
                ring=command.ring,
            )

        # 2. Look up the candidate draft (the only client input is candidate_id — server
        #    gathers everything else by type_ref, no eval_case_ids accepted).
        candidate_doc = await state.store.get(c.CANDIDATE, command.candidate_id)
        if candidate_doc is None:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={
                    "status": "not_found",
                    "candidate_id": command.candidate_id,
                },
            )

        type_ref = candidate_doc.get("type_ref", "")
        mandate_type_dict = candidate_doc.get("mandate_type")
        if not isinstance(type_ref, str) or not type_ref or not isinstance(mandate_type_dict, dict):
            return _promote_barred(
                reasons=["candidate draft is malformed (missing type_ref or mandate_type)"],
                ring=command.ring,
            )

        # 3. Server-side gather: all eval_cases for this type_ref (regardless of origin).
        # We do NOT strict-validate every case — the run-swarm path persists the case with
        # dashboard-friendly top-level ``score``/``passed`` mirrors that the EvalCase contract
        # doesn't carry (extra='forbid'). The gate cares about ``origin`` and the scorecard
        # sub-document; we read those defensively rather than rebuilding the typed object.
        all_eval_cases = await state.store.find(c.EVAL_CASE, {"type_ref": type_ref})

        from agentx_contracts.gym import EvalCase as _EvalCase
        from agentx_contracts.verification import Scorecard as _Scorecard

        eval_cases: list[_EvalCase] = []
        for case_doc in all_eval_cases:
            if not isinstance(case_doc, dict):
                continue
            origin = case_doc.get("origin")
            scorecard = case_doc.get("scorecard")
            if origin is None or not isinstance(scorecard, dict):
                continue
            try:
                # Drop dashboard-mirror top-level keys (score, passed) that aren't on the contract;
                # build a valid Scorecard sub-doc explicitly (the gate reads eval_case.scorecard.X).
                clean_case = {
                    "id": case_doc.get("id") or f"eval_unknown_{type_ref}",
                    "type_ref": type_ref,
                    "origin": origin,
                    "hydration": case_doc.get("hydration") or {},
                    "scorecard": _Scorecard(
                        origin=scorecard.get("origin", origin),
                        run_id=scorecard.get("run_id", ""),
                        rubric_name=scorecard.get("rubric_name", ""),
                        score=float(scorecard.get("score", 0.0)),
                        passed=bool(scorecard.get("passed", False)),
                    ).model_dump(mode="json"),
                    "reality_outcome": case_doc.get("reality_outcome"),
                    "tags": case_doc.get("tags", []) or [],
                }
                eval_cases.append(_EvalCase.model_validate(clean_case))
            except Exception:  # noqa: BLE001 — malformed rows are skipped.
                continue

        # 4. Ring-aware gate logic.
        canary_rings: set[Ring] = {"L0", "L1"}
        if command.ring in canary_rings:
            reasons, allowed = _canary_gate(
                eval_cases=eval_cases,
                human_approved=command.human_approved,
                ring=command.ring,
            )
        else:
            # L2+ calls the swarm's strict PromotionGate (DO NOT modify — Session I's
            # synthetic-bar test stays valid). We widen allow_rings so the gate enforces
            # ONLY evidence+human (the ring split is OUR concern, not the swarm gate's).
            decision = PromotionGate(allow_rings={"L0", "L1", "L2", "L3", "L4"}).evaluate(
                PromotionGateInput(
                    eval_cases=eval_cases,
                    scorecards=[],
                    human_approved=command.human_approved,
                    requested_ring=command.ring,
                )
            )
            allowed = decision.allowed
            reasons = decision.reasons

        if not allowed:
            return _promote_barred(reasons=reasons, ring=command.ring)

        # 5. ALLOW: register the MandateType + journal ManagerAction(promote).
        try:
            mandate_type = MandateType.model_validate(mandate_type_dict)
        except Exception as exc:  # noqa: BLE001
            return _promote_barred(
                reasons=[
                    f"candidate mandate_type did not validate against the contract: "
                    f"{type(exc).__name__}: {exc}"
                ],
                ring=command.ring,
            )

        try:
            registered = await state.control.register_mandate_type(mandate_type)
        except Exception as exc:  # noqa: BLE001
            return _promote_barred(
                reasons=[
                    f"register_mandate_type failed: {type(exc).__name__}: {exc}"
                ],
                ring=command.ring,
            )

        # Audit row: one ManagerAction(promote) per promotion. instance_id is the Creator
        # instance from the draft (carries through the bridge), run_id None (promote is
        # structural, not run-scoped).
        creator_instance_id = str(candidate_doc.get("creator_instance_id", "creator-unknown"))
        await _append_manager_action(
            state,
            instance_id=creator_instance_id,
            actor=command.actor,
            action="promote",
            detail=cast(
                JsonObject,
                {
                    "candidate_id": command.candidate_id,
                    "type_ref": type_ref,
                    "ring": command.ring,
                    "human_approved": command.human_approved,
                    "eval_case_count": len(eval_cases),
                    "gate_origin": "canary"
                    if command.ring in canary_rings
                    else "promotion_gate",
                    "promoted_at": datetime.now(UTC).isoformat(),
                },
            ),
            run_id=None,
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "promoted",
                "candidate_id": command.candidate_id,
                "type_ref": registered.name + "@" + registered.version,
                "mandate_id": registered.id,
                "ring": command.ring,
                "human_approved": command.human_approved,
                "eval_case_count": len(eval_cases),
                "gate_origin": "canary"
                if command.ring in canary_rings
                else "promotion_gate",
            },
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(request: Request) -> DashboardState:
    return cast(DashboardState, request.app.state.dashboard)


async def _append_manager_action(
    state: DashboardState,
    *,
    instance_id: str,
    actor: str,
    action: str,
    detail: JsonObject,
    run_id: str | None,
) -> None:
    """Append a ManagerAction and apply projections. Used by command endpoints that bypass
    KernelControl when the action is structural (catalog + manager command audit)."""
    from agentx_contracts.journal import ManagerAction

    event_id = f"{instance_id}:manager:{action}:{actor}:{int(datetime.now(UTC).timestamp())}"
    stamped = await state.journal.append(
        ManagerAction(
            event_id=event_id,
            seq=0,
            ts=datetime.now(UTC),
            instance_id=instance_id,
            run_id=run_id,
            actor=actor,
            action=action,
            detail=detail,
        )
    )
    await state.projections.apply(stamped)


def _derive_instance_id(business_name: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "_" for ch in business_name.strip())
    safe = safe.strip("_") or "instance"
    return f"inst_{safe}_{int(datetime.now(UTC).timestamp())}"


async def _resolve(request: Request, command: ApprovalCommand, *, decision: ApprovalDecision) -> dict[str, Any]:
    state = _state(request)
    inbox = await state.control.approval_inbox(instance_id=command.instance_id)
    target = next((item for item in inbox.items if item.run_id == command.run_id), None)
    if target is None:
        raise HTTPException(
            status_code=404,
            detail=f"no parked approval for instance={command.instance_id} run={command.run_id}",
        )
    resolution = await state.control.resolve_approval(
        instance_id=command.instance_id,
        run_id=command.run_id,
        decision=decision,
        actor=command.actor,
        now=datetime.now(UTC),
        edited=command.edited,
    )
    return {
        "supported": True,
        "decision": decision,
        "instance_id": command.instance_id,
        "run_id": command.run_id,
        "work_id": resolution.work_id,
        "work_enqueued": resolution.work_enqueued,
        "manager_action": resolution.action.model_dump(mode="json"),
        "resolution": resolution.resolution.model_dump(mode="json"),
        "status": "queued" if resolution.work_enqueued else "applied",
    }


app = create_app(
    seed_demo=_env_flag("AGENTX_API_SEED_DEMO"),
    start_worker=True,
)
