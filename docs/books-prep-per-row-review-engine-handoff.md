# Engine task — Per-row CA review resolution (books-prep Flag #1)

> **For the new session:** read this whole file, then read the files in §Context
> before writing any code. You are the **kernel + mandate** engine (see
> `CLAUDE.md`). This is an engine-only task in your lane. The books-prep *app*
> (read endpoints) is being built in a separate session/repo and does not block you.

---

## ✅ DONE (2026-06-24) — landed on `feat/books-prep-mandate`, in-lane, no contract change

Implemented as **resolution-as-micro-run** (§4): a CA decision on one flagged row is a tiny
settlement commit, not a per-row park — so the FROZEN `packages/contracts` seam was untouched
(no `BLOCKED` needed).

**Changed files**

- `packages/mandate/src/agentx_mandate/library/books_prep_review.py` *(new, mandate lane)* — pure
  `build_resolution_fact(row, …, decision, edits)` builds a `ledger_transaction` Fact in the SAME
  encoding as `books_prep_playbook.build_transaction_facts`. Only `ledger_head` / `gst_treatment`
  are editable (a CA fixes categorisation, never the immutable bank columns). `dedupe_key_for` /
  `apply_edits` helpers. Imports only frozen `agentx_contracts` submodules (invariant #2).
- `packages/kernel/src/agentx_kernel/books_review.py` *(new, kernel lane)* — `BooksReviewResolver`:
  - **approve** → commit the Fact (original category) via `SettlementCommitter` → heap write only
    through a `RunSettled` event (invariant #1, provenance-stamped).
  - **edit** → apply corrected fields, then commit.
  - **reject** → commit no Fact; rejection journaled as a `ManagerAction` (audit intact).
  - **all** → write a gym `EvalCase(origin="real")` to the `eval_case` projection (CA corrections
    feed the gym; invariant #7), mirroring `watch_maturation`'s direct-write convention.
  - **idempotency** → deterministic per-row run id `{instance}:ca_review:{dedupe_key}` keys a
    `ManagerAction` idempotency guard; a repeat resolve raises `DuplicateIdempotencyKey` and
    short-circuits to `already_resolved=True` (no double commit / eval case / audit row).
- `packages/kernel/src/agentx_kernel/bootstrap.py` *(edit)* — `build_books_review_resolver(*, journal,
  projection_store)`: inject the live Mongo stores (or omit both for in-memory sim/tests).
- `tests/kernel/test_books_review_resolution.py` *(new)* — the §5 done-when as failing-first tests.

**Gate status:** new tests **8 passed**; `mypy --strict packages db tests` **0 errors / 158 files**;
`ruff check` clean; `lint-imports` **3 kept / 0 broken**. Existing books-prep / run-loop / settlement
suites unchanged (purely additive). *(Pre-existing failures in `packages/syscall/tests/`
`*_does_not_import_credential_roots` are Codex-lane and fail on a clean tree without these changes.)*

**App integration (the request/response shape §9 asked for)**

```python
from agentx_kernel.bootstrap import build_books_review_resolver
resolver = build_books_review_resolver(journal=<mongo journal>, projection_store=<mongo projections>)

resolution = await resolver.resolve(
    instance=binding,                         # InstanceBinding for this books-prep instance
    row=row,                                  # the flagged row exactly as /manual-queue returned it
    decision="approve" | "edit" | "reject",
    edits={"ledger_head": "...", "gst_treatment": "..."} | None,   # edit only; only these 2 fields honored
    actor="ca_<id>",
    now=datetime.now(UTC),
)
# → BooksReviewResolution(decision, dedupe_key, run_id,
#                         committed_fact_id: str|None,   # set for approve/edit, None for reject
#                         eval_case_id, already_resolved: bool)
```

UI behavior: approve → committed with original category; edit → committed with corrections; reject →
nothing committed, audit journaled; `already_resolved=True` → treat as success (don't double-toast).
Do NOT route per-row resolution through the run-level `export_ledger` park — that's a separate gate.

### HTTP route — SHIPPED (2026-06-24, operator-authorized api/ edit)

The engine `api/` now exposes the resolver over HTTP. The books-prep BFF stays a pure HTTP client
(separate repo) and **must not** import `agentx_kernel` — it calls this route.

```
POST /commands/resolve-manual-task        (bearer-gated: Authorization: Bearer <AGENTX_OPERATOR_TOKEN>; 202)
body: {
  "instance_id": "<inst>",
  "task_id":     "<manual-queue card id from GET /manual-queue>",
  "decision":    "approve" | "edit" | "reject",
  "edits":       { "ledger_head": "...", "gst_treatment": "..." } | null,   # required for edit
  "actor":       "ca_<id>"                                                    # optional; defaults to manager:dashboard
}
→ 202 {
  "supported": true, "status": "applied",
  "decision", "dedupe_key", "run_id",
  "committed_fact_id": str | null,        # set for approve/edit, null for reject
  "eval_case_id", "already_resolved": bool
}
```

Server behaviour (api handler in `api/src/agentx_api/app.py`):
- Looks up the flagged row from the manual-queue card by `task_id` (the client never sends the row,
  so bank columns can't be tampered with); 404 if the card is missing, 409 if it belongs to another
  instance, 422 if it isn't a `review_transaction` card or `decision=edit` has no `edits`.
- Runs `state.review_resolver.resolve(...)` (one `BooksReviewResolver` built on `OperatorRuntime`
  with the SAME journal + projection store the run-loop uses).
- Closes the card (`manual_tasks.mark_outcome`) so it leaves the open queue; idempotent on repeat.

Changed api/ files: `app.py` (route + `ResolveManualTaskCommand`), `operator.py` (resolver on
`OperatorRuntime`), `state.py` (`review_resolver` accessor). Tests:
`api/tests/test_books_review_resolution.py` (6 passed). `api/` mypy/ruff clean for these files
(one pre-existing unrelated `test_books_prep_catalog.py` mypy ignore + pre-existing
`test_send_email_integration.py` failures are not from this change).

**BFF wiring (books-prep app):** `POST /clients/{id}/queue/{task_id}/{approve,edit,reject}` →
`EngineClient.resolve_manual_task` → `POST /commands/resolve-manual-task`; surface
`already_resolved` as an idempotent success (no double-toast). `GET /manual-queue` is unchanged.

---

## 1. Goal (one sentence)

Let a CA **approve / edit / reject a single flagged transaction row** from the
books-prep review queue, so that an approved/edited row is committed into the
client's books and the correction is recorded for the gym — **without touching
the frozen `packages/contracts` seam.**

## 2. Context — read these first

- `CLAUDE.md` — your lane, the 8 invariants, the frozen-seam rule, commands.
- `docs/superpowers/specs/2026-06-21-books-prep-and-harness-generalization-design.md`
  §1–2 — the v0 verification ladder explicitly includes **"human (the CA review
  queue) → reality (CA accept/correct)"** and settlement says **"CA corrections
  feed the gym."** Per-row review is spec-core for v0, not optional.
- `packages/mandate/src/agentx_mandate/library/books_prep_playbook.py` — the
  playbook. Note `_queue_call` (`:221`) emits one `queue_manual_action` per
  flagged row; `build_transaction_facts` (`:189`) claims `ledger_transaction`
  facts for **clean rows only** — queued rows are never committed.
- `packages/mandate/src/agentx_mandate/faculties/ledger_export.py` — the
  faculty that declares `export_ledger` + `queue_manual_action`.
- `packages/kernel/src/agentx_kernel/gateway.py:45` — `queue_manual_action`
  policy is `required_ring="L0", risk_class="read"` → it **executes immediately,
  never parks.** That is the whole reason flagged rows are not resolvable today.
- `packages/kernel/src/agentx_kernel/verifier.py:230` — `park_for_approval`
  journals a `RunParked` keyed `{run_id}:park:human_approval` — **one park per
  run.** The approve/reject/edit commands resolve **per-run**, not per-row.
- `packages/kernel/src/agentx_kernel/control.py:217` — `resolve_approval`, the
  single approve/reject path (run-keyed).

## 3. The problem (what's blocked, and why the obvious fix is off-limits)

Flagged rows are fire-and-forget `queue_manual_action` manual-queue cards. They
**never park** and have **no per-task resolution command**. The only approvable
thing is the single run-level `export_ledger` park.

The obvious fix — make each row "park" so the existing approve/edit/reject
commands can target it — would require adding a per-row key to `RunParked` /
`ApprovalResolved` / the command bodies. **Those events live in
`packages/contracts` (FROZEN).** Per `CLAUDE.md`, do **not** work around the
seam: if you conclude you must change it, STOP and emit
`BLOCKED: contract change needed — <reason>` in your handoff. Hermes coordinates
that across both engines.

## 4. The design that stays in your lane (resolution-as-micro-run)

Model a CA decision as a **small triggered follow-up run**, not a per-row park:

1. The flagged rows already exist and are readable (`/manual-queue`). The app
   shows them and lets the CA approve / edit a category / reject.
2. The app sends one CA decision for one row. The engine runs a tiny resolution
   trajectory that:
   - **approve** → commits that row as a `ledger_transaction` Fact
     (provenance-stamped — **invariant #1: no fact without a commit**).
   - **edit** → applies the CA's corrected fields, then commits as above.
   - **reject** → no fact; audit trail preserved.
   - in all cases, records the CA's decision as a **gym eval case** (the spec's
     "CA corrections feed the gym").
3. Reuse the existing run-loop / `Claim` / settlement machinery and the existing
   `/commands/trigger-run` surface — **all unchanged contracts.** The new logic
   (a resolution playbook/mode + any gateway policy entry) lives in
   `packages/mandate` and `packages/kernel` — your lane.

**First design step: confirm this avoids `packages/contracts`.** If approve/edit
can be expressed by reusing `Fact`, `Claim`, trigger-run, and settlement as they
exist, you are clear. If you find you must add/alter a contract model, STOP and
emit the `BLOCKED: contract change needed` handoff instead of editing it.

## 5. Done-when (write these as FAILING tests FIRST — they are the spec)

Encode behavior, not implementation:

1. **approve** a flagged row → a `ledger_transaction` Fact for that row's
   dedupe_key appears committed in the instance heap, provenance-stamped, with
   the original category.
2. **edit** a flagged row's `ledger_head` (and/or `gst_treatment`) then approve
   → the committed `ledger_transaction` Fact carries the **corrected** fields.
3. **reject** a flagged row → **no** `ledger_transaction` Fact is committed, but
   the rejection is journaled (audit trail intact).
4. Every approve/edit/reject is recorded as a **gym eval case** (CA correction
   feed). Assert the eval/gym artifact is written.
5. **Idempotency:** resolving the same row twice does not double-commit (reuse
   the journal's idempotency-key guard pattern).
6. **Lane fence stays green:** `uv run lint-imports` → 3 kept / 0 broken; no new
   import of `agentx_syscall` / `agentx_swarm` / `agentx_db` / `pymongo`.

## 6. Constraints (non-negotiable)

- `packages/contracts` is FROZEN — see §3/§4. STOP-and-coordinate if you need it.
- Lane: only `packages/kernel` + `packages/mandate`. Do not touch `api/`,
  `packages/syscall`, `packages/swarm`, or any credential/config root.
- Invariant #1 (no fact without a commit; provenance-stamped) and #2 (no creds in
  user space) apply directly. Self-review your diff against BLUEPRINT §4.
- Keep lead-finder and the existing books-prep flow working byte-for-byte —
  changes are additive.

## 7. Commands

```bash
uv sync
uv run pytest -q
uv run ruff check .
uv run mypy --strict packages db tests
uv run lint-imports            # expect 3 kept / 0 broken
```

## 8. Workflow

- Test-first: write §5 as failing tests, then the smallest change to GREEN.
- Commit small, prefix `[claude]`. **The user runs their own git commits/pushes —
  do not run `git commit`/`git push` yourself; stage/describe and let them.**
- Current branch at handoff time: `feat/books-prep-mandate`.
- If you hit the seam: STOP, emit `BLOCKED: contract change needed — <reason>`.

## 9. Handoff back

When done (or blocked), summarize: changed files, tests added + pass/fail, the
exact request/response shape the app's review screen should call (so the app
session can wire approve/edit/reject), and whether the design stayed in-lane or
needs contract coordination.
