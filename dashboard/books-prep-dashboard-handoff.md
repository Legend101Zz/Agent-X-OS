# books-prep dashboard handoff

**For:** Claude Code session that will build the books-prep operator surface in `dashboard/`.
**Read first:** This file. Then `docs/books-prep-implementation-handoff.md` (the build handoff). Then `docs/superpowers/specs/2026-06-21-books-prep-and-harness-generalization-design.md` (the design — §6 is the UI-contract section).

**Branch:** `feat/books-prep-mandate` (off `main`). Working tree at `C:\Users\XZNON\Agent-X-OS`.

**What we built on the backend** (already merged into `feat/books-prep-mandate`):
- `books-prep@0.1.0` MandateType registered (charter, faculties, domain pack, settlement)
- `IngestDocumentAdapter` + `ExportLedgerAdapter` (syscall lane)
- `books_prep_playbook` deterministic sim trajectory
- `RulesVerifier` extended with `every ledger_transaction has ...`, `balance_continuity` (per series), `unique ledger_transaction dedupe_key`
- `_ensure_canonical_mandate_registered` auto-seeds both lead-finder and books-prep@0.1.0
- 16 step-7 tests, all green (playbook shape, e2e sim, golden eval, swarm)

**What you build:** the operator-facing surface for books-prep in `dashboard/`. The CA will use this app for 1–2 weeks to test the mandate on their real clients. They need to:
1. Upload a PDF/Excel/CSV bank statement
2. Trigger a books-prep run
3. See the categorized ledger
4. Review the queue (low-confidence + extraction-suspect rows) and approve/reject/edit each row
5. Download the .xlsx output

**Lane fence:** Per `AGENTS.md`, the dashboard is Claude Code's lane. The Python/api lane is NOT writing TypeScript. Backend additions to `api/` for upload + queue + download are a coordination event with Hermes, not this workstream.

---

## What already exists in `dashboard/`

Read `dashboard/README.md` and `dashboard/src/components/` to see the existing shape. Key components:
- `operator-dashboard.tsx` — top-level shell
- `floor-view.tsx` — live + parked runs
- `approval-inbox.tsx` / `approvals-inbox.tsx` — the parked-card inbox
- `instances/instances-list.tsx` + `instances/instance-inspector.tsx` — instance file
- `instances/tabs/{overview,runs,approvals,memory,activity,trust,actions}-tab.tsx` — per-instance tabs
- `blueprints/{catalog-create,create-mandate-wizard,instantiate-drawer}.tsx` — instance creation flow
- `capability-registry.tsx`, `gym/{gym-list,gym-detail}.tsx`, `foundry/foundry-view.tsx` — registry/gym/foundry surfaces

The existing flow is: **Catalog → Create Instance → Instance File → Run Mandate → Approvals → Approve.** Books-prep slots into this flow additively. The existing approval inbox renders the `syscall / args / idempotency_key` shape, which is exactly what `export_ledger` and `queue_manual_action` produce.

---

## What the books-prep operator surface needs

### 1. Instance creation — "Upload documents"

The existing instantiate flow (`create-mandate-wizard.tsx`) takes `type_ref`, `business_name`, `ring`. Books-prep needs one extra field: **a list of document refs**.

The `target_override` JSON already accepts `documents` (list of strings or `{doc_id, path}` dicts) per the caveats. So the existing instantiate form just needs an additive field: a multi-file uploader or a comma-separated path input.

**What it does:**
- User picks one or more PDF/Excel/CSV files from disk
- The component POSTs them to `api/` (see §5 below for the upload endpoint shape)
- On success, it includes the resulting `doc_id` list in the `target_override.documents` of the instantiate POST
- The instantiated type_ref becomes `books-prep@0.1.0`

### 2. Instance file — books-prep-specific tab(s)

The instance inspector already has tabs: overview, runs, approvals, memory, activity, trust, actions. Books-prep needs at minimum:

**a. A "Ledger" tab** (when the instance has at least one settled run with `ledger_transaction` facts)
- Shows the categorized ledger rows: date, narration, ledger_head, gst_treatment, confidence, vendor, gstin, receivable_payable, source citation
- Filterable by ledger_head, by confidence band, by queued status
- Per-row "source citation" link to the originating doc page/line (rendered as `doc:<id> p<page>/l<line>`)

**b. A "Queue" tab** (when there are queued `queue_manual_action` items)
- One card per queued row, showing: narration, current ledger_head guess, confidence, the categorization reason, source citation
- Per-row actions: **Approve** (confirm the guess as-is), **Edit** (change ledger_head + comment), **Reject** (drop the row)
- These map to the existing `/commands/approve`, `/commands/reject`, `/commands/edit` shape

**c. A "Documents" tab** (when the instance has intake documents)
- Lists the documents in `target.documents`
- Per-doc status (ingested, structural-error-bounced, etc.)

### 3. Run details — the books-prep-specific journal view

The existing `run-detail.tsx` already renders trace events. Books-prep runs have a recognizable shape:
- A `thought` event with summary containing "sim synthetic" or "native ingest" (when in sim mode) OR a `syscall_result` for `ingest_document` (live mode)
- One or more `syscall_result` events for `queue_manual_action`
- One `parked` event for `export_ledger` (when ring < L1) OR one `syscall_result` for `export_ledger` (when ring ≥ L1)
- A `verify` event with fact_count

**What to add:** filter buttons / badges in the run-detail timeline that highlight books-prep-specific events (`ingest_document`, `queue_manual_action`, `export_ledger`) and show the categorizer's output per row inline.

### 4. .xlsx download

When the `export_ledger` call has settled (status="ok" in the journal), the .xlsx file lives at the path stored in the syscall result's output (`output.path`). The run-detail view should expose a "Download ledger" button that links to a new endpoint:

- `GET /runs/{run_id}/artifacts/export_ledger` → streams the .xlsx file with `Content-Disposition: attachment`

This needs a corresponding `GET` endpoint in `api/` (currently the api only has POST commands). **Coordinate with the kernel/api lane** — this is a new read endpoint, not a contract change.

### 5. Backend additions needed (NOT your work — file a coordination event)

The dashboard will need these backend endpoints to fully exercise books-prep. None exist yet. They are additive (no contract change).

**a. File upload** — `POST /commands/upload`
- Accepts multipart/form-data with one or more files
- Stores them in the configured `books_intake_dir`
- Returns `{"doc_id": "...", "path": "..."}` per file
- Auth: bearer operator token (same as existing commands)
- Status: 201 on success, 413 if too large, 415 if unsupported extension

**b. Per-row queue approval** — already works via existing `/commands/approve`, but the queue_manual_action card shape needs `args.transaction` (the full ledger row) surfaced in the approval card. Verify the existing approval card renders this — if it doesn't, the kernel/api lane needs to surface `args.transaction` as a top-level field on the card.

**c. .xlsx download** — `GET /runs/{run_id}/artifacts/export_ledger`
- Returns the file at the path stored in the export_ledger syscall result
- Auth: bearer operator token
- Status: 200 with xlsx body, 404 if no export_ledger result for that run

**d. Run fact query** — `GET /runs/{run_id}/facts?predicate=ledger_transaction`
- Returns the list of `ledger_transaction` facts for that run
- Used to render the Ledger tab

---

## Constraints (from AGENTS.md, invariants, caveats)

1. **No new contract.** The `MandateType`, `MandateInstance`, `Fact`, `SyscallRequest` shapes are frozen. The dashboard reads projections, writes through commands.

2. **No direct DB access.** Dashboard hits the api. Period.

3. **CORS.** Add the dashboard origin to `AGENTX_CORS_ORIGINS` env var on the api side. Default is same-origin (blocks cross-origin). For local dev: `http://127.0.0.1:3000`.

4. **Operator token.** All command writes need the bearer. Existing dashboard handles this; books-prep inherits.

5. **Auth.** Books-prep is a single-tenant CA account for v0. No client logins, no multi-tenant. The CA uses their operator token; their clients are folders.

6. **Lane separation.** You're building the UI. The kernel/api lane is building the new endpoints. Don't write Python backend — file a coordination request.

---

## What NOT to build

- **No Stripe / billing.** Separate workstream.
- **No multi-CA signup.** Single-tenant.
- **No client logins.** CAs handle their clients; clients don't log in to anything in v0.
- **No new mandate types.** Books-prep is the only mandate this app needs to surface for now; gst-recon and collections plug in later.
- **No GSTR-2B / Tally / Zoho export.** Out of scope.
- **No OCR/vision for scanned PDFs.** Scanned PDFs route to `human_task`; no special UI needed.

---

## File anchor cheat sheet

For books-prep on the backend:
- MandateType: `packages/mandate/src/agentx_mandate/library/books_prep.py` (id=`type_books_prep_v0`, name=`books-prep`)
- Playbook: `packages/mandate/src/agentx_mandate/library/books_prep_playbook.py`
- Adapters: `packages/syscall/src/agentx_syscall/books.py` (`IngestDocumentAdapter`, `ExportLedgerAdapter`)
- Domain pack: `packages/mandate/src/agentx_mandate/library/indian_smb_books.py`
- Seed helper: `api/src/agentx_api/app.py` `_ensure_canonical_mandate_registered` (~line 93)

For the dashboard:
- Top-level: `dashboard/src/components/operator-dashboard.tsx`
- Catalog: `dashboard/src/components/blueprints/`
- Instances: `dashboard/src/components/instances/`
- Approvals: `dashboard/src/components/approval-inbox.tsx`
- Floor: `dashboard/src/components/floor-view.tsx`
- API base URL: `dashboard/.env.local` (set `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000`)
- Existing tests: `dashboard/tests/*.test.ts`

---

## Suggested coordination events (file with Hermes / kernel-api lane)

1. **Add `POST /commands/upload`** — multipart file upload, stores in `books_intake_dir`, returns doc_id+path. **Priority: P0**, blocker for the dashboard upload UI.

2. **Add `GET /runs/{run_id}/artifacts/export_ledger`** — streams the .xlsx. **Priority: P0**, blocker for the download button.

3. **Add `GET /runs/{run_id}/facts?predicate=...`** — query ledger_transaction facts for the Ledger tab. **Priority: P1**.

4. **Surface `args.transaction` as top-level on the approval card** for `queue_manual_action` so the existing approval inbox can render the queued row inline. **Priority: P1**.

5. **Document books-prep's intake folder in the api config** so `POST /commands/upload` knows where to write. Currently `books_intake_dir` is a parameter to `build_phase1_registry`; needs to be env-driven for the dashboard's upload to land somewhere accessible. **Priority: P0**.

---

## Acceptance criteria for this dashboard work

When you're done, the CA can:
1. Open the dashboard, paste the operator token
2. Click Catalog → Create Instance → pick `books-prep@0.1.0`, fill in business name, upload 1+ PDFs, click Create
3. Land on the Instance File → click Run Mandate → pick `mode=sim` for dry run OR `mode=live` for real
4. Watch the journal stream (SSE) fill in real-time
5. Click the Queue tab → see the per-row queue cards with source citation → click Approve/Edit/Reject
6. Click the Ledger tab → see the categorized ledger rows
7. Click Download .xlsx → get the file with the three sheets (Ledger, Review Queue, Summary)

If any of those steps fail because a backend endpoint doesn't exist, file the coordination event and stop. Don't work around it with a client-side hack.

---

## What I (the kernel/api lane) did NOT do

- Did NOT add file upload, .xlsx download, or run-fact query endpoints — those are coordination events
- Did NOT change any contracts — `MandateType`, `MandateInstance`, `Fact`, `SyscallRequest` shapes unchanged
- Did NOT add multi-tenant auth or Stripe — out of scope
- Did NOT build a CRDT-style live-collaboration view of the queue — that's overkill for v0; the existing SSE polling pattern (8-second refresh) is fine

If you find yourself needing any of those for books-prep specifically, push back: there's probably a simpler design that fits the existing command surface.

---

## Test plan for the dashboard work

After you build, the CA test flow is:
1. Hand the CA a URL pointing at a fresh dashboard instance, with a pre-baked operator token
2. CA uploads their own real client statements (HDFC, SBI, ICICI PDFs)
3. CA runs books-prep in `mode=live` against the real PDFs
4. CA reviews the queue, makes corrections, approves
5. CA downloads the .xlsx
6. CA runs again on a different month's statement for the same client — verify the queue rate drops (the gym / cross-batch dedup is working)

A green engineering gate does NOT mean revenue-ready. The CA's "I'd pay for this" verdict after this 1-2 week test is the P2-1 acceptance criterion.