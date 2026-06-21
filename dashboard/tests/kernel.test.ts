import assert from "node:assert/strict";
import test from "node:test";

import {
  fetchKernelSnapshot,
  fetchSchedulerWork,
  fetchSystemInfo,
  fetchSystemJournal,
  mapSchedulerWorkList,
  mapSystemInfo,
  type KernelSnapshot,
  type SystemInfo,
} from "../src/lib/api";
import type { ApiResult } from "../src/lib/types";
import {
  backendTone,
  formatAttempts,
  healthStatusTone,
  kernelHealthTone,
  schedulerKindTone,
  schedulerStatusLabel,
  schedulerStatusTone,
} from "../src/lib/format";

// =============================================================================
// Format helpers — pure functions, no API calls.
// =============================================================================

test("schedulerStatusTone maps kernel scheduler states", () => {
  assert.equal(schedulerStatusTone("pending"), "info");
  assert.equal(schedulerStatusTone("claimed"), "warn");
  assert.equal(schedulerStatusTone("completed"), "good");
  assert.equal(schedulerStatusTone("failed"), "hot");
  assert.equal(schedulerStatusTone(undefined), "neutral");
  assert.equal(schedulerStatusTone("unknown_state"), "neutral");
});

test("schedulerStatusLabel is human-readable", () => {
  assert.equal(schedulerStatusLabel("pending"), "Pending");
  assert.equal(schedulerStatusLabel("claimed"), "Claimed");
  assert.equal(schedulerStatusLabel("completed"), "Completed");
  assert.equal(schedulerStatusLabel("failed"), "Failed");
  assert.equal(schedulerStatusLabel(undefined), "—");
});

test("schedulerKindTone distinguishes trigger vs approval", () => {
  assert.equal(schedulerKindTone("trigger"), "info");
  assert.equal(schedulerKindTone("approval"), "warn");
  assert.equal(schedulerKindTone(undefined), "neutral");
});

test("formatAttempts is 'n' on 1, plural otherwise", () => {
  assert.equal(formatAttempts(0), "0 attempts");
  assert.equal(formatAttempts(1), "1 attempt");
  assert.equal(formatAttempts(3), "3 attempts");
  assert.equal(formatAttempts(undefined), "—");
});

test("healthStatusTone maps kernel health values", () => {
  assert.equal(healthStatusTone("ok"), "good");
  assert.equal(healthStatusTone("healthy"), "good");
  assert.equal(healthStatusTone("degraded"), "warn");
  assert.equal(healthStatusTone("queued"), "warn");
  assert.equal(healthStatusTone("down"), "hot");
  assert.equal(healthStatusTone("failed"), "hot");
  assert.equal(healthStatusTone(undefined), "neutral");
});

test("backendTone reports backend health at a glance", () => {
  assert.equal(backendTone("memory"), "good"); // local in-memory backend always healthy
  assert.equal(backendTone("mongo"), "good");
  assert.equal(backendTone(undefined), "muted");
});

test("kernelHealthTone is the safe top-level summary for the Kernel view header", () => {
  // ok + backend present → good
  assert.equal(kernelHealthTone({ ok: true, backend: "mongo", mode: "live" }), "good");
  // !ok + mode disconnected → warn (degraded but reachable)
  assert.equal(kernelHealthTone({ ok: false, backend: "mongo", mode: "disconnected" }), "warn");
  // falsy backend → hot (kernel unreachable)
  assert.equal(kernelHealthTone({ ok: false, backend: undefined, mode: "disconnected" }), "hot");
});

// =============================================================================
// Mappers — kernel-specific JSON shapes the API returns.
// =============================================================================

test("mapSystemInfo normalises the /system/info envelope", () => {
  const mapped: SystemInfo = mapSystemInfo({
    service: "agentx-operator-api",
    internal_only: true,
    posture: "local-only",
    command_auth_configured: true,
    fixtures_allowed: false,
    backend: "memory",
  });
  assert.equal(mapped.service, "agentx-operator-api");
  assert.equal(mapped.posture, "local-only");
  assert.equal(mapped.backend, "memory");
  assert.equal(mapped.commandAuthConfigured, true);
  assert.equal(mapped.fixturesAllowed, false);

  // Tolerate missing fields (fixture / cold start).
  const fallback: SystemInfo = mapSystemInfo({});
  assert.equal(fallback.service, "agentx-kernel-api");
  assert.equal(fallback.backend, "memory");
  assert.equal(fallback.commandAuthConfigured, false);
});

test("mapSchedulerWorkList unwraps {work,count} and tolerates {items}", () => {
  const workRows: Record<string, unknown>[] = [
    {
      work_id: "wkr_abc123",
      kind: "trigger",
      status: "pending",
      attempts: 0,
      available_at: "2026-06-21T18:00:00Z",
      run_id: "run_xyz",
      instance_id: "inst_test",
      type_ref: "indian_b2b_lead_finder",
      updated_at: "2026-06-21T18:00:00Z",
    },
    {
      work_id: "wkr_def456",
      kind: "approval",
      status: "completed",
      attempts: 1,
      available_at: "2026-06-21T17:59:00Z",
      run_id: "run_abc",
      instance_id: "inst_test",
      type_ref: "indian_b2b_lead_finder",
      updated_at: "2026-06-21T17:59:30Z",
    },
  ];

  const fromEnveloped = mapSchedulerWorkList({ work: workRows, count: 2 });
  assert.equal(fromEnveloped.length, 2);
  assert.equal(fromEnveloped[0].workId, "wkr_abc123");
  assert.equal(fromEnveloped[0].kind, "trigger");
  assert.equal(fromEnveloped[1].status, "completed");

  // Backend sometimes returns `{items: [...]}` for symmetry — we accept both.
  const fromItems = mapSchedulerWorkList({ items: workRows });
  assert.equal(fromItems.length, 2);

  // Missing rows → empty list, never raise.
  const empty = mapSchedulerWorkList({ work: [], count: 0 });
  assert.deepEqual(empty, []);
  const noKey = mapSchedulerWorkList({});
  assert.deepEqual(noKey, []);
});

// =============================================================================
// Focused fetchers — graceful disable (fail-soft to fixture/empty) and
// the exact query strings the kernel endpoints expect.
// =============================================================================

const offlineFetcher: typeof fetch = (async () => {
  throw new Error("kernel offline");
}) as unknown as typeof fetch;

const liveFetcher = ((url: string | URL | Request) => {
  const u = String(url);
  if (u.endsWith("/system/info")) {
    return Promise.resolve(
      new Response(
        JSON.stringify({
          service: "agentx-operator-api",
          internal_only: true,
          posture: "local-only",
          command_auth_configured: true,
          fixtures_allowed: false,
          backend: "memory",
        }),
        { status: 200 },
      ),
    );
  }
  if (u.endsWith("/health")) {
    return Promise.resolve(new Response(JSON.stringify({ ok: true, backend: "memory" }), { status: 200 }));
  }
  if (u.includes("/scheduler-work") && !u.includes("/wkr_")) {
    return Promise.resolve(
      new Response(
        JSON.stringify({
          work: [
            {
              work_id: "wkr_live_1",
              kind: "trigger",
              status: "pending",
              attempts: 0,
              available_at: "2026-06-21T18:00:00Z",
              run_id: "run_live",
              instance_id: "inst_live",
              type_ref: "indian_b2b_lead_finder",
              updated_at: "2026-06-21T18:00:00Z",
            },
          ],
          count: 1,
        }),
        { status: 200 },
      ),
    );
  }
  if (u.endsWith("/scheduler-work/wkr_live_1")) {
    return Promise.resolve(
      new Response(
        JSON.stringify({
          work: {
            work_id: "wkr_live_1",
            kind: "trigger",
            status: "pending",
            attempts: 0,
            available_at: "2026-06-21T18:00:00Z",
            run_id: "run_live",
            instance_id: "inst_live",
            type_ref: "indian_b2b_lead_finder",
            updated_at: "2026-06-21T18:00:00Z",
          },
        }),
        { status: 200 },
      ),
    );
  }
  if (u.includes("/journal")) {
    return Promise.resolve(
      new Response(
        JSON.stringify({
          events: [
            {
              event_id: "evt_1",
              kind: "manager_action",
              seq: 1,
              ts: "2026-06-21T18:00:00Z",
              instance_id: "inst_test",
              run_id: "run_test",
              actor: "kernel",
              action: "trigger_run",
            },
          ],
        }),
        { status: 200 },
      ),
    );
  }
  if (u.includes("/system/overview")) {
    return Promise.resolve(
      new Response(
        JSON.stringify({
          backend: "memory",
          counts: { instances: 1, live_runs: 0, parked_awaiting_approval: 0, settled: 0, manual_queue: 0 },
          rings: { assist: 1 },
          pnl: { total: 0, currency: "INR" },
          recent_events: [],
        }),
        { status: 200 },
      ),
    );
  }
  if (u.includes("/core-gaps")) {
    return Promise.resolve(
      new Response(JSON.stringify({ gaps: [{ id: "gap-x", title: "demo", detail: "demo detail" }] }), {
        status: 200,
      }),
    );
  }
  return Promise.resolve(new Response("not found", { status: 404 }));
}) as unknown as typeof fetch;

const liveOpts = { baseUrl: "http://127.0.0.1:8000", fetcher: liveFetcher };

test("fetchSystemInfo degrades to fixture on offline", async () => {
  const result: ApiResult<SystemInfo> = await fetchSystemInfo({
    baseUrl: "http://127.0.0.1:8000",
    fetcher: offlineFetcher,
  });
  assert.equal(result.source, "fixture");
  assert.ok(result.error);
});

test("fetchSystemInfo maps the live /system/info body", async () => {
  const result: ApiResult<SystemInfo> = await fetchSystemInfo(liveOpts);
  assert.equal(result.source, "api");
  assert.equal(result.data.backend, "memory");
  assert.equal(result.data.commandAuthConfigured, true);
});

test("fetchSchedulerWork unwraps {work: {...}} on detail endpoint", async () => {
  const result = await fetchSchedulerWork("wkr_live_1", liveOpts);
  assert.equal(result.source, "api");
  assert.equal(result.data.work_id, "wkr_live_1");
});

test("fetchSystemJournal maps /journal envelope and degrades cleanly", async () => {
  const live = await fetchSystemJournal({ limit: 10 }, liveOpts);
  assert.equal(live.source, "api");
  assert.equal(live.data.length, 1);
  assert.equal(live.data[0].kind, "manager_action");

  const offline = await fetchSystemJournal({ limit: 10 }, {
    baseUrl: "http://127.0.0.1:8000",
    fetcher: offlineFetcher,
  });
  assert.equal(offline.source, "fixture");
});

test("fetchKernelSnapshot aggregates overview + scheduler + core-gaps", async () => {
  const result: ApiResult<KernelSnapshot> = await fetchKernelSnapshot(liveOpts);
  assert.equal(result.source, "api");
  assert.ok(result.data.overview);
  assert.equal(result.data.schedulerWork.length, 1);
  assert.equal(result.data.schedulerWork[0].workId, "wkr_live_1");
  assert.equal(result.data.coreGaps.length, 1);
  assert.equal(result.data.fetchedAt.length > 0, true);

  const offline = await fetchKernelSnapshot({
    baseUrl: "http://127.0.0.1:8000",
    fetcher: offlineFetcher,
  });
  assert.equal(offline.source, "fixture");
  // Offline → empty scheduler + gaps (not the fixture data) so the Kernel view
  // renders EmptyState on a cold install, never stale fixture rows.
  assert.deepEqual(offline.data.schedulerWork, []);
  assert.deepEqual(offline.data.coreGaps, []);
});
