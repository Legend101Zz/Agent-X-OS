import assert from "node:assert/strict";
import test from "node:test";

import { buildApiUrl, fetchJson, loadDashboardData, runSwarm } from "../src/lib/api";

test("buildApiUrl preserves path and omits empty query values", () => {
  const url = buildApiUrl("http://127.0.0.1:8000", "/runs", {
    state: "active",
    instance_id: "",
    limit: 25,
  });

  assert.equal(url, "http://127.0.0.1:8000/runs?state=active&limit=25");
});

test("fetchJson returns fixture data when the API fetch fails", async () => {
  const result = await fetchJson(
    "/health",
    { status: "fixture" },
    {
      baseUrl: "http://127.0.0.1:8000",
      fetcher: async () => {
        throw new Error("service offline");
      },
    },
  );

  assert.deepEqual(result.data, { status: "fixture" });
  assert.equal(result.source, "fixture");
  assert.equal(result.error, "service offline");
});

test("loadDashboardData maps the FastAPI envelope into dashboard view models", async () => {
  const fetcher = async (input: string | URL | Request) => {
    const url = new URL(String(input));
    const path = url.pathname;
    const payloads: Record<string, unknown> = {
      "/health": { ok: true, backend: "memory", ts: "2026-06-18T09:30:00Z" },
      "/system/overview": {
        system: "agent-x-os",
        counts: {
          instances: 1,
          live_runs: 0,
          parked_awaiting_approval: 1,
          settled: 1,
          manual_queue: 1,
        },
        rings: { L1: 1 },
        pnl: { total: 250, currency: "INR" },
        recent_events: [
          {
            event_id: "evt_1",
            kind: "run_parked",
            ts: "2026-06-18T09:20:00Z",
            actor: "kernel",
            instance_id: "inst_demo",
            run_id: "run_demo",
            reason: "approval needed",
          },
        ],
      },
      "/instances": {
        instances: [
          {
            instance: {
              id: "inst_demo",
              customer_id: "Orbit Dental Co",
              type_ref: "lead-finder@0.1.0",
              ring: "L1",
            },
            resume: { ring: "L1", trust_score: 7, counts: { settled: 1 } },
            approval_count: 1,
            billing_total: 250,
          },
        ],
      },
      "/runs": {
        runs: [
          {
            run_id: "run_demo",
            instance_id: "inst_demo",
            type_ref: "lead-finder@0.1.0",
            state: "parked",
            event_count: 4,
            updated_at: "2026-06-18T09:20:00Z",
            park: { reason: "approval needed", required_ring: "L2" },
          },
        ],
      },
      "/mandate-types": {
        mandate_types: [
          {
            id: "type_lead_finder_v0",
            name: "lead-finder",
            version: "0.1.0",
            charter: { goal: "Find leads", target: { icp: "clinics" } },
            faculties: [{ faculty_name: "research" }],
          },
        ],
      },
      "/journal": {
        events: [
          {
            event_id: "evt_1",
            kind: "run_parked",
            ts: "2026-06-18T09:20:00Z",
            actor: "kernel",
            instance_id: "inst_demo",
            run_id: "run_demo",
            reason: "approval needed",
          },
        ],
      },
      "/capabilities": {
        capabilities: [
          {
            name: "lead_research_batch",
            category: "research",
            maturity_level: 3,
            risk_class: "read",
            required_ring: "L0",
            tenant_auth: "api_key",
            is_terminal_fallback: false,
            health: { status: "ok", detail: "ready" },
            queue_volume: 0,
          },
        ],
      },
      "/eval-cases": {
        eval_cases: [
          {
            id: "eval_demo",
            type_ref: "lead-finder@0.1.0",
            origin: "synthetic",
            score: 0.74,
            passed: true,
            tags: ["indian_b2b_leads_v1"],
          },
        ],
      },
      "/manual-queue": {
        items: [
          {
            id: "manual_1",
            request_name: "queue_manual_action",
            args: { action: "review_lead", reason: "Need owner context" },
            instance_id: "inst_demo",
            run_id: "run_demo",
            created_at: "2026-06-18T09:10:00Z",
          },
        ],
      },
      "/core-gaps": {
        gaps: [{ id: "command.instantiate", title: "Instantiate missing", detail: "No command yet." }],
      },
    };

    return new Response(JSON.stringify(payloads[path]), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const { data, sources } = await loadDashboardData({ baseUrl: "http://api.test", fetcher });

  assert.equal(sources.instances.source, "api");
  assert.equal(data.health.status, "ok");
  assert.equal(data.overview.active_instances, 1);
  assert.equal(data.instances[0].id, "inst_demo");
  assert.equal(data.instances[0].trust_score, 7);
  assert.equal(data.runs[0].state, "parked");
  assert.equal(data.mandateTypes[0].title, "lead-finder");
  assert.equal(data.journal[0].title, "run_parked");
  assert.equal(data.capabilities[0].maturity, "live");
  assert.equal(data.manualQueue[0].title, "queue_manual_action");
  assert.equal(data.coreGaps[0].id, "command.instantiate");
});

test("runSwarm maps the swarm report into the timeline view model", async () => {
  const fetcher = async () =>
    new Response(
      JSON.stringify({
        supported: true,
        run_id: "run_sim_1",
        type_ref: "lead-finder@0.1.0",
        pack_id: "indian_b2b_leads_v1",
        eval_case_id: "eval_run_sim_1",
        trace: {
          run_id: "run_sim_1",
          events: [
            { seq: 0, ts: "2026-06-19T00:00:00Z", kind: "thought", summary: "hydrated", detail: {} },
            {
              seq: 1,
              ts: "2026-06-19T00:00:01Z",
              kind: "syscall_result",
              summary: "draft_email",
              detail: { fulfilled_by: "sim_adapter" },
            },
          ],
          scorecard: { run_id: "run_sim_1", score: 1, passed: true, origin: "synthetic" },
        },
        scorecard: {
          run_id: "run_sim_1",
          rubric_name: "lead_quality",
          score: 1,
          passed: true,
          origin: "synthetic",
          criteria: [{ criterion_id: "research", passed: true, score: 1, comment: "ok" }],
          failure_reasons: [],
          judge_comments: ["deterministic fallback"],
        },
        gate_decision: {
          allowed: false,
          reasons: ["synthetic-only evidence cannot promote customer-facing versions"],
          live_ring: null,
        },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );

  const result = await runSwarm(
    { type_ref: "lead-finder@0.1.0", pack_id: "indian_b2b_leads_v1", ring: "L2" },
    { baseUrl: "http://api.test", token: "swarm-token", fetcher },
  );

  assert.equal(result.source, "api");
  assert.equal(result.data.run_id, "run_sim_1");
  assert.equal(result.data.events.length, 2);
  assert.equal(result.data.events[1].kind, "syscall_result");
  assert.equal(result.data.events[1].summary, "draft_email");
  assert.equal(result.data.events[1].detail.fulfilled_by, "sim_adapter");
  assert.equal(result.data.scorecard?.passed, true);
  assert.equal(result.data.scorecard?.origin, "synthetic");
  assert.equal(result.data.gate_decision?.allowed, false);
  assert.equal(result.data.eval_case_id, "eval_run_sim_1");
});
