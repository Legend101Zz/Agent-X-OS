# books-prep implementation — working handoff

**Branch:** `feat/books-prep-mandate` (off `main`). **Goal:** build the `books-prep`
MandateType + generalize the Hermes runner. Sources of truth (read all three):
- `docs/superpowers/specs/2026-06-21-books-prep-and-harness-generalization-design.md` (design)
- `docs/books-prep-caveats-and-corrections.md` (OVERRIDES the design where they differ)
- `docs/BOOKS_PREP_DESIGN.html` (visual)

Apply caveats overrides: revised charter (not design §4.1), fold P0-1/P0-2/P0-3 into steps 4–5,
add P1 golden-eval in step 7. STOP & flag genuine spec-vs-code conflicts instead of guessing.

## Gate (run after EVERY step; must stay green)
```
uv run pytest -q                                # workspace
cd api && uv run pytest -q && cd ..             # api (separate)
uv run ruff check .
uv run mypy --strict packages db tests
cd api && uv run mypy --strict src tests && cd ..
uv run lint-imports                             # 3 kept / 0 broken
```
Baseline on this branch: workspace pytest GREEN (confirmed before any edits).

## Decisions locked
1. **Tool derivation (operator-approved):** generalized runner exposes only manifest syscalls
   that HAVE a `ToolSchema` (drops `score_lead`, which stays native). Add a thin lead-finder
   **`outreach`** faculty `tool_manifest=["draft_email"]`, bound LAST in `lead_finder.py`, so the
   union (in faculty-binding order) is `[lead_research_batch, read_url, draft_email]` →
   `[search_leads, read_url, draft_email]`, byte-identical to today's `_TOOLS`.
2. **Prompt composition:** kernel `PromptComposer` dispatches by mandate name — `lead-finder`
   uses the LEGACY `_system_prompt`/`_user_prompt` (byte-identical, regression-locked); all other
   mandates use a GENERIC composer (charter.goal + constraints + skill-pack fragments + target).
   books-prep uses generic. ("3rd mandate is just config.")
3. **Verifier:** `RulesVerifier` only understands `claimed_facts <op> N` and `fact:<pred> exists`.
   Extend it (kernel lane, NOT a contract change) with books-prep universal-quantifier exprs over
   transaction facts. New expr forms documented in verifier.py.
4. **Transaction Fact encoding:** each clean txn → ONE `Fact`, `predicate="ledger_transaction"`,
   `subject=<dedupe_key>`, `object=<JSON payload>` (ledger_head, gst_treatment, vendor, gstin,
   state, missing_supporting_doc, receivable_payable, balance, account_id, statement_period,
   extraction_confidence, extraction_suspect, queued flag), `confidence=<categorization conf>`,
   `provenance.evidence=[<source citation: doc_id+page/line>]`.
5. **Cross-batch dedup (P0-2):** dedupe guard in the ingest/commit path against hydration-snapshot
   facts + within-batch; `no_duplicate_commit` postcondition checks within-batch key uniqueness.
6. **confidence_threshold:** default 0.8 (PROVISIONAL); golden-eval (P1) reports calibration +
   false_confidence_rate as OBSERVATIONAL, not a CI gate. Don't fake a calibrated bar.

## Build order (7 steps; commit `[claude]` after each green step)
1. `agentx_contracts/toolschema.py` (`ToolSchema` + `TOOL_SCHEMAS`: lead_research_batch→search_leads,
   read_url, draft_email + new ingest_document, export_ledger, queue_manual_action) + Gemini Settings
   fields (use_gemini=False, gemini_api_key, gemini_model_id, gemini_base_url). Pure additive.
2. `agentx_kernel/hermes_runner.py`: build `_TOOLS`, risk map, prompt FROM the mandate; PromptComposer;
   keep arg-normalizer table. REGRESSION-LOCK test: lead-finder tools+prompt byte-identical.
3. `agentx_kernel/run_loop.py`: `sim_playbook_for(mandate)` resolver (default lead_finder); per-syscall
   read-result handler registry (+ ingest_document handler); ingest_document sim-native branch.
4. `agentx_syscall`: `IngestDocumentAdapter` (pdfplumber/pypdf/openpyxl/csv → rows + per-row source +
   per-row extraction_confidence; scanned/no-text or >frac structural-fail → status="error"),
   `ExportLedgerAdapter` (openpyxl → .xlsx, reversible_write/L1). Register in build_phase1_registry.
   SyscallTestCase fixtures. Add deps pdfplumber, pypdf, openpyxl to syscall pyproject.
5. `agentx_mandate`: faculties `extraction` ([ingest_document]) + `ledger-export`
   ([export_ledger, queue_manual_action]) + `outreach` ([draft_email], for lead-finder); register in
   faculties/__init__.py; `books_prep.py` MandateType (REVISED charter from caveats); deterministic
   `books_prep_playbook`; `indian-smb-books` domain pack; books skill packs; categorizer emits
   feed-forward fields + coverage summary.
6. api/kernel bootstrap: `build_faculty_transport(settings)` (Gemini when use_gemini & key, else
   MiniMax); register `books-prep@0.1.0` in catalog (mirror `_ensure_canonical_mandate_registered`
   app.py:~93); additive optional "document path(s)" studio input via trigger payload + local intake
   folder. NO new endpoint, NO contract change.
7. Tests + full gate: both adapters (digital PDF + Excel + CSV fixtures + scanned-PDF error path),
   tool-schema registry, build_books_prep_type builds+verifies, books_prep_playbook end-to-end in sim,
   swarm run over books-prep, P1 golden categorization eval (observational). Zero regressions.
   Then end-to-end: instantiate books-prep@0.1.0 → sample bank PDF → trigger → SSE journal → approve
   export → inspect .xlsx + review queue.

## Key files / line anchors (verify, they drift)
- runner: `packages/kernel/src/agentx_kernel/hermes_runner.py` (_TOOLS:54, _RISK_BY_SYSCALL:45,
  _system_prompt:170, _user_prompt:221, _to_action:330, _call:371)
- run loop: `packages/kernel/src/agentx_kernel/run_loop.py` (_runner:258, _apply_read_result:561,
  _fulfill_sim_native_read:579, read-result exclusion line:549)
- verifier: `packages/kernel/src/agentx_kernel/verifier.py` (_evaluate:62)
- lead-finder: `packages/mandate/src/agentx_mandate/library/lead_finder.py`
- faculties: `packages/mandate/src/agentx_mandate/faculties/__init__.py`
  (research=[lead_research_batch,read_url], enrichment=[read_url], judgment=[score_lead],
  memory-craft=[], escalation=[])
- adapters: `packages/syscall/src/agentx_syscall/adapters.py` (_AdapterBase:176, registry.py
  build_phase1_registry:47)
- contracts: faculty.py, mandate.py, syscall.py, config.py, enums.py (RiskClass), __init__.py
- api: `api/src/agentx_api/app.py` (_ensure_canonical_mandate_registered ~93, instantiate ~707)
- import rules: `.importlinter` (kernel/mandate must NOT import agentx_syscall → tool-schema
  registry MUST live in agentx_contracts)

## CONTINUATION PROMPT (paste into a fresh session if context runs out)
> Resume the books-prep build on branch `feat/books-prep-mandate`. Read
> `docs/books-prep-implementation-handoff.md` first — it has the locked decisions, build order,
> gate command, and file anchors. Check `git log --oneline main..HEAD` to see which steps are
> committed, then continue the next uncommitted step. Design = the spec; caveats doc OVERRIDES it;
> STOP & flag genuine spec-vs-code conflicts. Run the full gate after each step; keep lead-finder
> byte-for-byte (the step-2 regression-lock test proves it).

## Pre-existing failures (NOT mine — do not chase)
- `packages/syscall/tests/test_send_email_adapter.py::...does_not_import_credential_roots` — red on
  baseline `main` (adapters.py imports config/security).
- api `tests/test_send_email_integration.py::...without_transport...` (×2) — local `.env` has SMTP +
  RUN_LIVE_EMAIL set, so send_email registers; these "no transport" tests fail by environment, not code.
  Confirmed I touched zero api/syscall files.

## Progress log
- [x] Explored codebase, confirmed all seams, created branch, flagged + resolved tool-derivation conflict.
- [x] Step 1 — contracts: toolschema.py + Gemini config. GREEN.
- [x] Step 2 — generalized Hermes runner (mandate-driven tools/prompt/risk + arg-normalizers),
      thin `outreach` faculty bound in lead-finder, PromptComposer (legacy lead-finder dispatch +
      generic path), skill_packs.py stub, mandate threaded into start(). Regression-lock tests added
      (tools + prompt byte-identical). GREEN (lead-finder byte-for-byte proven).
- [x] Step 3 — run_loop unwired: sim_playbook_for(mandate) resolver (_SIM_PLAYBOOKS, default lead-finder),
      read-result handler registry (+ ingest_document handler stashing scratchpad["transactions"]),
      ingest_document sim-native synthetic-transactions branch. GREEN.
- [x] Step 4 — syscall adapters: books.py (IngestDocumentAdapter PDF/Excel/CSV→rows + per-row source +
      extraction_confidence + dedupe_key; scanned/structural-fail→error. ExportLedgerAdapter openpyxl
      .xlsx Ledger+Review Queue+Summary, reversible_write/L1). Registered in build_phase1_registry
      (books_intake_dir/books_output_dir params). Deps pdfplumber/pypdf/openpyxl added + mypy overrides.
      8 tests incl. hand-rolled digital PDF + scanned + structural-bounce. GREEN (205 passed).
- [x] Step 5 — mandate: extraction + ledger-export faculties; outreach (lead-finder draft_email seam);
      books_prep.py MandateType with REVISED charter (P0-1 GST sentinel, P0-2 no_duplicate_commit,
      P0-3 extraction_suspect, P2-3 per-series balance_continuity); books_prep_playbook deterministic
      (categorise → claim clean / queue low-conf & suspect / export); indian-smb-books domain pack
      (ledger heads + narration→vendor + GSTIN/state + §17(5) non-supply heads); skill_pack +
      domain_pack fragments; RulesVerifier extended with `every ledger_transaction has ...`,
      `confidence_ge_threshold`, `balance_continuity` (per (account_id, statement_period)),
      `unique ledger_transaction dedupe_key`. Cross-batch dedup via hydration snapshot. 205/205 + 1
      pre-existing baseline failure; mypy strict clean; lint-imports 3/0; ruff 0 new.
      [committed]
- [ ] Step 6  [ ] Step 7

### Canonical transaction shape (shared: adapter out / sim-native / categorizer / export)
date, narration, debit(float), credit(float), balance(float|None), ref, source{doc_id,page,line},
account_id, statement_period, extraction_confidence(float), extraction_suspect(bool), dedupe_key.
Categorizer ADDS: ledger_head, gst_treatment(determined|"indeterminate_from_source"), confidence,
vendor, gstin, state, receivable_payable, missing_supporting_doc, balance_break, queued, queue_reason.

### Step 5 plan (verifier + facts encoding)
- Clean txn → ONE Fact: predicate="ledger_transaction", subject=dedupe_key, object=JSON(full row),
  confidence=categorization conf, provenance.evidence=["doc:<id> p<page>/l<line>"].
- Extend RulesVerifier._evaluate (thread mandate.charter.target through) with books exprs:
  `every ledger_transaction has source|ledger_head|gst_treatment`, `... confidence_ge_threshold`,
  `... balance_continuity` (per account_id+statement_period; break OK if row.balance_break=true),
  `unique ledger_transaction dedupe_key`. Plus has_transactions=`claimed_facts >= 1` (existing).
- Cross-batch dedup (P0-2): categorizer skips rows whose dedupe_key is already in snapshot.facts.
- Register books_prep_playbook into run_loop._SIM_PLAYBOOKS["books-prep"].

Files touched steps 1-4 (for `git add`): contracts/{toolschema,__init__,config}, kernel/{hermes_runner,
run_loop}, mandate/{harness,skill_packs,faculties/__init__,faculties/outreach,library/lead_finder},
syscall/{books(new),registry,pyproject}, pyproject.toml(mypy overrides), tests/kernel/test_hermes_runner,
tests/mandate/{test_faculties,test_lead_finder_library}, syscall/tests/test_books_adapters(new).
