# Design — `books-prep` mandate + harness generalization

*Date: 2026-06-21. Status: awaiting approval. Companion docs: [docs/README.md](../../README.md) (mandate anatomy), [AGENTS.md], [.importlinter].*

---

## 1. Goal, in one paragraph

Ship a second revenue-ready MandateType — **`books-prep`** — that takes an Indian SMB's raw financial-document dump (v0: **digital-text PDF bank statements + Excel/CSV**) and produces a **clean, categorized, source-cited transaction ledger as an Excel file**, with every low-confidence or ambiguous line pushed to a **CA review queue** instead of being silently finalized. It is an *assistant that prepares the books for a CA to review and finalize* — never an autopilot that closes the books. To build it cleanly we also **generalize the Hermes runner** (today hard-wired to lead-finder's tools + prompt) so a mandate's tool set and system prompt are *derived from its faculties and charter*, and add an **optional Gemini toggle** for the model transport. Both changes are strictly additive: lead-finder must keep working byte-for-byte, and the dashboard↔backend contract must not change.

This design is the consensus shape the market already validated: even >98%-accurate OCR tools "still require lightweight approval queues for low-confidence items." We build that shape on an architecture the OCR tools lack — per-business heap (context gravity), an eval gym fed by CA corrections, and journaled, auditable receipts.

---

## 2. v0 scope (and explicit non-goals)

**In scope (v0):**
- Input: digital-text PDF bank statements (downloaded from net-banking) and Excel/CSV exports.
- Extraction: deterministic parsing (no LLM, no API) of date / debit / credit / running-balance / narration / reference fields.
- Categorization: MiniMax (via Hermes) maps each transaction → a ledger head + GST treatment + a confidence score; resolves vendor from the narration.
- Verification ladder: rules (schema, running-balance continuity, duplicate detection, sign sanity, GSTIN format) → judge (categorization plausibility) → **human (the CA review queue)** → reality (CA accept/correct).
- Output: a clean Excel ledger (one row per transaction, every row citing its source doc + page/line) plus a review-queue of flagged items.
- Settlement: clean transactions commit to the business's heap region; CA corrections feed the gym; one billing line per document batch.

**Explicit non-goals (deliberately deferred):**
- Scanned/photo statements and receipt images → route to `human_task` fallback in v0 (OCR / vision is a later add; see §8 Gemini).
- GSTR-2B / ITC reconciliation, GSTR-1/3B prep, TDS → a **separate `gst-recon` mandate**, spawned from a settled books-prep run (the composition story; not v0).
- Direct Tally / Zoho integration → Excel first; export adapters for Tally/Zoho are later.
- Multi-tenant signup / Stripe billing → separate workstream, not this spec.

---

## 3. Architecture — division of labor

The blueprint invariant "no brain does I/O directly" decides the split cleanly:

```
TRIGGER: CA provides a document batch for a client-business instance
   │
   ▼
[ ingest_document ]  syscall → adapter (pdfplumber / pypdf / openpyxl)   READ class, no LLM, no API
   │   returns: structured rows + per-row source citation (doc + page/line) + raw text snippet
   ▼
[ Hermes / MiniMax ]  the brain: for each row → ledger head + GST treatment + confidence + vendor
   │   (reuses faculties: judgment, enrichment; commits via memory-craft; flags via escalation)
   ├── confidence ≥ threshold  → claim_facts (clean transaction → heap)
   └── confidence <  threshold  → queue_manual_action (→ CA review card; or human_task fallback)
   ▼
[ export_ledger ]  syscall → adapter (openpyxl)  → clean Excel deliverable   REVERSIBLE_WRITE, L1 gated
   ▼
VERIFY (rules → judge → CA queue → reality)  →  SETTLE (heap + gym + billing line)
```

Why this is fast: the *new* real-world work is two deterministic adapters (`ingest_document`, `export_ledger`); everything else is reused (verification ladder, settlement, approval/park machinery, the heap, the gym). The MandateType itself is ~60 lines of declarative config, exactly like `lead_finder.py`.

---

## 4. Component-by-component design

### 4.1 The `books-prep` MandateType (new — `agentx_mandate`)
`packages/mandate/src/agentx_mandate/library/books_prep.py`, mirroring `lead_finder.py`:

- **Charter** `goal`: "Turn a business's raw financial-document dump into a clean, categorized, source-cited transaction ledger ready for CA review." Postconditions (all `rung="rules"`, mechanically checkable):
  - `has_transactions` — at least one transaction fact claimed.
  - `every_txn_has_source` — every claimed transaction carries a source citation (doc id + page/line).
  - `every_txn_categorized` — every transaction has a ledger head + GST treatment + confidence.
  - `low_confidence_queued` — no transaction below the confidence threshold is finalized without a queued review card.
  - `balance_continuity` — running-balance continuity holds across the statement, or each break is flagged.
  - `constraints`: never invent a transaction with no source; read-only on source docs; never moves money (books only).
  - `target`: `{ "documents": [...refs], "output_format": "xlsx", "confidence_threshold": 0.8 }` (the trigger carries the actual doc refs per run).
- **Faculties** (bindings):
  - `extraction` (**new, thin** — `tool_manifest: ["ingest_document"]`),
  - `judgment` (reuse — categorize), `enrichment` (reuse — vendor resolve),
  - `memory-craft` (reuse — claim clean transactions), `escalation` (reuse — flag to CA),
  - `ledger-export` (**new, thin** — `tool_manifest: ["export_ledger", "queue_manual_action"]`).
- **Domain pack** `indian-smb-books@0.1.0` (new): Indian chart-of-accounts conventions, common ledger heads, GST rate/HSN hints, the §17(5) blocked-credit list, narration→vendor patterns (UPI/IMPS/NEFT/POS), bank-format quirks. Versioned data, not prompt text.
- **Verification**: rules refs + judge rubrics for categorization quality (reuse the `VerificationSuite` shape).
- **Settlement**: `fact_commit_confidence` for probationary transactions, `watch_window_hours` for CA acceptance, `billing_per_run`, and a deferred **spawn rule** stub `on books_ready → spawn gst-recon` (declared, not implemented in v0).
- **service_ports**: `["clean_ledger"]`.

### 4.2 Two new faculties (new — `agentx_mandate`)
Each is data (a `Faculty` instance) plus a `propose` function, registered in `faculties/__init__.py` (`FACULTY_LIBRARY` + `_PROPOSERS`). They are thin: `extraction` declares it may request `ingest_document`; `ledger-export` declares `export_ledger` + `queue_manual_action`. Their `skill_pack` refs point at books-prep prompt artifacts (see §4.6). No new harness concepts — they ride the existing `tool_manifest` seam.

### 4.3 Two new syscall adapters (new — `agentx_syscall`)
`packages/syscall/src/agentx_syscall/adapters.py` (+ registry wiring in `registry.py`):
- **`IngestDocumentAdapter`** — `name="ingest_document"`, risk class `read`, maturity `automated`. Parses a document ref:
  - text PDF → `pdfplumber` (tables) with `pypdf` fallback; Excel/CSV → `openpyxl` / stdlib `csv`.
  - Output: `{ "transactions": [ {date, narration, debit, credit, balance, ref, source:{doc_id,page,line}} ... ], "doc_id": ..., "unparsed": [...] }`.
  - Scanned/image PDF (no extractable text) → returns `status="error"` with a clear reason, so the run loop feeds it back and the agent routes to `queue_manual_action` / the `human_task` tail.
- **`ExportLedgerAdapter`** — `name="export_ledger"`, risk class `reversible_write` (L1 — parks for approval), maturity `automated`. Writes the categorized rows to an `.xlsx` via `openpyxl` into a configured output dir; returns the file path + a row count in `output`.
- Both ship a `SyscallTestCase` fixture (the plugin contract) and a `verify` self-check. Registered in `build_phase1_registry`. Until registered they would fall to `human_task`; we register them so v0 is real.
- **New deps** (syscall package `pyproject.toml`): `pdfplumber`, `pypdf`, `openpyxl`. (Python 3.12.)

### 4.4 The tool-schema registry (new — **`agentx_contracts`**, forced by import-linter)
**Constraint:** `.importlinter` forbids `agentx_kernel` (home of `hermes_runner`) from importing `agentx_syscall`. So the syscall→tool-schema mapping the runner needs **must live in `agentx_contracts`** (the shared seam both lanes may import).

New module `packages/contracts/src/agentx_contracts/toolschema.py`:
- A `ToolSchema` model: `{ syscall_name, tool_name (as exposed to the LLM), description, parameters (JSON schema), risk_class, arg_normalizer_ref (optional str) }`.
- A `TOOL_SCHEMAS: dict[str, ToolSchema]` registry keyed by syscall name, covering every syscall a harness may expose: the existing lead-finder set (`lead_research_batch`→tool `search_leads`, `read_url`, `draft_email`) **plus** the new `ingest_document`, `export_ledger`, `queue_manual_action`. The lead-finder entries reproduce today's exact schemas/descriptions so generated tools are byte-identical (regression-locked, see §7).
- The three **control tools** (`think`, `claim_facts`, `finish`) stay defined in the runner — they are harness-control, not syscalls.

### 4.5 Generalizing the Hermes runner (modify — `agentx_kernel/hermes_runner.py`)
Replace the hard-coded lead-finder constants with mandate-derived construction. The runner already receives the mandate context; we thread the faculty list + charter through:
- **`_TOOLS`** → built dynamically: control tools (`think`, `claim_facts`, `finish`) + one function per syscall in the **union of the mandate's faculties' `tool_manifest`s**, each schema looked up in `agentx_contracts.toolschema.TOOL_SCHEMAS`. For lead-finder this reproduces the current four tools exactly.
- **`_RISK_BY_SYSCALL`** → sourced from `TOOL_SCHEMAS` (delete the hard-coded dict).
- **System / user prompt** → composed from the mandate: `charter.goal` + `charter.constraints` + the faculties' `skill_pack` prompt fragments + the `target`. A small `PromptComposer` builds it. **Lead-finder gets a `lead_finder` skill_pack whose composed prompt equals the current hard-coded prompt** (regression-locked).
- **`_to_action`** → generic: tool name maps to its `syscall_name` via the registry; args pass through, with an optional named `arg_normalizer` (kept as a tiny kernel-side function table, default identity) to preserve lead-finder's `search_leads → lead_research_batch {criteria,count}` shaping. New syscalls use identity (tool name == syscall name).
- **`HermesRunner.start`** signature already takes `context` + `faculties`; we additionally pass the `MandateType` (or the charter + faculty list) so the session can build its tools/prompt. The continuation `export_state`/`restore_state` shape is unchanged (history + counters), so parked-run resume still works.

### 4.6 Run-loop coupling to unwind (modify — `agentx_kernel/run_loop.py`)
Three lead-finder-specific spots must become mandate-driven without breaking lead-finder:
- **`_runner()` default playbook** (`run_loop.py:259`, `OwnHarness(playbook=lead_finder_playbook)`): replace with a `sim_playbook_for(mandate)` resolver — a small `{type_name → playbook}` map defaulting to `lead_finder_playbook`. Add a `books_prep_playbook` (deterministic) so the **swarm can drive books-prep in sim**.
- **`_apply_read_result`** (`run_loop.py:561`): generalize to a per-syscall read-result handler registry. Keep `lead_research_batch` / `read_url` handlers; add an `ingest_document` handler that stashes parsed transactions on `ctx.scratchpad["transactions"]`. Default handler stashes raw output under `scratchpad[syscall_name]`.
- **`_fulfill_sim_native_read`** (`run_loop.py:579`): add an `ingest_document` sim branch returning synthetic, clearly-marked transactions; keep the lead branches.
- The line `if outcome.result.status == "ok" and request.name != "lead_research_batch"` (`run_loop.py:549`) stays correct; verify it doesn't need a books-specific exclusion.

### 4.7 Books-prep skill packs / prompt artifacts (new — `agentx_mandate`)
A books-prep system-prompt fragment per new faculty (extraction: "call `ingest_document` for each provided doc ref, never invent rows"; judgment-for-books: "categorize each transaction into an Indian ledger head + GST treatment, output a confidence 0..1, cite the narration text you used"; ledger-export: "queue low-confidence rows; export the rest"). Stored as the faculties' `skill_pack` data, consumed by the `PromptComposer`.

---

## 5. The Gemini toggle (modify — `agentx_contracts/config.py` + runner construction)

Gemini exposes an **OpenAI-compatible chat endpoint**, and Hermes already drives an OpenAI-compatible `ChatTransport`. So the toggle is *just a transport/model selection at construction time* — no runner rewrite:
- New `Settings` fields (in `config.py`): `use_gemini: bool = False`, `gemini_api_key: SecretStr | None = None`, `gemini_model_id: str = ""` (e.g. `gemini-2.5-flash`), `gemini_base_url: str = ""` (the OpenAI-compat base).
- A `build_faculty_transport(settings)` factory (kernel-side bootstrap, where creds already live) returns a Gemini-pointed transport when `use_gemini` is true **and** a key is present; otherwise the MiniMax transport. **Default off → MiniMax → nothing changes.**
- This also satisfies the hackathon's "≥1 Gemini call in production" requirement when flipped on, with zero architectural change. Multimodal (scanned docs) is a *future* extension of the transport (image parts) — out of v0 scope.

---

## 6. Preserving the UI↔backend contract

The dashboard talks to a **generic** surface: `/commands/instantiate`, `/commands/trigger-run`, `/approvals`, `/commands/approve`, `/events` (SSE), `/runs/{id}`, `/journal`, `/scheduler-work/{id}`. None of these change.
- **Approval cards** are already generic: `{syscall, args, idempotency_key}` (`run_loop.py:509`). New syscalls (`export_ledger`, `queue_manual_action`) render in the existing approval-inbox with no contract change.
- **Instantiate/trigger** are parameterized by `type_ref` and a trigger payload; `books-prep@0.1.0` flows through unchanged once registered in the catalog (mirror `_ensure_canonical_mandate_registered`, `app.py:93`).
- **Providing documents to a run (the one genuinely new input):** v0 uses a **local intake folder** + the trigger's `target.documents` naming the file(s); `IngestDocumentAdapter` reads from the configured dir. This needs **no new endpoint** and no contract change. The studio-view gets an *additive* optional "document path(s)" field (purely additive; lead-finder's studio flow is untouched). A first-class `/commands/upload` endpoint is a later nicety, not v0.
- **Backward compatibility:** lead-finder's instantiate→find→approve→send flow is byte-for-byte unchanged; regression tests lock this (§7).

---

## 7. Non-breaking strategy + testing

The gate (`uv run pytest -q`, `mypy --strict`, `ruff`, `lint-imports`) must stay green. Specific guards:
- **Regression-lock lead-finder:** a test asserting the generalized runner's generated `_TOOLS` for `lead-finder` equals the current hard-coded list, and the composed system prompt equals the current prompt string. If these match, live lead-finder behavior is preserved by construction.
- **Import-linter:** new `toolschema.py` lives in `agentx_contracts` (allowed by all contracts). Confirm `lint-imports` passes — the kernel imports the registry from contracts (legal), never from `agentx_syscall` (forbidden). Adapters import their schema from contracts too.
- **New unit tests:** `IngestDocumentAdapter` (sample digital PDF + Excel + CSV fixtures; a scanned-PDF fixture → error path), `ExportLedgerAdapter` (writes a valid xlsx; verify self-check), the tool-schema registry, `build_books_prep_type` (builds + verifies), the `books_prep_playbook` (deterministic sim run end-to-end), and a swarm run over books-prep.
- **Mandate package may not import config/security/db** (invariant #2): the new faculties + MandateType hold only names/data; adapters (syscall lane) hold the parsing libs and may not import the kernel/mandate lane. Keep the layering clean.
- Run the **whole** existing suite to confirm zero regressions before any new feature is called done.

---

## 8. Build order (the plan-of-changes summary)

1. `agentx_contracts`: add `toolschema.py` (`ToolSchema` + `TOOL_SCHEMAS` incl. lead-finder + new syscalls) and the Gemini `Settings` fields. *(Pure additive; nothing consumes it yet.)*
2. `agentx_kernel/hermes_runner.py`: build `_TOOLS`, risk map, and prompt from the mandate + registry; add `PromptComposer`; keep arg-normalizer table. Regression-lock lead-finder.
3. `agentx_kernel/run_loop.py`: `sim_playbook_for`, generalized `_apply_read_result` + `_fulfill_sim_native_read`.
4. `agentx_syscall`: `IngestDocumentAdapter` + `ExportLedgerAdapter` (+ deps), register in `build_phase1_registry`, ship test cases.
5. `agentx_mandate`: `extraction` + `ledger-export` faculties, `books_prep.py` MandateType, `books_prep_playbook`, `indian-smb-books` domain pack, books skill packs.
6. Kernel bootstrap / `app.py`: `build_faculty_transport` (Gemini toggle); register `books-prep@0.1.0` in the catalog (mirror lead-finder); additive studio "document path" field.
7. Tests across all of the above; run the full gate; confirm lead-finder regression-locked and `lint-imports` green.

Each step is independently testable; lead-finder stays green throughout.

---

## 9. Open questions / risks

- **Digital-PDF parsing variance across banks** (SBI/HDFC/ICICI layouts differ). v0 mitigates by: deterministic table extraction + the rules rung (balance continuity) catching mis-parses + the CA queue catching the rest. Bank-specific parsing profiles are a domain-pack growth area, not a blocker.
- **Confidence threshold tuning** — start at 0.8; the gym + CA corrections calibrate it. It's a `target`/instance override, not hard-coded.
- **`arg_normalizer` for `search_leads`** is the one non-data shaping we keep kernel-side; if it proves awkward, fold the transform into the lead-finder skill pack instead. Either way it's isolated.
- **Continuation/resume across the new syscalls** — `export_ledger` parks at L1; confirm the parked-run resume path (`run_loop.resume`) replays it correctly (covered by a test).
