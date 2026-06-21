/**
 * Eval-case analytics — pure derivations from a `EvalCase[]`.
 *
 * Kept separate from the API mapper so the same logic can run on fixture data,
 * live data, or arbitrary slices (e.g. per-pack) without re-walking the wire.
 */

import type {
  CompilerScaffold,
  CompilerScaffoldState,
  EvalCase,
  EvalCaseStats,
  EvalOriginKey,
} from "./types";

/** Real-case threshold before the compiler will propose improvements (BLUEPRINT §5). */
export const COMPILER_REAL_CASE_THRESHOLD = 100;

const ORIGIN_KEYS: EvalOriginKey[] = ["synthetic", "real", "human_reviewed"];

function isOriginKey(value: string | undefined): value is EvalOriginKey {
  return value === "synthetic" || value === "real" || value === "human_reviewed";
}

function mean(values: number[]): number | null {
  if (values.length === 0) return null;
  let sum = 0;
  for (const v of values) sum += v;
  return sum / values.length;
}

/**
 * Compute the aggregate stats used by the Gym hero tiles, the origin
 * distribution panel, and the score-timeline sparkline.
 */
export function summariseEvalCases(cases: EvalCase[]): EvalCaseStats {
  const byOrigin: Record<EvalOriginKey, number> = {
    synthetic: 0,
    real: 0,
    human_reviewed: 0,
  };
  const scoresByOrigin: Record<EvalOriginKey, number[]> = {
    synthetic: [],
    real: [],
    human_reviewed: [],
  };
  const allScores: number[] = [];
  let eligible = 0;
  let blocked = 0;
  let needsReview = 0;

  for (const item of cases) {
    const origin: EvalOriginKey = isOriginKey(item.origin) ? item.origin : "synthetic";
    byOrigin[origin] += 1;
    if (typeof item.score === "number" && !Number.isNaN(item.score)) {
      scoresByOrigin[origin].push(item.score);
      allScores.push(item.score);
    }
    switch (item.promotion) {
      case "eligible":
        eligible += 1;
        break;
      case "blocked":
        blocked += 1;
        break;
      case "needs_review":
        needsReview += 1;
        break;
      default:
        break;
    }
  }

  const averageByOrigin: Partial<Record<EvalOriginKey, number>> = {};
  for (const key of ORIGIN_KEYS) {
    const m = mean(scoresByOrigin[key]);
    if (m !== null) averageByOrigin[key] = m;
  }

  // Score timeline — sort by the (deterministic) id so it stays stable across
  // renders. The dashboard reads the eval-case list from a stable projection,
  // so id-order is a good proxy for "as graded".
  const sorted = [...cases].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const scoreTimeline = sorted
    .map((c) => c.score)
    .filter((v): v is number => typeof v === "number" && !Number.isNaN(v));

  return {
    total: cases.length,
    byOrigin,
    eligible,
    blocked,
    needsReview,
    averageScore: mean(allScores),
    averageByOrigin,
    scoreTimeline,
  };
}

/**
 * Derive the compiler scaffold status. The compiler is gated on the same
 * `PromotionGate` as customer-facing promotion — synthetic-only is blocked
 * structurally (invariant #7). Real-case growth is what warms it up.
 */
export function deriveCompilerScaffold(
  stats: EvalCaseStats,
  threshold: number = COMPILER_REAL_CASE_THRESHOLD,
): CompilerScaffold {
  const realCases = stats.byOrigin.real + stats.byOrigin.human_reviewed;
  let state: CompilerScaffoldState;
  let note: string;

  if (stats.total === 0) {
    state = "not_started";
    note = "No eval cases yet. Run the swarm via Foundry to seed the gym.";
  } else if (realCases === 0) {
    state = "blocked_synthetic_only";
    note =
      "Only synthetic cases in the gym. The compiler stays blocked until real settles arrive (invariant #7).";
  } else if (realCases < threshold) {
    state = "warming_up";
    note = `Warming up — ${realCases}/${threshold} real cases. The compiler will start proposing at threshold.`;
  } else {
    state = "ready";
    note = `Ready — ${realCases} real cases have populated the gym. Proposals gated on the PromotionGate.`;
  }

  return {
    state,
    realCases,
    threshold,
    lastProposal: null, // wired when proposals land; backend hook TBD.
    note,
  };
}