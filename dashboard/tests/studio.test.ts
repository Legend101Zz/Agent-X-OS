import assert from "node:assert/strict";
import test from "node:test";

import {
  approveRun,
  deriveSendPosture,
  instantiate,
  mapScoredLeads,
  triggerRun,
} from "../src/lib/api";
import type { Capability } from "../src/lib/types";

// --- instantiate -------------------------------------------------------------------------

test("instantiate maps the 201 envelope into an instance id", async () => {
  const fetcher = async () =>
    new Response(
      JSON.stringify({ supported: true, instance: { id: "inst_acme_123" }, mandate_id: "type_acme" }),
      { status: 201, headers: { "Content-Type": "application/json" } },
    );

  const result = await instantiate(
    { type_ref: "lead-finder@0.1.0", customer_id: "Acme", business_name: "Acme", ring: "L1", actor: "dashboard/operator" },
    { baseUrl: "http://api.test", token: "op-token", fetcher },
  );

  assert.equal(result.supported, true);
  assert.equal(result.instanceId, "inst_acme_123");
});

test("instantiate sends a bearer token and POSTs", async () => {
  let captured: RequestInit | undefined;
  const fetcher = async (_input: string | URL | Request, init?: RequestInit) => {
    captured = init;
    return new Response(JSON.stringify({ supported: true, instance: { id: "x" } }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  };

  await instantiate(
    { type_ref: "lead-finder@0.1.0", customer_id: "A", business_name: "A", ring: "L0", actor: "x" },
    { baseUrl: "http://api.test", token: "op-token", fetcher },
  );

  assert.equal(captured?.method, "POST");
  const headers = new Headers(captured?.headers);
  assert.equal(headers.get("Authorization"), "Bearer op-token");
});

test("instantiate surfaces the API error detail on a non-ok response", async () => {
  const fetcher = async () =>
    new Response(JSON.stringify({ detail: "unknown type_ref: bad@0.0.0" }), {
      status: 404,
      headers: { "Content-Type": "application/json" },
    });

  const result = await instantiate(
    { type_ref: "bad@0.0.0", customer_id: "A", business_name: "A", ring: "L0", actor: "x" },
    { baseUrl: "http://api.test", token: "op-token", fetcher },
  );

  assert.equal(result.supported, false);
  assert.equal(result.message, "unknown type_ref: bad@0.0.0");
});

test("instantiate fails closed without an operator token (never calls fetch)", async () => {
  const fetcher = async () => {
    throw new Error("fetch should not be called without a token");
  };

  const result = await instantiate(
    { type_ref: "lead-finder@0.1.0", customer_id: "A", business_name: "A", ring: "L0", actor: "x" },
    { baseUrl: "http://api.test", fetcher },
  );

  assert.equal(result.supported, false);
  assert.match(result.message ?? "", /token/i);
});

// --- triggerRun --------------------------------------------------------------------------

test("triggerRun maps the 202 envelope into a work id + status", async () => {
  const fetcher = async () =>
    new Response(JSON.stringify({ supported: true, work_id: "work_1", status: "queued" }), {
      status: 202,
      headers: { "Content-Type": "application/json" },
    });

  const result = await triggerRun(
    { instance_id: "inst_acme_123", mode: "sim", actor: "dashboard/operator" },
    { baseUrl: "http://api.test", token: "op-token", fetcher },
  );

  assert.equal(result.supported, true);
  assert.equal(result.workId, "work_1");
  assert.equal(result.status, "queued");
});

// --- approveRun --------------------------------------------------------------------------

test("approveRun maps the 202 approve envelope", async () => {
  const fetcher = async () =>
    new Response(
      JSON.stringify({ supported: true, decision: "approve", status: "queued", work_id: "work_2" }),
      { status: 202, headers: { "Content-Type": "application/json" } },
    );

  const result = await approveRun(
    { instance_id: "inst_acme_123", run_id: "run_1", actor: "dashboard/operator" },
    { baseUrl: "http://api.test", token: "op-token", fetcher },
  );

  assert.equal(result.supported, true);
  assert.equal(result.status, "queued");
  assert.equal(result.workId, "work_2");
});

// --- mapScoredLeads ----------------------------------------------------------------------

test("mapScoredLeads turns claimed_facts into scored leads with cited evidence", () => {
  const runDetail = {
    run: { run_id: "run_1" },
    claimed_facts: [
      {
        id: "fact_1",
        instance_id: "inst_acme_123",
        subject: "lead_orbit",
        predicate: "qualified_lead_score",
        object: "0.82",
        confidence: 0.82,
        source: "agent-inferred",
        provenance: {
          run_id: "run_1",
          evidence: ["https://orbit.example/careers", "syscall_trace:lead_research_batch"],
          note: "matched clinic ICP and expansion signal",
        },
        created_at: "2026-06-18T09:34:00Z",
      },
    ],
  };

  const leads = mapScoredLeads(runDetail);

  assert.equal(leads.length, 1);
  assert.equal(leads[0].lead, "lead_orbit");
  assert.equal(leads[0].predicate, "qualified_lead_score");
  assert.equal(leads[0].score, 0.82);
  assert.equal(leads[0].confidence, 0.82);
  assert.deepEqual(leads[0].evidence, [
    "https://orbit.example/careers",
    "syscall_trace:lead_research_batch",
  ]);
  assert.equal(leads[0].note, "matched clinic ICP and expansion signal");
});

test("mapScoredLeads falls back to confidence when the object is non-numeric", () => {
  const leads = mapScoredLeads({
    claimed_facts: [
      {
        subject: "lead_x",
        predicate: "is_qualified",
        object: "true",
        confidence: 0.6,
        provenance: { evidence: [] },
      },
    ],
  });

  assert.equal(leads.length, 1);
  assert.equal(leads[0].score, 0.6);
  assert.deepEqual(leads[0].evidence, []);
});

test("mapScoredLeads returns an empty array when there are no claimed facts", () => {
  assert.deepEqual(mapScoredLeads({ run: { run_id: "r" } }), []);
  assert.deepEqual(mapScoredLeads({}), []);
});

test("mapScoredLeads also reads an instance-detail 'facts' array (durable leads)", () => {
  // GET /instances/{id} returns committed HEAP_FACT docs under `facts` — same Fact shape as
  // a settled run's claimed_facts. The Studio reuses one mapper for both sources.
  const instanceDetail = {
    instance: { id: "inst_acme_123" },
    facts: [
      {
        subject: "lead_nova",
        predicate: "qualified_lead_score",
        object: "0.71",
        confidence: 0.71,
        provenance: { run_id: "run_2", evidence: ["https://nova.example/about"], note: "expansion signal" },
      },
    ],
  };

  const leads = mapScoredLeads(instanceDetail);

  assert.equal(leads.length, 1);
  assert.equal(leads[0].lead, "lead_nova");
  assert.equal(leads[0].score, 0.71);
  assert.deepEqual(leads[0].evidence, ["https://nova.example/about"]);
});

// --- deriveSendPosture -------------------------------------------------------------------

test("deriveSendPosture is live when a send_email adapter is registered", () => {
  const capabilities = [
    { id: "send_email", syscall: "send_email" },
    { id: "human_task", syscall: "human_task" },
  ] as unknown as Capability[];

  assert.equal(deriveSendPosture(capabilities), "live");
});

test("deriveSendPosture is staged when only the human_task tail is present", () => {
  const capabilities = [{ id: "human_task", syscall: "human_task" }] as unknown as Capability[];

  assert.equal(deriveSendPosture(capabilities), "staged");
});
