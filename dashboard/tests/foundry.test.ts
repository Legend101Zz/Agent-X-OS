// C10 — Foundry / Swarm wind-tunnel.
//
// TDD: encode the done-when assertions as pure-function tests so the view
// itself can stay a thin shell of JSX over these helpers.  Every helper
// takes a typed SwarmRunReport (or part of one) and returns a structure
// the C1 design-system primitives (Timeline, Table, StatusPill, AsyncButton)
// can render directly.

import assert from "node:assert/strict";
import test from "node:test";

import type {
  GateDecisionView,
  MandateType,
  ScorecardCriterionView,
  ScorecardView,
  SwarmRunReport,
  SwarmTraceEvent,
} from "../src/lib/types";
import {
  buildGateBanner,
  buildSwarmTimelineEntries,
  buildTypeRefOptions,
  formatMandateRef,
  gateDecisionTone,
  gateToneToPill,
  isGateBlocked,
  scorecardPct,
  scorecardToCriteriaRows,
  timelineEntryTone,
} from "../src/components/foundry/foundry-view-helpers";

const baseEvent = (overrides: Partial<SwarmTraceEvent> = {}): SwarmTraceEvent => ({
  seq: 1,
  ts: "2026-06-21T08:00:00Z",
  kind: "thought",
  summary: "candidate decided to run scenario",
  detail: {},
  ...overrides,
});

const baseCriterion = (overrides: Partial<ScorecardCriterionView> = {}): ScorecardCriterionView => ({
  criterion_id: "lead_quality",
  passed: true,
  score: 0.9,
  comment: "strong evidence",
  ...overrides,
});

const baseScorecard = (overrides: Partial<ScorecardView> = {}): ScorecardView => ({
  run_id: "run_test",
  rubric_name: "lead_quality",
  score: 0.78,
  passed: true,
  origin: "synthetic",
  criteria: [baseCriterion()],
  failure_reasons: [],
  judge_comments: ["synthetic trial ok"],
  ...overrides,
});

const baseGate = (overrides: Partial<GateDecisionView> = {}): GateDecisionView => ({
  allowed: false,
  reasons: ["synthetic-only · barred by invariant #7"],
  live_ring: null,
  ...overrides,
});

const baseReport = (overrides: Partial<SwarmRunReport> = {}): SwarmRunReport => ({
  supported: true,
  run_id: "run_abc",
  type_ref: "lead-finder@0.1.0",
  pack_id: "indian_b2b_leads_v1",
  events: [baseEvent()],
  scorecard: baseScorecard(),
  gate_decision: baseGate(),
  eval_case_id: "ec_1",
  ...overrides,
});

const baseMandate = (overrides: Partial<MandateType> = {}): MandateType =>
  ({
    id: "mt_lead_finder",
    title: "lead-finder",
    type_ref: "lead-finder@0.1.0",
    stage: "0.1.0",
    ring_floor: "L2",
    unit_economics: "₹/lead",
    commands: ["draft_email", "send_email"],
    status: "ready",
    ...overrides,
  }) as MandateType;

// ---- formatMandateRef -----------------------------------------------------------

test("formatMandateRef lowercases + slugifies + versions the ref", () => {
  assert.equal(formatMandateRef("Lead Finder", "0.1.0"), "lead_finder@0.1.0");
  assert.equal(formatMandateRef("CRM-Refresh  v2", "1.0"), "crm-refresh_v2@1.0");
});

test("formatMandateRef handles empty stage as a no-version ref", () => {
  assert.equal(formatMandateRef("lead-finder", ""), "lead-finder");
});

// ---- buildTypeRefOptions --------------------------------------------------------

test("buildTypeRefOptions returns one option per mandate + the chosen ref is the first value", () => {
  const mandates = [
    baseMandate({ id: "mt_a", title: "alpha", stage: "0.1.0" }),
    baseMandate({ id: "mt_b", title: "beta", stage: "1.0.0" }),
  ];
  const options = buildTypeRefOptions(mandates);
  assert.equal(options.length, 2);
  assert.equal(options[0].value, "alpha@0.1.0");
  assert.equal(options[0].label, "alpha @ 0.1.0");
  assert.equal(options[1].value, "beta@1.0.0");
  assert.equal(options[1].label, "beta @ 1.0.0");
});

test("buildTypeRefOptions returns a sensible fallback when no mandates are present", () => {
  const options = buildTypeRefOptions([]);
  assert.equal(options.length, 1);
  assert.equal(options[0].value, "lead-finder@0.1.0");
  assert.match(options[0].label, /lead-finder/);
});

// ---- buildSwarmTimelineEntries --------------------------------------------------

test("buildSwarmTimelineEntries produces a Timeline entry per trace event in order", () => {
  const events = [
    baseEvent({ seq: 1, kind: "thought", summary: "decide" }),
    baseEvent({ seq: 2, kind: "syscall_attempt", summary: "draft_email" }),
    baseEvent({ seq: 3, kind: "verify", summary: "score" }),
  ];
  const entries = buildSwarmTimelineEntries(events);
  assert.equal(entries.length, 3);
  // Every entry has a unique id and a ts
  for (const entry of entries) {
    assert.ok(entry.id, "entry must carry a stable id");
    assert.ok(entry.ts, "entry must carry a ts (mono timeline requirement)");
  }
  // Order preserved
  assert.match(String(entries[0].title), /decide/);
  assert.match(String(entries[1].title), /draft_email/);
  assert.match(String(entries[2].title), /score/);
});

test("buildSwarmTimelineEntries returns the right tone per kind", () => {
  const entries = buildSwarmTimelineEntries([
    baseEvent({ kind: "error", summary: "oops" }),
    baseEvent({ kind: "verify", summary: "ok" }),
    baseEvent({ kind: "parked", summary: "wait" }),
    baseEvent({ kind: "thought", summary: "think" }),
  ]);
  assert.equal(entries[0].tone, "hot"); // error
  assert.equal(entries[1].tone, "good"); // verify
  assert.equal(entries[2].tone, "warn"); // parked
  assert.equal(entries[3].tone, "info"); // thought
});

test("buildSwarmTimelineEntries returns an empty array for an empty report", () => {
  assert.deepEqual(buildSwarmTimelineEntries([]), []);
});

// ---- timelineEntryTone + gateDecisionTone / gateToneToPill ----------------------

test("timelineEntryTone classifies the known wind-tunnel kinds", () => {
  assert.equal(timelineEntryTone("thought"), "info");
  assert.equal(timelineEntryTone("syscall_attempt"), "info");
  assert.equal(timelineEntryTone("syscall_result"), "good");
  assert.equal(timelineEntryTone("verify"), "good");
  assert.equal(timelineEntryTone("judge_comment"), "info");
  assert.equal(timelineEntryTone("decision"), "good");
  assert.equal(timelineEntryTone("resumed"), "good");
  assert.equal(timelineEntryTone("parked"), "warn");
  assert.equal(timelineEntryTone("error"), "hot");
  assert.equal(timelineEntryTone("nonsense"), "neutral");
});

test("isGateBlocked reflects the gate.allowed flag (synthetic-only → blocked)", () => {
  assert.equal(isGateBlocked(baseGate({ allowed: false })), true);
  assert.equal(isGateBlocked(baseGate({ allowed: true })), false);
  assert.equal(isGateBlocked(null), true); // no gate = blocked by default
});

test("gateDecisionTone returns 'good' when allowed and 'hot' when blocked", () => {
  assert.equal(gateDecisionTone(baseGate({ allowed: true })), "good");
  assert.equal(gateDecisionTone(baseGate({ allowed: false })), "hot");
  assert.equal(gateDecisionTone(null), "hot");
});

test("gateToneToPill maps gate tones onto the pill vocabulary (good/hot)", () => {
  assert.equal(gateToneToPill("good"), "good");
  assert.equal(gateToneToPill("hot"), "hot");
  assert.equal(gateToneToPill("warn"), "warn");
});

// ---- buildGateBanner (PromotionGate verdict view-model) --------------------------

test("buildGateBanner returns null when the gate is missing", () => {
  assert.equal(buildGateBanner(null, "synthetic"), null);
  assert.equal(buildGateBanner(undefined, "real"), null);
});

test("buildGateBanner flags synthetic-blocked cases with the invariant-#7 copy", () => {
  const banner = buildGateBanner(
    baseGate({ allowed: false, reasons: ["synthetic-only · barred by invariant #7"] }),
    "synthetic",
  );
  assert.ok(banner);
  assert.equal(banner!.allowed, false);
  assert.equal(banner!.tone, "hot");
  assert.equal(banner!.origin_label, "synthetic");
  assert.match(banner!.title, /blocked/);
  assert.match(banner!.title, /invariant #7/i);
  assert.match(banner!.subtitle, /synthetic.*barred|synthetic.*can never promote/i);
  assert.deepEqual(banner!.reasons, ["synthetic-only · barred by invariant #7"]);
  assert.equal(banner!.live_ring, null);
});

test("buildGateBanner flags real + human-approved open cases (live_ring bound)", () => {
  const banner = buildGateBanner(
    baseGate({ allowed: true, reasons: [], live_ring: "L1" }),
    "real",
  );
  assert.ok(banner);
  assert.equal(banner!.allowed, true);
  assert.equal(banner!.tone, "good");
  assert.equal(banner!.origin_label, "real");
  assert.equal(banner!.live_ring, "L1");
  assert.match(banner!.title, /open/);
  assert.match(banner!.title, /real.*human/i);
  // No API reasons → helper must surface at least one synthesised reason.
  assert.equal(banner!.reasons.length, 1);
  assert.match(banner!.reasons[0], /L1/);
});

test("buildGateBanner flags real + human-approved but un-ringed open cases", () => {
  const banner = buildGateBanner(
    baseGate({ allowed: true, reasons: [], live_ring: null }),
    "real",
  );
  assert.ok(banner);
  assert.equal(banner!.allowed, true);
  assert.equal(banner!.origin_label, "real");
  assert.equal(banner!.live_ring, null);
  assert.match(banner!.title, /open/);
  // Should explicitly call out the operator follow-up: bind a ring via /commands/set-ring.
  assert.ok(
    banner!.reasons.some((reason) => /set-ring|live ring/i.test(reason)),
    "expected a 'set-ring / live ring' operator follow-up reason when allowed with no live_ring",
  );
});

test("buildGateBanner treats unknown-origin blocked cases as a generic block", () => {
  const banner = buildGateBanner(
    baseGate({ allowed: false, reasons: ["score < 0.7"] }),
    null,
  );
  assert.ok(banner);
  assert.equal(banner!.origin_label, "unknown");
  assert.equal(banner!.allowed, false);
  assert.match(banner!.title, /blocked/);
  // Should NOT claim synthetic-barred when origin is unknown.
  assert.doesNotMatch(banner!.title, /synthetic-only/);
  assert.deepEqual(banner!.reasons, ["score < 0.7"]);
});

// ---- scorecard helpers ----------------------------------------------------------

test("scorecardPct rounds the scorecard.score to an integer percentage", () => {
  assert.equal(scorecardPct(baseScorecard({ score: 0.784 })), 78);
  assert.equal(scorecardPct(baseScorecard({ score: 0 })), 0);
  assert.equal(scorecardPct(baseScorecard({ score: 1 })), 100);
  assert.equal(scorecardPct(null), 0);
});

test("scorecardToCriteriaRows flattens criteria into table rows with pct + tone", () => {
  const scorecard = baseScorecard({
    criteria: [
      baseCriterion({ criterion_id: "lead_quality", passed: true, score: 0.9 }),
      baseCriterion({ criterion_id: "tone", passed: false, score: 0.3, comment: "too formal" }),
    ],
  });
  const rows = scorecardToCriteriaRows(scorecard);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].criterion_id, "lead_quality");
  assert.equal(rows[0].pct, 90);
  assert.equal(rows[0].tone, "good");
  assert.equal(rows[0].passed, true);
  assert.equal(rows[1].criterion_id, "tone");
  assert.equal(rows[1].pct, 30);
  assert.equal(rows[1].tone, "hot");
  assert.equal(rows[1].passed, false);
  assert.equal(rows[1].comment, "too formal");
});

test("scorecardToCriteriaRows returns an empty list when scorecard is null", () => {
  assert.deepEqual(scorecardToCriteriaRows(null), []);
});

// ---- end-to-end smoke: every helper composes on a real-ish report -------------

test("composed report: timeline + criteria + gate decision agree with the report", () => {
  const report = baseReport({
    events: [
      baseEvent({ seq: 1, kind: "thought", summary: "decide scenario" }),
      baseEvent({ seq: 2, kind: "syscall_attempt", summary: "draft_email" }),
      baseEvent({ seq: 3, kind: "verify", summary: "judge score" }),
    ],
    scorecard: baseScorecard({
      criteria: [
        baseCriterion({ criterion_id: "lead_quality", passed: true, score: 0.86 }),
        baseCriterion({ criterion_id: "tone", passed: false, score: 0.4 }),
      ],
    }),
    gate_decision: baseGate({
      allowed: false,
      reasons: ["synthetic-only · barred by invariant #7"],
    }),
  });
  const entries = buildSwarmTimelineEntries(report.events);
  assert.equal(entries.length, 3);
  const rows = scorecardToCriteriaRows(report.scorecard);
  assert.equal(rows.length, 2);
  assert.equal(rows.find((r) => r.criterion_id === "lead_quality")?.passed, true);
  assert.equal(rows.find((r) => r.criterion_id === "tone")?.passed, false);
  assert.equal(isGateBlocked(report.gate_decision), true);
  assert.equal(gateDecisionTone(report.gate_decision), "hot");
  assert.equal(scorecardPct(report.scorecard), 78);
});
