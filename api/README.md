# api/ — Agent-X Operator API

Thin FastAPI surface over the existing kernel command/query pieces. It reads the journal,
projection collections, mandate catalog collections, and syscall registry; commands only call the
current `KernelControl` command methods.

```bash
cd api
AGENTX_API_SEED_DEMO=1 uv run uvicorn agentx_api.app:app --reload --port 8000
```

Set `MONGODB_URI` and `MONGODB_DB_NAME` in `.env` to use Mongo through the existing config loader.
Without `MONGODB_URI`, the API runs in memory. Tests and frontend fallback use the seeded demo
state via `create_app(use_mongo=False, seed_demo=True)`.

Unsupported dashboard commands return HTTP 501 with a `core-gap` payload instead of mutating kernel
packages.
