# Operator Studio — Product Design

*Date: 2026-06-20. The last GUI phase. The Agent-X backend (Phases 1–6) is COMPLETE and gate-green on
`main`: real gated email send, Step-D feedback, Creator draft, ring-aware promote, swarm compiler.
This document designs the **interface a founder actually enjoys driving** — and commits to one polished
end-to-end vertical slice to build this session.*

> **Hard frame (no-gos, verbatim from the session):** No `packages`/contracts changes; no kernel/backend
> logic edits; lane fence stays 3/3. UI over **existing routes only** — no new backend capabilities.
> Don't break existing views (Studio is **additive**). Live-mode fail-closed + bearer-token posture stay
> intact. No component-library swap; no second design language; no light-mode SaaS reskin.

---

## 0. Thesis — two seats, one machine

Agent-X is **the operating system for running a business**. The UI should feel like a precision control
room watching live machinery — an oscilloscope / trading terminal / kernel `dmesg`, **not** a CRM.

Today the dashboard is a **god-view**: a nav rail of eight surfaces (Floor · Approvals · Catalog ·
Instance · Run · Capabilities · Ledger · Foundry) where a power user watches everything at once. That
is the right tool for *operating* the machine. It is the wrong tool for a founder who just wants to
**use it and earn** — to point at a business, find leads, and send real outreach.

So we add a **second seat**: the **Studio** — a guided, step-based throughline (inspiration: Zapier AI's
guided flow) that drives one mandate from ignition to a real send. Same engine, same data, same palette;
a different *posture*. The god-view is mission control. The Studio is the **driver's console**.

```
              ┌──────────────────────── one engine ────────────────────────┐
   STUDIO  ◀──┤  loadDashboardData · useJournalStream (SSE) · postCommand   ├──▶  OPERATOR
 (drive)      │  toasts · operator token · API base URL · live-mode guard   │     (god-view)
              └─────────────────────────────────────────────────────────────┘
```

### The aesthetic spine — "signal down a wire"

The operator god-view is *many panels watching at once*. The Studio is *one signal advancing down a
track*. The Studio's defining motif is a horizontal **drive track**: five stage-nodes joined by a
connector, with a phosphor **scan pulse** that travels the wire as the run advances. Each stage is a
focused **console card** with its own character — never a reskinned table.

We **honor and sharpen** the existing identity (`dashboard/app/globals.css`), we do not invent a new one:

| Token | Commitment |
|---|---|
| **Color** | Dominant `--green` (#b6ff63) on near-black `--bg` (#0b0d0b). Sharp `--cyan` for evidence/links, `--amber` for gated/staged, `--red` for danger. Dominant + sharp — never timid/even. No purple-on-white, no pastel SaaS. |
| **Type** | `--font-display` (Georgia serif) for headings + big numerals; `--font-mono` (IBM Plex Mono) for **all** data, journal events, traces, receipts, evidence (it's a ledger). **Never** Inter/Roboto/Arial/system-ui. |
| **Motion** | One orchestrated entrance per stage (staggered `floor-in` via `--i`). The live SSE run feels *alive* (events stream in). Reuse `scan` / `approval-breathe`. Respect the `prefers-reduced-motion` block already in `globals.css`. |
| **Atmosphere** | Reuse `.atmosphere` + the body oscilloscope grid; sharpen with a faint per-stage grid + scan-line, especially the Kernel Inspector. Depth, not flat fills. |

All new CSS lives under a `.studio-*` namespace appended to `globals.css`, reusing the existing CSS
variables, keyframes, and breakpoints. Zero new fonts, zero new color systems, zero new dependencies.

---

## 1. Studio vs. Operator — default landing & coexistence

**Decision (signed off): Studio is the default landing; a persistent top-bar toggle flips the whole
shell to the Operator god-view.** The mode is stored in `localStorage` (`agentx.shellMode`), like the
operator token. The two seats share one data layer; switching never reloads or refetches from scratch.

```
┌──────────────────────────────────────────────────────────────┐
│ Agent-X      [ STUDIO ◀▶ OPERATOR ]    ● live   12:04:33   ⟳   │   ← top bar (both modes)
├──────────────────────────────────────────────────────────────┤
│  ① Pick ──── ② Find ──── ③ Leads ──── ④ Draft ──── ⑤ Send     │   ← drive track (Studio only)
│                                                                │
│   ┌── active console card ───────────────────────────────┐    │
│   │  …the current stage…                                  │    │
│   └───────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
        toggle → the existing nav-rail god-view, unchanged
```

- **Studio mode** renders the new `StudioView` (drive track + active console card).
- **Operator mode** renders the **existing** `OperatorDashboard` content verbatim — the nav rail and all
  eight views are untouched. Studio is strictly additive; nothing existing is removed or restyled.
- The toggle is the *only* always-present chrome that differs. The clock, health pill, SSE status,
  source badge, refresh, and the bottom ledger are shared.

**Implementation shape:** `OperatorDashboard` already owns every piece of shared state (data, sources,
`postCommand`, `refresh`, `selectInstance`, `selectRun`, toasts, SSE, token, base URL). We add a `mode`
state and, when `mode === "studio"`, render `<StudioView … />` fed by those same props. No data plumbing
is duplicated; the Studio is a *consumer* of the existing engine.

---

## 2. The spine — Drive-a-mandate → SEND  *(this session's slice)*

The Studio's first and headline track. Five stages, each mapped to the exact route it rides. **This is
the vertical slice we build and prove this session.**

```
 ① PICK ───────▶ ② FIND ───────▶ ③ LEADS ───────▶ ④ DRAFT ───────▶ ⑤ SEND ───▶ Business File
 instantiate     trigger-run      /runs/{id}        /approvals       approve      /instances/{id}
 /instances      /events (SSE)    claimed_facts     drafted_effect   send(gated)
```

### ① PICK — ignition  *(reads `GET /instances`, `GET /mandate-types`; command `POST /commands/instantiate`)*
A "garage" of existing businesses (instance cards: name · ring · trust) plus **"spin up a new one"** — a
compact form (business name, mandate `type_ref`, ring, optional ICP/location/count target override). This
reuses the proven `catalog-create` logic via a typed `instantiate()` client helper. Selecting an existing
business or creating one **arms** the track and advances to ②. Character: an ignition panel — the chosen
business shown as a "key in the ignition" mono readout (`> Acme Dental · lead-finder@0.1.0 · L1`).

### ② FIND — the live run  *(command `POST /commands/trigger-run`; reads `GET /events` SSE + `GET /runs/{id}`)*
One button: **Find leads**. It POSTs `trigger-run` (`mode: "sim"` by default; live when chosen), then the
console becomes an **oscilloscope**: journal events for this instance stream in via the existing
`useJournalStream` SSE hook, rendered in mono like `dmesg` — `RunCreated → RunHydrated →
SyscallAttempted(lead_research_batch) → RunVerified → RunSettled` (or `RunParked`). A run-state chip
pulses "live"; a scan-line sweeps the trace. We poll `/runs/{id}` for the structured tail. This is the
"feels alive" moment — the one place motion is the point. When the run reaches a terminal/parked state the
track advances to ③.

### ③ LEADS — scored leads + cited evidence  *(reads `GET /runs/{id}` → `claimed_facts`, and `GET /instances/{id}` → facts)*
The settled run's `claimed_facts` (kernel `Fact`s) become **lead cards**: subject = the lead, a **score
dial** (from `object`/`confidence`), and the **cited evidence** — `provenance.evidence[]` URLs + the
`syscall_trace:` line + `provenance.note`, all in mono with cyan link styling. This is invariant #1 — *no
fact without a commit* — made visible: every score carries its receipt. Character: a "lab bench" of
qualified leads, each a small instrument readout. Advance to ④.

### ④ DRAFT — review the outreach  *(reads `GET /approvals` → `drafted_effect`)*
The parked approval card's `drafted_effect` (`{syscall: send_email|draft_email, args:{to, subject, body},
idempotency_key}`) rendered as an **email compose console** — the outreach exactly as it will go, with a
blinking phosphor cursor at the end of the body. A **gated-effect strip** shows the required ring + the
idempotency key (mono receipt). Crucially, a **send-posture banner** (derived from `GET /capabilities`)
tells the operator *before they act* what ⑤ will do:
- **LIVE** (green): `send_email` adapter present → a real email will be sent (Resend transport).
- **STAGED** (amber): no transport → fail-closed to the **manual-queue / human-task tail** (invariant #5).

Design for **both** states, always. Advance to ⑤.

### ⑤ SEND — the gated trigger  *(command `POST /commands/approve`; reads `GET /runs/{id}`, `GET /manual-queue`)*
A deliberate, weighty **Approve & send** action (bearer-authed; disabled without an operator token). On
approve, the kernel resumes the run and the `send_email` syscall executes — **real** (Resend, if
configured) or **staged** to the manual queue. The console then resolves to a **receipt stamp** (mono,
scan-swept): either `sent · message_id=…` (live) or `staged · manual-queue · the human tail will send`
(fail-closed). A CTA lands the driver in the **Business File** (§3) to "see it land."

### Graceful reality
The spine reflects *actual* projections, never a scripted happy path. If a run settles without parking
(nothing to approve), ③ shows leads and ④/⑤ show "already sent / nothing to approve." If it parks before
settling facts, ③ shows "research in progress." The stages render whatever the real reads return — that
honesty is the product.

### API glue to TDD this session (dashboard `tests/`, injected-`fetcher` pattern)
All pure/mapping logic, tested exactly like the existing `api-client.test.ts`:
1. `instantiate(payload, {token, fetcher})` → maps the `/commands/instantiate` envelope → `{supported, instanceId, message}`.
2. `triggerRun(payload, {token, fetcher})` → maps the `/commands/trigger-run` envelope → `{supported, workId, status}`.
3. `mapScoredLeads(runDetail)` → `claimed_facts[]` → `ScoredLead[] {lead, score, confidence, evidence[], note}`.
4. `deriveSendPosture(capabilities)` → `"live" | "staged"` (presence of a `send_email` adapter).
5. `approveRun(payload, {token, fetcher})` → maps the `/commands/approve` envelope → `{supported, status, workId}`.

These are added to `dashboard/src/lib/api.ts` + `dashboard/src/lib/types.ts` (view models only — the seam
stays frozen). The Studio components consume them; the existing `catalog-create`/`instance-file` inline
fetches are left intact (no regression risk).

---

## 3. Business File — the per-business cockpit  *(reads `GET /instances/{id}`)*
Already largely built as `instance-file.tsx` (runs · facts/leads · drafts · P&L · ring controls · trust ·
ring history · threads). The Studio's ⑤ lands here, and Studio's PICK stage links into it. **This session
we reuse it as-is** as the spine's terminus (rendered inside the Studio shell or reached via the toggle).
A later polish pass can give it the Studio's console character, but no new work is required for the slice.
Routes: `GET /instances/{id}`; commands `set-ring`, `trigger-run` (already wired).

---

## 4. Creator track — the mandate that makes mandates  *(Phase 2; design only)*
A second Studio track, mirroring the drive spine but building a **new business type** rather than running
one. Stages: **describe a job** → **draft a candidate** (`POST /commands/trigger-run` against the Creator
instance) → review the drafted `MandateType` in `/approvals` (`drafted_effect` = `draft_candidate_type`) →
**run-swarm** (`POST /commands/run-swarm`) → the BLUEPRINT §5 timeline (reuse `swarm-timeline.tsx`) →
**promote to L0 canary** (`POST /commands/promote`, ring-aware: L0/L1 canary accepts synthetic; L2+
real-gated). Reads `GET /eval-cases`, `GET /approvals`. Guardrail surfaced in the UI: the Creator emits
**candidates only** — the swarm pass + human promote is the bridge to live (invariants #4/#7). The
"Promote to L2" control is visibly real-gated. ≤ 1 session.

---

## 5. Foundry / Gym — the wind tunnel  *(Phase 3; design only)*
Deepen the existing `foundry-view.tsx` Swarm REPL: the **eval-case grid** gains a drill-down (click a
persisted case → its stored scorecard criteria + judge comments + §5 trace), and visibly separates
**synthetic** (origin=synthetic, `promotion=blocked`) from **real** (origin=real, `promotion=eligible`)
evidence. The **compiler proposal** surfaces as a read panel (the swarm compiler's proposed patch +
before/after rubric), and **promote-to-L2** wires `POST /commands/promote` with the real-gated posture
made explicit. Reads `GET /eval-cases`, `GET /capabilities`; command `run-swarm`, `promote`. ≤ 1 session.

---

## 6. Kernel Inspector — the machine, read-only  *(Phase 4; design only)*
A pure read surface off `GET /events` (SSE) + `GET /system/overview`, rendered as **machinery**, not a
table. The run-loop stages as a pipeline diagram (hydrate → reason → syscall → verify → settle) with live
syscalls streaming through it; the **journal as a WAL/ledger** ticker (the append-only truth); ring mix +
gateway health as instrument gauges; a faint oscilloscope grid + scan-line behind it all (the most
`dmesg`/`htop`/CRT surface in the product). Strictly read-only — it watches, it never commands. Reuses
`useJournalStream`. ≤ 1 session.

---

## 7. Phased plan (each ≤ 1 session)

| Phase | Deliverable | Routes | Build this session? |
|---|---|---|---|
| **P1 — Studio spine** | Studio shell + mode toggle + drive→send loop end-to-end (① PICK → ⑤ SEND → Business File), with the 5 TDD'd API-glue helpers. | instantiate · trigger-run · /events · /runs/{id} · /approvals · approve · /capabilities · /instances/{id} | **YES — the slice** |
| **P2 — Creator track** | Guided "build a mandate" track: describe → draft → run-swarm → §5 timeline → promote-to-L0. | trigger-run · /approvals · run-swarm · promote · /eval-cases | No (design only) |
| **P3 — Foundry/gym** | Eval drill-down (synthetic vs real), compiler-proposal panel, promote-to-L2 real-gated. | /eval-cases · run-swarm · promote · /capabilities | No (design only) |
| **P4 — Kernel Inspector** | Read-only run-loop-as-machinery + journal WAL, off SSE + overview. | /events · /system/overview | No (design only) |

### This session's slice — definition of done
- Studio is the default landing; the **STUDIO ◀▶ OPERATOR** toggle flips to the unchanged god-view (persisted).
- The full drive→send loop works against the live API end-to-end: instantiate → Find leads → live SSE run
  → scored leads + cited evidence → review draft → **Approve & send** → receipt → Business File.
- The send stage handles **both** live (Resend) and **staged** (manual-queue fail-closed) — the staged
  path is proven live this session (no mail creds); the live path is documented.
- 5 API-glue helpers TDD'd (red→green) in `dashboard/tests/`; existing tests stay green.
- The full gate is green before every push to `main`; existing views are not regressed; the design language
  is the existing one, sharpened — no second language, no SaaS reskin.

### Honest send-path note (carried to the proof doc)
The live email transport that is actually wired is **Resend** (`RUN_LIVE_EMAIL=1` + `RESEND_API_KEY` →
`build_configured_email_transport`). The prompt's "Gmail SMTP / `SMTP_*`/`EMAIL_*`" keys are *recognized
but not yet wrapped* in `packages/syscall/src/agentx_syscall/email_transports.py`. The Studio UI is
transport-agnostic: it shows LIVE vs STAGED from capability presence, and the staged fail-closed path is
the default, fully-functional demo.

---

## Out of scope (this session)
Creator/Foundry/Inspector code (P2–P4 are design only); any backend/contract change; new fonts, colors,
or a component library; light mode; real external email send; multi-user auth (bearer token stays the
Phase-1 trust boundary).
