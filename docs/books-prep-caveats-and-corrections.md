# `books-prep` — Caveats & Spec Corrections (v0)

_Companion to `2026-06-21-books-prep-and-harness-generalization-design.md`. Read alongside it. These are corrections and additions, not a rewrite — most are charter wording, verification-rung checks, and metrics, not new adapters or features._

---

## What the design already gets right (so the critique is calibrated)

The architecture is sound and several of my earlier concerns are already handled: deterministic-adapter-only I/O, the human review queue as the safety rung, scanned-PDF → `human_task` degradation, the regression-lock on lead-finder, the import-linter-forced `ToolSchema` seam, and — importantly — the _emitted-not-gated_ treatment of the feed-forward fields (vendor/gstin/state, missing_supporting_doc, receivable/payable). Those are correct calls. The gym (CA-corrections feedback loop) is also a real asset.

The caveats below are the gaps that survive a close read. They cluster into one theme: **the spec verifies that the pipeline runs; it does not yet verify that the judgment is correct or that the books stay correct across batches.** For a books product, correctness _is_ the product, and one of these gaps is a safety property, not a nicety.

Priority key: **P0** = fix before building the affected step; **P1** = the load-bearing one for whether this works at all; **P2** = de-risks the bet.

---

## P0-1 — The charter gates on GST treatment, which a bank statement cannot yield

**Current (§4.1):** `every_txn_categorized` is a `rung="rules"` postcondition defined as _"ledger head + GST treatment + confidence."_ GST treatment is therefore **gated** — a run fails if any transaction lacks it.

**Gap:** A bank-statement narration ("NEFT ABC TRADERS 50000") tells you money moved; it does **not** carry HSN/SAC, place of supply, tax split, or RCM applicability. Those live on the _invoice_, which v0 explicitly does not ingest. So for the actual v0 input, GST treatment is _indeterminate on most rows by construction_. As written, real input cannot satisfy the charter.

This is exactly the "spec conflicts with what the input can do — STOP and flag" case your own process names.

**Fix:** Demote GST treatment out of the hard gate; gate only what bank data can support.

- Gate `every_txn_has_ledger_head_and_confidence` (drop GST treatment from this rule).
- Add `gst_treatment_emitted`: every transaction carries a `gst_treatment` field whose value is either a determined treatment **or** the explicit sentinel `indeterminate_from_source`. `indeterminate_from_source` is a **valid pass**, not a failure.
- When `gst_treatment == indeterminate_from_source` on a row that looks taxable, set `missing_supporting_doc = true` (this is the hand-off signal to the future `gst-recon` mandate — the design already wants this field).

**Slots into:** step 5 (charter + categorizer output). Wording-only; no new adapter.

---

## P0-2 — Cross-batch duplicate commits will silently corrupt the heap

**Current (§2):** duplicate detection is listed in the rules rung; `idempotency_key` exists on approval cards.

**Gap:** Dedup as specced is _within-batch_ and _per-export_. But CAs re-upload overlapping periods constantly — April statement, then a Q1 statement that re-includes April; current account and an overlapping consolidated dump. Clean transactions commit to the **heap**. With only within-batch dedup, an overlapping re-ingest **double-commits the same transaction**. That corrupts the books and — worse — silently corrupts the ageing/receivable data the design intends to feed `collections` later. Nobody notices until a downstream mandate produces a wrong number.

**Fix:** Transaction-level idempotency against the heap, not just within the batch.

- Compute a per-transaction dedupe key (e.g. hash of `account_id + date + amount + running_balance + ref/narration`).
- Add `rung="rules"` postcondition `no_duplicate_commit`: a transaction whose dedupe key already exists in the business's heap region is **not** re-committed (it's reconciled/skipped, optionally surfaced as an info card).
- This is a heap-write guard, not a new syscall.

**Slots into:** step 4 (ingest/commit path) + step 5 (charter rule).

---

## P0-3 — A digital PDF that parses _wrong_ (not zero) rows sails straight through

**Current (§4.3):** scanned / no-text PDFs return `status="error"` → routed to the queue. Mis-parses are said to be caught by the balance-continuity rule + the CA queue.

**Gap, in two parts:**

1. The `error` path only fires when there's _no extractable text_. A digital PDF whose columns are misread — debit/credit swapped, multi-line narration truncated, a page header ingested as a transaction — produces _plausible-looking but wrong_ rows with no error. Balance continuity catches _some_ of this, but not column-swaps that happen to still reconcile, misattributed narration on a correct amount, or a statement where the balance column itself parsed unreliably.
2. The pipeline routes to the queue on **categorization confidence only**. A badly-_extracted_ row with a clean-looking narration can still get **high categorization confidence** and pass. The spec conflates two independent failure modes under one threshold: _"did we read the row right?"_ (extraction) vs _"did we classify it right?"_ (categorization). Both must be able to route to the queue, independently.

**Fix:** Make extraction quality a first-class, separately-routing signal.

- `IngestDocumentAdapter` emits a per-row `extraction_confidence` derived from deterministic checks: does `debit/credit` reconcile against the row-to-row balance delta? did the detected column schema match? was narration truncated/over-length?
- Add a rules-rung check: a row failing the arithmetic reconciliation is flagged `extraction_suspect` and routed to `queue_manual_action` **regardless of categorization confidence**.
- Add a **whole-document structural sanity gate**: if more than a configurable fraction of rows fail structural checks (column-count consistency, arithmetic), the adapter returns `status="error"` (same path as scanned PDFs) so the _whole doc_ goes to `human_task` — rather than emitting a confident, wrong ledger. Better to bounce the doc than to hand a CA a clean-looking lie.

**Slots into:** step 4 (adapter) + step 5 (rule). No LLM involved — all deterministic.

---

## P1 — Nothing measures cold-start categorization accuracy; the gym only helps _after_ the CA stays

**Current:** the gym ingests CA corrections and improves the mandate over time (§1, §4.1). All §7 tests check plumbing — adapter parses, registry builds, playbook runs, swarm runs.

**Gap:** The gym is a _runtime_ loop; it presumes the CA corrects and _comes back_. It measures nothing on day one. But day-one accuracy decides whether the CA's first experience is "this saved me a morning" or "it flagged everything / got the heads wrong — I'm not opening it again." First impression governs retention, and the gym only pays off if there's a second run. **No test measures whether the categorization is any good before a single correction exists.**

And this is not just UX — it's the **load-bearing safety property** of the whole design. The CA review queue protects _queued_ rows only. Every _un-queued_ ("clean") row is protected **solely by the confidence score being well-calibrated**. If the model is confidently wrong, a bad ledger head or GST sentinel rides through into books the CA approves without scrutiny. So calibration quality is the safety control, and right now it is unmeasured. The 0.8 threshold is a guess with nothing behind it.

**Fix:** A static categorization eval, distinct from the gym, that instantiates the verification ladder's **"reality" rung as a build artifact.**

- **Golden fixture:** ~50–150 real transaction rows from the target CA's _actual_ client statements, each hand-labeled by that CA with the correct `ledger_head` and (where applicable) `vendor`. Versioned in-repo (jsonl or xlsx), like the `SyscallTestCase` fixtures.
- **Metrics** (run categorization over the golden rows, no commit):
  - `ledger_head` top-1 accuracy
  - vendor-resolution accuracy (on labeled rows)
  - `queue_rate` = % routed to review at the chosen threshold (the CA's workload)
  - **`false_confidence_rate`** = % of rows scored ≥ threshold that were wrong ← _the safety-critical number_
  - a calibration table: accuracy bucketed by confidence band
- **Set the threshold from this curve**, not from a guessed 0.8. The right threshold is the one that drives `false_confidence_rate` below a level the CA accepts.
- **v0 honesty:** keep these **observational** (measured and reported in step 7), not hard CI gates, until there's enough labeled data to set real bars _with the CA_. Don't fake a threshold to make the gate green.

**Slots into:** step 7 (new eval alongside the pipeline tests). This is the single highest-value addition in this document.

---

## P2-1 — "Revenue-ready" has no acceptance test that involves the real CA

**Current:** build order ends at "full gate green"; the demo narrative ("Sharma Textiles' April dump…") is illustrative, not a test.

**Gap:** A green gate proves the code runs. It does not prove the CA will use or pay for it — the one thing the discovery work flagged as still unproven. The design's own ladder ends in a **reality** rung (CA accept/correct); make that a definition-of-done, not just a runtime concept.

**Fix:** Add an explicit acceptance gate after step 7: the real CA runs **one real client batch** end-to-end and rates (a) is the categorization usable as-is, (b) do you trust the clean-vs-queued split, (c) did it save time vs the junior. Capture every correction → seed both the gym and the golden fixture (P1). Green engineering gate is _necessary, not sufficient_; this is the "revenue-ready" proof.

**Slots into:** post-step-7 acceptance, before calling v0 done.

---

## P2-2 — The feed-forward fields seed the next mandates with unmeasured-quality data

**Current:** vendor/gstin/state, missing_supporting_doc, receivable/payable are emitted-not-gated (correct for v0 robustness) and explicitly intended to feed `gst-recon` and `collections`.

**Gap:** Ungated _and_ unmeasured means you'll seed the downstream mandates with data of unknown trustworthiness, and the defect surfaces only when `collections` emits a wrong ageing report months later — expensive to trace back.

**Fix:** Emit a per-batch **coverage + confidence summary** for these fields now (e.g. "GSTIN derivable on 38% of rows; receivable/payable tagged on 71%"). Ungated, cheap, but it means that when you build the money mandates you already know how much you can trust the seed. Cheap now; a retrofit later.

**Slots into:** step 5 (categorizer output) + the Excel summary sheet.

---

## P2-3 — `balance_continuity` must be scoped per account/statement

**Current:** `balance_continuity` holds "across the statement."

**Gap:** A multi-account or multi-period dump (current + savings, or three months concatenated) has _several_ independent running-balance series. A single global continuity rule will spuriously "break" at every account/period boundary.

**Fix:** Scope the rule to `(account_id, statement_period)`; continuity holds _within_ each series, breaks flagged per series. Minor wording change to the rule.

**Slots into:** step 5 (charter rule).

---

## Revised charter (postconditions) — drop-in for §4.1

**Gated (`rung="rules"`):**

- `has_transactions`
- `every_txn_has_source` — doc id + page/line
- `every_txn_has_ledger_head_and_confidence` — _(GST treatment removed from the gate)_
- `gst_treatment_emitted` — value is a determined treatment **or** `indeterminate_from_source`; the sentinel is a valid pass and sets `missing_supporting_doc` on taxable-looking rows
- `low_confidence_queued` — routes on **either** low categorization confidence **or** `extraction_suspect`
- `balance_continuity` — scoped per `(account_id, statement_period)`; breaks flagged per series
- `no_duplicate_commit` — transaction whose heap dedupe key already exists is not re-committed

**Emitted, not gated** (unchanged + new summary): `vendor`, `gstin`, `state`, `missing_supporting_doc`, `receivable`/`payable`, **plus** a per-batch coverage/confidence summary for these fields.

**target:** `{ documents:[…], output_format:"xlsx", confidence_threshold: <set from the calibration curve, not 0.8 by assumption> }`

---

## Scope guard — what these caveats deliberately do **not** add

To keep v0 tight, none of the above introduces: OCR/vision, GST reconciliation, Tally/Zoho export, new endpoints, or a contract change. Every fix is charter wording, a deterministic verification-rung check, a metric, or a fixture. The two genuinely new _test artifacts_ are the golden eval fixture (P1) and the CA acceptance run (P2-1) — both of which you need anyway to claim "revenue-ready" honestly.

---

## The one-line summary

The current spec is a well-built **pipeline**; these caveats make it a trustworthy **product**. The three P0s stop it from being unsatisfiable (GST gate), silently corrupting books (cross-batch dedupe), or handing the CA a confident-but-wrong ledger (extraction routing). The P1 turns the confidence score — which is secretly the safety control for every un-reviewed row — from a guessed 0.8 into a measured, calibrated number. Build those, and "revenue-ready" stops being an assertion.
