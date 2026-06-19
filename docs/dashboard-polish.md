# Dashboard Polish Backlog

Source: Pillar 1 of `PROPOSAL_NICE_DASHBOARD_SWARM_CREATOR.md`.

## P0 — Operability-completing

- [x] **D1 — True SSE journal stream + EventSource hook.** Completed in Session L. `/events`
  now emits the current journal tail and follows new per-instance sequence numbers; the dashboard
  silently refreshes on journal events while retaining the eight-second polling fallback.
- [x] **D2 — Toast/feedback system + recent-commands log.** Completed in Session L. Manager
  command results produce deduplicated, auto-dismissing toasts and remain visible in a bounded
  timestamped ledger.
- [ ] **D3 — Always-show Foundry nav + empty-state CTA "Run a swarm".** Owned by Session I
  (`feat/swarm-from-dashboard`).

## P1 — Truthfulness of the live system

- [ ] **D4 — Watch/timer strip.** Show 72-hour countdowns on Floor and Instance File.
- [ ] **D5 — Trust-ladder motion.** Visualize L0→L4 and clean-action eligibility; requires G6 data.
- [ ] **D6 — Eval-case drill-down.** Show scorecard criteria, judge comments, and trace timeline;
  depends on Pillar 2.

## P2 — Polish

- [ ] **D7 — Skeleton loaders + per-panel staleness badges.**
- [ ] **D8 — Accessibility pass.** Complete focus-visible and contrast review. Session L added
  a global `prefers-reduced-motion` safeguard, but the full item remains open.
- [ ] **D9 — Parked-run argument editing UI.** Drive `/commands/edit` after that route lands.

## Constraints

- No component-library swap.
- No theme or visual-identity redesign.
- No router or Next.js version bump.
