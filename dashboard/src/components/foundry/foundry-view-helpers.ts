// C10 — Foundry / Swarm wind-tunnel.
//
// Pure helpers for the Foundry view. The view itself is a thin JSX shell
// over these so the rendering decisions (type_ref selector options,
// Timeline entries, scorecard table rows, gate banner tone + text) are
// testable in isolation, without React or jsdom.
//
// Tone vocabulary is the C1 design system's PillTone: "good" | "warn" |
// "hot" | "info" | "neutral". TimelineEntry.tone is the same vocabulary
// minus the L-rung tokens.

import type {
  GateDecisionView,
  MandateType,
  ScorecardView,
  SwarmTraceEvent,
} from "../lib/types";
import type { TimelineEntry } from "./ui/timeline";
import type { PillTone } from "./ui/pill";

/** Slug + version a mandate title+stage into the `type_ref` the API expects. */
export function formatMandateRef(title: string, stage: string): string {
  const slug = title.trim().toLowerCase().replace(/\s+/g, "_");
  if (!stage) return slug;
  return `${slug}@${stage}`;
}

/** Map a MandateType to a {value,label} for the type_ref <select>. */
export function buildTypeRefOptions(mandates: MandateType[]): Array<{ value: string; label: string }> {
  if (mandates.length === 0) {
    return [{ value: "lead-finder@0.1.0", label: "lead-finder @ 0.1.0 (fallback)" }];
  }
  return mandates.map((mandate) => {
    const value = formatMandateRef(mandate.title, mandate.stage);
    return { value, label: `${mandate.title} @ ${mandate.stage}` };
  });
}

/** Map a swarm trace event to a TimelineEntry (ui/Timeline) — the BLUEPRINT §5 mono timeline. */
export function buildSwarmTimelineEntries(events: SwarmTraceEvent[]): TimelineEntry[] {
  return events.map((event) => ({
    id: `swarm-evt-${event.seq}`,
    ts: event.ts,
    title: event.summary || event.kind,
    detail: renderTraceDetail(event),
    tone: timelineEntryTone(event.kind),
  }));
}

function renderTraceDetail(event: SwarmTraceEvent): string | undefined {
  const detail = event.detail ?? {};
  // Prefer "fulfilled by <adapter>" / "ring <X>" when the backend stamps them.
  const fulfilledBy = detail.fulfilled_by;
  if (typeof fulfilledBy === "string") return `fulfilled by ${fulfilledBy}`;
  const ring = detail.required_ring ?? detail.ring;
  if (typeof ring === "string") return `ring ${ring}`;
  return undefined;
}

/** Per-kind tone for a trace event — the same vocabulary the ui/Timeline dot uses. */
export function timelineEntryTone(kind: string): "good" | "warn" | "hot" | "info" | "neutral" {
  switch (kind) {
    case "syscall_result":
    case "verify":
    case "decision":
    case "resumed":
      return "good";
    case "parked":
      return "warn";
    case "error":
      return "hot";
    case "thought":
    case "syscall_attempt":
    case "judge_comment":
      return "info";
    default:
      return "neutral";
  }
}

// ---- gate decision -------------------------------------------------------------

/** True iff the gate explicitly blocked promotion. Null gate == blocked. */
export function isGateBlocked(gate: GateDecisionView | null | undefined): boolean {
  if (!gate) return true;
  return !gate.allowed;
}

/** Tone for the gate decision banner — the BLUEPRINT §5 "promotion gate" verdict. */
export function gateDecisionTone(
  gate: GateDecisionView | null | undefined,
): "good" | "hot" {
  return gate?.allowed ? "good" : "hot";
}

/** Cast a gate tone to a PillTone so StatusPill accepts it directly. */
export function gateToneToPill(tone: "good" | "hot" | "warn"): PillTone {
  return tone;
}

/**
 * View-model for the §5 PromotionGate verdict banner. Pure so the rendering
 * decisions (title copy, reason lines, tone) are testable in isolation.
 *
 *  - Synthetic + blocked → "blocked (synthetic-only · invariant #7)"
 *  - Real + human-approved → "open — real + human approved, live @ L<ring>"
 *  - Real + human-approved + no live_ring yet → "open — real + human approved"
 *    (the operator still needs to flip the ring via /commands/set-ring)
 */
export interface GateBannerView {
  allowed: boolean;
  tone: "good" | "hot";
  title: string;
  subtitle: string;
  reasons: string[];
  origin_label: "synthetic" | "real" | "unknown";
  live_ring: string | null;
}

export function buildGateBanner(
  gate: GateDecisionView | null | undefined,
  origin: string | null | undefined,
): GateBannerView | null {
  if (!gate) return null;
  const allowed = !!gate.allowed;
  const origin_label: GateBannerView["origin_label"] =
    origin === "synthetic" ? "synthetic" : origin === "real" ? "real" : "unknown";
  const live_ring = gate.live_ring ?? null;
  const reasons = (gate.reasons ?? []).slice();
  if (allowed && reasons.length === 0) {
    reasons.push(
      live_ring
        ? `Live ring ${live_ring} approved by an operator — candidate may promote.`
        : "All criteria passed — promotion is allowed.",
    );
  }
  if (allowed && !live_ring) {
    reasons.push(
      "No live ring bound yet — an operator must call /commands/set-ring to enable real customers.",
    );
  }
  const title = allowed
    ? "Promotion gate · open — real + human approved"
    : origin_label === "synthetic"
      ? "Promotion gate · blocked — synthetic-only (invariant #7)"
      : "Promotion gate · blocked";
  const subtitle = allowed
    ? live_ring
      ? `Promotion allowed at ring ${live_ring}. Synthetic trials can never promote (invariant #7); this case cleared that bar.`
      : "Promotion is allowed in principle, but no live ring is bound yet. Synthetic trials can never promote (invariant #7); this case cleared that bar."
    : origin_label === "synthetic"
      ? "Synthetic (swarm) eval cases are recorded but barred from promoting customer-facing versions (BLUEPRINT §5 invariant #7)."
      : "Gate refused promotion. See reasons below for the failing rule(s).";
  return {
    allowed,
    tone: allowed ? "good" : "hot",
    title,
    subtitle,
    reasons,
    origin_label,
    live_ring,
  };
}

// ---- scorecard -----------------------------------------------------------------

/** Round scorecard.score to an integer percent (0..100). Null guard returns 0. */
export function scorecardPct(scorecard: ScorecardView | null | undefined): number {
  if (!scorecard) return 0;
  return Math.round(scorecard.score * 100);
}

export interface ScorecardRow {
  criterion_id: string;
  pct: number;
  passed: boolean;
  tone: PillTone;
  comment: string;
}

/** Flatten scorecard.criteria into table rows with computed pct + tone. */
export function scorecardToCriteriaRows(
  scorecard: ScorecardView | null | undefined,
): ScorecardRow[] {
  if (!scorecard) return [];
  return scorecard.criteria.map((criterion) => {
    const pct = Math.round(criterion.score * 100);
    const tone: PillTone = criterion.passed ? "good" : "hot";
    return {
      criterion_id: criterion.criterion_id,
      pct,
      passed: criterion.passed,
      tone,
      comment: criterion.comment ?? "",
    };
  });
}
