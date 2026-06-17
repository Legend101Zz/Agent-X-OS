# Agent-X — The Finalized Blueprint

*The canonical, build-from document. Consolidates everything from [README.md](./README.md), [MANDATE.md](./MANDATE.md), [SYSCALLS.md](./SYSCALLS.md), [ARCHITECTURE.md](./ARCHITECTURE.md), and the [syscall landscape research](../../Documents/Startup%20Idea/AGENT_X_SYSCALL_TOOL_LANDSCAPE_RESEARCH.md). When these disagree, this doc wins.*

> **One sentence:** Every business is a program; today humans run it by hand; Agent-X is the operating system that runs it — **mandates** are its processes, **trust rings** are its permissions, **syscalls** are how it touches the world, and **memory only commits when reality verifies it.**

> **Validation:** The OS framing is not a metaphor we invented in a vacuum. The [AIOS paper](https://arxiv.org/html/2403.16971v5) builds an LLM-agent kernel with a scheduler, snapshot/restore context manager, memory manager, tool manager, and a privilege-based access manager with user intervention. They built an OS for *running* agents efficiently. **We build the OS for *employing* them accountably** — authority, verification, settlement, trust, and verified business memory, which AIOS does not address. AIOS could even be a substrate we run on. The decomposition is proven; the employment layer is ours.

---

## 0. The whole system on one screen

```text
┌──────────────────────────────────────────────────────────────────────────┐
│  CONTROL SURFACE  (Manager Dashboard — §6)                                │
│  live floor · approval inbox · mandate catalog · instance files ·          │
│  eval gym & swarm · capability registry · P&L     ── all = views on kernel │
└───────────────────────────────────┬────────────────────────────────────────┘
                                     │
   USER SPACE (rented, disposable)   │   CONTROL PLANE (ours — the company)
   ┌──────────────────────────────┐  │  ┌────────────────────────────────────┐
   │ per-CUSTOMER pods            │  │  │  ONLINE — the live KERNEL (§4)       │
   │  faculties reason & draft    │◀─┼─▶│   scheduler · heap+journal · verifier │
   │  Hermes / OpenClaw / Cheetah │  │  │   syscall gateway · rings · supervis. │
   │  zero creds · zero state     │  │  │                                      │
   └──────────────┬───────────────┘  │  │  OFFLINE — the FOUNDRY (§4, §5)      │
                  │ intent           │  │   gym · swarm · compiler · creator   │
   ═══════ ADAPTER LINE ═════════════╪══│   (intelligence lives here, gated)   │
                  │                  │  └────────────────────────────────────┘
   ┌──────────────▼───────────────┐  │
   │ SYSCALL / INTEGRATION (§3)   │  │  Two things flow OUT of the kernel:
   │  gateway → adapter ladder →  │  │   ← REVENUE  (real effects in the world)
   │  API / connector / vendor /  │  │   → MOAT     (verified outcomes compiled
   │  browser / HUMAN-TASK queue  │  │              into better mandates)
   └──────────────┬───────────────┘  │
                  ▼
   HARDWARE (reality): WhatsApp · email · calendar · CRM · payments · phone · web
```

Three pillars to build, in order of how much they're *ours*: **the Mandate (§1–2)**, **the Kernel (§4)**, **the Syscall layer (§3)**. Then the two operator tools: **the Creator (§5)** and **the Dashboard (§6)**.

---

## 1. Pillar 1 — How a MANDATE looks

A mandate = an AI worker wrapped in an employment contract. It exists at three layers:

```text
   MANDATE TYPE        the class    — shared by all customers · almost open-source
        │                            (charter · faculties · domain pack ·
        │                             verification · settlement · gym · routing)
        │  instance registry: one per business
        ▼
   MANDATE INSTANCE    the object   — private to one business · THE MOAT
        │                            (heap region · trust/ring · résumé ·
        │                             channel binding · learned overrides)
        │  run table: one per trigger (durable, can park for days)
        ▼
   MANDATE RUN         the frame    — does the work, then dies at settlement
                                      (frozen hydration snapshot · trace ·
                                       claimed facts · scratchpad)
```

### The seven organs of a Type

```text
   1. CHARTER       what "done" means, checkable    pre / path / post conditions
   2. FACULTIES     reusable capability modules      research · conversation · …
   3. DOMAIN PACK   vertical knowledge + priors      "clinics book 2× if slot offered"
   4. VERIFICATION  the commit-time type system       rules → judge → human → reality
   5. SETTLEMENT    commit rules                       memory · trust · billing · spawn
   6. EVAL GYM      reality-graded benchmark + compiler  (the quality engine, §5)
   7. EXECUTION     per-faculty harness×model routing    (the disposable layer)
```

A **faculty** is the SDK brick — `{ skill_pack, tool_manifest (syscall stubs), rubrics, eval_slice, routing_hint, harness_adapter }`. Faculties are shared and compounding: fix `research` once, every mandate that links it improves. `memory-craft` and `escalation` are faculties too — writing good memory and failing safely are engineered once, reused everywhere.

**A faculty is a capability *contract*; the harness *realizes* it.** The `harness_adapter` is where a faculty binds to a specific harness (Hermes, OpenClaw, …) — and it does so by *enabling that harness's native skills*, not by reimplementing them. `research` turns on OpenClaw's web/MCP skills; `conversation` turns on Hermes's messaging/memory. The adapter then re-points every *effectful* tool to our gateway (the pod still holds no credentials) and treats the harness's native memory as per-run scratch only. So a faculty carries a **fulfillment preference** that mirrors the syscall ladder: *prefer the harness's strong native skill → fall back to our own implementation → hybrid.* The contract is harness-agnostic, so harnesses stay swappable (Model D) while we use each to its full native capability — see [§4.5](#45-using-harnesses-to-full-capability-safely).

### What each axis of quality maps to (so "make it good" is concrete)

| Axis | Question | Owned by |
|---|---|---|
| Perception | knows enough before acting? | hydration + heap + domain pack |
| Competence | acts well? | faculties + compiled prompts |
| Judgment | knows what it doesn't know? | verification + rings + escalation |
| Growth | run #1000 > run #1? | gym + compiler + settlement |

---

## 2. How a mandate RUNS (the core loop, end to end)

```text
  1. TRIGGER         message / deadline / spawn / demand arrives
  2. CREATE RUN      kernel makes a run row, freezes a HYDRATION snapshot from
                     the instance's heap (facts ranked by relevance×conf×recency)
  3. THINK           faculties (in a disposable pod) reason & draft.
                     pod holds NO credentials; every tool is a syscall stub.
  4. ACT (syscall)   gateway checks ring → idempotency → channel rules →
                     picks an adapter → injects credential → executes → journals.
                     too risky for current ring?  →  PARK + approval card to human
  5. VERIFY          rules → judge → human → (later) reality
  6. SETTLE          ONE atomic commit:
                       facts → heap (with provenance, on probation)
                       trust → résumé   ·   billing line   ·   journal (WAL)
                       register WATCH (did it really work in 72h?)
                       maybe SPAWN a child mandate
  7. DEFERRED SETTLE when the watch fires: promote facts, confirm trust,
                     run becomes a GRADED eval case → feeds the gym
```

Two semantics that never bend: **a human approval is just a parked state** (mechanically identical to waiting on a webhook), and **inter-mandate communication is the heap, not a message channel** — spawn is the call, committed facts are the return value.

### The memory layer (how a later run knows what to do, and what was done)

The harness remembers **nothing** across runs — each run is a fresh, disposable pod. Continuity is entirely the kernel's job: it **hydrates** a run from the instance's memory at the start, and **settles** back at the end. Memory is four per-instance stores (the moat) plus two shared type-level stores (the quality engine):

```text
   INSTANCE MEMORY (per business — private, the moat)
   ├── Heap      (semantic)    verified facts + provenance + confidence + decay
   │                           "accepts Star Health", "cleaning ₹1500"
   ├── Journal   (episodic)    what was DONE — every run, effect, outcome (the WAL/ledger)
   ├── Threads   (relational)  per-entity/conversation state: where we are with THIS lead/
   │                           patient ("messaged twice, asked price, awaiting reply")
   └── Résumé    (performance) trust/ring level, success rates — what this instance earned

   TYPE MEMORY (shared across businesses — improved by the gym)
   ├── Faculties (procedural)  compiled skill_packs = HOW to do the work
   └── Domain pack (priors)    distilled cross-customer patterns (never raw facts)
```

**Hydration = the read side:** at run start the kernel assembles a working set — relevant heap facts (ranked relevance × confidence × recency), the open thread for this entity, recent journal events, and the type-level skill_pack + domain pack — and freezes it onto the run as the snapshot the harness sees. The harness "knows what it needs to do and what was done" because we *told* it, fresh, this run. **Settlement = the write side:** verified facts → heap, the event → journal, thread advanced, trust → résumé. The harness is stateless by design; the memory layer is ours — which is why it survives harness swaps, stays auditable, and *is* the moat. *(Storage note: the Journal is the source of truth — an append-only event collection — and Heap/Threads/Résumé are projections built from it.)*

---

## 3. Pillar 3 — How the SYSCALL / INTEGRATION layer looks

This is "how mandates actually *do* things." The principle, validated by your research and the whole market: **own the gateway, rent the adapters, and a human is just the bottom adapter.**

### The gateway (ours — the moat)

```text
   faculty: "send this WhatsApp"          (intent — names WHAT, never HOW)
        │
        ▼
   ┌─────────── SYSCALL GATEWAY (kernel) ───────────┐
   │  ring check        (is this allowed now?)       │
   │  idempotency key   (LLMs retry; never double-do)│
   │  channel rules     (WhatsApp 24h window? opt-in?)│
   │  pick adapter      (first capable on the ladder) │
   │  inject credential (from vault — never to pod)   │
   │  execute + journal (audit trail = the ledger)    │
   └──────────────────────────┬──────────────────────┘
                              ▼   fulfillment ladder ↓
```

### The fulfillment ladder (climb as volume justifies)

```text
   1. Official API / official MCP server   most reliable, idempotent (Stripe, Google, HubSpot)
   2. Managed connector platform           Composio · Nango · Pipedream · Arcade (OAuth + vault)
   3. Specialized vendor SDK                Patter (voice) · AgentMail (email) · Kapso (WhatsApp)
   4. Browser / computer-use                Playwright MCP · Stagehand — LAST RESORT, never money
   5. HUMAN-TASK QUEUE  ◀── the tail of EVERY ladder. nothing is ever "unimplemented."
```

**The bottom rung is the unlock.** A new mandate ships before *any* hard integration exists: easy effects hit an API, everything else lands in the dashboard's manual queue, a human does it and marks the result (which feeds the gym). The interface (`send_whatsapp`) is frozen while the backend climbs from human → API. Difficulty becomes the moat; the manual queue's volume tells you exactly which integration to automate next.

### The adapter contract (every syscall installs as a plugin)

Adopted from your research doc — this is the extensibility layer that lets us add tools fast:

```text
   SyscallPlugin {
     name           "send_email"
     category       "communication"
     maturity_level 0=manual | 1=draft | 2=semi | 3=api
     risk_class     "external_message"
     required_ring  "L2"
     tenant_auth    oauth | api_key | agent_owned | manual
     input_schema   JSONSchema      output_schema  JSONSchema
     adapter()      dry_run()  verify()  settle()  health_check()  fixtures[]
   }
```

Adding a syscall = registering one plugin. **MCP is the protocol** the faculty speaks and the way we absorb the existing ecosystem (point an adapter at any MCP server → inherit it). But MCP is *behind* our gateway, never handed raw to the harness — the gateway adds the ring/idempotency/audit/tenancy that MCP lacks. Design syscalls **coarse/batched** (`lead_research_batch(criteria, count)` not five chatty calls) to cut latency and token cost.

### Own vs. rent (where effort goes)

| BUILD (the moat) | RENT (commodity — wrap, don't reinvent) |
|---|---|
| gateway · rings · idempotency · audit ledger | calendar / email / CRM / Stripe connectors |
| tenant isolation · approval policy · channel rules | OAuth vaults (Nango / Composio / Arcade) |
| verified heap · settlement · résumé · trust | web read (Agent-Reach / Exa / Firecrawl) |
| syscall **registry** + health checks + fixtures | voice (Patter) · browser (Playwright) · sandbox (E2B) |
| the manual-projection queue | the raw tool catalogs themselves |

> Rule: spend zero effort on commodity adapters so 100% goes to the gateway, the faculties, and the gym — the only three things that are actually ours.

---

## 4. Pillar 2 — How the KERNEL looks

The kernel has **two clocks**. This is the most important structural decision in the whole system.

```text
  ONLINE — the live kernel (dumb, trustworthy)   OFFLINE — the Foundry (smart, gated)
  ────────────────────────────────────────────   ──────────────────────────────────────
  runs per trigger, touches real money/customers  runs on a cadence, touches nothing live
  100% deterministic code                         optimizer + judges + swarm + creator
  "thinks" only via scoped, gated tool calls      intelligence concentrates here, safely
  ───────────────────────────────────────────     every output is a CANDIDATE, gated before
  modules:                                          it can go live
    scheduler    reality + deadlines → runs        ──────────────────────────────────────
    heap         per-customer, transactional       gym       reality-graded eval cases
    journal      the WAL = the ledger = audit      swarm     isolated sim / wind tunnel
    verifier     rules→judge→human→reality         compiler  GEPA-style: rewrites faculties
    gateway      all syscalls, ring-checked        creator   assembles new mandates (§5)
    rings L0–L4  earned authority                  gate      regression + canary + human
    supervision  crash → owner → memory
```

### Why the live kernel must be dumb

It touches money, credentials, commits, and the audit trail. An autonomous brain there means one hallucination compromises every customer and "why did it do that?" has no answer — which kills the accountability that *is* the moat. So: **the LLM proposes; deterministic code disposes.** Every smart suggestion (a rewritten faculty, a refund amount, a new mandate) is a gated candidate, never a direct mutation of live state.

### The trust ladder (the go-to-market motion, mechanically)

```text
   L0 recommend    L1 draft+approve    L2 act+review    L3 act+audit    L4 autonomous
   ─────────────────────────────────────────────────────────────────────────────────▶
   customers enter low · N clean actions → propose promotion · any verified failure → demote
   "your agent runs at L2 here, earned over 14 months" = non-portable earned state = moat
```

### The master invariant list (these make the architecture honest)

1. **No fact without a commit** — every heap write is verified + provenance-stamped.
2. **No credential in user space** — every effect is a gated syscall.
3. **No raw fact crosses customers** — only graded behavior (gym) + distilled patterns (domain pack) travel between instances.
4. **No brain in the live kernel** — intelligence is gated, scoped tool calls. (The founder's **Operator Agent**, [§6.1](#61-the-operator-agent-the-founders-assistant), operates the kernel from *outside* as a gated privileged user — never from within it.)
5. **A syscall is intent; fulfillment is swappable** — and the bottom rung is always a human.
6. **Money is API-only, idempotent, never LLM-executed, never browser** — L4 + human gate by default.
7. **No synthetic case promotes a customer-facing version** — the swarm pre-trains and tests; reality alone opens the gate.
8. **The business is the sender of record** — channel identity is per-instance, never shared (no shared-ban blast radius).

---

## 4.5 Using harnesses to full capability (safely)

Model D treats the harness as a swappable CPU — but *swappable* must not mean *underused*. Hermes, OpenClaw, and CheetahClaws ship rich native capability (skills, memory, scheduling, sub-agents). We use it to the **full**, governed by one line: **borrow the muscle, own the moat.**

```text
   Harness native capability        How Agent-X uses it
   ─────────────────────────        ───────────────────
   reasoning / planning / drafting  USE FULLY — the whole reason to rent a harness
   tool calling / native skills     USE — but every EFFECTFUL tool becomes a gateway stub
   native memory                    PER-RUN SCRATCH ONLY — hydrate from our heap, harvest
                                    at settlement; never the system of record
   scheduling                       within a run, fine; cross-run timing/watches are the
                                    kernel's (durable, auditable)
   sub-agents / swarm               USE for parallel internal work (effects still gated);
                                    also the swarm worker-runner (§5)
   durable learning                 NEVER the harness — the gym/compiler/trust are ours
```

We control everything that matters — the context we feed, which native skills are on, **all effects** (gateway), **all durable state** (heap/gym), verification, and rings — and delegate only the commodity loop. Where an existing harness is too opaque to control tightly, a faculty can bind to a thin/own harness instead (CheetahClaws is the moddable candidate), and different faculties of one mandate may run on different harnesses. The harness-agnostic faculty contract (§1) is what keeps all of this swappable.

---

## 5. The Foundry & the CREATOR MANDATE — how new mandates get born (fast)

Two engines live in the Foundry. The **compiler** makes existing mandates *better*; the **creator** makes *new* mandates *exist*.

### The Creator Mandate (the mandate that makes mandates)

It's the SDK turned into a mandate. The founder describes a job; the creator assembles a candidate Type from the faculty library:

```text
   founder: "I want a mandate that handles inbound WhatsApp for dental clinics."
        │
        ▼
   CREATOR MANDATE  (lives in the Foundry — design-time, never touches live customers)
        │  picks faculties: conversation + scheduling + memory-craft + escalation
        │  drafts charter (checkable done-conditions) + starter domain pack
        │  proposes verification rubrics + settlement rules + routing
        ▼
   CANDIDATE MandateType v0   ──────────▶   immediately runnable in the SWARM
```

It is itself a mandate (charter: "produce a swarm-passing Type from a description"; verification: "does it pass swarm smoke tests + human approval"; settlement: "learn which faculty combinations survive reality"). So **it self-improves** — over time it gets better at creating mandates, because its own gym fills with which assemblies worked. Guardrail: the creator emits **candidates only**; the gate (swarm pass + human approve) is the bridge to live. It can never spawn an unverified mandate onto a real customer.

### The Swarm REPL (how the human iterates "real fast")

This is the answer to "iterate fast": the creator + swarm form an edit -> run -> observe -> patch loop, like a REPL for mandates.

The important design choice: **the Swarm REPL is ours.** We should not make MiroFish, Hermes Swarm, or any other harness the source of truth. Those can be plugged in as engines. Agent-X owns the session, candidate mandate, scenarios, traces, scores, gates, and promotion rules.

Think of it like this:

| Layer | What it does | Good existing tools | What Agent-X must own |
|---|---|---|---|
| World simulator | Creates fake owners, leads, customers, edge cases, objections, and market conditions | MiroFish / OASIS-style agent society simulators | Scenario packs, labels, difficulty, and which synthetic cases count for testing only |
| Worker swarm | Runs many agents/faculties in parallel against the task | Hermes Swarm, OpenClaw, other harness swarms | Mandate charter, authority limits, tool permissions, parked states, and trace format |
| Judge + gate | Scores behavior and decides whether a candidate is safe to try live | scoped LLM judge, rules, human review | Rubrics, pass/fail thresholds, promotion, canary, audit trail |
| Real settlement | Learns from actual outcomes | our verifier + human/operator feedback | Verified heap, gym cases, trust update, billing, customer history |

So MiroFish is useful for **simulating a world**. Hermes Swarm is useful for **delegating work to many agents**. But the Swarm REPL is the **Foundry loop** that sits above both.

**The one principle that keeps the swarm honest:** the candidate mandate runs through the **same production gateway and run-loop** we ship — only the *adapters* swap. Simulated counterparties and sandboxed syscalls bind in place of real ones (a `SimAdapter` is just another rung on the [§3 fulfillment ladder](#3-pillar-3--how-the-syscall--integration-layer-looks), sitting where the human-task queue would). This means the swarm tests *exactly what reality will run*, not a look-alike. A harness-swarm engine (Hermes/OpenClaw) may serve as the **worker-runner adapter** that executes faculties in parallel — never as the orchestrator, or you'd be testing a foreign runtime.

**References vs. dependencies** (so we don't reinvent, and don't over-adopt):

- **ADOPT — [promptfoo](https://github.com/promptfoo/promptfoo)** (22k★, MIT) as the grading + regression-gate + scoreboard + red-team engine. It does LLM-as-judge, assertions, version comparison, CI gating, and adversarial generation — and it serves **both** the swarm (synthetic cases) **and** the real gym's promotion gate (one eval engine, two corpora). Our kernel is the custom "provider" it calls; our scenario packs are the inputs; its red-team mode delivers the "harder than reality" rule for free.
- **REFERENCE only — [agency-agents](https://github.com/msitarzewski/agency-agents)** (persona-authoring style for scenario actors; it's just markdown prompts) and **[OASIS](https://github.com/camel-ai/oasis)** (population-scale social sim — *later*, when we simulate *markets* of prospects, not 1:1 conversations).
- **WRONG LAYER for the REPL — Hermes Swarm** (it's production orchestration). Park it as a reference for *intra-mandate* sub-agent parallelism, a different concern from testing.

```text
             ┌─────────────────────────────── FOUNDRY / SWARM REPL ───────────────────────────────┐
             │                                                                                     │
   human ───▶│  /edit mandate charter                                                              │
             │  /run scenario_pack                                                                 │
             │  /watch traces                                                                      │
             │  /patch faculty | rubric | syscall policy | settlement logic                         │
             │  /compare candidate_A candidate_B                                                    │
             │  /gate                                                                              │
             │                                                                                     │
             └─────────────────────────────────────────────────────────────────────────────────────┘
                         │ owns session, candidates, scenarios, traces, scores, gates
                         ▼
      ┌────────────────────────────── isolated test world: no real creds, no money ──────────────────────────────┐
      │                                                                                                          │
      │   Scenario Pack              Candidate Mandate                Judge / Gate                                │
      │   synthetic owners/leads ──▶ runs through harness/swarm ───▶ scorecard + failure reasons                 │
      │   hard objections            sandboxed syscalls only          rule checks + LLM judge + human notes       │
      │                                                                                                          │
      │   optional engine:            optional engine:                 owned by Agent-X                           │
      │   MiroFish-style sim          Hermes/OpenClaw swarm                                                        │
      └──────────────────────────────────────────────────────────────────────────────────────────────────────────┘
                         │ passes smoke tests + human approves
                         ▼
                  PROMOTE to live at L0/L1
                         │
                         ▼
          real runs settle -> REAL gym cases -> compiler improves it
```

So a new mandate is: **created conversationally (minutes) -> iterated in the swarm (live, visual) -> shipped safe at L0/L1 -> grows automatically via the gym.** Days-to-hours, not weeks.

#### The REPL objects

```text
SwarmSession {
  id
  human_operator
  candidate_mandate_type
  scenario_pack
  harness_adapter
  simulator_adapter
  judge_rubric
  run_traces[]
  scorecards[]
  patches[]
  promotion_gate
}

ScenarioPack {
  business_contexts[]       fake but realistic SMBs
  actors[]                  owners, leads, customers, competitors
  tasks[]                   what the mandate must try to do
  traps[]                   spam risk, wrong-fit lead, missing context, policy edge
  expected_signals[]        what "good" behavior should notice
}

PromotionGate {
  synthetic_smoke_passed
  human_approved
  live_ring_allowed         usually L0 or L1 only
  synthetic_cases_barred_from_real_promotion = true
}
```

#### How to structure it in phases

**Phase 1: Foundry-min.** Do not build full MiroFish. Do not depend on Hermes Swarm. Build a tiny local Swarm REPL for one mandate: lead-finding.

```text
/create lead_finder_candidate
/run indian_b2b_leads_v1
/watch
/patch scoring_rubric
/run again
/promote L0
```

The first version only needs:

```text
1. scenario packs as JSON/DB rows
2. 10-30 synthetic lead/company cases
3. one harness runner
4. one judge rubric
5. trace viewer
6. manual approve/promote button
```

**Phase 2: plug in real engines.** Add adapters, not dependencies:

```text
SimulatorAdapter:
  simple_local_simulator
  mirofish_adapter          later, for richer synthetic markets

HarnessAdapter:
  single_agent_runner
  hermes_swarm_adapter      later, for parallel worker experiments
  openclaw_adapter          later, if useful

JudgeAdapter:
  rules
  scoped_llm_judge
  human_review
  promptfoo_adapter         the grading + regression-gate + red-team engine (ADOPT)
```

Adopt **promptfoo** as the JudgeAdapter's engine from Phase 1, not Phase 2 — it's the one true dependency here, and the same engine powers the real gym's promotion gate (§5 growth loop). Don't hand-roll scoring, version comparison, or CI gating; wire promptfoo to call our kernel as a provider and assert on the transcript/outcome via our rubrics.

**Phase 3: make it visual.** The human should see a run like a timeline:

```text
scenario -> mandate decision -> syscall attempt -> parked/manual step -> judge comment -> score -> patch suggestion
```

That is the "real fast" part. The founder should not be reading raw logs. They should be watching the mandate behave, changing the charter/rubric/faculty, then rerunning the same case immediately.

#### Source-of-truth rule

Synthetic swarm output is useful, but it is not reality. Therefore:

```text
synthetic case -> can improve prompts, catch obvious failures, and allow L0/L1 trial
real settled case -> can update heap, gym, trust, billing, and production promotion
```

This keeps the Swarm REPL powerful without letting fake success poison the business memory.

### The growth loop (the compiler, for completeness)

```text
   reality → settled runs → GYM grows → COMPILER (GEPA-style, ~100–500 evals)
   rewrites faculty skill packs → candidate version → GATE (beat live on REAL cases)
   → CANARY → PROMOTE → better runs → reality …
```

Synthetic (swarm) cases are tagged and **barred from the promotion gate** — they pre-train and test; only reality promotes.

---

## 6. The MANAGER DASHBOARD — your window into the running system

**The key idea:** the dashboard is *not a separate system.* The kernel already records everything (runs, rings, approvals, heap, gym, settlement) as journaled events. So the dashboard is **projections over the ledger + a handful of command buttons** — and every manager action (approve, promote, set-ring) is itself a journaled event. One source of truth, consistent by construction.

```text
   ┌─────────────────────────── MANAGER DASHBOARD ───────────────────────────┐
   │                                                                          │
   │  1. FLOOR (live)        active instances · live & parked runs            │
   │     └─ APPROVAL INBOX   the L0/L1 cards — your daily surface (approve/   │
   │     └─ MANUAL QUEUE     edit/reject)  ·  un-automated syscalls to do      │
   │                                                                          │
   │  2. CATALOG             browse MandateTypes → "plug in" = instantiate    │
   │     "plug into a         for a business · set its ring · bind channels    │
   │      mandate, use it"                                                     │
   │                                                                          │
   │  3. INSTANCE FILE       one business's "employee file":                  │
   │                          heap (verified facts + provenance) · trust/ring  │
   │                          history · résumé · run history · P&L            │
   │                                                                          │
   │  4. FOUNDRY             eval gym (real vs synthetic cases) · SWARM (run a  │
   │     "go to eval gym"     mandate, watch it, iterate) · CREATOR (new        │
   │                          mandate) · compiler runs · promote/canary         │
   │                                                                          │
   │  5. CAPABILITY REGISTRY syscalls · their maturity (manual→api) · adapter   │
   │                          health · queue volume = automation roadmap        │
   │                                                                          │
   │  6. ECONOMY (later)     demands · awards by résumé · P&L per mandate       │
   └──────────────────────────────────────────────────────────────────────────┘
```

**How to build it (simple, no reinvention):** the kernel exposes a typed API over its tables — mostly **reads** (projections, subscribed to the journal for real-time) plus a few **commands** (approve, instantiate, set-ring, run-swarm, promote). The dashboard is a thin web app (e.g. Next.js/React) on top. Phase 1 can even start as internal admin tooling (Mongo Compass / Retool) and graduate to custom UI — because the data model *is* the product, the UI is just a lens.

**Two audiences, same machinery:** the **manager (you)** gets the god-view across all instances + the Foundry. The **SMB owner** gets only their instance's approval cards (delivered to their own WhatsApp during a parked run) + a light view of their file. Both are projections over the same kernel.

### 6.1 The Operator Agent (the founder's assistant)

The dashboard is the GUI; the **Operator Agent** is its conversational twin — *your* chief-of-staff for running the whole OS. Crucially it is **not in the live kernel** (that would break invariant #4). It is a **gated, privileged *user* of the control surface**: its entire tool surface is the dashboard's own command/query API, so every action it takes is the same journaled, gated command you would otherwise click.

```text
   you ──talk──▶ OPERATOR AGENT ──command/query API──▶ kernel + Foundry
                 (a harness at FULL native capability — its blast radius is the
                  gated control surface, not customer reality, so it can safely
                  use native memory / scheduling / sub-agents — see §4.5)

   it can:    triage the approval inbox · answer "how's instance X?" · instantiate a
              mandate · set a ring · run a swarm test · invoke the Creator to draft a
              new mandate · read the gym · pull P&L
   it cannot  (without your explicit confirm): promote to L2+ on a live customer,
              raise a ring, or anything touching money — high-blast actions gate to you
```

It is dogfooded as a mandate whose principal is *you* (charter: "help operate the OS"; verification: "founder approval"), and it is the natural home of the **Creator** and the **Swarm REPL**: *"make me a mandate that does X"* → it calls Creator → runs it in the swarm → shows you → you approve → promote. This is the one place we use a harness to its absolute fullest — precisely because its effects are gated control-surface commands, not reality.

---

## 7. The build order (consolidated — start here)

```text
  PHASE 1 — One lead-finding mandate, manual projection, one operator (YOU)
    mandate:    lead-finder (faculties: research + judgment + memory-craft + escalation)
    syscalls:   lead_research_batch · read_url · score_lead   (auto, via Exa/Firecrawl/Agent-Reach)
                draft_email (draft mode) · queue_manual_action (HUMAN QUEUE) · mark_outcome
    kernel-min: scheduler · heap+journal · verifier (rules+human) · gateway (rings L0–L2) ·
                parked-run state machine                                  [MongoDB + worker loop]
    foundry-min: local Swarm REPL: scenario pack + candidate run + trace viewer + scoped judge
    dashboard-min: approval inbox + manual queue + instance file       [internal admin OK]
    AVOID:      WhatsApp · payments · ads · browser-as-default · voice
    WIN:        one operator gets real, scored leads + drafts; gym gets its first real cases

  PHASE 2 — Approved email/calendar/CRM syscalls
    send_email_with_approval · check_calendar · create_event_with_approval · update_crm_status
    rent: Composio/Nango/Pipedream + official APIs · add AgentMail inbox experiments

  PHASE 3 — Browser fallback + sandbox     (Playwright MCP first; E2B/Daytona for isolation)
  PHASE 4 — Voice/phone                     (Patter as actuator — our faculty stays the brain)
  PHASE 5 — WhatsApp + hard channels        (Tech Provider + Embedded Signup; per-instance identity)
```

The whole game in Phase 1: get one instance to `settle()` against reality ~100 times. The heap fills with verified facts, the gym gets its first real cases, and the OS story stops being a diagram and becomes a balance sheet.

---

## 8. Lineage (why this is a sound bet, not a hope)

| Our piece | Prior art | What we add |
|---|---|---|
| Business OS / kernel / syscalls | [AIOS (arXiv 2403.16971)](https://arxiv.org/html/2403.16971v5) | the *employment* layer: authority, verification, settlement, trust |
| Mandate = contract + verification | [Relari agent-contracts](https://github.com/relari-ai/agent-contracts); Design-by-Contract | settlement + trust ladder |
| Internal market (demand/résumé) | [Contract Net Protocol (Smith 1980)](https://en.wikipedia.org/wiki/Contract_Net_Protocol) | bids = verified track records |
| Compiled mandates | [DSPy / GEPA (ICLR'26)](https://github.com/gepa-ai/gepa) | gym = reality-graded trainset |
| Faculty library | [Voyager](https://arxiv.org/abs/2305.16291) | rubrics + eval slices + harness bindings |
| Swarm REPL eval & gate | [promptfoo](https://github.com/promptfoo/promptfoo) (judge/assert/regress/red-team); [OASIS](https://github.com/camel-ai/oasis) (population sim) | swarm runs on *our* gateway via Sim adapters; one eval engine for both swarm + real gym |
| Syscall adapter ladder | Agent-Reach (ordered backends + health checks); Docker MCP catalog (packaged/versioned tools) | the human-task bottom rung; per-tenant policy |
| Durable runs | [Temporal](https://temporal.io/) | continuations as journal rows |
| Supervision, crash-upward | Erlang/OTP | owner as root supervisor |

**Kill conditions (revisit each phase):** if churn doesn't rise with heap depth, context-gravity is fiction. If the compiler doesn't beat hand-tuning by ~customer 5, the gym is decoration. If owners won't tap Approve, the trust ladder's bottom rung is broken. If no demand is ever posted between mandates once 3+ types run, delete the market and keep spawn. Knowing these in advance is what makes this a bet rather than a wish.
