import assert from "node:assert/strict";
import test from "node:test";

import {
  fetchApprovals,
  fetchCapabilities,
  fetchCoreGaps,
  fetchEconomy,
  fetchEconomyUnits,
  fetchEvalCases,
  fetchInstances,
  fetchMandateTypes,
  fetchSystemOverview,
} from "../src/lib/api";

const fixtureFetcher: typeof fetch = (async () =>
  new Response(JSON.stringify({ ok: true }), { status: 200 })) as unknown as typeof fetch;

const errorFetcher: typeof fetch = (async () => {
  throw new Error("offline");
}) as unknown as typeof fetch;

test("fetchSystemOverview returns fixture fallback when API errors", async () => {
  const result = await fetchSystemOverview({
    baseUrl: "http://127.0.0.1:8000",
    fetcher: errorFetcher,
  });
  assert.equal(result.source, "fixture");
  assert.ok(result.error);
});

test("fetchInstances preserves the new focused fetcher shape", async () => {
  const result = await fetchInstances({
    baseUrl: "http://127.0.0.1:8000",
    fetcher: errorFetcher,
  });
  assert.equal(result.source, "fixture");
  assert.ok(Array.isArray(result.data));
});

test("fetchApprovals accepts instance_id query and degrades cleanly", async () => {
  const result = await fetchApprovals(
    { instance_id: "inst_test" },
    { baseUrl: "http://127.0.0.1:8000", fetcher: errorFetcher },
  );
  assert.equal(result.source, "fixture");
  assert.deepEqual(result.data, []);
});

test("fetchEconomy maps the C15 per-instance P&L envelope", async () => {
  const seen: string[] = [];
  const fetcher: typeof fetch = (async (input: string | URL | Request) => {
    const url = new URL(String(input));
    seen.push(`${url.pathname}?${url.searchParams.toString()}`);
    return new Response(JSON.stringify({
      instance_id: "inst_demo",
      billing_total: 250,
      currency: "INR",
      settled_count: 1,
      trust_score: 7,
      settlements: [{ run_id: "run_demo_settled", amount: 250, ts: "2026-06-18T09:36:00Z" }],
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as unknown as typeof fetch;

  const result = await fetchEconomy({ instance_id: "inst_demo" }, { baseUrl: "http://api.test", fetcher });

  assert.equal(result.source, "api");
  assert.deepEqual(seen, ["/economy?instance_id=inst_demo"]);
  assert.equal(result.data.instance_id, "inst_demo");
  assert.equal(result.data.billing_total, 250);
  assert.equal(result.data.currency, "INR");
  assert.equal(result.data.settled_count, 1);
  assert.equal(result.data.trust_score, 7);
  assert.equal(result.data.settlements[0].run_id, "run_demo_settled");
});

test("fetchEconomyUnits maps the C15 business-unit rollup", async () => {
  const fetcher: typeof fetch = (async () =>
    new Response(JSON.stringify({
      units: [
        {
          customer_id: "Orbit Dental Co",
          instance_count: 2,
          instance_ids: ["inst_a", "inst_b"],
          billing_total: 425,
          settled_count: 2,
          trust_score: 3,
          currency: "INR",
        },
      ],
      totals: { billing_total: 425, settled_count: 2, currency: "INR" },
    }), { status: 200, headers: { "Content-Type": "application/json" } })) as unknown as typeof fetch;

  const result = await fetchEconomyUnits({ baseUrl: "http://api.test", fetcher });

  assert.equal(result.source, "api");
  assert.equal(result.data.totals.billing_total, 425);
  assert.equal(result.data.totals.settled_count, 2);
  assert.equal(result.data.units[0].customer_id, "Orbit Dental Co");
  assert.deepEqual(result.data.units[0].instance_ids, ["inst_a", "inst_b"]);
});

test("economy fetchers degrade to typed empty envelopes", async () => {
  const opts = { baseUrl: "http://127.0.0.1:8000", fetcher: errorFetcher };

  const perInstance = await fetchEconomy({ instance_id: "inst_missing" }, opts);
  const units = await fetchEconomyUnits(opts);

  assert.equal(perInstance.source, "fixture");
  assert.equal(perInstance.data.missing, true);
  assert.equal(perInstance.data.instance_id, "inst_missing");
  assert.deepEqual(perInstance.data.settlements, []);
  assert.equal(units.source, "fixture");
  assert.deepEqual(units.data.units, []);
  assert.deepEqual(units.data.totals, { billing_total: 0, settled_count: 0, currency: "INR" });
});

test("fetchCapabilities / fetchCoreGaps / fetchEvalCases / fetchMandateTypes degrade", async () => {
  const opts = { baseUrl: "http://127.0.0.1:8000", fetcher: errorFetcher };
  const caps = await fetchCapabilities(opts);
  const gaps = await fetchCoreGaps(opts);
  const cases = await fetchEvalCases(opts);
  const types = await fetchMandateTypes(opts);
  for (const r of [caps, gaps, cases, types]) {
    assert.equal(r.source, "fixture");
    assert.ok(r.error);
  }
});

// Use the fixtureFetcher to silence the "unused" warning until/unless we
// add live-mode coverage later.
test("fixtureFetcher smoke (does not throw)", async () => {
  const res = await fixtureFetcher("http://127.0.0.1:8000/health");
  assert.ok(res.ok);
});