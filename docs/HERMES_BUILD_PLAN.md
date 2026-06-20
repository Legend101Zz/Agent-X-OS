# HERMES_BUILD_PLAN.md — Phases for the Hermes Autobuilder

This file is the phase plan referenced by `MINIMAX-TASK.md`. It is the
authoritative sequence for `agentx-orchestrator` / autobuilder work.

## Status legend
- ✅ done & live-proven on `main`
- 🟢 built, live-proven, scoped tight (further work needed but not blocking)
- 🟡 partial / scaffolded
- ❌ not built

---

## Phase 1 — Gated real email SEND ✅ DONE (`main`, 2026-06-20)
Gmail SMTP via App Password, idempotent, per-instance sender. Unit-tested
with a fake transport; live-proven against Gmail on 2026-06-20. Send-loop
live proof: `docs/SESSION_SEND_LOOP_LIVE_PROOF.md`.

## Phase 2 — Step-D reality feedback 🟢 DONE-SCAFFOLD
`WatchMaturationWorker` matures watches → promotes probation facts →
verified → emits one `EvalCase(origin="real")` graded on the real
`lead_quality` rubric. **Needs reply-watch data to demonstrate live.**

## Phase 3 — Creator mandate draft path 🟢 DONE-SCAFFOLD
`build_creator_type()` (4 §5 faculties) + draft-only `draft_candidate_type`
syscall at the canary rung. **Design-only finalization needed.**

## Phase 4 — Promote gate + canary ✅ DONE
Ring-aware `POST /commands/promote`. L0/L1 canary on
synthetic-smoke+human; L2+ on real+human via unmodified `PromotionGate`.
Synthetic-only **barred**, cherry-picking structurally blocked.

## Phase 5 — Compiler scaffold 🟢 DONE-MECHANISM
`compile_candidate(gym)` gates a proposal on the same `PromotionGate`
(synthetic-only never promotable). **Real improvement needs ~100 real
settles to populate the gym.**

## Phase 6 — End-to-end phase chain ✅ DONE
All phases 1–5 in `tests/integration/test_phase6_end_to_end.py`. Contracts
frozen throughout; lane fence 3/3.

---

## Phase 7 — Closed-loop Step-D with reply-watch (NEXT)
**Goal.** Wire the existing reply-watch maturation into the live
send-loop so each real send closes the loop: send → reply → watch fires →
maturation promotes → EvalCase → gym grows.

**Done-when.**
- ReplyWatch matures in <72h on a real Gmail reply (live-gated test).
- `EvalCase(origin="real")` count increments by 1 per matured watch.
- PromotionGate now sees ≥1 real case per swarm run.

**Constraints.** Don't break existing `send_email` adapter; don't
rebuild kernel verifiers; contracts frozen.

**Routes.** Likely `agentx-claude-coder` (kernel/mandate lane).

## Phase 8 — Creator finalization (catalog write)
**Goal.** Promote `draft_candidate_type` from canary to write. Creator
produces a real catalog entry, not just a draft.

**Done-when.** `/commands/instantiate` accepts a Creator-produced
`MandateType` end-to-end. `Origin=creator` stamp visible in catalog UI.

**Routes.** Mixed: `agentx-codex-coder` for the registry write, then
`agentx-claude-coder` for the kernel acceptance path.

## Phase 9 — Compiler on a real gym corpus
**Goal.** First compile run on ≥50 settled real cases. Measure before/after
on `lead_quality` rubric.

**Done-when.** One GEPA-style run produces a candidate skill pack; gate
evaluates it on the same corpus; report shows win/loss per rubric.

**Constraints.** Don't ship a promoted version without real+human
(invariant #7). First run is experiment-only.

## Phase 10 — Phase-2 channel: WhatsApp OR Calendar
**Goal.** Add ONE new external channel (business's pick). Per-instance
identity (invariant #8), idempotency, ring L2, human-task tail (invariant #5).

**Done-when.** One Phase-2 mandate uses the new channel end-to-end with
approval gates. Adapter follows the `SendEmailAdapter` pattern.

**Routes.** `agentx-codex-coder`.

## Phase 11 — First paying-customer pilot
**Goal.** Pick ONE paying customer; run one production mandate for them
end-to-end; measure billing, settlement, and one grown-domain-pack cycle.

**Done-when.** One invoice generated, paid, settled, and one
domain-pack promotion (gym → skill pack → next run uses it).

**Routes.** Founder-driven, with Hermes as the orchestrator.
