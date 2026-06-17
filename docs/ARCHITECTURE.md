# Agent-X Architecture — Diagrams & Full Flows

*Companion to [README.md](./README.md). Every diagram is walked through with one of two running examples:*
- **Sharma Dental Clinic** — inbound WhatsApp mandate, instance at ring L1
- **Agent-X itself (principal #0)** — acquisition mandate selling the inbound product

Diagrams are Mermaid (render on GitHub / VS Code with Mermaid preview) plus ASCII where structure reads better as text.

---

## Diagram 1 — The three layers of a mandate

*Which field lives at which layer is the entire scaling story: top is shared by all customers, middle is private per customer, bottom is born and dies per trigger.*

```text
┌─────────────────────────────────────────────────────────────────────┐
│  MandateType  "inbound-whatsapp.v7"                  (CLASS)        │
│  shared by every customer · almost open-source · compiler-owned     │
│                                                                     │
│   charter schema · faculties · domain pack · verification suite     │
│   settlement rules · eval gym · execution profile                   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ instantiated per customer
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│ INSTANCE      │      │ INSTANCE      │      │ INSTANCE      │
│ Sharma Dental │      │ Restaurant B  │      │ Salon C       │
│ (OBJECT)      │      │               │      │               │
│ private state:│      │  ring: L2     │      │  ring: L0     │
│  ring: L1     │      │  heap region  │      │  heap region  │
│  heap region  │      │  résumé       │      │  résumé       │
│  résumé       │      │  overrides    │      │  overrides    │
│  overrides    │      └───────────────┘      └───────────────┘
└───────┬───────┘
        │ triggered per event (message, deadline, spawn, demand)
        ▼
┌─────────────────────────────────────────────┐
│ RUN #582  (STACK FRAME → durable            │
│            continuation, parks for days)    │
│  hydration snapshot (frozen)                │
│  syscall trace · claimed facts · scratchpad │
│  state: created→running→parked→…→settled    │
└─────────────────────────────────────────────┘
```

**Walk-through:** A patient messages Sharma Dental at 14:02. The Type (v7) supplies *how an inbound-WhatsApp mandate behaves*. The Instance supplies *what is true at Sharma's* (accepts Star Health, cleaning ₹1500, ring L1 → drafts need owner approval). Run #582 is created, lives ~40 minutes including a parked approval, settles, and is never mutated again — it remains forever as a journal entry and an eval case.

---

## Diagram 2 — Inside a MandateType: the seven organs

```mermaid
flowchart TB
    subgraph TYPE["MandateType — the seven organs"]
        CH["1 · CHARTER<br/>done, in checkable terms<br/>pre / path / post conditions"]
        subgraph FAC["2 · FACULTIES (from shared library)"]
            F1["conversation"]
            F2["scheduling"]
            F3["memory-craft"]
            F4["escalation"]
        end
        DP["3 · DOMAIN PACK<br/>vertical playbooks +<br/>category priors (from outcome corpus)"]
        VS["4 · VERIFICATION SUITE<br/>rules → judge → human → reality<br/>(cheapest rung that suffices)"]
        SR["5 · SETTLEMENT RULES<br/>commits · trust Δ · billing ·<br/>watches · spawn rules"]
        GYM["6 · EVAL GYM<br/>reality-graded cases +<br/>compiler (GEPA-style)"]
        EX["7 · EXECUTION PROFILE<br/>per-faculty routing:<br/>harness adapter × model × budget"]
    end

    CH --> FAC
    DP --> FAC
    FAC --> VS
    VS --> SR
    SR --> GYM
    GYM -- "recompiles skill packs<br/>(new Type version)" --> FAC
    EX -.-> FAC
```

**Key reading:** the arrows form a loop — faculties act, verification judges, settlement records, the gym learns, the compiler rewrites the faculties. The quality of the mandate is the *speed of this loop*, not the cleverness of any single prompt. Each faculty is itself a bundle:

```text
Faculty "conversation" {
  skill_pack:    compiled prompts (compiler-owned artifact, versioned)
  tool_manifest: send_message, read_thread          (syscall stubs only)
  rubrics:       tone, factual grounding, one-question-per-message
  eval_slice:    its graded cases in the gym
  routing_hint:  strong model, latency-tolerant
}
```

---

## Diagram 3 — Full lifecycle of one run (the master flow)

*Sharma Dental, ring L1, patient asks: "Do you take Star Health insurance? How much is a cleaning?"*

```mermaid
sequenceDiagram
    autonumber
    participant W as WhatsApp (hardware)
    participant S as Scheduler (kernel)
    participant H as Heap+Journal (kernel)
    participant P as Pod (Hermes, user space)
    participant G as Syscall Gateway (kernel)
    participant O as Owner (root supervisor)
    participant V as Verifier (kernel)

    W->>S: webhook: inbound message (14:02)
    S->>W: instant pre-approved holding template ("Got it, checking! 🙏")
    S->>H: create RUN #582 (state: created)
    S->>H: HYDRATE: snapshot read of Sharma heap region
    Note over H: facts ranked by relevance × confidence × recency<br/>(accepts_insurer star_health, 0.95, owner-stated)<br/>(cleaning price ₹1500, 0.9) + thread + calendar + playbook
    S->>P: run(snapshot, tool_manifest, budget)
    Note over P: Hermes loops, plans, drafts.<br/>Pod holds ZERO credentials —<br/>every tool is a stub → gateway.
    P->>G: syscall check_calendar()
    G->>G: ring check (read: any ring) ✓ → execute
    G-->>P: slots: today 16:30, tomorrow 11:00
    P->>G: syscall send_whatsapp(draft reply)
    G->>G: ring check: needs L2, instance is L1 ✗
    G->>H: PARK run #582 (durable continuation, state: parked)
    G->>O: approval card → owner's WhatsApp<br/>[Approve / Edit / Reject]
    Note over O: owner taps APPROVE (14:05)
    O->>G: approve
    G->>H: resume run from row
    G->>W: execute send (idempotency key checked)
    P-->>S: done: {output, trace, claimed_facts}
    S->>V: verify (rules ✓, judge ✓, human ✓ already)
    V->>H: SETTLE: atomic commit (see Diagram 4)
    H->>S: register WATCH: booking/reply within 72h
    Note over W,H: 14:40 — patient books. Calendar webhook fires.
    W->>S: watch hit
    S->>H: DEFERRED SETTLE: promote facts, trust +1,<br/>billing line, run → graded eval case
```

**The three properties to notice:** (1) the hydration snapshot is frozen onto the run row — you can forever answer *"what did the agent know when it said that?"*; (2) the pod could be killed at any step and the run resumes from its row — no state lives in process memory; (3) the human approval is just another parked state, mechanically identical to waiting on a webhook.

---

## Diagram 4 — Settlement: the atomic commit fan-out

*Settlement is one transaction. Memory, trust, billing, evals, and spawns can never disagree about what happened.*

```mermaid
flowchart LR
    R["RUN #582 verified"] --> T{"SETTLE<br/>(one atomic txn)"}

    T --> M["HEAP commits<br/>claimed facts @ conf 0.6<br/>source: agent-inferred<br/>(probation)"]
    T --> C["OWNER CORRECTIONS<br/>commit @ conf 0.95<br/>+ before/after diff → gym (gold tier)"]
    T --> TR["TRUST<br/>streak +1 toward L2"]
    T --> B["BILLING<br/>line item written"]
    T --> WCH["WATCHES<br/>register: outcome within 72h"]
    T --> SP["SPAWN RULES<br/>on lead_warm_but_unbooked →<br/>spawn followup(lead_id)"]
    T --> J["JOURNAL<br/>WAL entry — the ledger"]

    WCH -. "72h later: booking happened" .-> D["DEFERRED SETTLE<br/>promote probation facts ↑<br/>trust confirmed · run becomes<br/>GRADED eval case"]
    D --> GYM["EVAL GYM grows"]
```

**The three births of customer memory**, all visible here: *claimed facts* enter on probation (the agent's beliefs, humbly); *owner corrections* enter as law (one thumb tap = one training event); *outcomes* promote or demote everything (reality is the only ungameable verifier). Six months of this is the heap region a departing customer loses.

---

## Diagram 5 — The excellence flywheel (how a mandate gets good)

```mermaid
flowchart TB
    RE["REALITY<br/>messages, bookings, replies, silence"] --> RUNS["Settled runs<br/>(verified, provenance-stamped)"]
    RUNS --> GYM["EVAL GYM (per Type)<br/>~900 graded cases / clinic / month<br/>gold tier: owner corrections"]
    GYM --> COMP["COMPILER (GEPA-style)<br/>reflects on failing traces,<br/>rewrites faculty skill packs<br/>(needs only 100–500 evals)"]
    COMP --> CAND["Candidate Type version v8"]
    CAND --> GATE{"REGRESSION GATE<br/>beats v7 on full gym?<br/>no rubric regressions?"}
    GATE -- fail --> COMP
    GATE -- pass --> CAN["CANARY<br/>consenting instances only"]
    CAN --> PROM["PROMOTE v8<br/>semver · changelog · rollback<br/>instance state survives (lives in heap)"]
    PROM --> RUNS

    style GYM fill:#1a3a1a,stroke:#4a4
    style COMP fill:#1a2a3a,stroke:#48f
```

**Why this kills the "Prompt Engineering Company" fear structurally:** a stolen prompt is a snapshot of `v7` — it decays the moment reality shifts, and the thief has no gym to compile `v8`. The founder's job moves up a level: curate rubrics, triage the compiler's losing cases, write the rule that catches a new failure class. One person's taste, compiled into every customer's agent.

---

## Diagram 6 — The Mandate SDK: assembling mandate #2 in days

```mermaid
flowchart LR
    subgraph LIB["FACULTY LIBRARY (shared, compounding)"]
        L1["research"]
        L2["judgment"]
        L3["conversation"]
        L4["outreach"]
        L5["scheduling"]
        L6["memory-craft"]
        L7["escalation"]
    end

    subgraph NEW["NEW: inbound-whatsapp.v1 (days of work)"]
        NC["Charter — NEW<br/>(1 day: done-conditions)"]
        ND["Domain pack — NEW<br/>(days: clinic playbook)"]
        NV["Verification — rubrics NEW,<br/>rules library REUSED"]
        NS["Settlement — config"]
        NG["Gym — starts EMPTY,<br/>self-fills from week 1"]
        NE["Execution — routing config"]
    end

    L3 --> NEW
    L5 --> NEW
    L6 --> NEW
    L7 --> NEW

    NEW --> SHIP["Ship at L0/L1:<br/>SAFE by construction<br/>(verification on, escalation linked)"]
    SHIP --> WK3["~Week 3: gym has enough cases,<br/>compiler takes over quality"]
```

**The honest promise:** mandate #2 does *not* start great — it starts **safe** (low ring, full verification, escalation wired in), and gets great automatically. `memory-craft` and `escalation` being library faculties is the deep win: writing good memory and failing well are engineered once, linked in everywhere.

---

## Diagram 7 — Workflow = deterministic spine, reasoning nodes

*The Sharma lead, across three mandates. Edges are declared in settlement rules (auditable in advance); node interiors are agentic (discovered at runtime).*

```mermaid
flowchart LR
    IN["INBOUND mandate<br/>run #582"] -- "settles: lead_warm_but_unbooked<br/>SPAWN followup(lead_id)" --> FU["FOLLOW-UP mandate<br/>run #601 (T+2 days)"]
    FU -- "settles: lead_ready<br/>SPAWN scheduling(lead_id)" --> SC["SCHEDULING mandate<br/>run #618"]
    SC -- "books 11:00" --> DONE["outcome: booked<br/>(watch fires on all 3 runs:<br/>attribution settles backward)"]

    IN -. "commits facts" .-> HEAP[("SHARED HEAP<br/>(this_lead, has_insurer, star_health, 0.9)<br/>(this_lead, interested_in, cleaning, 0.9)")]
    HEAP -. "hydrates" .-> FU
    HEAP -. "hydrates" .-> SC

    FU -- "crash: 'can I pay in Bitcoin?'" --> OWN["ESCALATE ↑ owner resolves<br/>resolution COMMITS to heap —<br/>same crash never repeats"]
    OWN --> FU
```

**Two semantics to hold onto:** there is no mandate-to-mandate message channel — *spawn is the function call, the heap is the return path*, and every inter-mandate "message" is a committed, verified fact with confidence attached. And failure is supervised, not handled: a confused mandate crashes upward with full context, and the human's resolution becomes permanent memory.

---

## Diagram 8 — The internal market (demand / résumé / award)

*Agent-X is principal #0: our own acquisition mandate fills our own funnel. Later, the same table is the marketplace.*

```mermaid
sequenceDiagram
    autonumber
    participant GTM as Agent-X GTM (principal #0)
    participant K as Kernel (demands table)
    participant ACQ as Acquisition mandate<br/>(service port: qualified_leads)
    participant ACQ2 as Competing fulfiller<br/>(future: 3rd-party type)
    participant V as Verifier

    GTM->>K: POST Demand {spec: 20 leads, ICP-X, fit ≥ 0.7,<br/>budget ₹500/day, verification: founder-accept}
    K->>K: match spec → service ports
    ACQ-->>K: candidate (résumé: 412 leads delivered,<br/>71% accepted, ₹38/lead)
    ACQ2-->>K: candidate (résumé: none yet)
    K->>ACQ: AWARD (by verified résumé, not self-claims)
    ACQ->>ACQ: child runs: research → judgment → outreach
    ACQ->>V: fulfillment verified (founder accepts 18/20)
    V->>K: SETTLE: demand closed, billing line,<br/>résumé update (now 430 delivered, 71.2%)
    Note over K: Contract Net (Smith, 1980), inside the OS:<br/>announce → bid → award → verify → settle.<br/>Marketplace = opening this table to 3rd parties.
```

**Why this matters strategically:** "the acquisition agent sells everything we build" stops being a slogan and becomes a row in a table. And when two mandate types can fulfill the same demand, résumé + cost decide — capability arbitrage with verified outcomes as the price signal.

---

## Diagram 9 — The whole Business OS

```text
                            ┌────────────────────────────────────────────┐
                            │              CUSTOMERS' PROGRAMS           │
                            │   (each = a set of standing mandates)      │
 USER SPACE                 │                                            │
 (rented, disposable,       │  ┌─ Sharma Dental pod ─┐ ┌─ Restaurant B ─┐│
 zero credentials,          │  │ inbound · follow-up │ │ inbound · ...  ││
 zero durable state)        │  │ scheduling          │ │                ││
                            │  │ [Hermes today]      │ │ [OpenClaw]     ││
                            │  └──────────┬──────────┘ └───────┬────────┘│
                            └─────────────┼────────────────────┼─────────┘
                ═════════ ADAPTER LINE ═══╪════════════════════╪══════════
                            ┌─────────────▼────────────────────▼─────────┐
                            │                 KERNEL (the company)       │
                            │                                            │
                            │  SCHEDULER     reality + deadlines → runs  │
                            │  HEAP          per-customer regions,       │
                            │                transactional, journaled    │
                            │  LEDGER        the heap's WAL = audit trail│
                            │  VERIFIER      rules→judge→human→reality   │
                            │  SYSCALLS      ring-checked, idempotent    │
                            │  RINGS L0–L4   earned authority            │
                            │  SUPERVISION   forest: 1 tree per customer,│
                            │                owner at root               │
                            │  DEMANDS       internal market             │
                            │  COMPILER+GYMS per-Type quality CI         │
                            └───────┬───────────────────────┬────────────┘
                                    │                       │
                     ┌──────────────▼─────────┐   ┌─────────▼──────────────┐
                     │  HARDWARE (reality)    │   │ CATEGORY INTELLIGENCE  │
                     │  WhatsApp · CRM ·      │   │ settled journals →     │
                     │  calendar · email ·    │   │ patterns only, never   │
                     │  money                 │   │ facts → domain packs → │
                     │                        │   │ customer #50 starts at │
                     │  ← REVENUE flows here  │   │ day-1000 knowledge     │
                     └────────────────────────┘   │  ← MOAT compounds here │
                                                  └────────────────────────┘
```

**The asymmetry is the company:** everything above the adapter line is fungible compute you rent; everything below it is durable state you own. Two flows leave the kernel — one is revenue (real effects in the world), the other is the moat (verified experience compiling into priors). Swapping Hermes for whatever is cheapest-per-verified-outcome next quarter touches nothing below the line.

---

## Diagram 10 — Syscall enforcement: rings at the gateway

```mermaid
flowchart TB
    SC["syscall from pod:<br/>send_whatsapp(draft, to: patient)"] --> IDEM{"idempotency key<br/>seen before?"}
    IDEM -- yes --> DROP["return cached result<br/>(LLMs retry; customers never<br/>get the message twice)"]
    IDEM -- no --> CLASS{"effect class?"}
    CLASS -- "read (calendar, thread)" --> EXEC["execute at any ring"]
    CLASS -- "reversible write" --> R2{"ring ≥ L2?"}
    CLASS -- "money / irreversible" --> R4{"ring ≥ L4 AND<br/>within budget envelope?"}
    R2 -- yes --> EXEC
    R2 -- "no (Sharma = L1)" --> PARK["PARK run →<br/>approval card to owner<br/>Approve / Edit / Reject"]
    R4 -- yes --> EXEC
    R4 -- no --> PARK
    PARK -- approve --> EXEC
    PARK -- edit --> EDIT["corrected effect executes +<br/>diff commits to heap @ 0.95 +<br/>gold-tier gym case"]
    PARK -- reject --> ESC["escalate ↑ supervision tree"]
    EXEC --> TRACE["append to syscall trace<br/>(journal)"]
```

**Ring promotion is mechanical, not vibes:** N consecutive approvals with zero edits on an effect class → propose promotion to the owner; any reality-verified failure → automatic demotion review. "Your agent runs at L2 here, earned over 14 months, clean audit trail" is a sentence with mechanical meaning — and it is non-portable, which is the second leg of the moat.

---

## Diagram 11 — Data model (the dozen tables that are the whole company)

```mermaid
erDiagram
    MANDATE_TYPE ||--o{ MANDATE_INSTANCE : "instantiated per customer"
    MANDATE_TYPE ||--o{ FACULTY_BINDING : "links library faculties"
    FACULTY ||--o{ FACULTY_BINDING : ""
    MANDATE_TYPE ||--|| EVAL_GYM : "quality CI"
    CUSTOMER ||--o{ MANDATE_INSTANCE : owns
    CUSTOMER ||--|| HEAP_REGION : "private facts"
    MANDATE_INSTANCE ||--o{ MANDATE_RUN : "per trigger"
    MANDATE_INSTANCE ||--|| RESUME : "verified track record"
    MANDATE_RUN ||--o{ SYSCALL : "traced effects"
    MANDATE_RUN ||--o{ FACT : "claims (probation)"
    HEAP_REGION ||--o{ FACT : "committed, provenance-stamped"
    MANDATE_RUN ||--o{ JOURNAL_ENTRY : "WAL / ledger"
    MANDATE_RUN ||--o{ WATCH : "deferred verification"
    WATCH ||--o| EVAL_CASE : "outcome grades the run"
    EVAL_GYM ||--o{ EVAL_CASE : accumulates
    DEMAND }o--|| MANDATE_INSTANCE : "awarded by résumé"
    MANDATE_RUN ||--o{ BILLING_LINE : "settlement writes"

    FACT {
        string subject_predicate_object
        float confidence
        string provenance "run id + evidence"
        string source "owner-stated | corrected | agent-inferred | outcome"
        datetime decay_at "GC: episodic facts expire, policies are tenured"
    }
    MANDATE_RUN {
        string state "created|running|parked|verifying|settled|crashed"
        json hydration_snapshot "frozen: what the agent knew"
    }
```

**Implementation honesty:** this is Postgres and a worker loop. The kernel-minimum for Phase 1 is roughly a dozen tables and one state machine — the sophistication is in the *invariants* (no fact without a commit; no credential in user space; no durable state below the adapter line; no cross-customer fact flow; no unverified résumé), not in the infrastructure.

---

## The flows, indexed

| # | Flow | Diagram |
|---|---|---|
| 1 | Class → object → stack frame | 1 |
| 2 | Inside a Type: the seven organs + quality loop | 2 |
| 3 | One run, trigger to deferred settlement | 3 |
| 4 | The atomic commit fan-out / births of memory | 4 |
| 5 | Gym → compiler → gate → canary → promote | 5 |
| 6 | Assembling a new mandate from the faculty library | 6 |
| 7 | Workflow: spawn edges, heap as return path, crash-upward | 7 |
| 8 | Internal market: demand → résumé award → settle | 8 |
| 9 | Whole OS: kernel / user space / hardware / intelligence | 9 |
| 10 | Ring enforcement + promotion mechanics | 10 |
| 11 | The data model | 11 |
