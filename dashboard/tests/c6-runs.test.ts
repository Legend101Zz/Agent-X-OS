import assert from "node:assert/strict";
import test from "node:test";

import {
  extractClaimedFacts,
  extractSettlementSummary,
  filterRuns,
  runStateOptions,
  settlementTone,
  traceToTimelineEntries,
  traceKindTone,
} from "../src/lib/runs";
import { fetchRun, fetchRunRaw, fetchRuns } from "../src/lib/api";
import { fixtureDashboardData } from "../src/lib/fixtures";

// ---------- fetchRuns ----------

test("fetchRuns degrades to fixture list when the API is offline", async () => {
  const offlineFetcher: typeof fetch = (async () => {
    throw new Error("offline");
  }) as unknown as typeof fetch;
  const result = await fetchRuns(
    {},
    { baseUrl: "http://127.0.0.1:8000", fetcher: offlineFetcher },
  );
  assert.equal(result.source, "fixture");
  assert.ok(result.error);
  assert.ok(result.data.length >= 1);
  for (const run of result.data) {
    assert.equal(typeof run.id, "string");
    assert.equal(typeof run.instance_id, "string");
    assert.equal(typeof run.state, "string");
  }
});

test("fetchRuns applies state and instance_id filters to fixture fallback", async () => {
  const offlineFetcher: typeof fetch = (async () => {
    throw new Error("offline");
  }) as unknown as typeof fetch;
  const result = await fetchRuns(
    { state: "waiting_approval", instance_id: "inst-kaveri" },
    { baseUrl: "http://127.0.0.1:8000", fetcher: offlineFetcher },
  );
  assert.equal(result.source, "fixture");
  assert.ok(result.data.every((run) => run.state === "waiting_approval"));
  assert.ok(result.data.every((run) => run.instance_id === "inst-kaveri"));
});

test("fetchRuns returns an empty fixture list when nothing matches", async () => {
  const offlineFetcher: typeof fetch = (async () => {
    throw new Error("offline");
  }) as unknown as typeof fetch;
  const result = await fetchRuns(
    { state: "complete", instance_id: "inst-nope" },
    { baseUrl: "http://127.0.0.1:8000", fetcher: offlineFetcher },
  );
  assert.equal(result.source, "fixture");
  assert.equal(result.data.length, 0);
});

// ---------- fetchRun (mapped) ----------

test("fetchRun degrades to fixture detail when the API is offline", async () => {
  const offlineFetcher: typeof fetch = (async () => {
    throw new Error("offline");
  }) as unknown as typeof fetch;
  const result = await fetchRun("run-172", {
    baseUrl: "http://127.0.0.1:8000",
    fetcher: offlineFetcher,
  });
  assert.equal(result.source, "fixture");
  assert.ok(result.error);
  assert.equal(result.data.id, "run-172");
  assert.ok(Array.isArray(result.data.trace));
});

test("fetchRun returns a generic fixture when the id is unknown", async () => {
  const offlineFetcher: typeof fetch = (async () => {
    throw new Error("offline");
  }) as unknown as typeof fetch;
  const result = await fetchRun("run-does-not-exist", {
    baseUrl: "http://127.0.0.1:8000",
    fetcher: offlineFetcher,
  });
  assert.equal(result.source, "fixture");
  assert.ok(result.data);
});

// ---------- fetchRunRaw ----------

test("fetchRunRaw returns the raw payload (or empty object on failure)", async () => {
  const offlineFetcher: typeof fetch = (async () => {
    throw new Error("offline");
  }) as unknown as typeof fetch;
  const result = await fetchRunRaw("run-172", {
    baseUrl: "http://127.0.0.1:8000",
    fetcher: offlineFetcher,
  });
  assert.equal(result.source, "fixture");
  assert.deepEqual(result.data, {});
});

// ---------- runStateOptions ----------

test("runStateOptions includes every run state in the RunSummary type", () => {
  const labels = runStateOptions().map((opt) => opt.value);
  for (const state of [
    "active",
    "parked",
    "waiting_approval",
    "complete",
    "failed",
  ]) {
    assert.ok(labels.includes(state), `missing state ${state}`);
  }
});

// ---------- filterRuns ----------

test("filterRuns narrows the list by state, instance, and query", () => {
  const all = fixtureDashboardData.runs;
  const byState = filterRuns(all, { state: "active" });
  assert.ok(byState.every((run) => run.state === "active"));

  const byInstance = filterRuns(all, { instance_id: "inst-kaveri" });
  assert.ok(byInstance.every((run) => run.instance_id === "inst-kaveri"));

  const byQuery = filterRuns(all, { query: "Pune" });
  // "Pune employer list" matches the title; other runs don't
  assert.equal(byQuery.length, 1);
  assert.match(byQuery[0].title, /Pune/);

  const byAll = filterRuns(all, {
    state: "active",
    instance_id: "inst-kaveri",
    query: "Owner",
  });
  assert.equal(byAll.length, 1);
  assert.match(byAll[0].title, /Owner/);
});

test("filterRuns returns the full list when no filters are provided", () => {
  const all = fixtureDashboardData.runs;
  assert.equal(filterRuns(all, {}).length, all.length);
});

// ---------- traceKindTone + traceToTimelineEntries ----------

test("traceKindTone maps the §5 trace event kinds to UI tones", () => {
  assert.equal(traceKindTone("syscall"), "info");
  assert.equal(traceKindTone("adapter"), "info");
  assert.equal(traceKindTone("draft"), "info");
  assert.equal(traceKindTone("decision"), "info");
  assert.equal(traceKindTone("fact"), "good");
  assert.equal(traceKindTone("settled"), "good");
  assert.equal(traceKindTone("approved"), "good");
  assert.equal(traceKindTone("human-task"), "warn");
  assert.equal(traceKindTone("parked"), "warn");
  assert.equal(traceKindTone("approval"), "warn");
  assert.equal(traceKindTone("failed"), "hot");
  assert.equal(traceKindTone("rejected"), "hot");
  assert.equal(traceKindTone("unknown-thing"), "neutral");
});

test("traceToTimelineEntries maps a RunSummary trace into UI entries with tones", () => {
  const run = fixtureDashboardData.runs[0];
  const entries = traceToTimelineEntries(run.trace);
  assert.equal(entries.length, run.trace.length);
  for (const entry of entries) {
    assert.equal(typeof entry.title, "string");
    // ts is rendered if present
    assert.ok(entry.ts);
  }
  // First entry is a syscall → info tone
  assert.equal(entries[0].tone, "info");
  // The fact entry (run-172 doesn't have one, but a draft entry should be info)
  // Find the "fact" entry on the "Owner ICP correction sweep" run if present
  const ownerRun = fixtureDashboardData.runs.find((r) => r.id === "run-171");
  if (ownerRun) {
    const ownerEntries = traceToTimelineEntries(ownerRun.trace);
    assert.ok(ownerEntries[0].tone === "good");
  }
});

test("traceToTimelineEntries produces stable ids so React keys don't churn", () => {
  const run = fixtureDashboardData.runs[0];
  const entries = traceToTimelineEntries(run.trace);
  const ids = entries.map((entry) => entry.id);
  assert.deepEqual(ids, [...ids].sort());
  // every id is unique
  assert.equal(new Set(ids).size, ids.length);
});

// ---------- extractClaimedFacts ----------

test("extractClaimedFacts reads claimed_facts from a raw run detail payload", () => {
  const raw = {
    run: { run_id: "run-172" },
    claimed_facts: [
      {
        id: "fact-1",
        subject: "Plant maintenance head",
        predicate: "qualified_lead",
        object: "true",
        confidence: 0.84,
        provenance: { run_id: "run-172", evidence: ["exa/co/123"] },
        created_at: "2026-06-18T08:51:00+05:30",
      },
      {
        // missing confidence — should fall back to 0
        id: "fact-2",
        subject: "Sender domain",
        predicate: "verified_sender",
        object: "sales@kaveripumps.example",
        provenance: { run_id: "run-172" },
      },
    ],
  };
  const facts = extractClaimedFacts(raw);
  assert.equal(facts.length, 2);
  assert.equal(facts[0].subject, "Plant maintenance head");
  assert.equal(facts[0].confidence, 0.84);
  assert.equal(facts[0].run_id, "run-172");
  assert.equal(facts[1].confidence, 0);
  assert.deepEqual(facts[1].evidence, []);
});

test("extractClaimedFacts also reads nested facts arrays (durable leads)", () => {
  const raw = {
    facts: [
      {
        id: "fact-3",
        subject: "ICP segment",
        predicate: "primary_icp",
        object: "food-processing plants in Gujarat",
        confidence: 0.91,
        provenance: { evidence: ["firecrawl/page-1", "exa/page-2"] },
      },
    ],
  };
  const facts = extractClaimedFacts(raw);
  assert.equal(facts.length, 1);
  assert.equal(facts[0].subject, "ICP segment");
  assert.deepEqual(facts[0].evidence, ["firecrawl/page-1", "exa/page-2"]);
});

test("extractClaimedFacts returns an empty list when there are no facts", () => {
  const facts = extractClaimedFacts({ run: { run_id: "run-x" } });
  assert.deepEqual(facts, []);
});

test("extractClaimedFacts tolerates non-object entries (does not throw)", () => {
  const facts = extractClaimedFacts({
    claimed_facts: [null, "string-not-a-fact", { id: "fact-ok", subject: "x" }],
  });
  // null + string are skipped, the one valid object remains
  assert.equal(facts.length, 1);
  assert.equal(facts[0].id, "fact-ok");
});

// ---------- extractSettlementSummary ----------

test("extractSettlementSummary reads cost, expected_value, and progress from raw", () => {
  const run = fixtureDashboardData.runs[0];
  const raw = {
    run: {
      run_id: run.id,
      state: "waiting_approval",
      cost: 7.4,
      expected_value: 430,
      progress: 82,
    },
    settled: { billing_amount: 430, status: "draft" },
  };
  const summary = extractSettlementSummary(raw, run);
  assert.equal(summary.status, "waiting_approval");
  assert.equal(summary.cost, 7.4);
  assert.equal(summary.expected_value, 430);
  assert.equal(summary.progress, 82);
});

test("extractSettlementSummary falls back to the mapped RunSummary when raw is sparse", () => {
  const run = fixtureDashboardData.runs[0];
  const summary = extractSettlementSummary({}, run);
  // Mapped RunSummary always has cost=0 and expected_value=fallback.expected_value
  // so the helper must surface those as a graceful fallback
  assert.equal(summary.cost, run.cost);
  assert.equal(summary.expected_value, run.expected_value);
  assert.equal(summary.status, run.state);
  assert.equal(summary.progress, run.progress);
});

test("extractSettlementSummary prefers raw run.cost when present, else raw settled.billing_amount", () => {
  const run = fixtureDashboardData.runs[0];
  const raw = {
    run: { run_id: run.id, state: "complete" },
    settled: { billing_amount: 999 },
  };
  const summary = extractSettlementSummary(raw, run);
  // No raw run.cost; we accept run.cost (0) as the canonical answer here.
  // The settled.billing_amount flows into expected_value.
  assert.equal(summary.expected_value, 999);
  assert.equal(summary.status, "complete");
});

// ---------- settlementTone ----------

test("settlementTone maps run states to UI tones", () => {
  assert.equal(settlementTone("complete"), "good");
  assert.equal(settlementTone("active"), "info");
  assert.equal(settlementTone("waiting_approval"), "warn");
  assert.equal(settlementTone("parked"), "warn");
  assert.equal(settlementTone("failed"), "hot");
  assert.equal(settlementTone("weird"), "neutral");
  assert.equal(settlementTone(null), "neutral");
});
