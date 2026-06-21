import assert from "node:assert/strict";
import test from "node:test";

import { mapCapabilitiesWithHealth, fetchCapabilitiesForProviders } from "../src/lib/api";

/**
 * C12 — Providers / Connectors view tests.
 *
 * The view is a pure consumer of the C11-extended /capabilities payload, so
 * most coverage lives at the mapper boundary. The mapper is the contract the
 * TSX renders against, and C11's three new top-level fields have to map into
 * the typed view model without crashing on missing sections.
 */

test("mapCapabilitiesWithHealth returns safe defaults when C11 sections are missing", () => {
  // Older backend (pre-C11) — no providers / transport / model_routing keys.
  const result = mapCapabilitiesWithHealth({ capabilities: [] });
  assert.deepEqual(result.providers, []);
  assert.equal(result.transport.configured, false);
  assert.equal(result.transport.name, null);
  assert.equal(result.transport.live_gated, false);
  // All keys are always present (consumers can read ``details.host`` without
  // a KeyError) but values are undefined when not provided.
  for (const key of ["host", "port", "username", "default_from", "from_name"]) {
    assert.equal(result.transport.details[key as keyof typeof result.transport.details], undefined);
  }
  assert.equal(result.model_routing.faculty_model.configured, false);
  assert.equal(result.model_routing.judge_model.configured, false);
  assert.ok(result.model_routing.checked_at);
});

test("mapCapabilitiesWithHealth maps per-provider reachability", () => {
  const result = mapCapabilitiesWithHealth({
    capabilities: [],
    providers: [
      { name: "exa", kind: "research", configured: true, reachable: true, error: null },
      {
        name: "firecrawl",
        kind: "research",
        configured: true,
        reachable: false,
        error: "timeout",
      },
      { name: "email", kind: "outbound", configured: false, reachable: false },
    ],
    transport: {},
    model_routing: {},
  });
  assert.equal(result.providers.length, 3);
  assert.equal(result.providers[0].name, "exa");
  assert.equal(result.providers[0].kind, "research");
  assert.equal(result.providers[0].configured, true);
  assert.equal(result.providers[0].reachable, true);
  assert.equal(result.providers[0].error, null);
  assert.equal(result.providers[1].error, "timeout");
  assert.equal(result.providers[2].kind, "outbound");
  // ``live_gated`` is only emitted for outbound providers; research providers
  // leave the field as ``undefined`` (the view's pill omits it).
  assert.equal(result.providers[2].live_gated, false);
  assert.equal(result.providers[0].live_gated, undefined);
});

test("mapCapabilitiesWithHealth maps email transport details (non-secret)", () => {
  const result = mapCapabilitiesWithHealth({
    capabilities: [],
    providers: [],
    transport: {
      configured: true,
      name: "smtp",
      live_gated: true,
      details: {
        host: "smtp.gmail.com",
        port: 587,
        username: "[email protected]",
        default_from: "[email protected]",
        from_name: "Agent-X",
      },
    },
    model_routing: {},
  });
  assert.equal(result.transport.configured, true);
  assert.equal(result.transport.name, "smtp");
  assert.equal(result.transport.live_gated, true);
  assert.equal(result.transport.details.host, "smtp.gmail.com");
  assert.equal(result.transport.details.port, 587);
  assert.equal(result.transport.details.username, "[email protected]");
  assert.equal(result.transport.details.default_from, "[email protected]");
  assert.equal(result.transport.details.from_name, "Agent-X");
});

test("mapCapabilitiesWithHealth maps model routing entries (faculty + judge)", () => {
  const result = mapCapabilitiesWithHealth({
    capabilities: [],
    providers: [],
    transport: {},
    model_routing: {
      faculty_model: {
        provider: "minimax",
        configured: true,
        base_url: "https://api.minimax.chat/v1",
        model_id: "minimax/MiniMax-M3",
      },
      judge_model: {
        via: "openrouter",
        configured: true,
        model_id: "openrouter/anthropic/claude-3.5-sonnet",
      },
      checked_at: "2026-06-21T18:00:00Z",
    },
  });
  assert.equal(result.model_routing.faculty_model.provider, "minimax");
  assert.equal(result.model_routing.faculty_model.configured, true);
  assert.equal(result.model_routing.faculty_model.base_url, "https://api.minimax.chat/v1");
  assert.equal(result.model_routing.faculty_model.model_id, "minimax/MiniMax-M3");
  assert.equal(result.model_routing.judge_model.via, "openrouter");
  assert.equal(result.model_routing.judge_model.model_id, "openrouter/anthropic/claude-3.5-sonnet");
  assert.equal(result.model_routing.checked_at, "2026-06-21T18:00:00Z");
});

test("mapCapabilitiesWithHealth coerces out-of-shape fields to safe defaults", () => {
  // Real backends sometimes return string booleans or nullish fields. The
  // mapper should never crash and should surface the operator's expected
  // shape regardless.
  const result = mapCapabilitiesWithHealth({
    capabilities: "not-an-array",
    providers: [
      { name: 42, kind: "made-up-kind", configured: "yes", reachable: 1, live_gated: "true" },
    ],
    transport: { configured: 1, name: "", live_gated: "false" },
    model_routing: { faculty_model: null, judge_model: {}, checked_at: "" },
  });
  // mapCapabilities tolerates a non-array by returning [] (it does not crash).
  assert.deepEqual(result.capabilities, []);
  assert.equal(result.providers.length, 1);
  assert.equal(result.providers[0].name, "42");
  assert.equal(result.providers[0].kind, "research"); // falls back to "research"
  assert.equal(result.providers[0].configured, false); // strict true required
  assert.equal(result.providers[0].reachable, false);
  // ``live_gated`` is only emitted for outbound providers. Here ``kind`` falls
  // back to research, so the field is undefined (not coerced).
  assert.equal(result.providers[0].live_gated, undefined);
  // Transport: configured=true (truthy), live_gated=false, name=null
  assert.equal(result.transport.configured, true);
  assert.equal(result.transport.name, null);
  assert.equal(result.transport.live_gated, false);
  // Model routing: faculty_model is null → defaults, judge_model is empty → configured=false
  assert.equal(result.model_routing.faculty_model.configured, false);
  assert.equal(result.model_routing.judge_model.configured, false);
  assert.ok(result.model_routing.checked_at); // falls back to epoch-zero ISO
});

test("fetchCapabilitiesForProviders falls back to fixtures when API errors", async () => {
  // Network failure → fetchJson returns the fixture sentinel + an error.
  // The mapper still produces a valid view model so the view can render the
  // "fixture" pill + the error state without crashing.
  const errorFetcher: typeof fetch = (async () => {
    throw new Error("offline");
  }) as unknown as typeof fetch;
  const result = await fetchCapabilitiesForProviders({
    baseUrl: "http://127.0.0.1:8000",
    fetcher: errorFetcher,
  });
  assert.equal(result.source, "fixture");
  assert.ok(result.error);
  assert.ok(Array.isArray(result.data.providers));
  assert.equal(result.data.transport.configured, false);
  assert.equal(result.data.model_routing.faculty_model.configured, false);
});

test("fetchCapabilitiesForProviders maps a live C11 response into the view model", async () => {
  const liveFetcher: typeof fetch = (async () =>
    new Response(
      JSON.stringify({
        capabilities: [],
        providers: [
          { name: "exa", kind: "research", configured: true, reachable: true },
        ],
        transport: {
          configured: true,
          name: "smtp",
          live_gated: true,
          details: { host: "smtp.example.com", port: 587 },
        },
        model_routing: {
          faculty_model: { provider: "minimax", configured: true, model_id: "minimax/M3" },
          judge_model: { via: "openrouter", configured: true, model_id: "openrouter/x" },
          checked_at: "2026-06-21T00:00:00Z",
        },
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    )) as unknown as typeof fetch;
  const result = await fetchCapabilitiesForProviders({
    baseUrl: "http://127.0.0.1:8000",
    fetcher: liveFetcher,
  });
  assert.equal(result.source, "api");
  assert.equal(result.data.providers.length, 1);
  assert.equal(result.data.providers[0].name, "exa");
  assert.equal(result.data.transport.configured, true);
  assert.equal(result.data.transport.details.host, "smtp.example.com");
  assert.equal(result.data.model_routing.faculty_model.model_id, "minimax/M3");
  assert.equal(result.data.model_routing.judge_model.via, "openrouter");
});
