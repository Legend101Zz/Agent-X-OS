# Agent-X — Build Kit & Setup Instructions

*The bridge from the [BLUEPRINT](./BLUEPRINT.md) to a running repo. Two coding agents build in parallel: **Claude Code (Opus 4.8)** builds the **Kernel + Mandate**; **Codex** builds the **Syscall + Swarm**. This doc gives you the exact prompts, the split, the shared seam, and the run order.*

---

## 0. How to use this document (run order)

```text
  SESSION A  (you, with Claude Code)
    └─ paste PROMPT 0 → Claude designs the repo: skeleton, the CONTRACTS seam,
       agent-guidance files (CLAUDE.md / AGENTS.md / .claude/agents), and a
       per-agent BUILD-PLAN.md.  NO feature code yet — design + scaffold + plan.
    └─ you review. The contracts package is the thing to scrutinize: it is the
       agreement both agents build against. Freeze it.

  SESSION B  (parallel — two terminals)
    ├─ paste PROMPT 1 into Claude Code → builds packages/kernel + packages/mandate
    └─ paste PROMPT 2 into Codex       → builds packages/syscall + packages/swarm
       both build ONLY against packages/contracts. They never edit each other's lane.

  INTEGRATION
    └─ run the integration test suite (PROMPT 0 scaffolds it). The seam is proven
       when a candidate mandate runs end-to-end through the kernel, calls a syscall
       adapter, parks for human approval, settles, and a swarm run grades it.
```

> **The single most important idea in this whole kit:** when two agents build two halves of one system, *the interfaces are defined and frozen before either agent writes feature code.* That shared interface is `packages/contracts`. Get it right in Session A and the two halves snap together in Session B. Get it wrong and you get integration hell. Everything below serves that principle.

---

## 1. Blueprint readiness — final analysis

**Verdict: implementation-ready for Phase 1.** Nothing conceptually missing. The thinking is unusually complete — primitive (Mandate), topology (Model D), kernel (two clocks), syscall layer (gateway + ladder + human rung), quality engine (gym + swarm + promptfoo), and the operator tools (Creator, Dashboard) are all specified, with 8 invariants and explicit kill-conditions. Validated against AIOS, Contract Net, DSPy/GEPA, Voyager, Temporal, OTP.

**Three couplings the build must respect (these drive the contracts seam):**

1. **The swarm runs *on* the kernel, not beside it.** This means the kernel's run-loop must be invokable in two modes — `live` and `sim` — *from day one.* If Claude builds a live-only run-loop, the swarm (Codex) can't drive it. → `RunInvoker` interface in contracts, with a `mode` parameter. This is the #1 thing to get right.
2. **The gateway is kernel-owned, but adapters are Codex's.** The gateway (Claude) *selects and calls* adapters; the adapters (Codex) *implement* a fixed interface. → `Adapter` interface in contracts. Claude consumes it; Codex implements it.
3. **The verifier has rungs owned by both sides.** Rules + human rungs are kernel (Claude); the judge rung is promptfoo in the swarm (Codex); reality rung is a watch (kernel). → `Verifier`/`Judge` interfaces in contracts so rungs are pluggable.

**Genuinely open decisions (taken below, override if you disagree):** language/stack, monorepo tool, DB layer. None are conceptual — they're plumbing.

**One scope discipline to enforce on both agents:** the blueprint describes the *whole* OS. The build is **Phase 1 only** (one lead-finder mandate, manual projection, rings L0–L2, no money/WhatsApp/voice/browser). Both prompts must forbid building ahead of Phase 1. The architecture is designed so Phases 2–5 are *additions*, never rewrites — so there is zero cost to deferring them and real cost to building them early.

---

## 2. Decisions taken (override if you disagree)

| Decision | Choice | Why |
|---|---|---|
| **Language (core)** | **Python 3.12** for kernel/mandate/syscall/swarm | The system's gravity is AI-native, and the moat-engine — the GEPA/DSPy **compiler** ("mandates are compiled") — is Python-only. A Python core keeps the most-iterated boundary (core ↔ compiler/eval) internal. |
| **Typed seam** | **Pydantic v2 + `typing.Protocol`** | Our contracts validate *LLM output at runtime* — Pydantic's home turf (TS types are erased at runtime). The two-agent seam = Pydantic models + Protocols, mypy-clean. |
| **Dashboard** | **TypeScript / React (Next.js)** — separate frontend over the kernel API | A frontend/API split is normal and cheap; only the UI is TS. |
| **Monorepo** | **uv workspace** (Python) + **npm** for the dashboard | uv = fast modern Python packaging; shares `packages/contracts` across both lanes. npm (your call) governs the dashboard + the promptfoo subprocess. |
| **Database** | **MongoDB**, event-sourced | The **Journal is an append-only event collection** → single-document atomic appends (sidesteps multi-doc transactions); **Heap / Threads / Résumé are projections** built from it. Flexible doc schemas fit per-vertical heaps/facts/scenario-packs. Driver: **Motor** (async). |
| **Eval/judge/gate** | **promptfoo** as a subprocess | Decided in BLUEPRINT §5/§8. Wired as a custom provider that calls the kernel — language-agnostic, so a Python core is fine. |
| **Compiler (later)** | native Python (GEPA/DSPy) | Now in-language, no sidecar boundary. Still Phase-2+; out of Phase-1 scope. |

> **Why this reverses the earlier TS lean:** the deciding factor is that the compiler (the engine of "mandates are compiled," the moat) is Python-only, and *runtime* validation of untrusted LLM output is Pydantic's strength, not TS's. The two things that pulled toward TS — promptfoo and the web dashboard — don't need a TS core: promptfoo runs as a subprocess, and the dashboard is a separate frontend regardless.

---

## 3. The split and the seam

```text
                         packages/contracts   ← THE SEAM (the only cross-boundary dependency)
                         types + interfaces, frozen after Session A
                                  ▲                         ▲
            depends on (read)     │                         │   depends on (read)
   ┌──────────────────────────────┴───┐         ┌───────────┴────────────────────────┐
   │  CLAUDE CODE  (Opus 4.8 = brain)  │         │  CODEX                              │
   │                                   │         │                                     │
   │  packages/kernel                  │         │  packages/syscall                   │
   │    scheduler · heap+journal       │         │    Adapter framework + registry     │
   │    verifier (rules+human rungs)   │         │    fulfillment ladder resolution    │
   │    GATEWAY policy (ring,          │  calls  │    Phase-1 adapters:                 │
   │      idempotency, channel rules,  │ ──────▶ │      lead_research_batch, read_url,  │
   │      adapter selection, cred      │ Adapter │      draft_email, queue_manual_action│
   │      injection, journaling)       │  iface  │      mark_outcome, HumanTaskAdapter  │
   │    supervision · run-loop         │         │    health checks · fixtures          │
   │      (live + SIM modes)           │◀──────  │                                     │
   │                                   │ RunInvk │  packages/swarm                      │
   │  packages/mandate                 │  the    │    Swarm REPL · scenario packs       │
   │    Type/Instance/Run models       │  swarm  │    SimAdapter · trace viewer data    │
   │    seven organs · faculties fw    │  runs   │    promptfoo bridge (judge/gate)     │
   │    hydration · settlement engine  │  ON the │    SwarmSession/PromotionGate        │
   │    Phase-1 faculties: research,   │  kernel │                                     │
   │      judgment, memory-craft,      │         │  dashboard/ (TS/React, npm — separate)│
   │      escalation                   │         │    reads kernel command/query API    │
   └───────────────────────────────────┘         └─────────────────────────────────────┘
```

### What lives in `packages/contracts` (designed in Session A, then frozen)

```python
# ---- Domain + MEMORY types (Pydantic v2 models; kernel-authored, everyone reads) ----
# MandateType, MandateInstance, MandateRun, Trigger, InstanceBinding
# Faculty(skill_pack, tool_manifest, rubrics, eval_slice, routing_hint, harness_adapter,
#         fulfillment_pref)            # harness-agnostic capability contract (BLUEPRINT §1/§4.5)
# Fact(subject, predicate, object, confidence, provenance, source, decay_at)   # Heap (semantic)
# Thread(entity_id, state, history)                                            # relational memory
# Resume(ring, success_rates, ...)                                             # performance memory
# JournalEvent(...)   # append-only SOURCE OF TRUTH; Heap/Threads/Résumé project from it
# Ring = Literal["L0","L1","L2","L3","L4"]; Trace, Scorecard, Rubric, SettlementEvent

# ---- SEAM 1: the syscall boundary (Codex implements, kernel gateway calls) ----
class Adapter(Protocol):
    name: str; category: str
    maturity_level: int                       # 0|1|2|3
    risk_class: str; required_ring: Ring
    tenant_auth: Literal["oauth", "api_key", "agent_owned", "manual"]
    input_schema: dict; output_schema: dict   # JSON Schema
    fixtures: list[SyscallTestCase]
    def can_handle(self, req: SyscallRequest, ctx: GatewayContext) -> bool: ...
    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult: ...
    async def dry_run(self, req: SyscallRequest) -> SyscallResult: ...
    async def verify(self, result: SyscallResult) -> VerifyOutcome: ...
    async def health_check(self) -> Health: ...

# ---- SEAM 2: the run boundary (kernel implements, swarm calls) — swarm runs ON the kernel ----
class RunInvoker(Protocol):
    async def invoke(self, *, mandate: MandateType, instance: InstanceBinding,
                     trigger: Trigger, mode: Literal["live", "sim"]) -> RunResult: ...
    #                                              ^ sim binds SimAdapters; the loop does not branch otherwise

# ---- SEAM 3: pluggable verification rungs ----
class Judge(Protocol):        # Codex: promptfoo subprocess
    async def grade(self, trace: Trace, rubric: Rubric) -> Scorecard: ...
class RuleCheck(Protocol):    # kernel: deterministic
    def check(self, req: SyscallRequest, ctx: GatewayContext) -> RuleVerdict: ...
```

The memory models (`Fact`, `Thread`, `Resume`, `JournalEvent`) live in `contracts` because both lanes read them; the kernel owns their *projection* logic (journal → heap/threads/résumé).

**Coordination protocol (Session B):** both agents depend only on `contracts`. If either discovers the seam is wrong, it is a **stop-and-coordinate event** — fix `contracts` first, both agents re-pull, then continue. No agent edits the other's package. Use separate git branches/worktrees per agent; `contracts` changes merge first.

---

## 4. Target repo layout (PROMPT 0 produces this)

```text
agent-x/
├── docs/                      ← copy of ~/Desktop/agent-x-os/*.md (BLUEPRINT.md canonical)
├── packages/                  ← uv workspace members (Python)
│   ├── contracts/             ← THE SEAM. Pydantic models + Protocols only. frozen after Session A.
│   ├── kernel/                ← CLAUDE: scheduler, heap+journal, verifier, gateway, run-loop, supervision, command API
│   ├── mandate/               ← CLAUDE: Type/Instance/Run, organs, faculties, memory layer, hydration, settlement
│   ├── syscall/               ← CODEX: adapter framework, registry, ladder, Phase-1 adapters, HumanTask
│   ├── swarm/                 ← CODEX: scenario packs, SimAdapter, promptfoo bridge, REPL, gates
│   └── operator/              ← optional/near-term: the Operator Agent over the command API (BLUEPRINT §6.1)
├── dashboard/                 ← TS/React (Next.js), npm — thin reads + command endpoints over the kernel API
├── db/                        ← MongoDB: collection + index setup; the append-only `journal` event
│                                collection is the source of truth; heap/threads/résumé are projections
├── tests/integration/         ← the seam proof: end-to-end run through both halves
├── pyproject.toml             ← uv workspace root
├── CLAUDE.md                  ← root context for Claude Code (points to docs, invariants, lane)
├── AGENTS.md                  ← root context for Codex (commands-first + lane + invariants)
├── BUILD-PLAN.md              ← Phase-1 task graph, split per agent, definition-of-done
└── .claude/agents/            ← custom subagents (see §5)
```

---

## 5. Subagent strategy (the brain delegates bounded work)

Both build agents run a **high model as the orchestrator/brain** that holds the architecture and integrates, and **dispatch subagents for bounded, parallelizable work** (per [Anthropic's subagent guidance](https://code.claude.com/docs/en/sub-agents) and [OpenAI's Codex best practices](https://developers.openai.com/codex/learn/best-practices)).

**Claude Code** — PROMPT 0 creates these in `.claude/agents/` (frontmatter: `name`, `description`, `tools`, `model`):

| Subagent | Model | Job |
|---|---|---|
| `kernel-module-builder` | opus | implement one kernel module against contracts + its tests |
| `faculty-builder` | sonnet | implement one faculty (research / judgment / memory-craft / escalation) |
| `test-writer` | sonnet | write test suites / fixtures for a module (TDD) |
| `contract-guardian` | opus | review a diff against `contracts` + the 8 invariants; read-only |
| `doc-researcher` | haiku | fetch current API docs (Motor/MongoDB, MCP Python SDK, Exa/Firecrawl, promptfoo) |

The brain (Opus, main session) keeps the architecture, sequences the plan, dispatches the above for independent work (e.g., four faculties in parallel), and integrates. It uses the available **superpowers skills**: `test-driven-development`, `writing-plans`, `subagent-driven-development`, `using-git-worktrees`, `verification-before-completion`.

**Codex** — uses `/fork` for branched work, **git worktrees** for parallel package work without collisions, and subagents for bounded tasks (e.g., one adapter each), while the main thread holds the syscall/swarm architecture. One thread per coherent task; `AGENTS.md` carries standing context.

---

## PROMPT 0 — Repo design & scaffold  ·  paste into Claude Code (Session A)

```text
You are the lead architect setting up the Agent-X monorepo. This session is DESIGN + SCAFFOLD ONLY — no feature implementation. You will be judged on the quality of the shared contracts and the clarity of the build plan, because two coding agents (you, and Codex) will build against what you produce here.

GOAL
Create the agent-x monorepo: skeleton, the shared `packages/contracts` seam, all agent-guidance files, DB migration scaffolding, integration-test scaffolding, and a Phase-1 BUILD-PLAN.md split between two agents.

REQUIRED READING (read fully before doing anything; internalize it)
- ~/Desktop/agent-x-os/BLUEPRINT.md   ← CANONICAL. When docs conflict, this wins.
- ~/Desktop/agent-x-os/MANDATE.md, SYSCALLS.md, ARCHITECTURE.md, README.md
- ~/Documents/Startup Idea/AGENT_X_SYSCALL_TOOL_LANDSCAPE_RESEARCH.md
- ~/Desktop/agent-x-os/BUILD-KIT.md   ← THIS kit: §1 readiness, §2 decisions, §3 the seam, §4 layout, §5 subagents. Implement the seam in §3 exactly.
Copy all of the agent-x-os/*.md docs into the repo at docs/ so the build agents have them in-tree.

STACK (from BUILD-KIT §2): Python 3.12 + uv workspace for the core (kernel/mandate/syscall/swarm); Pydantic v2 + typing.Protocol for contracts; MongoDB (Motor async) event-sourced; promptfoo as a subprocess for eval; a SEPARATE TS/React (Next.js, npm) dashboard. Use web search to confirm current setup commands/versions (uv, Pydantic v2, Motor/MongoDB, MCP Python SDK, promptfoo) — do not rely on memory for versions.

REPO LOCATION & SECRETS
- Create the repo at: "/Volumes/Mrigesh SSD/Startup/Agent-X-OS"  (the folder "/Volumes/Mrigesh SSD/Startup" already exists — create Agent-X-OS inside it; the path has a space, so quote it in every shell command). Run `git init`, set the remote to https://github.com/Legend101Zz/Agent-X-OS.git, and make ONE initial commit of the scaffold. Do NOT push unless I ask.
- Secrets live in `.env` (I will paste the real values myself — DO NOT ask me for them or invent any). Produce a `.env.example` listing every variable Phase 1 needs, each with a one-line comment: MONGODB_URI (my Mongo Atlas cluster), the LLM API key(s) the faculties use, the research-provider key (EXA_API_KEY or FIRECRAWL_API_KEY), and any promptfoo key. Wire a typed config loader (pydantic-settings) that reads `.env`. Add `.env` to `.gitignore`; commit only `.env.example`. Never hardcode, echo, or commit a secret value.

WHAT TO PRODUCE
1. The monorepo skeleton exactly as BUILD-KIT §4, with the uv workspace (root pyproject.toml + per-package pyproject) wired and importing (empty packages OK); the dashboard/ folder stubbed as a separate npm app.
2. packages/contracts — FULLY designed (the most important deliverable): Pydantic v2 models for the domain + MEMORY types (Fact, Thread, Resume, JournalEvent — the memory layer, BLUEPRINT §1) and the Faculty contract (incl. `harness_adapter` + fulfillment preference, BLUEPRINT §1/§4.5); typing.Protocol interfaces for SEAM 1 (Adapter), SEAM 2 (RunInvoker with live|sim mode), SEAM 3 (Judge/RuleCheck) — exactly as BUILD-KIT §3. Doc-string each. mypy-clean, no untyped dicts. Interfaces only; implementations are TODOs in the other packages.
3. db/ — MongoDB setup: collections + indexes for Phase-1 (mandate_type, mandate_instance, mandate_run, journal, heap_fact, thread, resume, watch, syscall_trace, billing_line, eval_case). Event-sourced: `journal` is the append-only source of truth (single-doc atomic appends); define the JournalEvent schema and the projection-builder interfaces (heap/threads/résumé). Interfaces/schemas only; no business logic.
4. CLAUDE.md (root) — points to docs/, states the 8 invariants verbatim from BLUEPRINT §4, states Claude's lane (kernel + mandate), and the Phase-1-only scope rule.
5. AGENTS.md (root) — commands-first (setup / test / lint / build), then Codex's lane (syscall + swarm), the 8 invariants, and the Phase-1-only scope rule. Keep it concise and practical.
6. .claude/agents/ — create the five subagents from BUILD-KIT §5 with correct frontmatter and focused system prompts.
7. tests/integration/ — a failing scaffolded test that describes the seam proof (candidate mandate → kernel run-loop → syscall adapter → park for approval → settle → swarm grades it). It should fail with "not implemented", documenting the integration target.
8. BUILD-PLAN.md — break Phase 1 (BLUEPRINT §7) into a task graph, split into CLAUDE LANE and CODEX LANE, each task with a one-line definition-of-done. Mark the contracts package FROZEN once this session ends, and note the stop-and-coordinate protocol for any later contract change.

CONSTRAINTS (the 8 invariants from BLUEPRINT §4 are inviolable; encode the structural ones as lint/types where possible)
- No credential type is ever importable into packages/mandate (pods hold no creds). Enforce via package boundaries.
- A syscall is intent; the Adapter interface must make the human-task queue the tail of every ladder.
- The run-loop interface MUST support sim mode (the swarm runs on the kernel).
- Do NOT implement Phase 2–5 anything (no money, WhatsApp, voice, browser).

METHOD
- Use the Plan skill to sequence this, then execute. Use subagents for independent scaffolding (e.g., doc-researcher to confirm tool versions while you design contracts).
- Verify the workspace builds and the integration test fails for the right reason before you finish.

DONE WHEN
- `uv sync` succeeds and the workspace imports clean (mypy passes on contracts); `uv run pytest` shows the integration test failing with a clear "not implemented" describing the seam.
- packages/contracts is complete, fully typed (Pydantic + Protocols), doc-stringed, and reviewed by the contract-guardian subagent against the 8 invariants.
- CLAUDE.md, AGENTS.md, .claude/agents/*, and BUILD-PLAN.md exist and are accurate.
- The repo exists at "/Volumes/Mrigesh SSD/Startup/Agent-X-OS" with `git init`, the remote set, one initial commit; `.env.example` is committed, `.env` is gitignored, and the pydantic-settings config loader reads `.env`.
- You print a short "Session B kickoff" summary: what each agent runs next, the frozen-contracts reminder, and a checklist of the `.env` values I must paste before the build session.
```

---

## PROMPT 1 — Build the Kernel + Mandate  ·  paste into Claude Code (Session B)

```text
You are the brain building the Agent-X KERNEL and MANDATE packages. You hold the architecture and integrate; dispatch subagents for bounded parallel work.

GOAL
Implement packages/kernel and packages/mandate for Phase 1, against the FROZEN packages/contracts, until the integration test's kernel-side passes.

REQUIRED READING
- docs/BLUEPRINT.md (canonical), docs/MANDATE.md, docs/SYSCALLS.md
- CLAUDE.md (your lane + the 8 invariants), BUILD-PLAN.md (your task graph + definitions-of-done)
- packages/contracts (the seam — depend on it; never change it without a stop-and-coordinate)

SCOPE — Phase 1 ONLY (BLUEPRINT §7)
- kernel: scheduler, heap+journal (MongoDB/Motor, event-sourced: append-only `journal` = source of truth; heap/threads/résumé = projections), verifier (rules + human rungs), GATEWAY policy (ring L0–L2 checks, idempotency keys, channel-rule hooks, adapter selection via the Adapter interface, credential-injection POINT — vault stub OK, journaling), supervision, the run-loop in BOTH live and sim modes (implements RunInvoker), and a typed command/query API over kernel projections (powers the dashboard now, the Operator Agent later — BLUEPRINT §6/§6.1).
- mandate: MandateType/Instance/Run models, the seven organs as data, and the FACULTIES FRAMEWORK — each faculty's `harness_adapter` enables the harness's *native* skills, re-points effectful tools to the gateway, and treats harness memory as per-run scratch only (BLUEPRINT §1, §4.5: "borrow the muscle, own the moat"). Build the MEMORY LAYER (Heap=semantic, Journal=episodic, Threads=relational, Résumé=performance — BLUEPRINT §1), HYDRATION (assemble + freeze the working set: relevant heap facts + open thread + recent journal + type-level skill_pack/domain-pack), and the SETTLEMENT engine (one atomic event-append → projections: facts→heap w/ provenance, thread advanced, trust→résumé, billing line, register watch, spawn). Phase-1 faculties: research, judgment, memory-craft, escalation.
- Do NOT implement adapters, the swarm, or any Phase 2–5 capability. Call adapters only through the Adapter interface; the syscall package is Codex's.

YOUR LANE / DON'T TOUCH
- Own: packages/kernel, packages/mandate. Read-only: packages/contracts. Never edit packages/syscall or packages/swarm.

CONSTRAINTS — the 8 invariants are inviolable. Especially:
- No fact enters the heap without passing verification + carrying provenance (enforce in the settlement engine — no bypass path).
- The live kernel is deterministic: no LLM call decides a ring, a commit, or a credential use. Faculties (LLM) propose; kernel code disposes.
- The run-loop must run identically in live and sim modes (sim swaps adapters; the loop does not branch on mode beyond adapter binding).

METHOD
- Test-driven: write the test (or use scaffolded fixtures) before each module. Use the test-driven-development skill.
- Dispatch subagents: faculty-builder for each of the four faculties (parallel), kernel-module-builder for independent kernel modules, test-writer for suites. You integrate and hold the seam.
- Use web/Anthropic docs as needed (Motor/MongoDB patterns, event-sourcing & projections, durable continuations) — verify, don't guess.
- Use verification-before-completion before claiming any component done: run the tests, show output.

DONE WHEN
- packages/kernel + packages/mandate import clean (mypy passes) and unit tests pass (`uv run pytest`).
- The kernel side of tests/integration passes: a lead-finder MandateRun hydrates, a faculty proposes a syscall, the gateway ring-checks and (at L1) PARKS for approval, approval resumes it, settlement commits atomically with provenance, and the run is invokable in sim mode via RunInvoker.
- You report which integration points await Codex's adapters/swarm, and confirm you changed nothing in contracts (or, if you had to, that it was a logged stop-and-coordinate).
```

---

## PROMPT 2 — Build the Syscall + Swarm  ·  paste into Codex (Session B)

```text
You are building the Agent-X SYSCALL and SWARM packages. Hold the syscall/swarm architecture in the main thread; use worktrees and subagents for bounded parallel work (e.g., one adapter per worktree).

GOAL
Implement packages/syscall and packages/swarm for Phase 1, against the FROZEN packages/contracts, until the integration test's syscall+swarm side passes.

CONTEXT / REQUIRED READING
- docs/BLUEPRINT.md (canonical — esp. §3 syscall layer and §5 swarm), docs/SYSCALLS.md, docs/AGENT_X_SYSCALL_TOOL_LANDSCAPE_RESEARCH.md
- AGENTS.md (your lane + the 8 invariants + commands), BUILD-PLAN.md (your task graph + definitions-of-done)
- packages/contracts (the seam — implement the Adapter and Judge interfaces; never change contracts without a stop-and-coordinate with the kernel agent)

SCOPE — Phase 1 ONLY
- syscall: the Adapter framework + capability registry + fulfillment-ladder resolution (with the HumanTaskAdapter as the tail of EVERY ladder), health checks, and fixtures. Phase-1 adapters: lead_research_batch (Exa/Firecrawl — confirm current APIs via web), read_url, draft_email (draft mode only — no send), queue_manual_action (the manual-projection queue), mark_outcome. Wrap any MCP server BEHIND the gateway's Adapter interface — never expose raw MCP to the harness.
- swarm: the Swarm REPL — scenario packs (JSON/Mongo docs; 10–30 synthetic lead/company cases), the SimAdapter (simulated counterparties + sandboxed syscalls; bind in sim mode), the promptfoo bridge as the Judge (run promptfoo as a SUBPROCESS; wire the kernel's RunInvoker as a promptfoo custom provider for grading + regression gate + scoreboard), trace data for a viewer, and the PromotionGate (synthetic cases BARRED from real promotion).
- Do NOT implement money/WhatsApp/voice/browser adapters, the compiler, or any Phase 2–5 capability. Money is never an LLM/browser path.

YOUR LANE / DON'T TOUCH
- Own: packages/syscall, packages/swarm. Read-only: packages/contracts. Never edit packages/kernel or packages/mandate.

CONSTRAINTS — the 8 invariants are inviolable. Especially:
- A syscall is intent; fulfillment is swappable; the human-task queue is always the bottom rung (nothing is ever "unimplemented").
- The pod/faculty holds NO credentials — credentials are injected by the kernel gateway, not the adapter caller.
- No synthetic (swarm) case may promote a customer-facing version — only reality does. Enforce in PromotionGate.
- Adapters are actuators, not brains: no adapter runs its own autonomous agent loop that makes decisions outside the kernel.

SETUP / TEST / DONE (lead with commands, per AGENTS.md)
- setup: `uv sync`; test: `uv run pytest`; lint: `uv run ruff check`; promptfoo runs as a subprocess (`npx promptfoo ...`).
- Use the four-part discipline per task: Goal, Context, Constraints, Done-when. Reasoning level: High for the swarm/promptfoo wiring, Medium for adapters.
- Write tests and run them; review your own diff against the invariants before claiming done.

DONE WHEN
- packages/syscall + packages/swarm import clean (mypy passes) and unit tests pass (`uv run pytest`); every adapter has fixtures and a passing health check; the HumanTaskAdapter resolves as the tail of the ladder.
- The syscall+swarm side of tests/integration passes: the gateway can select and call a Phase-1 adapter; a candidate lead-finder mandate runs in the SimAdapter world via the kernel's RunInvoker; promptfoo grades the trace and the PromotionGate blocks synthetic-only promotion.
- You confirm contracts is unchanged (or log any stop-and-coordinate), and report the integration points that join the kernel agent's work.
```

---

## 6. Appendix — guardrails to keep both agents honest

**Definition of done (every component, both agents):** builds · unit tests pass with shown output · respects all 8 invariants · changed nothing in `contracts` unilaterally · no Phase 2–5 code · verified by running, not asserted.

**The invariants, restated as build rules (from BLUEPRINT §4):**
1. No fact without a commit (settlement has no bypass).
2. No credential in user space (package boundary forbids it).
3. No raw fact crosses customers (heap is per-instance; only gym/domain-pack patterns cross — not in Phase 1).
4. No brain in the live kernel (LLM proposes, code disposes). The Operator Agent (BLUEPRINT §6.1) operates the kernel from *outside* as a gated user — never from within.
5. A syscall is intent; human-task is the bottom rung.
6. Money is API-only, idempotent, never LLM/browser (not in Phase 1 — but the gateway must reserve the high-ring + human-gate path).
7. No synthetic case promotes a customer-facing version (PromotionGate enforces).
8. The business is the sender of record (channel identity per-instance — relevant Phase 5; don't design it away now).

**If an agent wants to change `contracts`:** stop. It's a coordination event. Edit `contracts`, both agents re-pull, then resume. The seam is sacred — it's the only reason two agents can build one system in parallel.

**Sources for the setup conventions:** [Claude Code subagents](https://code.claude.com/docs/en/sub-agents) · [OpenAI Codex best practices](https://developers.openai.com/codex/learn/best-practices) · [AGENTS.md conventions](https://agentsmd.net/)
```
