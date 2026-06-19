# api/ — Agent-X Operator API

Thin FastAPI surface over the lifespan-owned `OperatorRuntime` (see `agentx_api/operator.py`).
Reads journal + projection collections, the mandate catalog, the manual-task repository, and the
syscall registry. Commands call the kernel's existing `KernelControl` paths; **no command
endpoint constructs a registry, journal, or invoker on its own.**

## Run

```bash
cd api
# Local-only by default. Set a bearer token to enable commands; set CORS origins if the
# dashboard is on a different origin.
AGENTX_OPERATOR_TOKEN="$(openssl rand -hex 32)" \
AGENTX_CORS_ORIGINS="http://127.0.0.1:3000" \
uv run uvicorn agentx_api.app:app --reload --port 8000
```

Without `MONGODB_URI` in `.env`, the API runs against the in-memory OperatorRuntime (tests, sim).
Set `MONGODB_URI` + `MONGODB_DB_NAME` and the lifespan will construct a Mongo-backed runtime.

`AGENTX_API_SEED_DEMO=1` injects the legacy demo instance + one parked approval card on startup
(memory mode only).

## Endpoints

| Path | Method | Notes |
| --- | --- | --- |
| `/health`, `/system/info` | GET | Mode + posture. |
| `/system/overview`, `/instances`, `/instances/{id}`, `/runs`, `/runs/{id}` | GET | Read-side. |
| `/approvals` | GET | First-class approval inbox (separate from `/manual-queue`). |
| `/manual-queue` | GET | Human-task tail only. |
| `/mandate-types`, `/journal`, `/events`, `/capabilities`, `/eval-cases`, `/core-gaps` | GET | Read-side. |
| `/scheduler-work/{work_id}` | GET | One scheduler row status. |
| `/commands/instantiate` | POST | 201. |
| `/commands/trigger-run` | POST | 202, returns `work_id`. |
| `/commands/approve`, `/commands/reject` | POST | 202. Approve enqueues `ApprovalWork`. |
| `/commands/set-ring` | POST | 200. |
| `/commands/edit`, `/commands/run-swarm`, `/commands/promote` | POST | 501 (genuinely open). |

`/commands/*` require `Authorization: Bearer <AGENTX_OPERATOR_TOKEN>`. Without the token they all
return 401 (fail closed).
