# Agent-X — State of the Build & Roadmap

*Companion to [BLUEPRINT.md](./BLUEPRINT.md) (canonical). This doc is the living snapshot: **what is built
today**, **what is left**, and **how to tackle it**. When this and the blueprint disagree on intent, the
blueprint wins; when they disagree on *what currently exists in code*, this doc wins (it's verified against
the tree). Last verified: 2026-06-18 after Sessions D–G. Session E fixed the P0/P1 correctness issues,
Session F made MiniMax drive the loop and produced sendable leads, and Session G made trigger/approval runs
repeatable through first-class resume + scheduler-min. Items below marked ✅ are live-proven; remaining
🟢/🟡 are proven-but-incomplete. See the session proof documents for exact evidence.*

> **Status legend:** ✅ built & proven (live) · 🟢 implemented + live-proven but blocked/incomplete · 🟡 partial / scaffolded · ❌ not built · 🏗️ in progress (parallel agent)

> **Session G (2026-06-18) update:** **G2 (repeatable runner + first-class parked-run resume + scheduler-min)**
> is built and live-proven. A real dental run went trigger→park→ApprovalResolved→kernel resume→verify→settle
> through Mongo-backed work items; same-key receipt replay added zero journal rows. See
> [SESSION_G_LIVE_PROOF.md](./SESSION_G_LIVE_PROOF.md). Next: Step D maturation, then P2 polish.

---

## 0. The whole system on one screen — *what we actually have*

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│  CONTROL SURFACE — Manager Dashboard (§6)                                      │
│  approval inbox · manual queue · instance file · floor · swarm view   🏗️ DONE  │
│  (built in parallel; backed by KernelControl API — verify integration)         │
└───────────────────────────────────┬────────────────────────────────────────────┘
                                     │ KernelControl (control.py): approval_inbox,
                                     │ instance_file, floor, approve, set_ring  ✅
   USER SPACE (rented, disposable)   │   CONTROL PLANE (ours)
   ┌──────────────────────────────┐  │  ┌──────────────────────────────────────────┐
   │ MANDATE pod (agentx_mandate)  │  │  │ ONLINE — live KERNEL (agentx_kernel)        │
   │  faculties: research·judgment │◀─┼─▶│  run_loop (Phase1RunInvoker)        ✅      │
   │   ·memory-craft·escalation ✅ │  │  │  gateway: ring·idem·channel·adapter         │
   │  harness seam: Think/Call/    │  │  │   ·credential-inject·journal        ✅      │
   │   Claim/Escalate/Finish,      │  │  │  verifier: rules rung + human park  ✅      │
   │   HarnessSession.step()  ✅   │  │  │  settlement + projections (event-src)✅     │
   │   OwnHarness + playbook  ✅   │  │  │  hydration (freeze snapshot)        ✅      │
   │  pod holds NO creds      ✅   │  │  │  ConfigVault (credential inject)    ✅      │
   │  LLM DRIVES the loop?    ✅   │  │  │  HermesClient → Minimax (Reasoner)  ✅      │
   └──────────────┬───────────────┘  │  │  scheduler / worker loop            ✅      │
                  │ intent           │  │  parked-run RESUME api (kernel)     ✅      │
   ═══════ ADAPTER LINE ═════════════╪══│  ──────────────────────────────────────────│
                  │                  │  │ OFFLINE — FOUNDRY (agentx_swarm)            │
   ┌──────────────▼───────────────┐  │  │  SimAdapter / SimRegistry           ✅      │
   │ SYSCALL (agentx_syscall)      │  │  │  promptfoo Judge (+offline fallback)✅      │
   │  gateway → adapter ladder:    │  │  │  PromotionGate (bars synthetic)     ✅      │
   │  lead_research_batch (Exa/    │  │  │  scenario packs (indian_b2b_v1)     ✅      │
   │   Firecrawl) ✅ · read_url ✅ │  │  │  trace viewer payload               ✅      │
   │  draft_email (DRAFT only) ✅  │  │  │  swarm REPL surface (cmds)          ❌      │
   │  queue_manual_action ✅       │  │  │  CREATOR mandate (makes mandates)   ❌      │
   │  mark_outcome ✅              │  │  │  compiler (GEPA growth loop)        ❌      │
   │  HUMAN-TASK tail ✅           │  │  └──────────────────────────────────────────┘
   └──────────────┬───────────────┘  │
                  ▼                   │   PERSISTENCE (agentx_db, MongoDB async)
   reality: Firecrawl/Exa (live) ✅   │   journal·heap_fact·thread·resume·watch·
   email send ❌(P2) · WhatsApp ❌(P5)│   syscall_trace·billing_line·eval_case  ✅ wired
                                      │   mandate_type·mandate_instance·mandate_run ✅ persists (Session E, live /instances proven)
```

**Read this diagram as:** the online kernel, syscall ladder, event sourcing, LLM-driven harness,
first-class resume, scheduler-min worker, and swarm grading loop are real. The remaining Phase-1 feedback
gap is deferred maturation: reality must promote probation facts and emit real graded cases.

---

## 1. What is BUILT and PROVEN ✅ (with evidence)

### Kernel (online, deterministic) — `packages/kernel`
- **Run loop** `Phase1RunInvoker.invoke()` — hydrate → faculties → gateway → verify → settle. `run_loop.py`
- **First-class resume** `Phase1RunInvoker.resume()` — restores a durable continuation, replays the parked
  syscall idempotently, continues the harness, verifies, and settles. `run_loop.py`, `continuations.py`
- **Scheduler-min worker** — deterministic trigger/approval work, in-memory + atomic Mongo stores.
  `scheduler.py`, `stores/`
- **Gateway** — ring check → idempotency (journal replay) → channel rule → adapter resolve → **credential
  injection** → execute → journal Attempted/Settled. Parks when ring is too low. `gateway.py`
- **Verifier** — deterministic `rules` rung (`claimed_facts >= N`, `fact:PRED exists`) + **human approval
  park/resolve** as journal events. `verifier.py`
- **Settlement + projections** — one atomic `RunSettled`; facts → heap with **provenance** (`probation`),
  journal is source-of-truth, heap/resume/syscall_trace are projections. `settlement.py`, `projections.py`
- **Hydration** — freezes a working-set snapshot onto the run. `hydration.py`
- **ConfigVault** (Session C) — config-backed credential injection; pod never sees the secret. `vault.py`
- **KernelControl** — `approval_inbox`, `instance_file`, `floor`, `approve`, `set_ring` (manager API). `control.py`
- **Stores** — in-memory (sim/tests) + **PyMongo async** (live). Journal **seq race hardened** (Session C). `stores/`
- **HermesClient** — OpenAI-compatible client → Minimax; **proven live** (Hermes↔Minimax test passes). `hermes.py`

### Mandate (user-space pod logic) — `packages/mandate`
- Four faculties: **research** (emits read intent, no fabrication after Session C), **judgment** (scores),
  **memory-craft** (provenance-stamped fact claims), **escalation**. `faculties/`
- Harness seam: `Think/Call/Claim/Escalate/Finish`, `HarnessSession.step()`/`HarnessRunner` Protocols,
  `OwnHarness` (recorded | playbook). The live and sim loops both drive this seam. `harness.py`
- `build_lead_finder_type()` — the Phase-1 mandate, in code. `library/lead_finder.py`

### Syscall ladder — `packages/syscall`
- Real adapters: `lead_research_batch` + `read_url` (Exa/Firecrawl SDK), `draft_email` (**draft only,
  `sent:false`**), `queue_manual_action`, `mark_outcome`, and the **`human_task` terminal tail**. `adapters.py`
- `Phase1SyscallRegistry` / `build_phase1_registry()` — maturity-ranked resolve, human tail guaranteed. `registry.py`

### Swarm / Foundry-min — `packages/swarm`
- `SimAdapter`/`SimRegistry` (deterministic), `PromptfooJudge` (shells `npx promptfoo` over OpenRouter; **offline
  fallback** when keys absent), `PromotionGate` (**bars synthetic-only**, allows real+human), scenario packs,
  trace viewer. **End-to-end proven in sim** (Session C T6).

### Persistence — `packages/db` / MongoDB
- Collections + indexes for journal/heap/thread/resume/watch/syscall_trace/billing/eval_case plus
  run-continuation and scheduler work **wired & used**.
- **Proven live**: a real dogfood run settled with provenance facts in Mongo (Session C T7).

### Invariants enforced
- Lane isolation + `mandate` holds-no-credentials enforced by `lint-imports` (3/3) + `tests/test_credential_boundary.py`.
- Gate green after Session G: `mypy --strict` (99 files), `ruff`, `pytest` (111 + 2 live-gated skips),
  import fences 3/3, seam proof green.

---

## 2. What is LEFT — the gap table

| # | Gap | Status | Why it matters | Blueprint ref |
|---|---|---|---|---|
| G1 | **LLM drives the run loop** via `step()` (proposes; kernel disposes) | ✅ | **Session F:** the run loop drives `HarnessRunner.step(observation)`. Live, MiniMax-M3 (OpenAI tool-calling) emits Think/Call/Claim/Finish and the kernel disposes (ring-checks + journals effectful Calls, fulfils reads + feeds the SyscallResult back, stamps fact provenance, verifies + settles); sim drives `OwnHarness` + a lead-finder playbook. **Live-proven end-to-end** (2 ICPs). The hardcoded faculty order + hardcoded draft are gone | §2.3, §4.5 |
| G2 | **Scheduler / worker loop + kernel parked-run RESUME** | ✅ | **Session G:** TriggerWork invokes; ApprovalWork calls first-class `resume()`. Durable continuation stores preserve frozen snapshot/scratch/claims/trace/cursor/Hermes history and exact pending call. Live dental run settled through the Mongo worker; same-key replay returned the receipt with zero journal delta. Scripts no longer hand-build gateway replay/verify/settle. See `SESSION_G_LIVE_PROOF.md` | §4 (scheduler), §2.4 |
| G3 | **Deferred-settle / WATCH → gym** | ✅ source bug fixed + live-proven; loop still ❌ | **Session E P0-1** fixed the source bug: `SettlementCommitter.commit` now journals + projects a `WatchRegistered` per watch (thread-advance still deferred — no frozen Phase-1 thread event). **Live-proven (Session E proof):** a live settle appends `watch_registered` (seq 16, right after `run_settled`) and projects **one `WATCH` doc in Mongo (count=1, was 0)**. The **full deferred-settle maturation loop** (watch matures → probation→verified → emit real `eval_case`, Step D) is still **not built** | §2.7, §5 |
| G4 | **Real, actionable lead quality** | ✅ sendable leads live-proven (2/2 ICPs) | **Session F (after G1 landed):** with the LLM driving multi-step research (search → refine query → read 3–4 candidate pages → ground claims → draft), the loop produced a **founder-sendable, evidence-grounded draft for BOTH Session-E ICPs**: dental (Microdent Dentistry, Pune — SETTLED) and the vendor-shaped ICP (American Marketing & Publishing, DeKalb IL — **competitor rejection now works**; it picked a buyer, not Callbox/Belkins). Each lead = real org + decision-maker grounded in cited page text + reachable URL + a citable buying signal — vs Session E's **0/6**. Honest caveats: quality depends on search results (the LLM skips junk and refines queries); the dental signal is partly interpretive while the vendor signal is a hard growth signal. See [SESSION_F_LIVE_PROOF.md](./SESSION_F_LIVE_PROOF.md) §F5 | §7 WIN |
| G5 | **Mandate registry / Catalog persistence** | ✅ implemented + live-proven | **Session E P1-3** added a projection-backed `MandateRegistry` that persists `MandateType`/`MandateInstance` and exposes register/instantiate/list via `KernelControl`; live edge persists a real instance. **Live-proven (Session E proof):** a real non-`inst_demo` instance (`agentx_dogfood_…`, customer "Agent-X dogfood") is in Mongo `mandate_instance` and is surfaced by `/instances` with its settled run, facts, and watch ids | §1, §6 (Catalog) |
| G6 | **Trust-ladder promote/demote automation** | 🟡 | `set_ring` is manual; no "N clean → propose promote / verified failure → demote" mechanics | §4 trust ladder |
| G7 | **`score_lead` syscall** | 🟡 | Declared in gateway policy but has no adapter (judgment scores in-pod). Harmless, but inconsistent with §7 | §7 |
| G8 | **Swarm REPL command surface** (`/create /run /watch /patch /promote`) | ❌ | Pieces work; no interactive loop for the founder to iterate a candidate | §5 |
| G9 | **Manager Dashboard** | ✅ truthfulness fixed + live-proven (API path) | `agentx_api` + Next dashboard are built and honest about missing commands (`gaps.py`). **Session E P0-3** made the approval card truthful (gateway journals `SyscallAttempted` before the park; `approval_inbox` returns the real draft card). **Live-proven (Session E proof):** at park the journal kinds are `[…, syscall_attempted, run_parked]`, so the dashboard reconstruction `api/state.py:_drafted_effect` returns `draft_email` (CORRECT) with the full draft body — was null/wrong in Session D; and `/instances` (Mongo-backed, no `seed_demo`) returns the real registry instance. (The React UI itself was not browser-opened this session — proof is at the API/contract code path that backs it.) | §6 |
| G10 | **Creator Mandate** (assemble a Type from a description) | ❌ | On-plan as *later*; Phase-1 Foundry-min is the swarm only | §5 |
| G11 | **Operator Agent** (founder's chief-of-staff over the control surface) | ❌ | Later; needs the dashboard command/query API as its tool surface | §6.1 |
| G12 | **Compiler (GEPA growth loop)** | ❌ | Later; needs a full gym of real cases first | §5 |
| G13 | **Phases 2–5 channels** (send email, calendar, CRM, browser, voice, WhatsApp, money) | ❌ | **Deliberately deferred** — not Phase 1 | §7 |

---

## 3. How to tackle it — the completion path

**Sequencing principle:** finish the *agent* and the *repeatability* first (G1, G2), because everything else
(quality, grading, trust) compounds on top of a loop that actually runs itself many times. Keep the gate green
and the seam proof passing on the OwnHarness double at every step.

```text
  ── PHASE 1 COMPLETION (close the WIN: "one instance settles vs reality ~100×") ──────────────
  STEP A  G1  The real agent loop                                  ✅ SESSION F — DONE & LIVE-PROVEN
              • MiniMax-M3 (OpenAI tool-calling, 4 concrete syscall tools) drives HarnessRunner.step();
                kernel disposes (ring-check + journal effectful Calls, fulfil reads + feed result back,
                stamp fact provenance, verify + settle). Hardcoded draft moved into the lead-finder PLAYBOOK.
              • mode selects: live→Hermes runner+live registry; sim→OwnHarness(playbook)+sim registry.
              • Agent-loop resilience added: gateway turns adapter exceptions into error results; the loop
                FEEDS syscall errors back so the LLM recovers (only Escalate + max_steps terminate).

  STEP B  G2  Repeatable runner + kernel resume                    ✅ SESSION G — DONE & LIVE-PROVEN
              • restore frozen continuation + Hermes history; replay approved call through receipt-backed
                gateway; continue to verify + settle.
              • scheduler-min: trigger→run; ApprovalResolved→resume→settle (memory + Mongo).
              • live dental proof: one attempt, one settlement, zero-row receipt replay.

  STEP C  G4  Real, actionable leads (multi-step research)         ✅ SESSION F — sendable leads live-proven (2/2 ICPs) now that G1 landed (LLM does search→refine→read→ground→draft)
              • search → pick real candidate COMPANIES → read_url top picks → extract
                {company, decision-maker/role, buying signal, source URL} → judgment on real signals →
                memory-craft real provenance → draft_email = usable per-lead outreach.
              • add a postcondition barring non-actionable "leads" (require real URL + org-name + cited signal).

  STEP D  G3  Deferred-settle / WATCH → gym                        🟡 watch now registers + live-proven (Session E P0-1: WATCH doc count=1); maturation→promote→eval_case loop NOT built (the only remaining half of Step D)
              • watch matures (or mark_outcome) → promote probation→verified, update résumé/trust,
                emit run as graded eval_case origin="real" (PromotionGate already needs a real origin).

  STEP E  G5  Mandate registry + Catalog                           ✅ SESSION E LANDED + live-proven (MandateRegistry persists type/instance via KernelControl; real instance on /instances)
              • persist/load MandateType (mandate_type, unique name+version), InstanceBinding
                (mandate_instance), run rows (mandate_run). MandateRegistry behind a Protocol +
                KernelControl: register_type / list_catalog / instantiate / get_instance_file.
              • script loads the Type by type_ref instead of building it inline.

  STEP F  G6/G7  Trust ladder mechanics + score_lead tidy-up (smaller; do after A–E)   ❌ NOT STARTED

  ── BEYOND PHASE 1 (use BLUEPRINT §5–7 + this doc; only after A–E settle repeatedly) ──────────
  G8  Swarm REPL command surface (CLI is fine; don't build MiroFish / don't depend on Hermes Swarm)
  G10 Creator Mandate (assemble Type from description → swarm → gate → catalog)
  G11 Operator Agent (gated privileged user of the dashboard API; never inside the live kernel)
  G12 Compiler / GEPA growth loop (needs a real gym corpus)
  G13 Phase 2 (approved email/calendar/CRM) → 3 (browser) → 4 (voice) → 5 (WhatsApp). Money: API-only, gated.
```

---

## 4. Definition of "Phase 1 complete" (the finish line)

From BLUEPRINT §7 — **the whole game is: get one instance to `settle()` against reality ~100 times.**
Concretely, Phase 1 is done when:

```text
[✅] one lead-finder mandate runs end-to-end and settles with provenance facts        (done once)
[✅] the LLM actually drives the run (G1) — not a deterministic pipeline               Session F: live, MiniMax drives step(); kernel disposes
[✅] runs are repeatable without hand-wiring (G2) — toward ~100 settles                Session G: live worker + kernel resume proven; 100 settles not yet run
[✅] leads are actionable: real orgs/people/URLs + usable drafts (G4)                  Session F: founder-sendable, grounded drafts on 2/2 ICPs (dental settled; vendor parked)
[🟢] reality grades runs back into the gym (G3)                                        watch registers + live-proven (Session E: WATCH count=1); maturation→promote→eval_case loop still ❌
[✅] manager can approve from a dashboard surface (G9)                                 approval card truthful + live-proven at API path (Session E); React UI not browser-tested
[✅] (nice) mandates live in a catalog, not in code (G5)                               registry persists + real instance live on /instances (Session E)
```

**Kill-conditions to keep honest (BLUEPRINT §8):** if owners won't tap Approve, the trust ladder's bottom rung
is broken; if the compiler doesn't beat hand-tuning by ~customer 5, the gym is decoration; if churn doesn't
rise with heap depth, context-gravity is fiction. Watch these as real data arrives.

---

## 5. How to use this doc
1. ~~**Now:** run the evaluation/shakedown session~~ ✅ **DONE (Session D, 2026-06-18)** → see
   [EVAL_FINDINGS.md](./EVAL_FINDINGS.md): lead quality judged (0/6 actionable), kernel/swarm/dashboard/memory
   exercised live, prioritized P0/P1/P2 punch-list + a ready-to-paste **Session E** prompt produced.
2. ~~**Now:** run **Session E** — clear P0/P1~~ ✅ **IMPLEMENTED + LIVE-PROVED + MERGED (Session E, 2026-06-18,
   branch `session-e/p0-p1-fixes`, PR #3):** settlement watch (P0-1), faithful idempotency replay (P0-2), truthful
   approval card (P0-3), actionable-lead pipeline (P1-1), real promptfoo judge (P1-2), mandate persistence
   (P1-3). Offline + seam + live-Hermes gate green. **LIVE PROOF DONE** (Task 7): all three P0 bugs reproduced
   as fixed; 2 live ICP runs (machinery actionable, but sendable leads blocked on G1); real promptfoo Scorecard
   over OpenRouter on Node v24.13.1; real non-demo instance on Mongo/`/instances`. Full evidence in
   [SESSION_E_LIVE_PROOF.md](./SESSION_E_LIVE_PROOF.md).
3. ~~Step A (G1), Step B (G2), and Step C (G4)~~ ✅ **DONE and live-proven through Session G.** Next =
   **Step D maturation** (watch/`mark_outcome` → probation→verified, trust/résumé, graded
   `eval_case origin="real"`), plus P2 polish; then accumulate settles toward ~100.
