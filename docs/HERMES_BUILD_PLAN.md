# HERMES_BUILD_PLAN.md — phased backend build for the autonomous builder

*Operating manual: [`MINIMAX-TASK.md`](../MINIMAX-TASK.md) (read it first, every phase). Canon:
[`docs/BLUEPRINT.md`](./BLUEPRINT.md) (wins all conflicts), [`docs/STATE_AND_ROADMAP.md`](./STATE_AND_ROADMAP.md)
(what's already built). TDD always: write the **Done-when** tests RED first, then implement to GREEN, then
run the full gate. STOP after Phase 2 and emit the Checkpoint Review Prompt. Frontend is Claude's job AFTER
Phase 6 — build no UI.*

Each phase is **one bounded unit**: `Goal · Context (file anchors) · Constraints · Done-when (the exact
test assertions)`. Stay in the named lane; keep `lint-imports` 3/3; never touch `packages/contracts`
(STOP + ask if you think you must).

---

## Phase 1 — Gated real email SEND  *(syscall lane; closes the "draft never sends" gap, G13-start)*

**Goal.** An approved draft becomes a really-sent email: a gated, idempotent `send_email` syscall that
sends via a real transport, using the **instance's own sender identity**, and never double-sends.

**Context.** Model on `DraftEmailAdapter` (`packages/syscall/src/agentx_syscall/adapters.py:367` —
`external_message`, `required_ring="L2"`, `sent:False`). Register in `registry.py`
(`build_phase1_registry`). Inject the transport behind a Protocol (mirror `ResearchProvider` in
`adapters.py` — the real provider reads its key kernel-side; the pod never holds it). The
draft→approve→resume flow already exists (draft parks at L2 → `/commands/approve` → kernel `resume()`).

**Transport is DECIDED: Gmail SMTP via an App Password** (`smtplib` STARTTLS — no new pip dep). Add these
fields to `agentx_contracts.config.Settings` (UPPER_SNAKE env vars, already in `.env`; `SMTP_PASSWORD` is a
`SecretStr`): `smtp_host` (`SMTP_HOST`, default `smtp.gmail.com`), `smtp_port` (`SMTP_PORT`, default `587`),
`smtp_username` (`SMTP_USERNAME`), `smtp_password` (`SMTP_PASSWORD`, `SecretStr`), `email_from`
(`EMAIL_FROM`), `email_from_name` (`EMAIL_FROM_NAME`). The adapter reads them kernel-side (like the research
providers) — the mandate pod never sees them (invariant #2; `config.py` stays forbidden to `agentx_mandate`).
Gmail rewrites `From:` to the authenticated account, so `email_from` must equal `smtp_username` (or a verified
alias). Note #8: this single Gmail is a shared sender — acceptable for dogfooding only; still thread the
sender identity per-instance so per-instance senders drop in later with no structural change.

**Constraints.** Invariant #2 (credential from the vault at `execute(req, cred)`, never the pod — keep
`tests/test_credential_boundary.py` green). Invariant #8 (per-instance sender identity; NO shared
sender). Invariant #5 (if no transport is configured, resolve to the `human_task` tail — never None).
Invariant #6 (this is not money). Unit tests use a **fake transport**; the real send is gated on
`RUN_LIVE_EMAIL=1`. This is syscall-lane only — do NOT import the kernel/mandate lane.

**Done-when (write these tests first):**
1. `send_email` adapter exists, `maturity_level >= 2`, `risk_class == "external_message"`, gated at a ring
   that requires human approval; registered and resolvable.
2. Executing it with a fake transport returns `{sent: True, message_id: ...}` and calls `transport.send` **exactly once**.
3. Executing it **twice with the same `idempotency_key`** calls `transport.send` **once** (no double-send) and replays the receipt.
4. The `From`/sender identity equals the **instance's** channel identity, not a shared/global one.
5. No transport configured ⇒ resolves to the `human_task` terminal tail (assert `is_terminal_fallback`, never None).
6. `tests/test_credential_boundary.py` still passes; full gate green.

> Wiring note (surface as a checkpoint question if unsure): the cleanest path is the email syscall as a
> maturity ladder — draft parks at L2; after human approval the resumed run issues the `send_email` Call,
> which `SendEmailAdapter` fulfils. The adapter is the heart of this phase; the post-approval wiring may be
> a thin `api/`-edge step. Do NOT change the kernel run-loop's contract to achieve it.

---

## Phase 2 — Step-D reality feedback  *(kernel lane; closes G3 — the last Phase-1 engine gap)*

**Goal.** A matured watch (deadline fires, or `mark_outcome`) promotes the run's **probation** facts to
**verified**, updates trust/résumé, and emits **exactly one** `eval_case(origin="real")` into the gym.

**Context.** `settlement.py` already journals `WatchRegistered` per watch (and projects one `WATCH` doc).
The deferred-settle worker belongs with `scheduler.py`/`settlement.py` (kernel lane). `EvalCase` requires a
`HydrationSnapshot` + `Scorecard` (grade the settled run's real trace via the existing Judge, `origin="real"`).
`mark_outcome` adapter already exists (`adapters.py`).

**Constraints.** Kernel lane only (no syscall/swarm import). Invariant #1 (facts reach `verified` only via a
committed, provenance-stamped event). Invariant #7 stays intact — this is where the gate finally gets a
**real** origin. No `packages/contracts` change (Fact status, EvalCase, Scorecard already exist).

**Done-when (tests first):**
1. A watch matures (simulate the deadline / a `mark_outcome="success"`) → the run's probation facts flip to
   `verified` (assert the heap projection), and a trust delta is applied to the instance résumé.
2. **Exactly one** `EvalCase(origin="real")` is written for that run (assert count delta == 1), carrying the
   real scorecard + hydration snapshot.
3. `PromotionGate.evaluate(PromotionGateInput(eval_cases=[that real case], human_approved=True))` now
   **ALLOWS** (the inverse of Session I's synthetic bar) — proving reality opens the gate.
4. A matured watch with `mark_outcome="failure"` demotes/does not promote, and records the negative case. Full gate green.

---

## ⏸ CHECKPOINT — STOP after Phase 2. Emit the Checkpoint Review Prompt (template in MINIMAX-TASK.md §7). Wait for Claude's approval before Phase 3.

---

## Phase 3 — Creator mandate draft path  *(mandate + syscall lanes; starts G10)*

**Goal.** "Make me a mandate that does X" → the Creator drafts a candidate `MandateType` from a brief,
runnable in the Session-I swarm. Candidate is **draft-only** — never registered live.

**Context.** Mirror `build_lead_finder_type()` (`packages/mandate/src/agentx_mandate/library/lead_finder.py`).
New faculties `conversation` + `scheduling` (`packages/mandate/.../faculties/`, reuse the frozen `Faculty`
contract). New `draft_candidate_type` syscall (`packages/syscall/.../adapters.py` + `registry.py`),
**draft-only, no live effect** (like `draft_email`'s `sent:False`).

**Constraints.** Respect the lane split (faculties + library = mandate lane; the syscall = syscall lane;
they meet only through contracts). Invariant #7 + #4: the Creator emits candidates only; it is a gated
*user*, never code in the live kernel. No contract change (the candidate IS a `MandateType`).

**Done-when (tests first):**
1. `build_creator_type()` returns a `MandateType` with the four §5 faculties (conversation, scheduling,
   memory-craft, escalation) + checkable postconditions ("candidate has ≥1 faculty", "has a charter goal",
   "names a scenario pack").
2. `draft_candidate_type` is draft-only: it stages a candidate `MandateType` as run output and performs
   **no** live registration (assert no `mandate_type` doc is written).
3. A Creator run drafts a candidate and parks it for human review (appears as a draft, not a live type). Full gate green.

---

## Phase 4 — Promote gate + canary  *(kernel + api; closes the candidate→live bridge, G11/Session K)*

**Goal.** A gated `/commands/promote` registers an approved, swarm-tested candidate at a **canary** ring
(L0/L1), enforcing real-evidence + human approval through `PromotionGate`.

**Context.** `KernelControl.register_mandate_type` (kernel lane) is the registration primitive. The route is
the still-501 `POST /commands/promote` (`api/src/agentx_api/app.py`). `PromotionGate` already enforces
real+human (Phase 2 gives it real cases).

**Constraints.** Promote MUST call `PromotionGate.evaluate` with real evidence + human approval before any
`register_mandate_type`. Behind `Depends(_require_command_auth)`. Invariant #6/#7: no auto-promotion; L2+
gates to a human; synthetic-only is rejected.

**Done-when (tests first):**
1. Promote is **rejected** with synthetic-only evidence (gate bars it; route returns the reasons, no registration).
2. Promote is **allowed** with real+human evidence → registers the type at the requested canary ring (assert the catalog now lists it).
3. Unauthorized (no bearer) → 401. `command.promote` retired from `gaps.py` CORE_GAPS → KNOWN_CLOSED. Full gate green.

---

## Phase 5 — Compiler scaffold (GEPA-style)  *(swarm/foundry lane; G12 — mechanism only)*

**Goal.** The compiler mechanism: read the gym (real eval cases) → propose a rewritten faculty skill-pack
candidate → **gate it against live on REAL cases** (promptfoo regression) → canary. **Honest limit:** real
improvement needs ~100 real settles; build + test the MECHANISM on seeded cases. Do NOT claim it improves anything.

**Context.** Swarm/foundry lane (`packages/swarm`). Reuse the promptfoo `Judge` for regression scoring and
`PromotionGate` for the real-only bar. The gym corpus = `EvalCase(origin="real")` from Phase 2.

**Constraints.** Swarm lane only. Invariant #7: synthetic cases pre-train/test but NEVER decide promotion —
only real cases gate a compiled candidate. No contract change. A compiled candidate is itself a candidate
(goes through Phase-4 promote, never auto-live).

**Done-when (tests first):**
1. `compiler.propose(gym)` returns a candidate faculty skill-pack version from a seeded real-case corpus.
2. The gate **rejects** a candidate that does not beat live on the real cases; **accepts** one that does (seeded).
3. A synthetic-only corpus can **never** produce a promotable candidate (invariant #7). Full gate green.

---

## Phase 6 — Finalize the mandate (end-to-end integration proof)

**Goal.** One integration test walks the whole new chain on the in-memory backend and proves the mandate
works as a living system on seeded data:

```
instantiate → trigger run → research → draft → approve → SEND (fake transport) → mark_outcome
   → Step-D matures the watch → verified facts + trust delta + eval_case(origin="real")
   → promote gate ALLOWS (real+human) → registered at canary → compiler can read the real case
```

**Done-when.** The integration test is green; the FULL gate is green; `docs/STATE_AND_ROADMAP.md` is
updated (G3/G10/G11/G12 + send moved out of ❌). Emit a final summary listing **every new API route +
view-model the frontend will consume** (Claude builds the UI next).

---

## After Phase 6 — Claude builds the frontend

Claude (this Code session) then builds the Operator Studio + the surfaces these phases unlocked: drive a
mandate → find leads → draft → **approve & send** → see the outcome mature; the Creator view; the
promote/canary control; the gym/compiler view; and the read-only Kernel Inspector. The design lives in
`docs/OPERATOR_STUDIO_DESIGN.md` (to be written at that point). Your job ends at a green, fully-tested
backend with the API routes documented.
