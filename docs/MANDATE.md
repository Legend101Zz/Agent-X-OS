# The Mandate — Structure, and How It Improves

*Focused companion to [README.md](./README.md) and [ARCHITECTURE.md](./ARCHITECTURE.md). This doc does one job: get the mandate right, simply, and answer three questions — (1) is the instance/heap/gym picture correct, (2) does the kernel have a brain, (3) what exactly is the swarm.*

---

## 0. The whole thing in one paragraph

A **mandate** is a job we delegate to an AI worker, wrapped in a contract that says what "done" means and who checks it. We define it once as a **type** (the class). Each business that uses it gets an **instance** (the object), with its own private memory that grows as it works. Every time a trigger fires (a message, a deadline), we create a **run** (a stack frame) that does the work and then *settles* — committing what it learned and whether it succeeded. The live system that runs all this (**the kernel**) is dumb, trustworthy code; it never improvises with money or credentials. A separate, offline workshop (**the Foundry**) takes settled results plus a sandbox (**the swarm**) and forges better versions of the mandate — and only ships them after they beat the current version on real, graded results.

---

## 1. The three layers (your mental model, checked)

```text
MANDATE TYPE          the class — shared by every business, almost open-source
  charter · faculties · domain pack · verification · settlement · gym · routing
        │
        │  one per business that subscribes  (the INSTANCE REGISTRY)
        ▼
MANDATE INSTANCE      the object — private to one business. THE MOAT LIVES HERE.
  heap region (private facts) · trust/ring level · résumé · learned overrides
        │
        │  one per trigger  (the RUN TABLE — durable, can park for days)
        ▼
MANDATE RUN           the stack frame — does the work, then dies at settlement
  frozen hydration snapshot · syscall trace · claimed facts · scratchpad
```

**Two registries, not one** (this is correction #1 to your model):

- **Instance registry** — *which businesses* use this mandate. Long-lived. One row per customer. ("Sharma Dental, Restaurant B, Salon C are all running inbound-whatsapp.v7.")
- **Run table** — *which executions* are currently alive. Per-trigger. Born when a message arrives, dies at settlement, may park for three days waiting on an owner in between.

You had these slightly merged ("per-trigger table of active instances"). They're different: instances are the businesses; runs are the events.

---

## 2. The heap, and how instances make the mandate better

Each instance has a **heap region** — private facts about that one business, growing over runs:

```text
Sharma Dental heap region
  (clinic, accepts_insurer, star_health,  conf 0.95, source: owner-stated)
  (cleaning, price, ₹1500,               conf 0.90, source: owner-stated)
  (dr_sharma, unavailable, tuesday_eve,  conf 0.95, source: owner-correction)
  (lead_4471, interested_in, cleaning,   conf 0.60, source: agent-inferred)
```

Now the important part — **how one business's work improves the mandate for everyone** — and the one correction your model needs:

> **Raw facts NEVER cross between businesses.** Sharma's heap is invisible to Restaurant B's agent, forever. That isolation *is* the product.

What crosses instances is only these two things, and both are safe:

```text
                  ┌─────────────────────────────────────────────┐
   every run  →   │  (a) GRADED BEHAVIOR CASE  → the gym         │
   that settles   │      "given this situation, this output,     │
                  │       reality said: booked / failed"         │
                  │      → trains the shared faculties            │
                  │                                              │
                  │  (b) DISTILLED PATTERN     → the domain pack │
                  │      "clinics: offering a slot in the first  │
                  │       reply books 2× more"                    │
                  │      → a statistic, never a fact about anyone │
                  └─────────────────────────────────────────────┘
```

So your sentence "we use heap info from other instances to improve the mandate" becomes precise: **we use the *graded outcomes* and *aggregate patterns* from other instances — never their facts.** Same benefit you wanted, no privacy leak. Patterns and behavior travel; facts stay home.

---

## 3. Does the kernel have a brain? (the real question)

Short answer: **the live kernel does not think.** It is deterministic code. Intelligence is invoked as **scoped, gated tools** — never as an autonomous agent that owns live state.

Here's why this matters, then how the "intelligent improvement" you want actually happens.

### Why the live kernel must be dumb

The kernel is the part that touches **money, credentials, commits, and the audit trail.** If an autonomous LLM brain sits there:

- a hallucination or prompt-injection can compromise *every* customer at once;
- "why did it issue that refund?" has no answer except "the brain felt like it" — which destroys the accountability that is the entire moat;
- a thinking kernel optimizing *anything* re-opens the reward-hacking problem at the most dangerous layer.

An OS kernel that "thought" would be a terrifying OS. Same here. **The kernel enforces; it does not improvise.**

### So where does intelligence live? Two safe places.

```text
   ┌───────────────────────────────────────────────────────────────┐
   │  INTELLIGENCE LIVES HERE (sandboxed)                          │
   │                                                                │
   │  1. FACULTIES  — at runtime, inside the mandate, in user-space │
   │     pods. The agent reasons, drafts, plans. But it holds no    │
   │     credentials and every real effect is a gated syscall.      │
   │                                                                │
   │  2. THE FOUNDRY — offline, on a cadence (nightly/weekly).      │
   │     Where new mandate VERSIONS are forged. Touches no real     │
   │     customer until a candidate passes the gate.                │
   └───────────────────────────────────────────────────────────────┘
```

### The control plane has two clocks

This is the cleanest way to hold it:

| | **The live kernel (ONLINE)** | **The Foundry (OFFLINE)** |
|---|---|---|
| When | per trigger, real-time | per cadence, batch |
| Touches | real money, real customers | nothing live until gated |
| Made of | deterministic code | optimizer + judges + swarm |
| Brain? | **no** — gated tool calls only | yes — but every output is a *candidate* |
| Job | run mandates safely | make mandates better safely |

### What's code vs. what's an LLM call

The kernel "thinks" only through **scoped, stateless, gated** tool calls. It never runs an autonomous loop that owns state.

| Job | Code or LLM? |
|---|---|
| Scheduling (reality → runs) | **code** |
| Syscall gateway · ring checks · idempotency | **code** — never an LLM; this is the security boundary |
| Commit · journal · billing | **code** |
| Demand allocation (award by résumé) | **code / policy** |
| Verification — rules rung | **code** |
| Verification — judge rung | scoped LLM call (stateless, its output is checked) |
| Verification — reality rung | **code** (webhooks) |
| Compiler — the optimization loop | **code** |
| Compiler — *propose* a better skill pack | scoped LLM call (GEPA-style mutator) |
| Swarm — *generate* synthetic cases | scoped LLM call (a **different** model) |
| Distill journals → category patterns | scoped LLM call, output gated |
| **Decide what ships** | **code gate** (regression + canary) + human approve |

Read the bottom row twice. **The LLM proposes; deterministic code disposes.** Every smart suggestion — a rewritten faculty, a new domain-pack pattern, a charter tweak — becomes a *candidate mandate version* that must beat the current one on real graded results before it can go live. That's how you get "the kernel intelligently improves the domain pack, fixes a wrong faculty, tunes the charter" — *all of which you asked for* — without ever putting a sovereign brain in charge of production.

### "A faculty was wrong — fix it everywhere"

You raised this exactly right: if the Foundry discovers a faculty (say `research`) was making a systematic mistake, the recompiled faculty improves **every mandate that links it**. That's the faculty-library payoff. Mechanically: faculties are versioned shared artifacts; a new `research.v4` passes its own gym slice, then every mandate type that depends on it gets a candidate bump, each re-gated on its own gym before promotion. One fix, fleet-wide, but still gated per mandate so a fix that helps Acquisition can't silently break Inbound.

### The most "agentic" thing allowed near the control plane

An **Improvement Advisor** — a copilot for *you*, the founder — that triages the Foundry's losing cases, drafts domain-pack updates, and suggests which faculty to fix. It produces **proposals that enter the same gate as everything else.** It advises; it never commits. Think of it as a very good engineer who can open PRs but cannot merge to production.

---

## 4. The swarm and the gym (your third question)

Keep two words distinct — it'll save you confusion forever:

- **The gym** = the *corpus*. The accumulating set of graded cases the compiler trains against.
- **The swarm** = the *environment*. An isolated sandbox that runs the mandate against simulated reality and *fills part of the gym* with synthetic cases.

You said the gym should *be* swarms. Almost — the swarm **feeds** the gym and **is** the test harness. The gym holds two clearly-tagged kinds of cases:

```text
   GYM (corpus)
   ├── SYNTHETIC cases  ← from the swarm. Tagged. For dev + safety.
   └── REAL cases       ← from settled runs. Ground-truth. The moat.
```

### The swarm does the two jobs you named

```text
   ┌──────────────────── THE SWARM (isolated, no real creds/money) ──────────┐
   │                                                                          │
   │   simulated         the mandate          kernel's judge                 │
   │   prospects/   ───▶  under test    ───▶  (scoped LLM-as-judge) ───▶ ...  │
   │   owners/leads       (real code,         scores the behavior            │
   │   (different model)   sandboxed effects)                                │
   │                                                                          │
   │   JOB 1: does the mandate work as expected?   → a functional test       │
   │   JOB 2: generate synthetic graded cases      → bootstrap the gym        │
   └──────────────────────────────────────────────────────────────────────────┘
```

Yes — the kernel's judge (a scoped LLM call, *not* a sovereign brain) grades the swarm runs. That's exactly the right use of it.

### Four rules so the swarm doesn't lie to you

1. **Synthetic cases never promote a customer-facing version.** Only the real-cases portion of the gym opens the gate that raises autonomy or ships to customers. Synthetic pre-trains and tests; reality decides.
2. **Drive the swarm with a different model** than the mandate runs on — otherwise the agent is grading its own homework and aces a sim that flatters it.
3. **Make the swarm harder than reality.** A pessimistic sim is safe to over-train on; an easy one is poison.
4. **Seed it from real anonymized cases** the moment you have any, and treat sim-vs-reality divergence as a quality score on the swarm itself.

### What this buys you before customer #1

- You can **prove the whole improvement loop runs** (gym → compiler → gate → promote) with zero customers.
- A new mandate ships not just *safe* (low ring, verification on) but **pre-flighted** — the obvious failure modes wrung out in the wind tunnel first.

---

## 5. How it all works, simply (end to end)

```text
  ONLINE (live kernel — dumb, trustworthy)        OFFLINE (Foundry — smart, gated)
  ───────────────────────────────────────         ────────────────────────────────

  1. trigger fires (message / deadline)
  2. kernel creates a RUN, hydrates it
     from the instance's heap
  3. faculties (in a disposable pod) reason
     and draft; every real effect is a
     gated SYSCALL (ring-checked)
  4. VERIFY (rules → judge → human → reality)
  5. SETTLE — one atomic commit:
       • facts → heap (with provenance)
       • trust → résumé
       • billing line
       • register a WATCH (did it really work?)
       • maybe SPAWN a child mandate
  6. the run becomes a GRADED CASE ─────────────▶  7. gym grows (real cases) +
                                                      swarm adds synthetic cases
                                                   8. COMPILER reflects on failures,
                                                      proposes better faculties /
                                                      domain pack / charter
                                                   9. GATE: candidate must beat the
                                                      live version on REAL cases,
                                                      no rubric regressions
                                                  10. CANARY on consenting instances
                                                  11. PROMOTE new version
       ◀─────────────────────────────────────────    (instance heap survives —
       better runs next time                           state lives in the heap,
                                                        not in the prompt)
```

That loop is the company. The left side earns the revenue; the right side compounds the moat. The kernel never crosses from left to right on its own — a human-approved gate is the bridge.

---

## 6. The invariants this all rests on

Short list. Each one absolute; each one is what keeps the structure honest:

1. **No fact without a commit.** Every heap write passes verification and carries provenance.
2. **No credential in user space.** Every real-world effect is a gated syscall.
3. **No raw fact crosses customers.** Only graded behavior (gym) and distilled patterns (domain pack) travel between instances.
4. **No brain in the live kernel.** Intelligence is scoped, gated tool calls — never a sovereign agent owning live state.
5. **No synthetic case promotes a customer-facing version.** The swarm pre-trains and tests; reality alone opens the gate.
6. **The LLM proposes; deterministic code disposes.** Every improvement is a gated candidate.

---

## 7. What we'd build first (so this isn't just a picture)

To make *one* mandate real, the minimum is:

- **Kernel-minimum (online):** scheduler, heap + journal, syscall gateway with rings L0–L2, the rules + human verification rungs, the parked-run state machine. Postgres + a worker loop.
- **One mandate type:** charter, 3–4 library faculties, a thin domain pack, settlement rules, an empty gym.
- **Swarm-minimum (offline):** a sandbox that runs that mandate against a handful of simulated owners/leads, judged by a scoped LLM call, filling synthetic cases — enough to prove the loop and pre-flight the mandate.

Get one instance to `settle()` against reality a hundred times, watch the heap fill and the gym's first real cases appear, and the structure stops being a diagram and starts being a balance sheet.
