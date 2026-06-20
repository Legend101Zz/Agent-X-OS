import assert from "node:assert/strict";
import test from "node:test";

import {
  fetchApprovals,
  fetchCapabilities,
  fetchCoreGaps,
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