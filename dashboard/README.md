# dashboard/ - Agent-X Operator Dashboard

A separate Next.js/React application that consumes the FastAPI service in `../api`. It never reads
Mongo or credentials directly.

## Surfaces

1. Floor with live and parked runs plus the journal stream.
2. **Approval Inbox** reading the first-class `/approvals` endpoint (parked `RunParked` events
   awaiting a manager decision — distinct from the manual-queue human-task tail). Working Approve
   and Reject buttons that POST with the bearer token.
3. **Mandate catalog** with a working **Create Instance** form (POSTs `/commands/instantiate`).
4. Instance files with facts, provenance, trust, ring, threads, runs, P&L, and a **Run Mandate**
   button (POSTs `/commands/trigger-run`).
5. Run detail with hydration, trace, syscall, park, verification, and settlement events.
6. Capability registry with maturity, health, credential boundary, and queue volume.
7. Filterable audit ledger.
8. Foundry view — gated behind real `eval_cases` (synthetic cases are listed; promote stays
   501 until the kernel exposes that command).

The client refreshes from the API every eight seconds.

## Operator token + live-mode fail-closed

The API is **internal/local-only by design** (BLUEPRINT §6) — do not expose it to the public
internet. Every command route requires `Authorization: Bearer <AGENT...N>` matching
`AGENTX_OPERATOR_TOKEN` in the API process. The dashboard:

1. Stores the token in `localStorage` after you paste it into the "Operator Token" field in the
   side rail. Without it, every command button is disabled.
2. Sends the token on every `POST /commands/*` and on `GET /scheduler-work/{id}`.
3. Fails **closed** in live mode: if the API is unreachable, the dashboard renders a blocking
   "disconnected" overlay instead of pretending to be operational on fixture data.
4. CORS is restricted to `AGENTX_CORS_ORIGINS` (comma-separated). Same-origin by default.

To run the dashboard against the API with command writes enabled:

```bash
cd api
AGENTX_OPERATOR_TOKEN="$(openssl rand -hex 32)" \
AGENTX_CORS_ORIGINS="http://127.0.0.1:3000" \
uv run uvicorn agentx_api.app:app --reload --port 8000

# In another shell
cd dashboard
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

Paste the same token into the dashboard's "Operator Token" field. Then Catalog → Create Instance →
Instance File → Run Mandate → Approvals → Approve.

## Development

```bash
npm install
npm run dev
```

The API defaults to `http://127.0.0.1:8000`. Override it with:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

## Verification

```bash
npm test
npm run build
```

Note: `npm test` runs `tsx --test tests/*.test.ts`, which needs Node ≥ 18. On systems where the
default `node` is older (e.g. macOS ships v16), prefix with `PATH=/opt/homebrew/bin:$PATH`.

