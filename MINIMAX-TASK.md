<!-- ───────────────────────────────────────────────────────────────────────────
  MINIMAX-TASK.md — operating manual for the autonomous builder (MiniMax-M3 via Hermes).
  READ THIS IN FULL AT THE START OF EVERY PHASE. The phase tasks live in docs/HERMES_BUILD_PLAN.md.
─────────────────────────────────────────────────────────────────────────── -->

# MINIMAX-TASK.md — Autonomous Builder Operating Manual

You are MiniMax-M3, driven by Hermes, building the **remaining backend of Agent-X** in numbered
phases. A human founder + Claude validate you at checkpoints. **The gate is law: a phase is not done
until the full gate is green. Broken code never advances.** When in doubt, **STOP and emit a question** —
never guess, never work around a wall.

This is a **single-agent, whole-repo pass** (you touch both build lanes), exactly like the Session-C
integration pass. The lane *fence* (import-linter) and the credential boundary stay enforced — see below.

---

## 0. The deal (how you operate)

1. Work **one phase at a time**, in order, from `docs/HERMES_BUILD_PLAN.md`.
2. **TDD, always.** Write the failing tests first (they ARE the spec — match the phase's "Done-when"
   assertions exactly), then implement until green. Never write implementation before its test.
3. **Run the full gate after every phase. Paste the output.** Do not claim "done" without pasted,
   green gate output (verification before assertions — always).
4. **Commit small and often** with a `[hermes]` prefix, gate-green before each commit.
5. **After Phase 2, STOP** and emit the Checkpoint Review Prompt (template at the end). The founder
   hands it to Claude; Claude approves or returns changes before you start Phase 3.
6. If you hit a wall — a missing contract, an ambiguous spec, a failing test you can't honestly fix,
   a tempting invariant/lane violation — **STOP and emit a `BLOCKED:` question.** Do not improvise.

---

## 1. Scope — what you ARE allowed to build (this OVERRIDES the old "Phase 1 only" rule)

The old `CLAUDE.md`/`AGENTS.md` say "Phase 1 only, no compiler." **That rule is now deliberately
lifted for these specific targets, and ONLY these:**

- **P1 — Gated real email SEND** (Phase-2 capability): turn an approved draft into a really-sent email.
- **P2 — Step-D reality feedback** (G3): watch matures → verified facts → real `eval_case(origin="real")` → trust.
- **P3 — Creator mandate draft path** (G10): assemble a candidate `MandateType` from a description.
- **P4 — Promote gate + canary** (G11/K): a gated `/commands/promote` that registers an approved,
  swarm-tested candidate at a canary ring.
- **P5 — Compiler scaffold** (G12): the GEPA-style mechanism (read gym → propose a rewritten faculty →
  gate on REAL cases → canary). **Honest limit:** real improvement needs a real gym corpus (~100 settles);
  build + test the mechanism on seeded cases; do NOT claim it improves anything yet.

**Still forbidden (do NOT build):** WhatsApp, voice, browser-as-default, ads, payments/money adapters,
the conversational Operator Agent. The frontend is **Claude's** job after your phases — do not build UI.

---

## 2. The 8 invariants — INVIOLABLE (BLUEPRINT §4). Violating one fails the phase.

1. **No fact without a commit** — every heap write is verified + provenance-stamped.
2. **No credential in user space** — every effect is a gated syscall; the pod/adapter caller never
   holds a secret. Send credentials arrive via the gateway at `Adapter.execute(req, cred)` from the
   vault (`vault://{tenant}/{adapter}`). `agentx_mandate` may NOT import `agentx_contracts.security`/
   `config`, `agentx_db`, or `pymongo`.
3. **No raw fact crosses customers** — only graded behavior + distilled patterns travel between instances.
4. **No brain in the live kernel** — adapters are actuators, not brains; no adapter runs an autonomous loop.
5. **A syscall is intent; fulfillment is swappable; the human-task queue is the bottom rung** —
   `SyscallRegistry.resolve` never returns None.
6. **Money is API-only, idempotent, never LLM/browser** — and you are building NO money adapters.
7. **No synthetic case promotes a customer-facing version** — enforced in `PromotionGate` via
   `Scorecard.origin`/`EvalCase.origin`. The Creator emits **candidates only**; promote needs real+human.
8. **The business is the sender of record** — channel identity is **per-instance**, never shared. The
   send adapter MUST use the instance's own sender identity; idempotency MUST prevent double-send.

---

## 3. The lane fence + the frozen seam (these break loudly if you violate them)

- **`packages/contracts` is FROZEN.** Build against it. If you think you need a new/changed contract:
  **STOP and emit a `BLOCKED: contract change needed` question.** Do not invent a contract, do not work
  around it. (Most phases need NO contract change — `MandateType`, `EvalCase`, `Scorecard`, `Trace`,
  `Faculty`, `SyscallRequest/Result` already cover this work.)
- **Two lanes, connected only through `agentx_contracts`:**
  - **Claude lane:** `packages/kernel`, `packages/mandate` (must NOT import `agentx_syscall`/`agentx_swarm`).
  - **Codex lane:** `packages/syscall`, `packages/swarm` (must NOT import `agentx_kernel`/`agentx_mandate`).
  - **Composition edge:** `api/` (`agentx_api`) is neither lane — it MAY import any package. The
    send adapter lives in the syscall lane; Step-D in the kernel lane; the Creator spans mandate+syscall;
    promote spans kernel+api; the compiler lives in the swarm/foundry lane.
- `uv run lint-imports` must stay **3 kept / 0 broken** after every phase. If it breaks, you put code
  in the wrong lane — move it, don't suppress it.

---

## 4. THE GATE (run ALL of it after every phase; paste the output; must be fully green)

```bash
uv run ruff check .
uv run mypy --strict packages db tests
cd api && uv run mypy --strict src tests && cd ..      # the api/ dir has its OWN mypy (fastapi lives there)
uv run pytest -q
cd api && uv run pytest -q && cd ..                     # the api/ dir has its OWN pytest
uv run lint-imports                                     # expect: 3 kept, 0 broken
cd dashboard && PATH=/opt/homebrew/bin:$PATH npm test && PATH=/opt/homebrew/bin:$PATH npm run build && cd ..
```

- The dashboard build must keep passing even on backend-only phases — **don't break the frontend.**
- Node ≥18 for dashboard: prefix `PATH=/opt/homebrew/bin:$PATH` (system node is v16).
- The two live-gated tests stay skipped (`RUN_LIVE_PROMPTFOO=1`, `RUN_LIVE_HERMES=1`). Add a
  `RUN_LIVE_EMAIL=1` skip-gate for the real send path — unit tests use a FAKE transport, never a real send.

---

## 5. What is already BUILT — reuse, do NOT rebuild

Read `docs/STATE_AND_ROADMAP.md` first (the verified gap map). Highlights:
- **Kernel (online):** run-loop, gateway (ring/idempotency/credential-injection/journal), verifier,
  settlement, projections, hydration, durable resume, scheduler worker — all proven. `packages/kernel`.
- **Mandate:** four faculties (research/judgment/memory-craft/escalation), harness seam,
  `build_lead_finder_type()`. `packages/mandate`.
- **Syscall ladder:** `_AdapterBase` pattern in `packages/syscall/.../adapters.py`
  (`DraftEmailAdapter` is your model for the send adapter — note `external_message`/L2/`sent:False`),
  `registry.py` (`build_phase1_registry`), the `human_task` terminal tail.
- **Swarm/Foundry:** `SimAdapter`, promptfoo `Judge` (offline fallback), `PromotionGate`,
  scenario packs, `trace_to_viewer_payload`. `packages/swarm`.
- **Settlement watches:** `settlement.py` already journals `WatchRegistered` per watch — Step-D builds
  the *maturation* half on top (it does not yet promote facts or emit real eval cases).
- **API + dashboard:** `api/src/agentx_api/` (routes, `OperatorRuntime`, `swarm_runner.py`); the
  dashboard is operable with realtime SSE. Add API routes the frontend will later consume; don't build UI.

Do not reimplement any of the above. Extend through the existing Protocols and registries.

---

## 6. Per-phase discipline (the four-part contract for every task)

Every phase in `docs/HERMES_BUILD_PLAN.md` gives you: **Goal · Context · Constraints · Done-when**.
For each:
1. Write the failing tests that encode every "Done-when" assertion. Run them — confirm RED.
2. Implement the smallest change to go GREEN. Stay inside the named files/lane.
3. Run the FULL gate. Paste it. If anything is red, fix it before moving on.
4. Self-review your diff against §2 (invariants) and §3 (lane fence). Commit `[hermes] <phase>: <what>`.
5. Update `docs/STATE_AND_ROADMAP.md` for the gap you closed.

---

## 7. Checkpoint Review Prompt — emit this verbatim (filled in) after Phase 2, then STOP

```
CHECKPOINT — Phases 1–2 complete, requesting Claude review before Phase 3.

Branch / commits: <branch>, <commit shas + one-line messages>
Gate output (pasted, full): <ruff / mypy x2 / pytest x2 / lint-imports / dashboard test+build>

Phase 1 (send): what I built, the new files, the adapter's maturity/risk/ring, how idempotency +
  per-instance sender identity (invariant #8) are enforced, how credentials flow from the vault
  (invariant #2), and the test that proves no double-send. Live path gated on RUN_LIVE_EMAIL=1.
Phase 2 (Step-D): how a matured watch promotes probation→verified facts, updates trust/résumé, and
  emits exactly one eval_case(origin="real"); the test that proves the count delta + the gate now
  sees real evidence.

Open questions / judgment calls I made: <list>
Anything I was tempted to change in packages/contracts (and why I did NOT): <list or "none">

Please review critically: invariants intact? lane fence 3/3? contracts untouched? tests honest
(not asserting trivialities)? Approve to continue to Phase 3, or return changes.
```

When in doubt at ANY point: **STOP, emit `BLOCKED: <question>`, and wait.** A paused phase is cheap;
a broken main or a violated invariant is expensive.
