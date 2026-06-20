# Agent-X Control Surface — UI Overhaul Design Spec (2026-06-21)

> **What this is.** The design for rebuilding the Agent-X dashboard into a powerful, calm control
> surface a developer/founder can use to *see and drive* every Agent-X subsystem (mandates,
> instances, runs, approvals, gym, swarm, kernel, economy) — with the look/feel of the Hermes agent
> dashboard, evolved on our existing Next.js app. This doc doubles as the **Hermes Kanban USER-card
> prompt** (§11) and the **suggested child-card decomposition** (§10) the orchestrator will create.
>
> **Companions:** [BLUEPRINT.md](../../BLUEPRINT.md) · [MANDATE.md](../../MANDATE.md) ·
> [README.md](../../README.md) · [STATE_AND_ROADMAP.md](../../STATE_AND_ROADMAP.md) ·
> [WORKFLOW.md](../../WORKFLOW.md) (the Kanban operating contract).

---

## 1. Problem & goal

The current dashboard (`dashboard/`, a single 683-line `OperatorDashboard` on Next.js 15 / React 19,
no design system, custom CSS, a Studio/Operator toggle) is hard to use: confusing IA, no loading
feedback ("hit a button, nothing happens"), and it doesn't let you *see what a mandate instance is
actually doing* in depth. Meanwhile Agent-X is a powerful Business OS — mandates, instances, runs,
gym/evals, swarm, kernel — that deserves a control surface as good as the [Hermes agent
dashboard](https://github.com/NousResearch/hermes-agent/tree/main/web/src).

**Goal:** a beautiful, intuitive, powerful control surface where a dev can observe and operate every
subsystem without overload — with a first-class **per-instance deep Inspector** ("what is this
mandate doing, what does it remember, what has it done") as the centerpiece, and the approval gate
(BLUEPRINT kill-condition #2) treated as a primary surface.

**Non-goals (this overhaul):** new kernel/mandate semantics; contract changes; multi-tenant auth;
mobile-first. We surface what exists (and add *read* APIs where a view needs data the backend
doesn't expose yet), nothing more.

## 2. Decisions (resolved with the founder)

| # | Decision | Choice |
|---|---|---|
| 1 | Frontend approach | **Evolve the Next.js app** + introduce a **Hermes-derived design system**. Keep our working `lib/api.ts`, `lib/events.ts` (SSE), `lib/types.ts`, tests, and the Studio drive→send flow; rebuild the shell + views on a real design system. |
| 2 | What we deliver | **This spec + the decomposed Kanban cards** (Hermes builds it via the orchestrator + coder subagents). |
| 3 | Backend gaps | **Build the missing read-APIs alongside** — each feature slice pairs a `codex` backend card (READ endpoints only) with a `claude` frontend card. |
| 4 | Information architecture | **Mission Control + entities**: a live ops "home" + an entity rail + the deep Inspector. (Borrows Hermes's *visual* language, not its 4-bucket nav.) |

## 3. Design language (Hermes-derived)

Port Hermes's tokens into a small theme system (CSS custom properties; dark by default). Concrete
starting palette (from Hermes `web/src/index.css`), adapt as needed:

```
--background-base : #041c1c   /* deep teal canvas */
--surface/card    : cream 4–6% over background
--accent          : cream 10% over background  (warm #ffe6cb family)
--foreground      : #ffffff ; --muted-foreground : dimmed
--success #4ade80 · --warning #ffbd38 · --destructive #fb2c36
--radius 0.5rem (sm −4px / lg +4px) ; spacing via a multiplier scale
font sans: system-ui stack ; font mono: ui-monospace / JetBrains Mono (terminal + JSON + trace)
```

Aesthetic: **dark, sophisticated, terminal-adjacent, analytical** — warm cream on deep teal, high
contrast, monospace for traces/JSON/IDs, calm (no neon, no motion thrash). Theme tokens live in one
place so the whole app re-themes from variables.

## 4. Foundation (the base every other card depends on)

A single foundation slice that everything else builds on. **Keep** `lib/api.ts`, `lib/events.ts`,
`lib/types.ts` (rich, tested — preserve & extend). **Add:**

- **Theme + tokens** (`app/globals.css` rewrite to the §3 token system) + a `ThemeProvider`/context.
- **Contexts/providers:** API base URL, operator token (localStorage), live-data (SSE-backed) + a
  small query/cache layer (or lightweight SWR-style hooks over `fetchJson`).
- **Primitive kit** (`src/components/ui/`): `AsyncButton` (built-in spinner, disabled-while-pending,
  success/error **toast** — fixes "no loader"), `Card`, `Table`/`DataGrid`, `Tabs`, `Badge`/
  `StatusPill` (ring/run-state/health), `Drawer`, `Modal`, `Toast`/`ToastStack`, `Skeleton`,
  `EmptyState`, `ErrorState`, `JsonViewer`/`CodeBlock` (mono), `Timeline`, `Sparkline`/stat tiles.
- **App shell:** left nav rail + top bar (env/live-mode/token/health/refresh) + content; the
  Mission Control home (§5).
- **Routing:** Next.js App Router routes per section (deep-linkable, shareable URLs).
- **Global states:** every list has loading-skeleton / empty / error; every command is an
  `AsyncButton` with toast feedback; SSE updates are calm (no layout thrash).

**Done-when:** shell + theme + primitives render; `npm test` + `npm run build` green; a demo page
shows every primitive incl. an `AsyncButton` that spins+toasts; no view yet (views are later cards).

## 5. Information architecture — Mission Control + entities

**Left rail (primary):** Home · Instances · Blueprints · Runs · Approvals · Gym · Foundry
**Left rail (System group, collapsible):** Providers · Kernel · Economy · Docs

```
┌────────────┬───────────────────────────────────────────────┐
│ ◆ Agent-X  │  MISSION CONTROL                                │
│            │  ┌────────┬─────────┬──────────┬─────────────┐  │
│ ▸ Home  ◀  │  │ 3 runs │ 2 await │ ₹4,820   │ ● kernel    │  │
│ ▸ Instances│  │ active │ approval│ P&L today│ ● providers │  │
│ ▸ Blueprint│  └────────┴─────────┴──────────┴─────────────┘  │
│ ▸ Runs     │  Needs you ▸ approve "Nova outreach" (inst_nova)│
│ ▸ Approvals│  Live ▌ inst_acme · send_email · settled        │
│ ▸ Gym      │  Recent settles · trust deltas · last commit    │
│ ▸ Foundry  │                                                 │
│ ─ System ─ │                                                 │
│ ▸ Providers│  (click an instance anywhere → deep Inspector)  │
│ ▸ Kernel   │                                                 │
│ ▸ Economy  │                                                 │
│ ▸ Docs     │                                                 │
└────────────┴───────────────────────────────────────────────┘
```

**Mission Control (Home):** the founder's exception-review board — stat tiles (active runs, pending
approvals, P&L, settles, health), a "Needs you" queue (parked approvals), a live event ribbon (SSE
`/events`), recent settles + trust deltas. Everything links into a detail view.

**Route map & API per section** (✱ = needs a new READ API, see §8):

| Section | Route | Purpose | API (existing unless ✱) |
|---|---|---|---|
| Home | `/` | Mission Control board | `/system/overview`, `/approvals`, `/events`, `/runs` |
| Instances | `/instances`, `/instances/{id}` | list + **deep Inspector** (§6) | `/instances`, `/instances/{id}`, `/runs?instance_id`, `/approvals?instance_id`, `/events`, ✱heap |
| Blueprints | `/blueprints`, `/blueprints/{ref}` | mandate **Types**: 7 organs, faculties, versions, instantiate | `/mandate-types`, `/commands/instantiate` |
| Runs | `/runs`, `/runs/{id}` | runs across instances; trace timeline, claimed facts, settlement | `/runs`, `/runs/{id}` |
| Approvals | `/approvals` | L0/L1 inbox: approve / reject / edit (diff) | `/approvals`, `/commands/{approve,reject,edit}` |
| Gym | `/gym` | eval cases (synthetic/real), scores, promote gate, compiler scaffold | `/eval-cases`, `/commands/promote`, ✱eval detail |
| Foundry | `/foundry` | swarm wind-tunnel: run → judge → gate timeline | `/commands/run-swarm` |
| Providers | `/providers` | capabilities/connectors: adapters, Exa/Firecrawl, email transport, model routing + health/credential status | `/capabilities`, ✱health detail |
| Kernel | `/kernel` | journal stream, scheduler work, health, core-gaps | `/journal`, `/events`, `/scheduler-work/{id}`, `/system/*`, `/core-gaps`, ✱scheduler list |
| Economy | `/economy` | P&L per instance + business unit | ✱economy/P&L API |
| Docs | `/docs` | rendered BLUEPRINT/MANDATE/README + concept explainers | static |

## 6. The Instance Inspector (centerpiece)

`/instances/{id}` — the single most important screen ("what is this mandate doing, in depth"). Header:
name/customer · type_ref · ring + trust · channel binding · live run state · P&L summary. Tabs:

1. **Overview** — charter/target, ring/trust ladder, résumé (verified record), latest run, P&L.
2. **Live Activity** — the BLUEPRINT §5 trace "oscilloscope": Think / Call / Claim / park / send
   events streaming via SSE (`/events` filtered to the instance), with a per-run timeline.
3. **Memory / Heap** ✱ — the instance's facts: subject·predicate·object, confidence, provenance
   (run_id + evidence), status (probation/verified). Needs a heap-browse READ API (§8).
4. **Actions / Syscalls** — journaled `SyscallAttempted`/`SyscallSettled` (what effects it took),
   from `/journal?instance_id=`.
5. **Runs** — list → drill into Run detail (§5 Runs).
6. **Approvals** — this instance's parked cards (approve/reject/edit inline).
7. **Trust & Ring** — ring history, trust points, `set-ring` control (AsyncButton + confirm).

## 7. Per-section UX notes (anti-overload)

- **Progressive disclosure:** list → detail → deep tabs. Never show everything at once.
- **One primary action per screen** (e.g., Instances list → "Instantiate"; Approvals → "Approve").
- **Live but calm:** SSE drives incremental updates + a subtle "updated" pulse; never re-layout.
- **Consistent status vocabulary:** `StatusPill` for ring (L0–L4), run-state (running/parked/
  settled/crashed), health (ok/degraded/down), eval origin (synthetic/real).
- **Graceful disable:** any control whose backend API isn't live yet renders disabled with a
  "coming soon / not yet wired" tooltip (never a fake success). Driven off `/capabilities` +
  feature flags.
- **Keyboard + deep links:** every entity has a stable URL; lists are keyboard-navigable.

## 8. Backend gaps to fill (codex READ-only cards)

Contracts FROZEN; these add **read** endpoints (and projections) only — no contract edits.

| Gap | Proposed endpoint | Source | Consumer |
|---|---|---|---|
| Heap / memory browse by instance | `GET /instances/{id}/memory` (facts + provenance + status) | projection store `fact` docs | Inspector → Memory tab |
| Economy / P&L | `GET /economy?instance_id=` + `GET /economy/units` | aggregate `RunSettled` billing_amount/trust_delta | Economy view, Home P&L tile |
| Scheduler work list | `GET /scheduler-work?status=` | scheduler store | Kernel view |
| Capability health detail | extend `GET /capabilities` (provider reachability, transport configured, model routing) | runtime health checks | Providers view |
| Eval-case detail (if `/eval-cases` is summary-only) | `GET /eval-cases/{id}` | projection store `eval_case` | Gym view |

Each backend card: define the response shape, add the route + a state.py reader, **gate-green**
(ruff · mypy --strict · pytest), and a test per endpoint. The matching frontend card consumes it and
**gracefully disables** until it's live.

## 9. Interaction & quality bar

- Every command button: `AsyncButton` (spinner + disabled + success/error toast). No silent clicks.
- Every data view: skeleton while loading · `EmptyState` when empty · `ErrorState` (with retry) on
  failure. Never a blank screen.
- Optimistic where safe; otherwise pending → confirmed via SSE invalidation
  (`invalidationsForJournalEvent`).
- Accessibility: focus states, `aria-live` on toasts, keyboard nav.
- Dark theme by default; tokens centralised; mono for IDs/JSON/traces.

## 10. Decomposition → suggested child cards (the Kanban breakdown)

The orchestrator creates these CHILD cards under the USER card (do not hand-create — per WORKFLOW.md
§10). Profiles per WORKFLOW.md §4: `agentx-claude-coder` (TSX/React), `agentx-codex-coder` (Python
API). Each child works on `wt/<task-id>`, commits to its branch, marks done; the founder/reviewer
merges. **Every card's done-when includes the gate** (claude: `npm test` + `npm run build`; codex:
`ruff` · `mypy --strict` · `pytest`) and the **graceful-disable** rule.

| # | Card (CHILD) | Profile | Depends on | Scope / done-when |
|---|---|---|---|---|
| C1 | `CODER: Foundation — design system + shell + theming + primitives` | claude | — | §3,§4. Tokens, ThemeProvider, contexts, primitive kit incl. AsyncButton/Toast/Skeleton/Empty/Error/StatusPill/JsonViewer/Timeline, app shell + routing, Mission Control home (§5). Demo page renders all primitives. **Blocks all others.** |
| C2 | `CODER: Instances list + Instance Inspector (Overview/Activity/Runs/Approvals/Trust)` | claude | C1 | §6 tabs minus Memory/Actions. Uses `/instances*`,`/runs`,`/approvals`,`/events`. |
| C3 | `CODER: Heap/memory read API` | codex | C1 | §8 `GET /instances/{id}/memory`; tests; gate-green. |
| C4 | `CODER: Inspector Memory + Actions tabs` | claude | C2, C3 | Memory tab (uses C3) + Actions tab (`/journal?instance_id=`). |
| C5 | `CODER: Blueprints (mandate types) — organs, faculties, versions, instantiate` | claude | C1 | `/mandate-types`, `/commands/instantiate` (with `sender_identity`). |
| C6 | `CODER: Runs & Trace viewer` | claude | C1 | `/runs`,`/runs/{id}`: §5 timeline, claimed facts, settlement. |
| C7 | `CODER: Approvals inbox (approve/reject/edit + diff)` | claude | C1 | `/approvals`,`/commands/{approve,reject,edit}`; first-class gate UX. |
| C8 | `CODER: Gym & Evals (cases, scores, promote gate)` | claude | C1 | `/eval-cases`,`/commands/promote`; origin synthetic/real; compiler scaffold status. |
| C9 | `CODER: eval-case detail API (if needed)` | codex | C1 | §8 `GET /eval-cases/{id}` if list is summary-only. |
| C10 | `CODER: Foundry / Swarm wind-tunnel (run→judge→gate)` | claude | C1 | `/commands/run-swarm`; §5 timeline + gate decision. |
| C11 | `CODER: Capability health detail API` | codex | C1 | §8 extend `/capabilities` (reachability, transport, routing). |
| C12 | `CODER: Providers / Connectors view` | claude | C1, C11 | adapters, Exa/Firecrawl, email transport, model routing + health/credential pills. |
| C13 | `CODER: Scheduler-work list API` | codex | C1 | §8 `GET /scheduler-work?status=`. |
| C14 | `CODER: Kernel / System view` | claude | C1, C13 | journal stream, scheduler, health, core-gaps. |
| C15 | `CODER: Economy / P&L API` | codex | C1 | §8 `GET /economy*` from settlement billing; tests. |
| C16 | `CODER: Economy / P&L view` | claude | C1, C15 | per-instance + business-unit P&L; Home P&L tile. |
| C17 | `CODER: Docs view (render markdown + concept explainers)` | claude | C1 | render BLUEPRINT/MANDATE/README. |
| C18 | `STATUS: regenerate AGENTX_STATUS_<DATE>.html after UI overhaul` | status | all | per WORKFLOW.md §7. |

**Build order:** C1 → (C2, C5, C6, C7, C8, C10, C17 in parallel) → C3→C4, C11→C12, C13→C14, C15→C16
→ C18. Coder cards may share the new design system; the first integrator resolves any
`globals.css`/route-table merge collisions (union), as in prior multi-card sessions.

## 11. The Hermes Kanban USER-card prompt (paste into `hermes kanban create --triage`)

```
TASK: Rebuild the Agent-X dashboard into a powerful, calm control surface (Hermes-style)

WHAT: Evolve the Next.js dashboard (dashboard/) into a beautiful, intuitive control surface a dev
can use to SEE and DRIVE every Agent-X subsystem — mandates, instances, runs, approvals, gym,
swarm, kernel, economy — without overload. Adopt the Hermes agent dashboard's visual design
language (deep-teal canvas + warm cream accents, dark, terminal-adjacent, mono for traces/JSON;
see github.com/NousResearch/hermes-agent/web/src). Centerpiece: a per-instance deep INSPECTOR
(live trace, memory/heap, actions, runs, trust). Treat the L0/L1 approval gate as a first-class
surface. Fix the current pain: confusing IA and NO loading feedback on actions.

IA: "Mission Control + entities" — a live ops home (active runs, pending approvals, P&L, health,
event stream) + a left entity rail (Instances, Blueprints, Runs, Approvals, Gym, Foundry) + a
System group (Providers, Kernel, Economy, Docs). Full design + route map + per-view API mapping +
the suggested child-card decomposition are in:
  docs/superpowers/specs/2026-06-21-agentx-ui-overhaul-design.md   (READ THIS FIRST)

HOW: Keep our working lib/api.ts, lib/events.ts (SSE), lib/types.ts, tests, and the Studio
drive→send flow; rebuild the shell + views on a real design system. Where a view needs data the
backend doesn't expose, add a READ-only API as a paired codex card (per the spec §8) — never fake
data; gracefully disable un-wired controls.

DECOMPOSE per the spec §10 (C1 Foundation blocks all; then feature slices; codex cards for the
read-API gaps; a STATUS card at the end). Route TSX/React work to agentx-claude-coder and Python
API work to agentx-codex-coder.

NON-NEGOTIABLE: packages/contracts is FROZEN (backend cards add READ endpoints only — emit
"BLOCKED: contract change needed" if you think otherwise). Lane fence 3/3 must stay green. Every
card is gate-green before done (claude: npm test + npm run build; codex: ruff + mypy --strict +
pytest). Children commit to wt/<task-id> branches; do not push to main directly.
```

## 12. Invariants & no-gos

- `packages/contracts` **FROZEN**; backend cards add **READ** endpoints only. Contract change ⇒
  `BLOCKED: contract change needed` → orchestrator coordinates.
- **Lane fence 3/3** stays green (`lint-imports`); the API is the composition edge.
- **Gate-green before every card's done** (claude: `npm test` + `npm run build`; codex: `ruff` ·
  `mypy --strict` · `pytest`). Children branch on `wt/<task-id>`, never push to `main`.
- **No faked data / no silent success** — a control with no live backend renders disabled.
- Reuse the existing client/SSE/types layer; don't reimplement it.

## 13. Out of scope (deferred)

Demands/internal-market UI · multi-tenant auth/RBAC · mobile layout · Creator/Operator-Agent
conversational surfaces (G10/G11) · i18n · a literal port of Hermes source files (we adopt its
*design language + patterns*, re-implemented on our stack).
