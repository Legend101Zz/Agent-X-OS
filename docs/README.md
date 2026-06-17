# Agent-X: The Business OS and the Anatomy of a Mandate

*A first-principles design document. Companion: [ARCHITECTURE.md](./ARCHITECTURE.md) — the diagrams and full flows.*

---

## The thesis, restated for this document

Everything we settled in previous sessions stands: harnesses commoditize execution; the company is the state that accumulates through verified work; the primitive is the **Mandate** — a unit of delegated authority with a verification function attached; the system is a **Business OS** where a business is a running program, mandates are its processes, the context graph is a transactional heap, verification is a commit-time type system, and trust levels are protection rings.

This document answers the question all of that left open, the one that decides whether the thesis becomes software:

> **How do you structure a single mandate so that it is genuinely excellent at its business task — and so that the second mandate takes a day to build instead of a quarter?**

The answer has a shape worth stating up front, because every section below is a consequence of it:

> **A mandate is not written. A mandate is compiled — from reusable faculties, against an eval corpus that reality itself grades.**

If you take one sentence from this document into the next ideation session, take that one. It is the structural answer to "what stops us from being Prompt Engineering Company Inc." A competitor can steal a prompt. A prompt is a *build artifact* — a snapshot of the compiler's output at one moment, against one corpus. They cannot steal the gym that produced it, and the snapshot decays while the gym compounds.

---

## Part 1 — What "good" actually means for a mandate

Before designing the structure, be precise about the target, because "make the agent really good" is not an engineering requirement. From first principles, a mandate's quality decomposes into **four independent axes**, and the reason most AI agents on the market are mediocre is that their builders only engineer one of them:

| Axis | Question | Where it lives |
|---|---|---|
| **Perception** | Does it know enough before it acts? | Hydration + context graph + domain pack |
| **Competence** | Does it act well, given what it knows? | Faculties + compiled prompts + model routing |
| **Judgment** | Does it know what it *doesn't* know? | Escalation calibration + confidence + ring discipline |
| **Growth** | Is run #1,000 measurably better than run #1? | Eval gym + settlement + the compiler |

Almost every agent product you can name engineers **Competence** only — a clever prompt, good tools, a strong model. That produces impressive demo behavior and flat long-term quality, because:

- Without **Perception**, the agent is a brilliant stranger. It writes beautiful replies containing wrong prices.
- Without **Judgment**, the agent is a confident intern. Its worst outputs are indistinguishable from its best until the damage is done. (An agent that escalates correctly at L1 is *more* valuable than an agent that acts boldly and is right 92% of the time — the 8% is where the customer's trust dies.)
- Without **Growth**, the agent is a goldfish. Month six performs like week one, and the customer correctly concludes they're renting a commodity.

The mandate structure below is not decoration around an agent. **Each organ of the mandate exists to own one of these axes.** That is the design principle: structure follows the axes of quality, not the convenience of the implementation.

One reframe before the anatomy. You said it yourself: mandates are not small — *"they contain an agent harness in themselves... they themselves are agents running, but better."* Exactly right, and here is the precise sense of "better":

> **A mandate is an agent with an employment contract.**
> The agent (harness + model + loop) is the worker's brain. The mandate wraps it with a charter (what done means), authority (what it may touch), perception (what it knows), verification (who checks), settlement (what's remembered), and a growth loop (how it improves). Remove the wrapper and you have a freelancer with amnesia. The wrapper *is* the product.

---

## Part 2 — The anatomy of a mandate

### 2.1 The three vertical layers (recap, sharpened)

A mandate exists at three layers. Knowing which field lives where is what makes 100 customers tractable with one codebase:

```text
MandateType        =  class      — shared across ALL customers. Almost open-source.
MandateInstance    =  object     — private per customer. The moat lives here.
MandateRun         =  stack frame — born per trigger, durable, dies at settlement.
```

- The **Type** holds everything that should improve when *any* customer's runs settle: the charter schema, the faculty set, the verification suite, the compiled prompts, the category priors.
- The **Instance** holds everything that should *never* leave one customer: their heap region (context graph), trust level, correction history, performance record.
- The **Run** holds nothing durable of its own — it is a durable *continuation* (it can park three days for an owner's approval and survive ten deploys), but at settlement everything it learned either commits to the Instance/Type layers or evaporates.

### 2.2 The seven organs

Open up a MandateType and you find seven organs. This is the heart of the document.

```text
MandateType: "acquisition.v3"
│
├── 1. CHARTER          what "done" means, in checkable terms        [axis: all]
├── 2. FACULTIES        composable capability modules                 [axis: Competence]
├── 3. DOMAIN PACK      vertical knowledge + category priors          [axis: Perception]
├── 4. VERIFICATION     the commit-time type system                   [axis: Judgment]
├── 5. SETTLEMENT       commit rules: memory, trust, billing, spawn   [axis: Growth]
├── 6. EVAL GYM         the self-growing benchmark + compiler         [axis: Growth]
└── 7. EXECUTION        per-faculty harness/model routing table       [axis: Competence]
```

**1. Charter** — the goal schema. Not "find leads" (unverifiable) but a typed contract: *target* (booked discovery calls), *quantity* (10), *window* (30 days), *constraints* (never contact existing customers; budget ₹500/day). The discipline: **if a clause can't be checked, it can't be in the charter.** Unverifiable intent goes in the domain pack as guidance, not in the charter as a promise. This is Design-by-Contract ported to delegated work — the lineage runs from Hoare/Meyer through [Relari's agent-contracts](https://github.com/relari-ai/agent-contracts) (preconditions / pathconditions / postconditions for AI systems), and we adopt their triad directly: preconditions gate the run, pathconditions constrain *how* (e.g., "every claim about the prospect must cite a source the research faculty fetched"), postconditions define done.

**2. Faculties** — the SDK you asked for. A faculty is a self-contained capability module:

```text
Faculty {
  skill_pack:     compiled prompts + procedures for this capability
  tool_manifest:  which syscalls it may request (MCP-shaped)
  rubrics:        how its output is judged (its slice of verification)
  eval_slice:     its slice of the gym — graded cases for THIS capability
  routing_hint:   what execution it wants (cheap/fast vs strong/slow)
}
```

Faculties are the reusable bricks. The library starts with roughly:

| Faculty | What it does | First used by |
|---|---|---|
| `research` | find + ground facts about an entity, with citations | Acquisition |
| `judgment` | score/qualify/prioritize against an ICP or rubric | Acquisition |
| `conversation` | multi-turn dialogue on a channel, tone-controlled | Inbound WhatsApp |
| `outreach` | sequenced sending with deliverability discipline | Acquisition |
| `scheduling` | calendar negotiation and booking | Inbound WhatsApp |
| `memory-craft` | propose heap facts with provenance + confidence | every mandate |
| `escalation` | detect own uncertainty, package context, crash upward | every mandate |

Note that `memory-craft` and `escalation` are faculties — *writing good memory and failing well are skills*, engineered once, reused everywhere. That is the deepest payoff of the faculty model: the behaviors that make the whole OS work are not re-implemented per mandate; they're linked in like a standard library.

This is also where your "harness inside the mandate" intuition lands without violating Model D (control plane over disposable harnesses): **a faculty binds to a harness *adapter*, not a harness.** The outreach faculty might run on an OpenClaw pod (channel automation is its strength); research on Hermes with a cheap model; conversation drafting on a strong model. The mandate contains harness *bindings*; pods stay disposable, credential-free, and swappable. (Precedent for the library-of-skills approach: [Voyager](https://arxiv.org/abs/2305.16291)'s ever-growing skill library is the closest published analogue — skills as accumulating, composable, reusable artifacts rather than monolithic prompts.)

**3. Domain Pack** — what the mandate knows before it knows the customer. The vertical playbook (how dental clinics talk about insurance), the objection library, and — crucially — **category priors distilled from the outcome corpus** ("clinics: offering a concrete slot in the first reply books 2× more"). The domain pack is how customer #50 starts at day-1000 knowledge. It is versioned data, not prompt text, and it is the *only* place cross-customer learning re-enters a mandate — as patterns, never as facts traceable to another business.

**4. Verification Suite** — the type system, organized as a **ladder of checkers, cheapest first**:

```text
rules        deterministic: schema, budget, blacklist, rate, idempotency   ~free
judge        LLM-as-judge against the faculty rubrics                      cheap
human        owner approval card (the L0/L1 path)                          costly
reality      the watch: did the lead reply? did the booking happen?        free but slow
```

Every proposed effect and every proposed heap write must pass the rungs its risk class requires. The design rule that keeps margins alive: **push every check as far down the ladder as it can go.** Each owner correction is studied for the rule or rubric that would have caught it automatically — verification costs should *fall* with volume while coverage rises. Reality (the watch) is the only rung that can't be fooled, which is why settlement is split: an immediate commit at run end, and a deferred commit when the watch fires (72h later, the booking happened → probationary facts promote, trust ticks up, the run becomes a *graded* eval case).

**5. Settlement Rules** — what happens at commit, declaratively: which claimed facts enter the heap at what confidence; what trust delta on which outcome; what billing line; what watches to register; and — composition's hook — **what to spawn** (`on lead_warm_but_unbooked → spawn followup(lead_id, inherit_authority)`).

**6. Eval Gym** — the organ that makes the mandate *get* good and *stay* good; it gets its own section (Part 3).

**7. Execution Profile** — the routing table: per-faculty harness adapter + model + budget. This is where harness arbitrage becomes real ("route by cost-per-verified-outcome"), because routing decisions are made per capability, not per product, and the gym tells you exactly what each routing change does to quality before you ship it.

### 2.3 What the instance adds

A MandateInstance = Type version + customer binding + the accumulating private state: heap region, trust/ring level, correction history, **learned overrides** (instance-level deltas the compiler distills from this customer's corrections: "this owner signs off casually; never use 'Dear'"), and the instance's **résumé** — its verified performance record, which Part 4 turns into the currency of the internal market.

---

## Part 3 — The excellence flywheel: mandates are compiled

Here is the answer to "how do we make a single mandate so f***ing good," and it is mostly *not* "hire a great prompt engineer."

### 3.1 The gym

Every settled run automatically becomes an eval case: `(hydration snapshot, output, verification result, eventual reality outcome)`. Owner corrections are gold-tier cases (they carry the exact before/after diff). Watch outcomes are ground truth. After one month of one clinic at ~30 conversations/day, the inbound mandate's gym holds ~900 graded, real, in-distribution cases. No synthetic benchmark in the world is worth one month of settled runs.

### 3.2 The compiler

This is where 2025–26 research hands us the mechanism. [GEPA](https://github.com/gepa-ai/gepa) (Genetic-Pareto, an [ICLR 2026 oral, shipped in DSPy](https://dspy.ai/api/optimizers/GEPA/overview/)) optimizes prompts by *reflecting on execution traces* — it reads why a case failed and proposes targeted fixes — and it needs only **100–500 evals** to outperform both hand-tuning and RL-style approaches. Read that number against the gym: **a single SMB customer generates a GEPA-sized training corpus every few weeks.** The loop:

```text
reality → settled runs → gym grows → compiler (GEPA-style) re-optimizes
faculty skill packs against the gym → candidate Type version → regression
gate (must beat current version on the full gym, no rubric regressions)
→ canary on consenting instances → promote → better runs → reality…
```

Three consequences worth sitting with:

1. **Quality becomes a build pipeline, not an art.** "Make the mandate good" decomposes into: grow the gym (ship and verify), run the compiler, gate, canary, promote. Mandate versions ship like software releases — semver, changelog, rollback — and *instance state survives type upgrades* because state lives in the heap, not in the prompt.
2. **The moat gets a third leg.** Context gravity and earned authority were per-customer. The gym is per-*type*: every customer's settled runs make the shared mandate better for all of them (patterns only — the gym stores graded behavior, the heap stores private facts, and the two never mix). A competitor with our prompt has our output; a competitor without our gym can't produce the *next* version of it.
3. **The fear in the original brief dissolves structurally.** "Prompt Engineering Company Inc." is a company whose asset is prompt *text*. Our asset is the corpus + compiler + verification machinery that *generates* prompt text on demand, freshly fitted to reality. The text is the exhaust.

There is a humbler precedent for the loop's spirit — [Reflexion](https://arxiv.org/abs/2303.11366) showed agents improving from verbal feedback on failures — but Reflexion improves *within* an episode and forgets. The gym is Reflexion with a ledger: feedback survives, accumulates, and compiles.

### 3.3 What the founder does in this picture

The human's job shifts from writing prompts to **curating the gym and the rubrics**: deciding what counts as good, triaging the compiler's losing cases, writing the verification rule that catches a new failure class. That is leverage — one person's taste, amplified across every customer of every mandate of a type, permanently.

---

## Part 4 — Composition: spawn, the internal market, workflows, business units

### 4.1 Two ways mandates connect — and why you need both

**Spawn** (the function call): a settlement rule creates a child run with parameters. Deterministic, declared in the Type, auditable in advance. The child *reads its inputs from the heap* — committed, verified, provenance-stamped facts — never from a private message channel. *Spawn is the call; the heap is the return path.*

**Demand** (the market): the genuinely new piece, and the direct answer to your lego question — *"the acquisition mandate should be able to find clients for the sales-call mandate."* A mandate (or a human) posts a **Demand** to the kernel:

```text
Demand {
  principal:     who this work is FOR (a customer — or Agent-X itself)
  spec:          "20 qualified leads matching ICP-X, ≥0.7 fit score"
  verification:  how fulfillment is checked (inherits a charter)
  budget:        what fulfillment may spend
  deadline:      when it expires
}
```

The kernel matches the demand against mandates that have published a **service port** ("I produce `qualified_leads`") and **awards it by résumé** — the verified track record, not self-claims. Fulfillment runs as a normal child mandate with its own verification and settlement. This is [Smith's Contract Net Protocol (1980)](https://en.wikipedia.org/wiki/Contract_Net_Protocol) running *inside* the OS: announce → bid (résumé-based) → award → execute → verify → settle → résumé update. Three things fall out:

1. **Your bootstrapping story becomes architecture.** "The acquisition agent sells everything we build" = *Agent-X is principal #0*. Our own acquisition instance fulfills demands posted by our own go-to-market. Dogfooding isn't a phase; it's a row in the demands table.
2. **The marketplace is latent from day one.** The day a third party writes a MandateType, it publishes service ports and competes for demands on résumé. The platform's Phase-3 story is "we opened the demands table," not "we built a marketplace."
3. **Specialization gets priced.** When two mandate types can fulfill the same demand, the résumé + cost decide. That is harness arbitrage generalized: *capability arbitrage*, with verified outcomes as the price signal.

### 4.2 Workflows: deterministic spine, reasoning nodes

Your instinct here is exactly right and worth canonizing: **the workflow graph is deterministic; the nodes are not.** A workflow is a typed graph where edges are spawn rules and demand postings — fully auditable, "what triggers what, under what contract" is knowable in advance — while *how* each node fulfills its charter is discovered at runtime by the agent inside the mandate. This is the synthesis of Zapier and agents that neither can reach alone: Zapier has the spine with no brain in the nodes; raw agent swarms have brains with no spine. (It also matches [Anthropic's own guidance](https://www.anthropic.com/research/building-effective-agents): workflows for predictability, agents for flexibility — we use each exactly where it's strong.)

Nothing new is ever built for this. A workflow is rows in the spawn-rules and demands tables. It exists the day run #1 settles.

### 4.3 Business units, then the business

A **business unit** is a module: a set of mandate instances sharing one heap region, one budget envelope, one supervisor subtree — and, because every settlement writes a billing line, **one P&L**. "Acquisition unit: spent ₹14,200, produced 31 verified meetings, ₹458/meeting" is a query, not a dashboard project. The Lightcone endgame — an AI-operated business — is then just *a deep program*: many units, most actors at low rings, the owner as root supervisor reviewing exceptions and P&Ls. No rearchitecting between here and there; the program just grows.

---

## Part 5 — The whole system, briefly (what the kernel owns)

Full diagrams in [ARCHITECTURE.md](./ARCHITECTURE.md); the one-screen recap of the OS the mandates run on:

```text
KERNEL (the company)                         USER SPACE (rented)
├── Scheduler      reality → runs            ├── per-CUSTOMER pods
├── Heap           transactional, journaled  │   Hermes / OpenClaw / next
├── Ledger         the heap's WAL            │   zero credentials
├── Verifier       commit-time type system   │   zero durable state
├── Syscall table  all real-world effects    └── stateless, disposable
├── Rings L0–L4    earned authority
├── Supervision    crashes → owner → memory  HARDWARE (reality)
├── Demands        the internal market       WhatsApp · CRM · calendar · money
└── Compiler+Gyms  per-type quality CI
```

Invariants that make it scale (each one a sentence, each one absolute):

- **No fact without a commit.** Every heap write passes verification and carries provenance. No debug shortcut, ever.
- **No credential in user space.** Every real-world effect is a syscall; the gateway checks the ring, enforces idempotency, appends to the trace.
- **No durable state below the adapter line.** Pods hydrate from the heap, harvest at settlement, and can be destroyed mid-run with zero loss (the run is a durable continuation in the database — the [Temporal](https://temporal.io/)-style property, hand-rolled cheaply because every transition is already a journal entry).
- **No cross-customer fact flow.** Learning crosses customers only as compiled patterns (domain packs, gym-trained skill packs), never as facts.
- **No unverified résumé.** Market awards run on settled outcomes only.

Scale story in one line per dimension: more customers → more instances + pods (linear, isolated); more mandate types → more rows + faculty reuse (sublinear engineering cost); more volume per customer → more runs (the gym and the moat grow *faster* than the cost).

---

## Part 6 — How fast can mandate #2 ship? (the SDK test)

The structure is only right if it passes this test. Building **Inbound WhatsApp** when **Acquisition** already exists:

| Organ | Work required |
|---|---|
| Charter | new (a day: define done + constraints in checkable terms) |
| Faculties | `conversation` + `scheduling` + `memory-craft` + `escalation` — **all from the library** |
| Domain pack | new vertical playbook (days, and it compounds forever after) |
| Verification | rubrics for the two new faculty uses; rules library reused |
| Settlement | declarative config |
| Eval gym | starts empty, self-fills from week one; compiler takes over ~week three |
| Execution | routing table config |

Honest estimate: **days, not weeks — and week-one quality is mediocre by design.** The structure's promise is not that mandate #2 starts great; it's that mandate #2 starts *safe* (L0/L1, verification on, escalation linked in) and gets great *automatically* (the gym fills, the compiler runs). Safe-then-compounding beats impressive-then-flat in every market we care about.

---

## Part 7 — Kill conditions (kept honest, updated for this design)

1. **If the compiler doesn't beat hand-tuning** on real gyms by ~customer five, the "compiled mandate" story is decoration and we're back to artisanal prompts — viable business, weaker moat. *(Testable early; GEPA's published numbers say we shouldn't be surprised if it works.)*
2. **If owners won't tap Approve** — if L1 review feels like work instead of control — the trust ladder's bottom rung is broken and the whole climb is fiction. The approval UX is therefore a first-class product surface, not an afterthought.
3. **If verification cost doesn't fall with volume** (corrections not converting into rules/rubrics), margins die at exactly the scale where the business should get good.
4. **If no demand is ever posted between mandates** by the time we run 3+ types in production, the market is architecture astronautics — delete it and keep spawn.

Each failure has a fallback; knowing them in advance is what makes this a bet, not a hope.

---

## Part 8 — What we build first (preview — full project setup is the next session)

Level 1, completely, for one clinic: **kernel-minimum** (scheduler, heap + journal, verifier with rules+human rungs, syscall gateway with rings L0–L2, parked-run state machine — Postgres + a worker loop, nothing exotic) plus **one MandateType** (inbound WhatsApp: charter, 4 library faculties, thin domain pack, settlement rules, empty gym). Let one process `commit()` against reality a hundred times. The gym's first 100 graded cases are the moment this stops being an essay.

---

## Appendix — Research lineage

| Idea here | Prior art | What we take / change |
|---|---|---|
| Mandate = contract + verification | [Relari agent-contracts](https://github.com/relari-ai/agent-contracts); Design-by-Contract | pre/path/post-conditions → charter + verification ladder; we add settlement + trust |
| Internal market | [Contract Net Protocol, Smith 1980](https://en.wikipedia.org/wiki/Contract_Net_Protocol) | announce/bid/award → demand/résumé/award; bids are verified track records, not claims |
| Compiled prompts | [DSPy](https://dspy.ai/) / [GEPA (ICLR'26)](https://github.com/gepa-ai/gepa) | the compiler organ; gym = reality-graded trainset |
| Faculty library | [Voyager](https://arxiv.org/abs/2305.16291) skill library | skills → faculties with rubrics + eval slices + harness bindings |
| Learning from feedback | [Reflexion](https://arxiv.org/abs/2303.11366) | episodic verbal feedback → durable, compiled, ledgered |
| Durable runs | [Temporal](https://temporal.io/) durable execution | continuations as journal rows |
| Supervision, crash-upward | Erlang/OTP | owner as root supervisor; resolutions commit to memory |
| Heap/WAL/commit | Event sourcing / CQRS | settlement = commit; ledger = WAL; verification at commit-time |
| Spine vs nodes | [Anthropic, Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) | deterministic workflow graph, agentic node interiors |
| BDI agents | Rao & Georgeff | beliefs/desires/intentions ≈ heap/charter/run — the 90s architecture, given a ledger |

**Sources:** [relari-ai/agent-contracts](https://github.com/relari-ai/agent-contracts) · [gepa-ai/gepa](https://github.com/gepa-ai/gepa) · [DSPy GEPA overview](https://dspy.ai/api/optimizers/GEPA/overview/) · [GEPA tutorial](https://dspy.ai/tutorials/gepa_ai_program/)
