import assert from "node:assert/strict";
import test from "node:test";

import {
  buildFacultyLibrary,
  fetchMandateType,
  fetchMandateTypes,
  mapMandateType,
} from "../src/lib/api";
import type { MandateType } from "../src/lib/types";

// --- mapMandateType ------------------------------------------------------------------------

test("mapMandateType hydrates the 7 organs from a kernel payload (id+name+version+charter+faculties+...)", () => {
  const mapped = mapMandateType({
    id: "lead-finder",
    name: "Lead Finder",
    version: "0.3.1",
    charter: {
      goal: "Find B2B prospects that match the ICP and draft outreach.",
      preconditions: ["approved ICP target"],
      pathconditions: ["per-instance sender identity bound"],
      postconditions: ["qualified_lead facts committed to heap"],
      constraints: ["no money adapters"],
      target: { industry: "b2b-saas", region: "IN" },
    },
    faculties: [
      { faculty_name: "research", faculty_version: "1.4.0" },
      { faculty_name: "outreach", faculty_version: "2.1.0" },
    ],
    domain_pack: { name: "lead-finder-pack", version: "0.3.1", vertical: "b2b" },
    verification: {
      ladder: [
        { rung: "rules", present: true },
        { rung: "judge", present: true },
        { rung: "human", present: true },
        { rung: "reality", present: false },
      ],
      rules: ["icp-match"],
      rubrics: ["promptfoo/lead-finder-rubric@0.3.1"],
    },
    settlement: {
      fact_commit_confidence: 0.72,
      trust_on_success: 2,
      trust_on_failure: -2,
      watch_window_hours: 72,
      spawn_rules: [{ on_condition: "lead_qualified", child_type_ref: "creator@0.1.0" }],
    },
    gym_ref: { name: "lead_finder_gym", version: "0.3.1", status: "active" },
    execution: {
      routing: [
        { faculty_name: "research", harness: "exa+scrapingbee", model: "sonnet", budget: 0.4 },
        { faculty_name: "outreach", harness: "send_email", model: "sonnet", budget: 0.6 },
      ],
    },
    released_at: "2026-06-12T10:00:00+05:30",
    changelog: "Ship send-loop wiring.",
  });

  assert.equal(mapped.id, "lead-finder");
  assert.equal(mapped.type_ref, "Lead Finder@0.3.1");
  assert.equal(mapped.stage, "0.3.1");
  assert.equal(mapped.ring_floor, "L0");
  assert.equal(mapped.status, "ready");
  assert.equal(mapped.charter.goal.includes("Find B2B prospects"), true);
  assert.equal(mapped.charter.preconditions[0], "approved ICP target");
  assert.deepEqual(mapped.charter.target, { industry: "b2b-saas", region: "IN" });
  assert.equal(mapped.faculties.length, 2);
  // Faculty + execution joined: outreach gets the send_email harness from routing.
  const outreach = mapped.faculties.find((f) => f.faculty_name === "outreach");
  assert.ok(outreach);
  assert.equal(outreach?.harness, "send_email");
  assert.equal(outreach?.model, "sonnet");
  assert.equal(outreach?.budget, 0.6);
  assert.equal(mapped.verification.ladder.length, 4);
  assert.ok(mapped.verification.ladder.find((r) => r.rung === "rules"));
  assert.equal(mapped.settlement.trust_on_success, 2);
  assert.equal(mapped.settlement.spawn_rules[0].child_type_ref, "creator@0.1.0");
  assert.equal(mapped.gym_ref?.name, "lead_finder_gym");
  assert.equal(mapped.execution.routing.length, 2);
  assert.equal(mapped.versions[0].version, "0.3.1");
  assert.equal(mapped.versions[0].status, "live");
});

test("mapMandateType tolerates a legacy lean row (title + commands only)", () => {
  const mapped = mapMandateType({
    title: "Outbound SDR",
    commands: ["research", "outreach"],
  });
  assert.equal(mapped.id, "outbound-sdr");
  assert.equal(mapped.title, "Outbound SDR");
  assert.equal(mapped.type_ref, "outbound-sdr@0.1.0");
  assert.equal(mapped.faculties.length, 2);
  assert.equal(mapped.status, "ready");
  // Synthesized organs so the page renders.
  assert.equal(mapped.verification.ladder.length, 4);
  assert.equal(mapped.settlement.watch_window_hours, 72);
  assert.equal(mapped.versions[0].changelog.includes("synthesized"), true);
});

test("mapMandateType marks a gap status from the kernel payload", () => {
  const mapped = mapMandateType({
    title: "WhatsApp Follow-up",
    status: "gap",
    commands: ["send_whatsapp"],
  });
  assert.equal(mapped.status, "gap");
});

test("mapMandateType marks locked status when present", () => {
  const mapped = mapMandateType({
    title: "Money Desk",
    status: "locked",
    commands: ["settle_invoice"],
  });
  assert.equal(mapped.status, "locked");
});

// --- buildFacultyLibrary -------------------------------------------------------------------

test("buildFacultyLibrary de-duplicates by name+version across all mandate types", () => {
  const types: MandateType[] = [
    {
      ...mapMandateType({ title: "alpha", commands: ["research", "outreach"] }),
      faculties: [
        {
          faculty_name: "research",
          faculty_version: "1.0.0",
          harness: "sim",
          model: "—",
          budget: null,
        },
        {
          faculty_name: "outreach",
          faculty_version: "2.0.0",
          harness: "sim",
          model: "—",
          budget: null,
        },
      ],
    },
    {
      ...mapMandateType({ title: "beta", commands: ["research", "analysis"] }),
      faculties: [
        {
          faculty_name: "research",
          faculty_version: "1.0.0",
          harness: "sim",
          model: "—",
          budget: null,
        }, // duplicate
        {
          faculty_name: "analysis",
          faculty_version: "1.5.0",
          harness: "sim",
          model: "—",
          budget: null,
        },
      ],
    },
  ];
  const lib = buildFacultyLibrary(types);
  const keys = lib.map((entry) => `${entry.name}@${entry.version}`);
  assert.equal(new Set(keys).size, keys.length, "no duplicate faculty keys");
  assert.ok(keys.includes("research@1.0.0"));
  assert.ok(keys.includes("outreach@2.0.0"));
  assert.ok(keys.includes("analysis@1.5.0"));
});

// --- fetchMandateTypes / fetchMandateType -------------------------------------------------

test("fetchMandateTypes degrades to fixture when the kernel is unreachable", async () => {
  const result = await fetchMandateTypes({
    baseUrl: "http://127.0.0.1:1",
    fetcher: async () => {
      throw new Error("ECONNREFUSED");
    },
  });
  assert.equal(result.source, "fixture");
  assert.ok(result.data.length >= 1, "fixture has at least one mandate type");
  const leadFinder = result.data.find((m) => m.id === "lead-finder");
  assert.ok(leadFinder, "fixture includes lead-finder");
  assert.ok(leadFinder?.faculties.length >= 1);
});

test("fetchMandateTypes parses a kernel 200 envelope into the dashboard view", async () => {
  const fetcher = async () =>
    new Response(
      JSON.stringify({
        mandate_types: [
          {
            id: "lead-finder",
            name: "Lead Finder",
            version: "0.3.1",
            charter: { goal: "find leads" },
            faculties: [{ faculty_name: "research", faculty_version: "1.0.0" }],
            domain_pack: { name: "core", version: "0.1.0", vertical: "b2b" },
            verification: { ladder: [{ rung: "rules", present: true }] },
            settlement: { fact_commit_confidence: 0.6, watch_window_hours: 72 },
            gym_ref: null,
            execution: { routing: [] },
          },
        ],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  const result = await fetchMandateTypes({ baseUrl: "http://api.test", fetcher });
  assert.equal(result.source, "api");
  assert.equal(result.data.length, 1);
  assert.equal(result.data[0].type_ref, "Lead Finder@0.3.1");
});

test("fetchMandateType resolves by id or fully-qualified type_ref", async () => {
  const fetcher = async () =>
    new Response(
      JSON.stringify({
        mandate_types: [
          {
            id: "lead-finder",
            name: "Lead Finder",
            version: "0.3.1",
            charter: { goal: "x" },
            faculties: [],
            domain_pack: { name: "core", version: "0.1.0" },
            verification: { ladder: [] },
            settlement: { fact_commit_confidence: 0.5, watch_window_hours: 24 },
            gym_ref: null,
            execution: { routing: [] },
          },
        ],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  const byId = await fetchMandateType("lead-finder", { baseUrl: "http://api.test", fetcher });
  assert.equal(byId.data?.id, "lead-finder");

  const byRef = await fetchMandateType("Lead%20Finder%400.3.1", {
    baseUrl: "http://api.test",
    fetcher,
  });
  assert.equal(byRef.data?.id, "lead-finder");

  const missing = await fetchMandateType("does-not-exist", {
    baseUrl: "http://api.test",
    fetcher,
  });
  assert.equal(missing.data, null);
});