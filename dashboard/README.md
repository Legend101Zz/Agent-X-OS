# dashboard/ - Agent-X Operator Dashboard

A separate Next.js/React application that consumes the FastAPI service in `../api`. It never reads
Mongo or credentials directly.

## Surfaces

1. Floor with live and parked runs plus the journal stream.
2. Approval inbox with working approve and explicit core-gap states for edit/reject.
3. Mandate catalog and staged instance creation.
4. Instance files with facts, provenance, trust, ring, threads, runs, and P&L.
5. Run detail with hydration, trace, syscall, park, verification, and settlement events.
6. Capability registry with maturity, health, credential boundary, and queue volume.
7. Filterable audit ledger.
8. Foundry view for real versus synthetic eval evidence and promotion status.

The client refreshes from the API every eight seconds and falls back to fixtures when the API is
unavailable.

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
npm audit --omit=dev
```
