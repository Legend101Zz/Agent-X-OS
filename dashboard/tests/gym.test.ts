import assert from "node:assert/strict";
import test from "node:test";

import {
  COMPILER_REAL_CASE_THRESHOLD,
  deriveCompilerScaffold,
  summariseEvalCases,
} from "../src/lib/eval-stats";
import {
  evalOriginLabel,
  evalOriginTone,
  evalStatusTone,
  formatScore,
  promotionLabel,
  promotionTone,
  scoreTone,
  shortId,
} from "../src/lib/format";
import {
  compilerStateLabel,
  compilerStateTone,
  type EvalCase,
} from "../src/lib/types";
import { mapEvalCases } from "../src/lib/api";

// ----------------------------------------------------------------------------
// Fixtures — three synthetic + two real + one human_reviewed, with scorecards.
// Mirrors what the /eval-cases projection returns (raw API shape before the
// view-model mapper).
// ----------------------------------------------------------------------------

const RAW_FIXTURE = [
  {
    id: "eval_synth_001",
    type_ref: "lead_finder.outreach",
    tags: ["scenario:lead_finder.outreach"],
    origin: "synthetic",
    score: 0.62,
    passed: true,
    scorecard: {
      run_id: "run_synth_001",
      rubric_name: "lead_finder.outreach",
      score: 0.62,
      passed: true,
      criteria: [
        { criterion_id: "subject", passed: true, score: 0.7 },
        { criterion_id: "tone", passed: false, score: 0.55 },
      ],
      failure_reasons: ["tone too formal"],
    },
  },
  {
    id: "eval_synth_002",
    type_ref: "lead_finder.outreach",
    tags: ["scenario:lead_finder.outreach"],
    origin: "synthetic",
    score: 0.41,
    passed: false,
    scorecard: {
      run_id: "run_synth_002",
      rubric_name: "lead_finder.outreach",
      score: 0.41,
      passed: false,
      criteria: [{ criterion_id: "subject", passed: false, score: 0.4 }],
      failure_reasons: ["subject misaligned"],
    },
  },
  {
    id: "eval_real_001",
    type_ref: "lead_finder.outreach",
    tags: ["scenario:lead_finder.outreach"],
    origin: "real",
    score: 0.88,
    passed: true,
  },
  {
    id: "eval_real_002",
    type_ref: "lead_finder.outreach",
    tags: ["scenario:lead_finder.outreach"],
    origin: "real",
    score: 0.74,
    passed: true,
  },
  {
    id: "eval_human_001",
    type_ref: "lead_finder.outreach",
    tags: ["scenario:lead_finder.outreach"],
    origin: "human_reviewed",
    score: 0.91,
    passed: true,
  },
];

const CASES: EvalCase[] = mapEvalCases(RAW_FIXTURE);

// ----------------------------------------------------------------------------
// summariseEvalCases — the engine behind the hero tiles.
// ----------------------------------------------------------------------------

test("summariseEvalCases counts total + per-origin buckets", () => {
  const stats = summariseEvalCases(CASES);
  assert.equal(stats.total, 5);
  assert.equal(stats.byOrigin.synthetic, 2);
  assert.equal(stats.byOrigin.real, 2);
  assert.equal(stats.byOrigin.human_reviewed, 1);
});

test("summariseEvalCases computes the eligible/blocked/needs_review counters", () => {
  const stats = summariseEvalCases(CASES);
  // All synthetic cases are coerced to "blocked" by the mapper (invariant #7),
  // so blocked = 2 and eligible = 3 (2 real + 1 human_reviewed).
  assert.equal(stats.blocked, 2);
  assert.equal(stats.eligible, 3);
  assert.equal(stats.needsReview, 0);
});

test("summariseEvalCases averages scores across the corpus and per origin", () => {
  const stats = summariseEvalCases(CASES);
  // (0.62 + 0.41 + 0.88 + 0.74 + 0.91) / 5 = 0.712
  assert.ok(stats.averageScore !== null);
  assert.equal(Math.round((stats.averageScore ?? 0) * 1000), 712);
  assert.equal(stats.averageByOrigin.synthetic?.toFixed(2), "0.52");
  assert.equal(stats.averageByOrigin.real?.toFixed(2), "0.81");
  assert.equal(stats.averageByOrigin.human_reviewed?.toFixed(2), "0.91");
});

test("summariseEvalCases produces a deterministic score timeline", () => {
  const stats = summariseEvalCases(CASES);
  // The mapper drops numeric scores; we just check length + stability.
  assert.equal(stats.scoreTimeline.length, 5);
  const stats2 = summariseEvalCases(CASES);
  assert.deepEqual(stats2.scoreTimeline, stats.scoreTimeline);
});

test("summariseEvalCases returns null averages on an empty corpus", () => {
  const stats = summariseEvalCases([]);
  assert.equal(stats.total, 0);
  assert.equal(stats.averageScore, null);
  assert.equal(stats.scoreTimeline.length, 0);
});

// ----------------------------------------------------------------------------
// deriveCompilerScaffold — the compiler scaffold status indicator.
// Maps to the §5 row "Compiler scaffold status".
// ----------------------------------------------------------------------------

test("deriveCompilerScaffold is not_started when the gym is empty", () => {
  const scaffold = deriveCompilerScaffold(summariseEvalCases([]));
  assert.equal(scaffold.state, "not_started");
  assert.equal(scaffold.realCases, 0);
  assert.equal(scaffold.threshold, COMPILER_REAL_CASE_THRESHOLD);
});

test("deriveCompilerScaffold is blocked_synthetic_only when no real cases exist", () => {
  const onlySynthetic = CASES.filter((c) => c.origin === "synthetic");
  const scaffold = deriveCompilerScaffold(summariseEvalCases(onlySynthetic));
  assert.equal(scaffold.state, "blocked_synthetic_only");
  assert.equal(scaffold.realCases, 0);
});

test("deriveCompilerScaffold warms up while below the real-case threshold", () => {
  const stats = summariseEvalCases(CASES); // 3 real+human_reviewed
  const scaffold = deriveCompilerScaffold(stats, 100);
  assert.equal(scaffold.state, "warming_up");
  assert.equal(scaffold.realCases, 3);
  assert.equal(scaffold.threshold, 100);
});

test("deriveCompilerScaffold turns ready at threshold", () => {
  const stats = summariseEvalCases(CASES);
  const scaffold = deriveCompilerScaffold(stats, 3);
  assert.equal(scaffold.state, "ready");
  assert.equal(scaffold.realCases, 3);
});

test("compilerStateTone + compilerStateLabel give a usable pill for each state", () => {
  for (const state of [
    "ready",
    "warming_up",
    "blocked_synthetic_only",
    "not_started",
  ] as const) {
    const tone = compilerStateTone(state);
    assert.ok(["good", "warn", "hot", "info", "neutral"].includes(tone));
    const label = compilerStateLabel(state);
    assert.ok(label.length > 0);
  }
});

// ----------------------------------------------------------------------------
// Origin / status / promotion / score tone helpers — the per-row pill surfaces.
// ----------------------------------------------------------------------------

test("evalOriginTone surfaces synthetic as info, real as warn, human_reviewed as good", () => {
  assert.equal(evalOriginTone("synthetic"), "info");
  assert.equal(evalOriginTone("real"), "warn");
  assert.equal(evalOriginTone("human_reviewed"), "good");
  assert.equal(evalOriginTone(undefined), "neutral");
});

test("evalOriginLabel is human-readable", () => {
  assert.equal(evalOriginLabel("synthetic"), "synthetic");
  assert.equal(evalOriginLabel("real"), "real");
  assert.equal(evalOriginLabel("human_reviewed"), "human-reviewed");
  assert.equal(evalOriginLabel(undefined), "—");
});

test("promotionTone returns good for eligible, hot for blocked, warn for needs_review", () => {
  assert.equal(promotionTone("eligible"), "good");
  assert.equal(promotionTone("blocked"), "hot");
  assert.equal(promotionTone("needs_review"), "warn");
  assert.equal(promotionTone(undefined), "neutral");
});

test("promotionLabel surfaces the synthetic-bar message on blocked cases", () => {
  assert.equal(promotionLabel("eligible"), "eligible");
  assert.equal(promotionLabel("blocked"), "blocked · synthetic");
  assert.equal(promotionLabel("needs_review"), "needs review");
  assert.equal(promotionLabel(undefined), "—");
});

test("evalStatusTone maps graded/passed/failed/pending", () => {
  // graded + passed should read as good (passed) or info (graded); failed as hot.
  assert.equal(evalStatusTone("passed"), "good");
  assert.equal(evalStatusTone("graded"), "info");
  assert.equal(evalStatusTone("failed"), "hot");
  assert.equal(evalStatusTone("pending"), "warn");
  assert.equal(evalStatusTone("queued"), "warn");
});

test("scoreTone buckets 0–1 scores into good/info/warn/hot", () => {
  assert.equal(scoreTone(0.95), "good");
  assert.equal(scoreTone(0.8), "good");
  assert.equal(scoreTone(0.79), "info");
  assert.equal(scoreTone(0.6), "info");
  assert.equal(scoreTone(0.59), "warn");
  assert.equal(scoreTone(0.4), "warn");
  assert.equal(scoreTone(0.3), "hot");
  assert.equal(scoreTone(0), "hot");
  assert.equal(scoreTone(null), "neutral");
  assert.equal(scoreTone(undefined), "neutral");
  assert.equal(scoreTone(Number.NaN), "neutral");
});

test("formatScore renders 2-decimal numbers, em-dash for nulls", () => {
  assert.equal(formatScore(0.62), "0.62");
  assert.equal(formatScore(1), "1.00");
  assert.equal(formatScore(0), "0.00");
  assert.equal(formatScore(null), "—");
  assert.equal(formatScore(undefined), "—");
});

test("shortId strips the type-prefix and truncates with an ellipsis", () => {
  assert.equal(shortId("inst_abcdef"), "abcdef");
  assert.equal(shortId("run_abcdef123"), "abcdef…");
  assert.equal(shortId(undefined), "—");
  assert.equal(shortId(""), "—");
});

// ----------------------------------------------------------------------------
// mapEvalCases — the wire-format → view-model bridge.
// This is the surface invariant #7 lives on: synthetic cases are forced to
// promotion="blocked" regardless of what the API says.
// ----------------------------------------------------------------------------

test("mapEvalCases forces synthetic origin to promotion=blocked (invariant #7)", () => {
  const raw = [
    {
      id: "eval_x",
      type_ref: "t",
      tags: [],
      origin: "synthetic",
      score: 0.5,
      passed: true,
    },
  ];
  const mapped = mapEvalCases(raw);
  assert.equal(mapped.length, 1);
  assert.equal(mapped[0].origin, "synthetic");
  assert.equal(mapped[0].promotion, "blocked");
});

test("mapEvalCases leaves real / human_reviewed as eligible", () => {
  const mapped = mapEvalCases([
    {
      id: "a",
      type_ref: "t",
      tags: [],
      origin: "real",
      score: 0.9,
      passed: true,
    },
    {
      id: "b",
      type_ref: "t",
      tags: [],
      origin: "human_reviewed",
      score: 0.9,
      passed: true,
    },
  ]);
  assert.equal(mapped[0].promotion, "eligible");
  assert.equal(mapped[1].promotion, "eligible");
});

test("mapEvalCases marks passed:false as status=failed", () => {
  const mapped = mapEvalCases([
    {
      id: "x",
      type_ref: "t",
      tags: [],
      origin: "real",
      score: 0.3,
      passed: false,
    },
  ]);
  assert.equal(mapped[0].status, "failed");
});

test("mapEvalCases prefers the first tag for the pack label", () => {
  const mapped = mapEvalCases([
    {
      id: "x",
      type_ref: "t",
      tags: ["scenario:lead_finder", "secondary"],
      origin: "real",
      score: 0.8,
      passed: true,
    },
  ]);
  assert.equal(mapped[0].pack, "scenario:lead_finder");
});

test("mapEvalCases falls back to type_ref when tags are empty", () => {
  const mapped = mapEvalCases([
    { id: "x", type_ref: "t", tags: [], origin: "real", score: 0.8, passed: true },
  ]);
  assert.equal(mapped[0].pack, "t");
});

test("mapEvalCases leaves a raw EvalCase doc untouched when it already has a title", () => {
  const mapped = mapEvalCases([
    {
      id: "x",
      title: "Already shaped",
      origin: "real",
      score: 0.8,
      passed: true,
    },
  ]);
  assert.equal(mapped[0].title, "Already shaped");
});

// ----------------------------------------------------------------------------
// End-to-end invariant: synthetic case is "blocked" everywhere it surfaces.
// ----------------------------------------------------------------------------

test("end-to-end: synthetic case row surfaces origin=synthetic, promotion=blocked, score≠null", () => {
  const stats = summariseEvalCases(CASES);
  const synthCases = CASES.filter((c) => c.origin === "synthetic");
  assert.equal(synthCases.length, stats.byOrigin.synthetic);

  for (const c of synthCases) {
    assert.equal(evalOriginTone(c.origin), "info");
    assert.equal(promotionTone(c.promotion), "hot");
    assert.ok(formatScore(c.score) !== "—");
  }

  // Compiler scaffold must read blocked_synthetic_only if only synthetic cases existed.
  const onlySynth = CASES.filter((c) => c.origin !== "real" && c.origin !== "human_reviewed");
  const scaffold = deriveCompilerScaffold(summariseEvalCases(onlySynth));
  assert.equal(scaffold.state, "blocked_synthetic_only");
});