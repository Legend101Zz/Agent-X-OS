import {
  fixtureDashboardData,
  getCoreGap,
  getFixtureInstance,
  getFixtureRun,
} from "./fixtures";
import type {
  ApiResult,
  ApprovalCard,
  ApprovePayload,
  ApproveResult,
  Capability,
  CapabilitiesWithHealth,
  CommandPayload,
  CommandResult,
  CoreGap,
  DashboardData,
  EmailTransportDetails,
  EvalCase,
  Fact,
  HealthStatus,
  InstantiatePayload,
  InstantiateResult,
  InstanceSummary,
  JournalEvent,
  GateDecisionView,
  MandateType,
  ManualTask,
  ModelRoutingEntry,
  ModelRoutingStatus,
  ProviderReachability,
  RejectPayload,
  RunSummary,
  RunSwarmPayload,
  ScoredLead,
  SchedulerWork,
  ScorecardView,
  SendPosture,
  SetRingPayload,
  SwarmRunReport,
  SwarmTraceEvent,
  SystemOverview,
  TimelineEntry,
  TransportStatus,
  TriggerRunPayload,
  TriggerRunResult,
} from "./types";

type QueryValue = string | number | boolean | null | undefined;

interface RequestOptions {
  baseUrl?: string;
  query?: Record<string, QueryValue>;
  init?: RequestInit;
  fetcher?: typeof fetch;
}

export const DEFAULT_API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export function buildApiUrl(
  baseUrl: string,
  path: string,
  query: Record<string, QueryValue> = {},
): string {
  const url = new URL(path, baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`);

  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    url.searchParams.set(key, String(value));
  });

  return url.toString();
}

const getErrorMessage = (error: unknown): string =>
  error instanceof Error ? error.message : "API request failed";

export async function fetchJson<T>(
  path: string,
  fallback: T,
  options: RequestOptions = {},
): Promise<ApiResult<T>> {
  const {
    baseUrl = DEFAULT_API_BASE_URL,
    query,
    init,
    fetcher = fetch,
  } = options;

  try {
    const response = await fetcher(buildApiUrl(baseUrl, path, query), {
      cache: "no-store",
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });

    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`.trim());
    }

    return { data: (await response.json()) as T, source: "api" };
  } catch (error) {
    return { data: fallback, source: "fixture", error: getErrorMessage(error) };
  }
}

export interface LiveOptions {
  /** When true, treat any fetch error as a blocking disconnected state (live-mode fail-closed). */
  live?: boolean;
}

export async function fetchJsonStrict<T>(
  path: string,
  options: RequestOptions = {},
): Promise<ApiResult<T>> {
  const {
    baseUrl = DEFAULT_API_BASE_URL,
    query,
    init,
    fetcher = fetch,
  } = options;

  try {
    const response = await fetcher(buildApiUrl(baseUrl, path, query), {
      cache: "no-store",
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });

    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`.trim());
    }

    return { data: (await response.json()) as T, source: "api" };
  } catch (error) {
    return { data: undefined as unknown as T, source: "fixture", error: getErrorMessage(error) };
  }
}

export async function loadDashboardData(
  options: RequestOptions = {},
): Promise<{ data: DashboardData; sources: Record<keyof DashboardData, ApiResult<unknown>> }> {
  const entries = await Promise.all([
    fetchJson("/health", fixtureDashboardData.health, options),
    fetchJson("/system/overview", fixtureDashboardData.overview, options),
    fetchJson("/instances", fixtureDashboardData.instances, options),
    fetchJson("/runs", fixtureDashboardData.runs, options),
    fetchJson("/mandate-types", fixtureDashboardData.mandateTypes, options),
    fetchJson("/journal", fixtureDashboardData.journal, {
      ...options,
      query: { limit: 30 },
    }),
    fetchJson("/capabilities", fixtureDashboardData.capabilities, options),
    fetchJson("/eval-cases", fixtureDashboardData.evalCases, options),
    // /approvals is the FIRST-CLASS approval inbox — distinct from /manual-queue, which is the
    // human-task tail. The Approval Inbox view reads from this dataset.
    fetchJson("/approvals", [], options),
    fetchJson("/manual-queue", fixtureDashboardData.manualQueue, options),
    fetchJson("/core-gaps", fixtureDashboardData.coreGaps, options),
  ]);

  const [
    health,
    overview,
    instances,
    runs,
    mandateTypes,
    journal,
    capabilities,
    evalCases,
    approvals,
    manualQueue,
    coreGaps,
  ] = entries;

  return {
    data: {
      health: mapHealth(health.data),
      overview: mapOverview(overview.data),
      instances: mapInstances(instances.data),
      runs: mapRuns(runs.data),
      mandateTypes: mapMandateTypes(mandateTypes.data),
      journal: mapJournal(journal.data),
      capabilities: mapCapabilities(capabilities.data),
      evalCases: mapEvalCases(evalCases.data),
      approvals: mapApprovals(approvals.data),
      manualQueue: mapManualQueue(manualQueue.data),
      coreGaps: mapCoreGaps(coreGaps.data),
    },
    sources: {
      health,
      overview,
      instances,
      runs,
      mandateTypes,
      journal,
      capabilities,
      evalCases,
      approvals,
      manualQueue,
      coreGaps,
    },
  };
}

export function fetchApprovals(
  query: { instance_id?: string } = {},
  options: RequestOptions = {},
): Promise<ApiResult<ApprovalCard[]>> {
  return fetchJson("/approvals", [], { ...options, query }).then((result) => ({
    ...result,
    data: mapApprovals(result.data),
  }));
}

export function fetchSchedulerWork(
  workId: string,
  options: RequestOptions = {},
): Promise<ApiResult<SchedulerWork>> {
  return fetchJson(`/scheduler-work/${encodeURIComponent(workId)}`, {} as SchedulerWork, options).then(
    (result) => ({
      ...result,
      data: (result.data ?? ({} as SchedulerWork)) as SchedulerWork,
    }),
  );
}

export function fetchSystemInfo(
  options: RequestOptions = {},
): Promise<ApiResult<{
  service: string;
  internal_only: boolean;
  posture: string;
  command_auth_configured: boolean;
  fixtures_allowed: boolean;
  backend: string;
}>> {
  return fetchJson("/system/info", {} as never, options);
}

function mapApprovals(raw: unknown): ApprovalCard[] {
  return unwrapArray(raw, "items").map((item) => {
    const value = asRecord(item);
    const drafted = asRecord(value.drafted_effect);
    const syscall = stringValue(drafted.syscall, "");
    const idem = stringValue(drafted.idempotency_key, "");
    const argsValue = asRecord(drafted.args);
    const timeline = arrayValue(value.timeline).map((entry) => {
      const v = asRecord(entry);
      const ev = asRecord(v.event);
      return {
        kind: stringValue(v.kind, stringValue(ev.kind, "journal")),
        ts: stringValue(v.ts, stringValue(ev.ts, new Date().toISOString())),
        actor: stringValue(v.actor, "kernel"),
        summary: stringValue(v.summary, stringValue(ev.kind, "event")),
        event: ev,
      } as TimelineEntry;
    });
    return {
      run_id: stringValue(value.run_id, ""),
      reason: stringValue(value.reason, ""),
      required_ring: stringValue(value.required_ring, ""),
      seq: numberValue(value.seq),
      approval_card: value.approval_card,
      instance_id: stringValue(value.instance_id, ""),
      drafted_effect:
        syscall && idem
          ? {
              syscall,
              args: argsValue as Record<string, unknown>,
              idempotency_key: idem,
            }
          : {},
      timeline,
    };
  });
}

export function fetchInstance(
  instanceId: string,
  options: RequestOptions = {},
): Promise<ApiResult<InstanceSummary>> {
  return fetchJson(`/instances/${instanceId}`, getFixtureInstance(instanceId), options).then((result) => ({
    ...result,
    data: mapInstance(result.data, getFixtureInstance(instanceId)),
  }));
}

export function fetchRun(runId: string, options: RequestOptions = {}): Promise<ApiResult<RunSummary>> {
  return fetchJson(`/runs/${runId}`, getFixtureRun(runId), options).then((result) => ({
    ...result,
    data: mapRunDetail(result.data, getFixtureRun(runId)),
  }));
}

export function fetchRuns(
  query: { state?: string; instance_id?: string },
  options: RequestOptions = {},
): Promise<ApiResult<RunSummary[]>> {
  const fallback = fixtureDashboardData.runs
    .filter((run) => !query.state || run.state === query.state)
    .filter((run) => !query.instance_id || run.instance_id === query.instance_id);

  return fetchJson("/runs", { runs: fallback }, { ...options, query }).then((result) => ({
    ...result,
    data: mapRuns(result.data),
  }));
}

export function fetchJournal(
  query: { instance_id?: string; run_id?: string; kind?: string; limit?: number },
  options: RequestOptions = {},
): Promise<ApiResult<JournalEvent[]>> {
  const fallback = fixtureDashboardData.journal
    .filter((event) => !query.instance_id || event.instance_id === query.instance_id)
    .filter((event) => !query.run_id || event.run_id === query.run_id)
    .filter((event) => !query.kind || event.kind === query.kind)
    .slice(0, query.limit ?? 30);

  return fetchJson("/journal", { events: fallback }, { ...options, query }).then((result) => ({
    ...result,
    data: mapJournal(result.data),
  }));
}

async function postCommand(
  path: string,
  payload: CommandPayload,
  fallbackGapId: string,
): Promise<CommandResult> {
  const result = await fetchJson<CommandResult>(
    path,
    {
      supported: false,
      gap: getCoreGap(fallbackGapId),
      message: "API command unavailable; fixture gap returned.",
    },
    {
      init: {
        method: "POST",
        body: JSON.stringify(payload),
      },
    },
  );

  return mapCommandResult(result.data, fallbackGapId);
}

export function approveCommand(payload: Required<Pick<CommandPayload, "instance_id" | "run_id" | "actor">>) {
  return postCommand("/commands/approve", payload, "gap-edit-reject");
}

export function setRingCommand(payload: Required<Pick<CommandPayload, "instance_id" | "ring" | "actor">>) {
  return postCommand("/commands/set-ring", payload, "gap-create-instance");
}

export async function runSwarm(
  payload: RunSwarmPayload,
  options: RequestOptions & { token?: string } = {},
): Promise<ApiResult<SwarmRunReport>> {
  const { token, baseUrl, fetcher } = options;
  const result = await fetchJson<unknown>(
    "/commands/run-swarm",
    {},
    {
      baseUrl,
      fetcher,
      init: {
        method: "POST",
        body: JSON.stringify(payload),
        ...(token ? { headers: { Authorization: `Bearer ${token}` } } : {}),
      },
    },
  );
  return { ...result, data: mapSwarmRunReport(result.data) };
}

// --- Studio drive→send helpers (Operator Studio slice) -------------------------------------
// Typed, bearer-authed command wrappers + pure mappers for the guided Studio spine. They read
// the SAME existing routes the operator views use; the seam stays frozen. All accept an injected
// ``fetcher`` for unit testing (see dashboard/tests/studio.test.ts).

export interface CommandOptions {
  baseUrl?: string;
  token?: string;
  fetcher?: typeof fetch;
}

async function postTypedCommand(
  path: string,
  payload: unknown,
  options: CommandOptions,
): Promise<{ ok: boolean; body: Record<string, unknown>; message?: string }> {
  const { baseUrl = DEFAULT_API_BASE_URL, token, fetcher = fetch } = options;
  // Fail closed: without an operator token, never touch the network — commands are disabled.
  if (!token) {
    return { ok: false, body: {}, message: "Set the operator token to enable writes." };
  }
  try {
    const response = await fetcher(buildApiUrl(baseUrl, path), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });
    const body = asRecord(await response.json());
    if (!response.ok) {
      const detail = typeof body.detail === "string" ? body.detail : response.statusText;
      return { ok: false, body, message: detail };
    }
    return { ok: true, body };
  } catch (error) {
    return { ok: false, body: {}, message: getErrorMessage(error) };
  }
}

export async function instantiate(
  payload: InstantiatePayload,
  options: CommandOptions = {},
): Promise<InstantiateResult> {
  const { ok, body, message } = await postTypedCommand("/commands/instantiate", payload, options);
  if (!ok) return { supported: false, message };
  const instance = asRecord(body.instance);
  return {
    supported: true,
    instanceId: stringValue(instance.id, "") || undefined,
    message: typeof body.message === "string" ? body.message : undefined,
  };
}

export async function triggerRun(
  payload: TriggerRunPayload,
  options: CommandOptions = {},
): Promise<TriggerRunResult> {
  const { ok, body, message } = await postTypedCommand("/commands/trigger-run", payload, options);
  if (!ok) return { supported: false, message };
  return {
    supported: true,
    workId: stringValue(body.work_id, "") || undefined,
    status: stringValue(body.status, "queued"),
  };
}

export async function approveRun(
  payload: ApprovePayload,
  options: CommandOptions = {},
): Promise<ApproveResult> {
  const { ok, body, message } = await postTypedCommand("/commands/approve", payload, options);
  if (!ok) return { supported: false, message };
  return {
    supported: true,
    status: stringValue(body.status, "accepted"),
    workId: stringValue(body.work_id, "") || undefined,
  };
}

/**
 * Map kernel ``Fact`` docs into scored leads with cited evidence. Reads a settled run's
 * ``claimed_facts`` (``GET /runs/{id}``) or, falling back, a committed instance's ``facts``
 * (``GET /instances/{id}``) — both carry the same Fact shape (invariant #1: every fact cites
 * its provenance).
 */
export function mapScoredLeads(raw: unknown): ScoredLead[] {
  const record = asRecord(raw);
  const source = Array.isArray(record.claimed_facts) ? record.claimed_facts : record.facts;
  return unwrapArray(source, "facts").map((item) => {
    const value = asRecord(item);
    const provenance = asRecord(value.provenance);
    const parsed = Number.parseFloat(stringValue(value.object, ""));
    const confidence = numberValue(value.confidence);
    const note = typeof provenance.note === "string" && provenance.note ? provenance.note : undefined;
    return {
      lead: stringValue(value.subject, "lead"),
      predicate: stringValue(value.predicate, ""),
      score: Number.isFinite(parsed) ? parsed : confidence,
      confidence,
      evidence: arrayValue(provenance.evidence).map((entry) => stringValue(entry, "")).filter(Boolean),
      note,
    };
  });
}

/** Decide whether ``send_email`` will really send (Resend adapter present) or stage to the queue. */
export function deriveSendPosture(capabilities: Capability[]): SendPosture {
  const hasSendEmail = capabilities.some(
    (capability) => capability.syscall === "send_email" || capability.id === "send_email",
  );
  return hasSendEmail ? "live" : "staged";
}

/** Raw ``GET /runs/{id}`` JSON (un-mapped) so the Studio can read ``claimed_facts`` via mapScoredLeads. */
export function fetchRunRaw(runId: string, options: RequestOptions = {}): Promise<ApiResult<unknown>> {
  return fetchJson<unknown>(`/runs/${encodeURIComponent(runId)}`, {}, options);
}

/** Raw ``GET /instances/{id}`` JSON (un-mapped) so the Studio can read committed ``facts``. */
export function fetchInstanceRaw(
  instanceId: string,
  options: RequestOptions = {},
): Promise<ApiResult<unknown>> {
  return fetchJson<unknown>(`/instances/${encodeURIComponent(instanceId)}`, {}, options);
}

// ============================================================================
// v2 focused fetchers (UI overhaul, C1 + downstream cards).
// Each one targets a single resource the new views need; they keep the same
// fail-soft contract (ApiResult + source: "api" | "fixture") so un-wired
// endpoints degrade to a fixture (or null) instead of throwing.
// ============================================================================

export function fetchSystemOverview(
  options: RequestOptions = {},
): Promise<ApiResult<SystemOverview>> {
  return fetchJson("/system/overview", fixtureDashboardData.overview, options).then((result) => ({
    ...result,
    data: mapOverview(result.data),
  }));
}

export function fetchInstances(
  options: RequestOptions = {},
): Promise<ApiResult<InstanceSummary[]>> {
  return fetchJson("/instances", fixtureDashboardData.instances, options).then((result) => ({
    ...result,
    data: mapInstances(result.data),
  }));
}

export function fetchMandateTypes(
  options: RequestOptions = {},
): Promise<ApiResult<MandateType[]>> {
  return fetchJson("/mandate-types", fixtureDashboardData.mandateTypes, options).then((result) => ({
    ...result,
    data: mapMandateTypes(result.data),
  }));
}

export function fetchEvalCases(
  options: RequestOptions = {},
): Promise<ApiResult<EvalCase[]>> {
  return fetchJson("/eval-cases", fixtureDashboardData.evalCases, options).then((result) => ({
    ...result,
    data: mapEvalCases(result.data),
  }));
}

export function fetchCapabilities(
  options: RequestOptions = {},
): Promise<ApiResult<Capability[]>> {
  return fetchJson("/capabilities", fixtureDashboardData.capabilities, options).then((result) => ({
    ...result,
    data: mapCapabilities(result.data),
  }));
}

export function fetchCoreGaps(
  options: RequestOptions = {},
): Promise<ApiResult<CoreGap[]>> {
  return fetchJson("/core-gaps", fixtureDashboardData.coreGaps, options).then((result) => ({
    ...result,
    data: mapCoreGaps(result.data),
  }));
}

/** Raw GET — used by the Inspector Memory tab (C4) to keep source provenance intact. */
export function fetchInstanceMemoryRaw(
  instanceId: string,
  options: RequestOptions = {},
): Promise<ApiResult<unknown>> {
  return fetchJson(`/instances/${encodeURIComponent(instanceId)}/memory`, { facts: [] }, options);
}

export function fetchEvalCase(
  caseId: string,
  options: RequestOptions = {},
): Promise<ApiResult<unknown>> {
  return fetchJson(`/eval-cases/${encodeURIComponent(caseId)}`, {}, options);
}

export function fetchSchedulerWorkList(
  query: { status?: string } = {},
  options: RequestOptions = {},
): Promise<ApiResult<unknown>> {
  return fetchJson("/scheduler-work", { items: [] }, { ...options, query });
}

export function fetchEconomy(
  query: { instance_id?: string } = {},
  options: RequestOptions = {},
): Promise<ApiResult<unknown>> {
  return fetchJson("/economy", {}, { ...options, query });
}

export function fetchEconomyUnits(
  options: RequestOptions = {},
): Promise<ApiResult<unknown>> {
  return fetchJson("/economy/units", { units: [] }, options);
}

/**
 * `/capabilities` may be extended (C11) with `health_detail` per row. This
 * fetch returns raw rows; callers can pass the result to `mapCapabilities` for
 * the base shape and then overlay the health_detail field as needed.
 */
export function fetchCapabilitiesWithHealth(
  options: RequestOptions = {},
): Promise<ApiResult<Capability[]>> {
  return fetchCapabilities(options);
}

/**
 * C12 — Providers / Connectors view. The C11 backend extends `GET /capabilities`
 * with three new top-level fields (`providers`, `transport`, `model_routing`).
 * This fetcher returns the full payload (base capabilities + health detail) so
 * the Providers view can render adapters, transport, and model routing from a
 * single round-trip. The mapper below splits the response into the four
 * sections and is used by both the view and the tests.
 */
export function fetchCapabilitiesForProviders(
  options: RequestOptions & { token?: string } = {},
): Promise<ApiResult<CapabilitiesWithHealth>> {
  const { token, ...rest } = options;
  return fetchJson<unknown>(
    "/capabilities",
    {
      capabilities: fixtureDashboardData.capabilities,
      providers: [],
      transport: { configured: false, name: null, live_gated: false, details: {} },
      model_routing: {
        faculty_model: { configured: false },
        judge_model: { configured: false },
        checked_at: new Date(0).toISOString(),
      },
    },
    {
      ...rest,
      init: {
        ...(rest.init ?? {}),
        ...(token ? { headers: { Authorization: `Bearer ${token}` } } : {}),
      },
    },
  ).then((result) => ({
    data: mapCapabilitiesWithHealth(result.data),
    source: result.source,
    error: result.error,
  }));
}

/** Reject a parked approval (L0/L1 inbox). */
export function rejectCommand(payload: Required<Pick<CommandPayload, "instance_id" | "run_id" | "actor">>) {
  return postCommand("/commands/reject", payload, "gap-edit-reject");
}

/** Edit a parked approval (the "old → new" diff path on the inbox). */
export function editCommand(
  payload: Required<Pick<CommandPayload, "instance_id" | "run_id" | "actor">> & {
    edited_drafted_effect?: Record<string, unknown>;
  },
) {
  return postCommand("/commands/edit", payload, "gap-edit-reject");
}

/** Promote a gym eval case (`/commands/promote`). */
export function promoteCommand(
  payload: Required<Pick<CommandPayload, "case_id" | "actor">>,
) {
  return postCommand("/commands/promote", payload, "gap-eval-promote");
}

function mapHealth(raw: unknown): HealthStatus {
  const value = asRecord(raw);
  if (typeof value.status === "string") return raw as HealthStatus;
  return {
    status: value.ok === true ? "ok" : stringValue(value.status, "unknown"),
    service: stringValue(value.backend, "agentx-api"),
    checked_at: stringValue(value.ts, new Date().toISOString()),
  };
}

function mapOverview(raw: unknown): SystemOverview {
  const value = asRecord(raw);
  if (typeof value.system_state === "string") return raw as SystemOverview;
  const counts = asRecord(value.counts);
  const pnl = asRecord(value.pnl);
  const recentEvents = arrayValue(value.recent_events);
  return {
    system_state: stringValue(value.system, stringValue(value.backend, "agent-x-os")),
    active_instances: numberValue(counts.instances),
    active_runs: numberValue(counts.live_runs),
    parked_runs: numberValue(counts.parked_awaiting_approval),
    approvals_waiting: numberValue(counts.parked_awaiting_approval),
    manual_queue_depth: numberValue(counts.manual_queue),
    ledger_events_today: recentEvents.length,
    automation_coverage: 0,
    monthly_net: numberValue(pnl.total),
    gateway_health: stringValue(value.backend, "kernel gateway"),
    ring_mix: numberRecord(value.rings),
    last_commit_at: stringValue(asRecord(recentEvents[0]).ts, new Date().toISOString()),
  };
}

function mapInstances(raw: unknown): InstanceSummary[] {
  const rows = unwrapArray(raw, "instances");
  return rows.map((row) => mapInstance(row)).filter(Boolean);
}

function mapInstance(raw: unknown, fallback = fixtureDashboardData.instances[0]): InstanceSummary {
  const value = asRecord(raw);
  if (typeof value.name === "string" && typeof value.business === "string") return raw as InstanceSummary;

  const instance = asRecord(value.instance ?? raw);
  const resume = asRecord(value.resume);
  const billing = asRecord(value.billing);
  const facts = unwrapArray(value.facts, "facts").map(mapFact);
  const threads = unwrapArray(value.threads, "threads").map((thread) => {
    const item = asRecord(thread);
    return {
      id: stringValue(item.id, "thread"),
      channel: "kernel",
      subject: stringValue(item.entity_id, stringValue(item.id, "thread")),
      state: stringValue(item.state, "open"),
      updated_at: stringValue(item.updated_at, new Date().toISOString()),
    };
  });
  const approvalCount = numberValue(value.approval_count) || unwrapArray(value.approvals, "approvals").length;
  const billingTotal = numberValue(value.billing_total) || numberValue(billing.total);
  const ring = stringValue(resume.ring, stringValue(instance.ring, fallback.ring));
  const trustScore = numberValue(resume.trust_score, fallback.trust_score);

  return {
    id: stringValue(instance.id, fallback.id),
    name: stringValue(instance.customer_id, fallback.name),
    business: stringValue(instance.customer_id, fallback.business),
    mandate_type: stringValue(instance.type_ref, fallback.mandate_type),
    ring,
    trust_score: trustScore,
    state: approvalCount > 0 ? "parked" : "live",
    health: approvalCount > 0 ? "amber" : "green",
    owner: "operator",
    monthly_net: billingTotal,
    facts: facts.length > 0 ? facts : fallback.facts,
    ring_history: [
      {
        at: stringValue(resume.updated_at, new Date().toISOString()),
        ring,
        actor: "kernel",
        reason: "current resume projection",
      },
    ],
    trust_history: [{ label: "trust", score: trustScore, delta: 0 }],
    threads: threads.length > 0 ? threads : fallback.threads,
    pnl: {
      revenue: billingTotal,
      cost: 0,
      margin: billingTotal,
    },
  };
}

function mapFact(raw: unknown): Fact {
  const value = asRecord(raw);
  const provenance = asRecord(value.provenance);
  return {
    id: stringValue(value.id, "fact"),
    label: stringValue(value.predicate, stringValue(value.subject, "fact")),
    value: stringValue(value.object, ""),
    confidence: numberValue(value.confidence),
    provenance: [
      stringValue(provenance.run_id, ""),
      ...arrayValue(provenance.evidence).map((item) => stringValue(item, "")),
    ].filter(Boolean).join(" / "),
    source: stringValue(value.source, "journal"),
    committed_at: stringValue(value.created_at, new Date().toISOString()),
  };
}

function mapRuns(raw: unknown): RunSummary[] {
  return unwrapArray(raw, "runs").map((run) => mapRunDetail(run)).filter(Boolean);
}

function mapRunDetail(raw: unknown, fallback = fixtureDashboardData.runs[0]): RunSummary {
  const value = asRecord(raw);
  if (typeof value.title === "string" && Array.isArray(value.trace)) return raw as RunSummary;
  const run = asRecord(value.run ?? raw);
  const timeline = unwrapArray(value.timeline, "timeline");
  const state = mapRunState(stringValue(run.state, fallback.state));
  const park = asRecord(run.park);
  const trace = timeline.map((entry, index) => mapTraceEvent(entry, index));
  return {
    id: stringValue(run.run_id, fallback.id),
    instance_id: stringValue(run.instance_id, fallback.instance_id),
    title: stringValue(park.reason, stringValue(run.type_ref, stringValue(run.run_id, fallback.title))),
    state,
    syscall: firstSyscall(timeline) ?? fallback.syscall,
    ring: stringValue(park.required_ring, fallback.ring),
    started_at: stringValue(run.created_at, fallback.started_at),
    updated_at: stringValue(run.updated_at, fallback.updated_at),
    ledger_commits: numberValue(run.event_count, fallback.ledger_commits),
    cost: 0,
    expected_value: numberValue(asRecord(run.settled).billing_amount, fallback.expected_value),
    progress: state === "complete" ? 100 : state === "parked" ? 68 : 42,
    trace: trace.length > 0 ? trace : fallback.trace,
  };
}

function mapRunState(state: string): RunSummary["state"] {
  if (state === "parked") return "parked";
  if (state === "settled" || state === "complete") return "complete";
  if (state === "crashed" || state === "failed") return "failed";
  if (state === "waiting_approval") return "waiting_approval";
  return "active";
}

function mapTraceEvent(raw: unknown, index: number): TimelineEntry {
  const value = asRecord(raw);
  const event = asRecord(value.event);
  const timeline: TimelineEntry = {
    kind: stringValue(value.kind, stringValue(event.kind, "journal")),
    ts: stringValue(value.ts, stringValue(event.ts, new Date().toISOString())),
    actor: stringValue(value.actor, stringValue(event.actor, "kernel")),
    summary: stringValue(value.summary, stringValue(event.kind, "journal event")),
    event: event as Record<string, unknown>,
  };
  return timeline;
}

function firstSyscall(timeline: unknown[]): string | undefined {
  for (const item of timeline) {
    const event = asRecord(asRecord(item).event);
    const syscall = stringValue(event.syscall, "");
    if (syscall) return syscall;
  }
  return undefined;
}

function mapMandateTypes(raw: unknown): MandateType[] {
  return unwrapArray(raw, "mandate_types").map((item) => {
    const value = asRecord(item);
    if (typeof value.title === "string") return item as MandateType;
    const charter = asRecord(value.charter);
    return {
      id: stringValue(value.id, "mandate"),
      title: stringValue(value.name, "Mandate"),
      stage: stringValue(value.version, "Phase 1"),
      ring_floor: "L0",
      unit_economics: stringValue(charter.goal, "kernel-managed mandate"),
      commands: unwrapArray(value.faculties, "faculties").map((faculty) =>
        stringValue(asRecord(faculty).faculty_name, "faculty"),
      ),
      status: "ready",
    };
  });
}

function mapJournal(raw: unknown): JournalEvent[] {
  return unwrapArray(raw, "events").map((item, index) => {
    const value = asRecord(item);
    if (typeof value.title === "string") return item as JournalEvent;
    const title = stringValue(value.action, stringValue(value.kind, `event ${index + 1}`));
    const baseId = stringValue(value.event_id, `journal-${index}`);
    return {
      id: `${baseId}-${index}`,
      at: stringValue(value.ts, new Date().toISOString()),
      kind: stringValue(value.kind, "journal"),
      instance_id: stringValue(value.instance_id, ""),
      run_id: stringValue(value.run_id, ""),
      actor: stringValue(value.actor, "kernel"),
      title,
      detail: stringValue(value.reason, stringValue(value.decision, title)),
      source: "kernel-journal",
    };
  });
}

function mapCapabilities(raw: unknown): DashboardData["capabilities"] {
  return unwrapArray(raw, "capabilities").map((item) => {
    const value = asRecord(item);
    if (typeof value.title === "string") return item as DashboardData["capabilities"][number];
    const health = asRecord(value.health);
    return {
      id: stringValue(value.name, "capability"),
      title: stringValue(value.name, "capability").replaceAll("_", " "),
      syscall: stringValue(value.name, ""),
      maturity: mapMaturity(numberValue(value.maturity_level)),
      health: mapHealthStatus(stringValue(health.status, "degraded")),
      queue_volume: numberValue(value.queue_volume),
      credential_boundary: `${stringValue(value.tenant_auth, "manual")} via kernel gateway`,
      terminal_fallback: value.is_terminal_fallback === true,
    };
  });
}

/**
 * Map the C11-extended `/capabilities` payload into the four-section view model
 * the Providers / Connectors view consumes. Missing sections fall back to safe
 * defaults so the view never crashes on a partial response (e.g. an older
 * backend that predates C11).
 */
export function mapCapabilitiesWithHealth(raw: unknown): CapabilitiesWithHealth {
  const value = asRecord(raw);
  return {
    capabilities: mapCapabilities(value),
    providers: mapProviders(value.providers),
    transport: mapTransport(value.transport),
    model_routing: mapModelRouting(value.model_routing),
  };
}

function mapProviders(raw: unknown): ProviderReachability[] {
  return arrayValue(raw).map((item) => {
    const value = asRecord(item);
    // ``name`` is permissive on purpose: real backends occasionally return a
    // number (e.g. an internal id) instead of a string. Coerce the obvious
    // cases so the view never has to render a row whose name is the literal
    // string "unknown" — the operator would have no clue what provider that is.
    const name = coerceName(value.name);
    const rawKind = stringValue(value.kind, "research");
    const kind: ProviderReachability["kind"] = rawKind === "outbound" ? "outbound" : "research";
    const liveGated =
      typeof value.live_gated === "boolean"
        ? value.live_gated
        : typeof value.live_gated === "string"
          ? value.live_gated === "1" || value.live_gated === "true"
          : false;
    const error =
      typeof value.error === "string" && value.error.length > 0 ? value.error : null;
    return {
      name,
      kind,
      configured: value.configured === true,
      reachable: value.reachable === true,
      live_gated: kind === "outbound" ? liveGated : undefined,
      error,
    };
  });
}

function mapTransport(raw: unknown): TransportStatus {
  const value = asRecord(raw);
  // ``configured`` is permissive (truthy counts) because the C11 backend
  // can return the int ``1`` for a present-but-boolean transport; a strict
  // ``=== true`` would mark the transport as missing on a healthy backend.
  // ``live_gated`` stays strict — a non-boolean means "gate state unclear",
  // and we'd rather show a "not live" pill than silently open the gate.
  const configured = truthy(value.configured);
  const name = typeof value.name === "string" && value.name ? value.name : null;
  const liveGated = value.live_gated === true;
  const details = mapTransportDetails(value.details);
  return { configured, name, live_gated: liveGated, details };
}

function mapTransportDetails(raw: unknown): EmailTransportDetails {
  const value = asRecord(raw);
  const port = value.port;
  return {
    host: typeof value.host === "string" ? value.host : undefined,
    port:
      typeof port === "number"
        ? port
        : typeof port === "string" && port.length > 0
          ? port
          : undefined,
    username: typeof value.username === "string" ? value.username : undefined,
    default_from: typeof value.default_from === "string" ? value.default_from : undefined,
    from_name: typeof value.from_name === "string" ? value.from_name : undefined,
  };
}

function mapModelRouting(raw: unknown): ModelRoutingStatus {
  const value = asRecord(raw);
  const faculty = asRecord(value.faculty_model);
  const judge = asRecord(value.judge_model);
  return {
    faculty_model: {
      provider: typeof faculty.provider === "string" ? faculty.provider : undefined,
      configured: faculty.configured === true,
      base_url: typeof faculty.base_url === "string" ? faculty.base_url : undefined,
      model_id: typeof faculty.model_id === "string" ? faculty.model_id : undefined,
    },
    judge_model: {
      via: typeof judge.via === "string" ? judge.via : undefined,
      configured: judge.configured === true,
      base_url: typeof judge.base_url === "string" ? judge.base_url : undefined,
      model_id: typeof judge.model_id === "string" ? judge.model_id : undefined,
    },
    checked_at:
      typeof value.checked_at === "string" && value.checked_at
        ? value.checked_at
        : new Date(0).toISOString(),
  };
}

function mapMaturity(level: number): DashboardData["capabilities"][number]["maturity"] {
  if (level >= 3) return "live";
  if (level >= 1) return "api";
  return "manual";
}

function mapHealthStatus(status: string): DashboardData["capabilities"][number]["health"] {
  if (status === "ok") return "healthy";
  if (status === "down") return "queued";
  return "degraded";
}

function mapEvalCases(raw: unknown): EvalCase[] {
  return unwrapArray(raw, "eval_cases").map((item) => {
    const value = asRecord(item);
    if (typeof value.title === "string") return item as EvalCase;
    const origin = stringValue(value.origin, "synthetic") as EvalCase["origin"];
    return {
      id: stringValue(value.id, "eval"),
      pack: stringValue(arrayValue(value.tags)[0], stringValue(value.type_ref, "scenario pack")),
      origin,
      title: stringValue(value.id, "Eval case"),
      status: value.passed === false ? "failed" : "graded",
      score: numberValue(value.score),
      promotion: origin === "synthetic" ? "blocked" : "eligible",
    };
  });
}

function mapSwarmTraceEvent(raw: unknown): SwarmTraceEvent {
  const value = asRecord(raw);
  return {
    seq: numberValue(value.seq),
    ts: stringValue(value.ts, ""),
    kind: stringValue(value.kind, "thought"),
    summary: stringValue(value.summary, ""),
    detail: asRecord(value.detail),
  };
}

function mapScorecardView(raw: unknown): ScorecardView {
  const value = asRecord(raw);
  return {
    run_id: stringValue(value.run_id, ""),
    rubric_name: stringValue(value.rubric_name, ""),
    score: numberValue(value.score),
    passed: value.passed === true,
    origin: stringValue(value.origin, "synthetic"),
    criteria: arrayValue(value.criteria).map((entry) => {
      const criterion = asRecord(entry);
      return {
        criterion_id: stringValue(criterion.criterion_id, ""),
        passed: criterion.passed === true,
        score: numberValue(criterion.score),
        comment: typeof criterion.comment === "string" ? criterion.comment : undefined,
      };
    }),
    failure_reasons: arrayValue(value.failure_reasons).map((reason) => stringValue(reason, "")).filter(Boolean),
    judge_comments: arrayValue(value.judge_comments).map((comment) => stringValue(comment, "")).filter(Boolean),
  };
}

function mapGateDecisionView(raw: unknown): GateDecisionView {
  const value = asRecord(raw);
  return {
    allowed: value.allowed === true,
    reasons: arrayValue(value.reasons).map((reason) => stringValue(reason, "")).filter(Boolean),
    live_ring: typeof value.live_ring === "string" ? value.live_ring : null,
  };
}

export function mapSwarmRunReport(raw: unknown): SwarmRunReport {
  const value = asRecord(raw);
  const trace = asRecord(value.trace);
  return {
    supported: value.supported === true,
    run_id: stringValue(value.run_id, ""),
    type_ref: stringValue(value.type_ref, ""),
    pack_id: stringValue(value.pack_id, ""),
    eval_case_id: stringValue(value.eval_case_id, ""),
    events: arrayValue(trace.events).map(mapSwarmTraceEvent),
    scorecard: value.scorecard ? mapScorecardView(value.scorecard) : null,
    gate_decision: value.gate_decision ? mapGateDecisionView(value.gate_decision) : null,
    message: typeof value.message === "string" ? value.message : undefined,
  };
}

function mapManualQueue(raw: unknown): ManualTask[] {
  return unwrapArray(raw, "items").map((item) => {
    const value = asRecord(item);
    if (typeof value.title === "string") return item as ManualTask;
    const args = asRecord(value.args);
    return {
      id: stringValue(value.id, "manual-task"),
      instance_id: stringValue(value.instance_id, ""),
      run_id: stringValue(value.run_id, ""),
      title: stringValue(value.request_name, "manual action"),
      drafted_effect: stringValue(args.reason, stringValue(args.action, JSON.stringify(args))),
      priority: "normal",
      age_minutes: 0,
      trace: [
        stringValue(value.source_adapter, "manual queue"),
        stringValue(value.idempotency_key, "idempotent task"),
      ],
      status: "open",
    };
  });
}

function mapCoreGaps(raw: unknown): CoreGap[] {
  return unwrapArray(raw, "gaps").map((item) => {
    const value = asRecord(item);
    return {
      id: stringValue(value.id, "core-gap"),
      title: stringValue(value.title, "Core gap"),
      detail: stringValue(value.detail, ""),
    };
  });
}

function mapCommandResult(raw: unknown, fallbackGapId: string): CommandResult {
  const value = asRecord(raw);
  if (value.supported === true) {
    const action = asRecord(value.action);
    return {
      supported: true,
      status: stringValue(action.action, "accepted"),
      receipt: stringValue(action.event_id, ""),
      message: "Journaled by KernelControl",
    };
  }
  const gap = asRecord(value.gap);
  return {
    supported: false,
    gap: gap.id ? {
      id: stringValue(gap.id, fallbackGapId),
      title: stringValue(gap.title, "Core gap"),
      detail: stringValue(gap.detail, ""),
    } : getCoreGap(fallbackGapId),
    message: stringValue(value.message, "Command unavailable."),
  };
}

function unwrapArray(raw: unknown, key: string): unknown[] {
  if (Array.isArray(raw)) return raw;
  const value = asRecord(raw);
  const nested = value[key];
  return Array.isArray(nested) ? nested : [];
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function stringValue(value: unknown, fallback: string): string {
  return typeof value === "string" && value.length > 0 ? value : fallback;
}

/**
 * Permissive truthy coercion. Accepts:
 *  - booleans (passthrough)
 *  - numbers (any non-zero finite is true; 0 / NaN are false)
 *  - strings ("1" / "true" / "yes" / "on" / any non-empty non-"0" string)
 *  - null / undefined / everything else → false
 *
 * Used by the C12 transport mapper where the C11 backend historically
 * returned an int ``1`` for a present-but-boolean transport. Strict
 * ``=== true`` would mark the transport as missing on a healthy backend.
 */
function truthy(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return Number.isFinite(value) && value !== 0;
  if (typeof value === "string") {
    const lower = value.toLowerCase();
    if (lower === "0" || lower === "false" || lower === "no" || lower === "off") return false;
    return value.length > 0;
  }
  return false;
}

/**
 * Coerce a provider ``name`` field into a displayable string. Most backends
 * emit a string (e.g. ``"exa"``) but a few return a numeric id; we surface
 * the original value as a string rather than masking it as ``"unknown"``.
 * Empty strings and missing values still fall back to ``"unknown"``.
 */
function coerceName(value: unknown): string {
  if (typeof value === "string") return value.length > 0 ? value : "unknown";
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return "unknown";
}

function numberValue(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function numberRecord(value: unknown): Record<string, number> {
  return Object.fromEntries(
    Object.entries(asRecord(value)).map(([key, item]) => [key, numberValue(item)]),
  );
}
