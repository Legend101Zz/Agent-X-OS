export type ApiSource = "api" | "fixture";

export interface ApiResult<T> {
  data: T;
  source: ApiSource;
  error?: string;
}

export interface HealthStatus {
  status: string;
  service?: string;
  checked_at?: string;
}

export interface SystemOverview {
  system_state: string;
  active_instances: number;
  active_runs: number;
  parked_runs: number;
  approvals_waiting: number;
  manual_queue_depth: number;
  ledger_events_today: number;
  automation_coverage: number;
  monthly_net: number;
  gateway_health: string;
  ring_mix: Record<string, number>;
  last_commit_at: string;
}

export interface Fact {
  id: string;
  label: string;
  value: string;
  confidence: number;
  provenance: string;
  source: string;
  committed_at: string;
}

export interface RingHistory {
  at: string;
  ring: string;
  actor: string;
  reason: string;
}

export interface TrustPoint {
  label: string;
  score: number;
  delta: number;
}

export interface ThreadSummary {
  id: string;
  channel: string;
  subject: string;
  state: string;
  updated_at: string;
}

export interface InstanceSummary {
  id: string;
  name: string;
  business: string;
  mandate_type: string;
  ring: string;
  trust_score: number;
  state: "live" | "parked" | "setup";
  health: string;
  owner: string;
  monthly_net: number;
  facts: Fact[];
  ring_history: RingHistory[];
  trust_history: TrustPoint[];
  threads: ThreadSummary[];
  pnl: {
    revenue: number;
    cost: number;
    margin: number;
  };
}

export interface RunSummary {
  id: string;
  instance_id: string;
  title: string;
  state: "active" | "parked" | "waiting_approval" | "complete" | "failed";
  syscall: string;
  ring: string;
  started_at: string;
  updated_at: string;
  ledger_commits: number;
  cost: number;
  expected_value: number;
  progress: number;
  trace: TimelineEntry[];
}

export interface TraceEvent {
  id: string;
  at: string;
  kind: string;
  title: string;
  detail: string;
  actor: string;
  confidence?: number;
}

export interface MandateType {
  id: string;
  title: string;
  stage: string;
  ring_floor: string;
  unit_economics: string;
  commands: string[];
  status: "ready" | "gap" | "locked";
  gap_id?: string;
}

export interface JournalEvent {
  id: string;
  at: string;
  kind: string;
  instance_id?: string;
  run_id?: string;
  actor: string;
  title: string;
  detail: string;
  source: string;
}

export interface Capability {
  id: string;
  title: string;
  syscall: string;
  maturity: "manual" | "fixture" | "api" | "live";
  health: "healthy" | "degraded" | "queued";
  queue_volume: number;
  credential_boundary: string;
  terminal_fallback: boolean;
}

export interface EvalCase {
  id: string;
  pack: string;
  origin: "synthetic" | "real" | "human_reviewed";
  title: string;
  status: string;
  score: number;
  promotion: "blocked" | "eligible";
}

// --- Swarm REPL view models (Session I) ----------------------------------------------------
// These are DASHBOARD view models, not contracts. The packages/contracts seam stays frozen; these
// only shape the JSON that POST /commands/run-swarm returns for the §5 timeline.

export interface SwarmTraceEvent {
  seq: number;
  ts: string;
  kind: string;
  summary: string;
  detail: Record<string, unknown>;
}

export interface ScorecardCriterionView {
  criterion_id: string;
  passed: boolean;
  score: number;
  comment?: string;
}

export interface ScorecardView {
  run_id: string;
  rubric_name: string;
  score: number;
  passed: boolean;
  origin: string;
  criteria: ScorecardCriterionView[];
  failure_reasons: string[];
  judge_comments: string[];
}

export interface GateDecisionView {
  allowed: boolean;
  reasons: string[];
  live_ring: string | null;
}

export interface SwarmRunReport {
  supported: boolean;
  run_id: string;
  type_ref: string;
  pack_id: string;
  events: SwarmTraceEvent[];
  scorecard: ScorecardView | null;
  gate_decision: GateDecisionView | null;
  eval_case_id: string;
  message?: string;
}

export interface RunSwarmPayload {
  type_ref: string;
  pack_id: string;
  ring?: string;
  judge_live?: boolean;
  actor?: string;
}

export interface ManualTask {
  id: string;
  instance_id: string;
  run_id: string;
  title: string;
  drafted_effect: string;
  priority: "low" | "normal" | "high";
  age_minutes: number;
  trace: string[];
  status: "open" | "approved" | "gap";
}

export interface CoreGap {
  id: string;
  title: string;
  detail: string;
}

// --- Studio view models (Operator Studio slice) --------------------------------------------
// View models only — the packages/contracts seam stays frozen. These shape the JSON the Studio
// drive→send spine reads from existing routes (/runs/{id} claimed_facts, /capabilities).

export interface ScoredLead {
  /** The lead subject (the kernel Fact's ``subject``). */
  lead: string;
  /** The predicate that scored it (e.g. ``qualified_lead_score``). */
  predicate: string;
  /** Numeric score (parsed from the Fact ``object``, falling back to ``confidence``). */
  score: number;
  /** The Fact's own confidence (0..1). */
  confidence: number;
  /** Cited evidence — provenance evidence URLs + syscall_trace lines (invariant #1). */
  evidence: string[];
  /** Optional provenance note. */
  note?: string;
}

/** Whether ``send_email`` will really send (Resend transport registered) or stage to the manual queue. */
export type SendPosture = "live" | "staged";

export interface CommandOutcome {
  supported: boolean;
  message?: string;
}

export interface InstantiateResult extends CommandOutcome {
  instanceId?: string;
}

export interface TriggerRunResult extends CommandOutcome {
  workId?: string;
  status?: string;
}

export interface ApproveResult extends CommandOutcome {
  status?: string;
  workId?: string;
}

export interface ApprovalCard {
  run_id: string;
  reason: string;
  required_ring?: string;
  seq: number;
  approval_card?: unknown;
  instance_id: string;
  drafted_effect: {
    syscall: string;
    args: Record<string, unknown>;
    idempotency_key: string;
  } | Record<string, unknown>;
  timeline: TimelineEntry[];
}

export interface TimelineEntry {
  kind: string;
  ts: string;
  actor: string;
  summary: string;
  event: Record<string, unknown>;
}

export interface SchedulerWork {
  work_id: string;
  kind: "trigger" | "approval";
  status: "pending" | "claimed" | "completed" | "failed";
  attempts: number;
  available_at: string;
  run_id?: string;
  instance_id?: string;
  type_ref?: string;
  updated_at: string;
}

export interface SystemInfo {
  service: string;
  internalOnly: boolean;
  posture: string;
  commandAuthConfigured: boolean;
  fixturesAllowed: boolean;
  backend: string;
}

export interface DashboardData {
  health: HealthStatus;
  overview: SystemOverview;
  instances: InstanceSummary[];
  runs: RunSummary[];
  mandateTypes: MandateType[];
  journal: JournalEvent[];
  capabilities: Capability[];
  evalCases: EvalCase[];
  approvals: ApprovalCard[];
  manualQueue: ManualTask[];
  coreGaps: CoreGap[];
}

export type CommandPayload = Record<string, unknown>;

export interface CommandResult {
  supported: boolean;
  status?: string;
  receipt?: string;
  message?: string;
  work_id?: string;
  work_enqueued?: boolean;
  decision?: string;
  manager_action?: Record<string, unknown>;
  resolution?: Record<string, unknown>;
  gap?: CoreGap;
}

export interface ApprovePayload {
  instance_id: string;
  run_id: string;
  actor: string;
}

export interface RejectPayload extends ApprovePayload {
  edited?: boolean;
}

export interface InstantiatePayload {
  type_ref: string;
  customer_id: string;
  business_name: string;
  ring: string;
  target_override?: Record<string, unknown>;
  actor: string;
}

export interface TriggerRunPayload {
  instance_id: string;
  target?: Record<string, unknown>;
  mode: string;
  actor: string;
}

export interface SetRingPayload {
  instance_id: string;
  ring: string;
  actor: string;
}

// ============================================================================
// Inspector + dashboard view models added by C1 (UI overhaul).
// These are DASHBOARD view models, NOT contracts — packages/contracts stays
// frozen. They are the shapes the new UI consumes; backend READ APIs (C3,
// C9, C11, C13, C15) will return JSON that maps into these.
// ============================================================================

/** A single fact in an instance's heap (Memory tab). */
export interface MemoryFact {
  id: string;
  subject: string;
  predicate: string;
  object: string;
  confidence: number;
  status: "probation" | "verified" | "disputed";
  run_id: string | null;
  evidence: string[];
  committed_at: string;
}

/** The full memory page for an instance. */
export interface InstanceMemory {
  instance_id: string;
  total: number;
  probation: number;
  verified: number;
  facts: MemoryFact[];
}

/** Per-instance P&L row. */
export interface InstancePnL {
  instance_id: string;
  instance_name: string;
  business: string;
  revenue: number;
  cost: number;
  net: number;
  runs: number;
  period_start: string;
  period_end: string;
}

/** Per-business-unit P&L row. */
export interface BusinessUnitPnL {
  business: string;
  revenue: number;
  cost: number;
  net: number;
  runs: number;
  instance_count: number;
}

/** The full economy page payload. */
export interface EconomySnapshot {
  period_start: string;
  period_end: string;
  total_revenue: number;
  total_cost: number;
  total_net: number;
  instances: InstancePnL[];
  units: BusinessUnitPnL[];
}

/** A scheduler work item (Kernel view, C13/C14). Dashboard-facing camelCase view model. */
export interface SchedulerWorkItem {
  workId: string;
  kind: "trigger" | "approval";
  status: "pending" | "claimed" | "completed" | "failed";
  attempts: number;
  availableAt: string;
  runId?: string;
  instanceId?: string;
  typeRef?: string;
  updatedAt: string;
}

/** Aggregated Kernel / System view snapshot (C14). */
export interface KernelSnapshot {
  overview: SystemOverview;
  schedulerWork: SchedulerWorkItem[];
  coreGaps: CoreGap[];
  overviewAvailable: boolean;
  schedulerAvailable: boolean;
  coreGapsAvailable: boolean;
  fetchedAt: string;
}

/** Extended capability with health detail (C11). */
export interface CapabilityHealth {
  reachable: boolean;
  transport_configured: boolean;
  model_routing: string | null;
  credential_status: "ok" | "missing" | "invalid" | "unknown";
  last_checked_at: string | null;
  notes?: string;
}

export interface CapabilityWithHealth extends Capability {
  health_detail: CapabilityHealth;
}

/** Eval-case detail (C9). */
export interface EvalCaseDetail extends EvalCase {
  rubric: string;
  expected_outputs: Record<string, unknown>;
  history: Array<{
    run_id: string;
    score: number;
    at: string;
    origin: string;
  }>;
  notes?: string;
}

/** Status of a feature/backend wiring — drives graceful disable. */
export type FeatureStatus = "live" | "wip" | "stub";

export interface FeatureFlags {
  heap_read: FeatureStatus;
  eval_case_detail: FeatureStatus;
  capability_health: FeatureStatus;
  scheduler_work_list: FeatureStatus;
  economy_pnl: FeatureStatus;
}

/** SSE event kinds we route into the global invalidation table. */
export type DashboardSliceV2 =
  | "overview"
  | "instances"
  | "runs"
  | "journal"
  | "approvals"
  | "evalCases"
  | "mandateTypes"
  | "capabilities"
  | "coreGaps"
  | "economy"
  | "scheduler";

/** An entry on the Mission Control live event ribbon. */
export interface LiveRibbonEvent {
  id: string;
  kind: string;
  ts: string;
  title: string;
  detail: string;
  tone: "good" | "warn" | "hot" | "info" | "neutral";
  instance_id?: string;
  run_id?: string;
}
