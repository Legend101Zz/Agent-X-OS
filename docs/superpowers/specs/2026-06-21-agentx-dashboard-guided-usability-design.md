# Agent-X Dashboard — Guided Usability Layer + Endpoint Audit (Design Spec, 2026-06-21)

> **What this is.** An *additive* usability layer over the existing Agent-X control surface
> (the dashboard rebuilt by the 2026-06-21 UI overhaul) so a developer/founder can understand
> and operate it without prior knowledge: a guided "Create a Mandate" wizard, ⓘ info tooltips
> and "How this page works" help panels across the app, and a centralised glossary of concepts.
> Preceded by a full audit of every API endpoint the UI calls.
>
> **Companion:** [2026-06-21-agentx-ui-overhaul-design.md](2026-06-21-agentx-ui-overhaul-design.md)
> (the overhaul this builds on) · [BLUEPRINT.md](../../BLUEPRINT.md) · [MANDATE.md](../../MANDATE.md).

---

## 1. Problem & goal

The overhaul delivered a complete, good-looking control surface (Mission Control + entity rail +
deep Instance Inspector). But a first-time user — even the founder — finds it **hard to understand
how to use it**: what a "blueprint" vs an "instance" is, what a ring (L0–L4) or trust delta means,
how to actually create a mandate and drive it through approval. There is no onboarding, no inline
explanation of terms, and the create-flow (`InstantiateDrawer`) assumes you already know the model.

**Goal:** make the dashboard *self-explanatory and easy to operate* by adding (a) a step-by-step
guided wizard for the core create→run→approve loop, (b) always-available ⓘ tooltips and a
collapsible per-page help panel, and (c) a single glossary of concepts — taking visual/interaction
inspiration from the [Hermes agent dashboard](https://github.com/NousResearch/hermes-agent/tree/main/web/src)
(calm, analytical, terminal-adjacent), reusing our existing deep-teal/cream theme tokens.

**Non-goals (this slice):** changing any existing functionality, behaviour, props, or API calls;
new kernel/mandate/contract semantics; a full app-wide spotlight product tour; mobile layout;
auth/RBAC. This layer is purely additive and read-mostly.

## 2. Decisions (resolved with the founder)

| # | Decision | Choice |
|---|---|---|
| 1 | Guidance style | **Wizard + tooltips** — a guided "Create a Mandate" wizard for the core flow PLUS ⓘ info-tooltips and a "How this page works" panel across pages. (Not a full spotlight product tour.) |
| 2 | Scope priority | **Core loop first** — deep, polished guidance on Blueprints → Instantiate → Instance Inspector → Approvals; lighter tooltip/help pass on the rest. |
| 3 | Endpoint audit | **Full audit + fix** — enumerate every endpoint the dashboard calls, exercise each against the live API, document pass/fail, fix breakages. Runs **first**, before the UI work. |
| 4 | Existing functionality | **Untouched.** The plain "Instantiate" drawer stays; the wizard is an additional entry point that reuses the *same* submit code path. |
| 5 | Backend-side problems | If the audit finds a problem on the API side (`agentx_api`/packages), **flag it** in the audit report — do not edit it (that is Codex's lane per CLAUDE.md). Only frontend mapping issues are fixed here. |

## 3. Design language (reuse, don't reinvent)

Reuse the existing token system in `app/globals.css` and the `ui/` primitive kit. Mirror Hermes's
*calm, analytical* treatment: quiet ⓘ glyphs (never loud badges), monospace for IDs/JSON/traces,
terse high-signal copy, no motion thrash. New surfaces (tooltip popover, help panel, wizard) themed
entirely from existing CSS custom properties so the app re-themes from one place.

## 4. Phase 0 — Endpoint audit (runs first)

A throwaway script (`scripts/audit_dashboard_endpoints.*`, removed after) hits every endpoint the
dashboard calls against the live API (`NEXT_PUBLIC_API_BASE_URL` / `http://127.0.0.1:8000`) and
records HTTP status + a light response-shape sanity check. Read endpoints are GET-probed; commands
are checked for existence/shape only — **not fired destructively**.

**Endpoints in scope** (derived from `grep` of `src`/`app`):

- **Reads:** `/system/overview`, `/system/info`, `/health`, `/core-gaps`, `/runs`, `/runs/{id}`,
  `/instances`, `/instances/{id}`, `/instances/{id}/memory`, `/approvals`, `/journal`,
  `/capabilities`, `/economy`, `/economy/units`, `/scheduler-work`, `/scheduler-work/{id}`,
  `/eval-cases`, `/eval-cases/{id}`, `/mandate-types`, `/mandate-types/{ref}`, `/events` (SSE).
- **Commands (POST):** `/commands/{instantiate, approve, reject, edit, promote, run-swarm,
  set-ring, trigger-run}`.

**Deliverable:** a pass/fail table shared with the founder. Frontend mapping breakages are fixed in
this effort; backend-side breakages are flagged for Codex. **Done-when:** table produced; every
frontend-fixable failure resolved; `npm test` + `npm run build` + `tsc --noEmit` green.

## 5. Phase 1 — New design-system primitives (`src/components/ui/`)

Three new, independently-testable primitives plus a glossary module. Each has one clear purpose,
a well-defined props interface, and no dependency on app state beyond what's passed in.

| Unit | Purpose | Interface (sketch) | Depends on |
|---|---|---|---|
| `InfoTip` | The ⓘ icon + accessible popover explaining a term/field. | `<InfoTip term="ring" />` or `<InfoTip label="Ring" content={…} href?="/docs/blueprint" />` | glossary, theme tokens |
| `HelpPanel` | Collapsible "How this page works" strip under the `AppShell` title; remembers open/closed in localStorage. | `<HelpPanel id="blueprints" title? body={ReactNode} />` | localStorage, theme tokens |
| `Wizard` | Generic multi-step stepper (progress dots, Back/Next/Finish, per-step validation) rendered inside the existing `Modal`/`Drawer`. | `<Wizard steps={Step[]} onFinish={…} />`, `Step = { id, title, render, validate? }` | `Modal`/`Drawer`, `AsyncButton` |
| `lib/glossary.ts` | Single source of all explanatory copy: `term → { label, short, href? }`. | `glossary.ring`, `getTerm(id)` | — |

**Accessibility:** `InfoTip` uses `aria-describedby`, is reachable by keyboard (focus + Enter/Space),
dismissable with Escape, and works on hover, focus, and tap. Toasts/help already follow the
overhaul's a11y bar.

**Done-when:** all four exist with unit tests; rendered on the existing `/design-system` demo page;
gate green.

## 6. Phase 2 — "Create a Mandate" guided wizard (centerpiece)

A new **"New mandate (guided)"** `AsyncButton` on `/blueprints` (the existing plain "Instantiate"
control is unchanged and stays). It opens a 4-step `Wizard`:

1. **Pick blueprint** — what a blueprint / mandate-type is (the reusable "recipe"); choose from
   `/mandate-types`.
2. **Identity** — `sender_identity` and *why the business is the sender of record* (invariant #8);
   per-instance channel identity.
3. **Charter / target** — the instance's charter/target inputs the drawer already collects.
4. **Review & launch** — summary, then submit.

**Single code path:** the wizard's submit and the existing `InstantiateDrawer` submit are unified
into one shared helper (e.g. `lib/instantiate.ts` wrapping the current `/commands/instantiate`
call with `sender_identity`). The drawer is refactored to call the helper with **identical
behaviour** (verified by its existing tests); the wizard calls the same helper. On success the
wizard deep-links to `/instances/{id}` (the new instance's Inspector). Every field carries an
`InfoTip`.

**Done-when:** wizard creates an instance via the same endpoint as the drawer; drawer behaviour
unchanged (existing tests pass); new wizard-flow tests pass; gate green.

## 7. Phase 3 — Tooltips + help across pages

**Deep** (the core loop): `HelpPanel` + `InfoTip`s on
- **Blueprints** (`/blueprints`, `/blueprints/{ref}`): blueprint vs instance, the 7 organs,
  faculties, versions, ring floor, status.
- **Instance Inspector** (`/instances/{id}`, all 7 tabs): ring (L0–L4), trust & deltas, run-state,
  charter/target, heap fact provenance/status, syscall actions, approvals.
- **Approvals** (`/approvals`): what L0/L1 parking means, approve vs reject vs edit-diff, the gate.

**Lighter** (HelpPanel + a few key tooltips): Home, Runs, Gym, Foundry, Providers, Kernel, Economy,
Docs.

All copy lives in `lib/glossary.ts`. **Done-when:** core-loop pages carry help panel + tooltips;
remaining pages carry a help panel; gate green.

## 8. Architecture & data flow

Purely client-side and additive. `InfoTip`/`HelpPanel`/`Wizard` are presentational primitives;
they read static copy from `glossary.ts` and (for the wizard) call the *existing* API helpers. No
new global state, no new providers, no new backend calls beyond what the create flow already makes.
The wizard reuses `useOperator()` (baseUrl/token) and the unified instantiate helper. SSE/polling,
data fetching, and command behaviour are unchanged.

## 9. Error handling

- Wizard submit uses `AsyncButton` semantics (spinner, disabled-while-pending, success/error toast)
  — same as the drawer. Failures surface the API error and keep the wizard open on the review step.
- Per-step `validate?` blocks Next until required fields are valid; never a silent dead-end.
- `InfoTip`/`HelpPanel` are inert on data errors (static copy); they never block a page from
  rendering.
- Graceful-disable rule from the overhaul still holds: controls whose backend isn't live render
  disabled with a reason — the wizard respects the same `isLive`/token gating as the drawer.

## 10. Testing

- Unit tests: `InfoTip` (open/close, aria, keyboard, Escape), `HelpPanel` (localStorage persist),
  `Wizard` (step nav, validation gating, finish), `glossary` (term lookup integrity).
- Wizard-flow test: builds an instance through the same helper the drawer uses; asserts the
  `/commands/instantiate` payload shape (incl. `sender_identity`) is identical to the drawer's.
- Regression: existing 162 dashboard tests stay green; `npm run build` + `tsc --noEmit` green.

## 11. Invariants & no-gos

- **No change to existing functionality, props, behaviour, or API calls.** Additive only.
- The drawer and wizard share **one** instantiate code path (no divergent duplicate).
- Backend (`agentx_api`, `packages/*`) is **not edited** here; audit findings on that side are
  **flagged** for Codex (CLAUDE.md lane fence). `packages/contracts` remains FROZEN.
- Reuse the existing `ui/` kit, theme tokens, `lib/api.ts`/`lib/events.ts`/`lib/types.ts`; do not
  reimplement them.
- Gate-green before done: `npm test` + `npm run build` + `tsc --noEmit`.

## 12. Build order

Phase 0 (audit + fix) → Phase 1 (primitives + glossary) → Phase 2 (wizard, drawer refactor to
shared helper) → Phase 3 (tooltips/help: core loop, then lighter pass). Each phase is independently
gate-green and committed.

## 13. Out of scope (deferred)

Full app-wide spotlight product tour · mobile layout · auth/RBAC · backend endpoint changes ·
i18n of the glossary · per-user persisted onboarding progress beyond a localStorage open/closed
flag.
