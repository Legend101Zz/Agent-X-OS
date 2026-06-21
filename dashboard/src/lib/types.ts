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

// --- Blueprints (C5) view models -------------------------------------------------------
// DASHBOARD view models, not contracts. They mirror the seven organs of a
// MandateType (BLUEPRINT §1) plus the faculty library the type binds to. The
// `mapMandateTypes`/`mapMandateType` reducers tolerate the existing lean
// shape (legacy rows with `commands[]` / `unit_economics`) AND the rich
// kernel payload (charter / faculties / domain_pack / verification /
// settlement / gym_ref / execution). When the kernel is unavailable we
// fall back to the fixtures (which carry the rich shape so the UI is
// scannable offline).

/** Organ 1 — Charter (Design-by-Contract). */
export interface CharterOrgan {
  goal: string;
  preconditions: string[];
  pathconditions: string[];
  postconditions: string[];
  constraints: string[];
  /** Typed-JSON goal schema (quantity / window / budget / ICP). */
  target: Record<string, unknown>;
}

/** Organ 2 — Faculties: the reusable bricks a mandate binds. */
export interface FacultyBindingView {
  faculty_name: string;
  faculty_version: string;
  /** Per-faculty routing: harness × model × budget (Organ 7 surface). */
  harness: string;
  model: string;
  budget: number | null;
  /** Optional description shown in the inspector. */
  description?: string;
}

/** Organ 3 — Domain pack reference (vertical playbook + cross-customer priors). */
export interface DomainPackRefView {
  name: string;
  version: string;
  /** Short label for the inspector (e.g. "B2B SaaS, India"). */
  vertical?: string;
}

/** Organ 4 — Verification suite (commit-time type system). */
export interface VerificationRungView {
  rung: "rules" | "judge" | "human" | "reality";
  present: boolean;
}

export interface VerificationOrgan {
  ladder: VerificationRungView[];
  rules: string[];
  rubrics: string[];
}

/** Organ 5 — Settlement rules (what happens at commit). */
export interface SettlementOrgan {
  fact_commit_confidence: number;
  trust_on_success: number;
  trust_on_failure: number;
  watch_window_hours: number;
  spawn_rules: { on_condition: string; child_type_ref: string }[];
  billing_per_run: number | null;
}

/** Organ 6 — Eval Gym reference (where this type's scorecards live). */
export interface GymRefView {
  name: string;
  status: "active" | "dormant" | "blocked";
  cases_count: number;
}

/** Organ 7 — Execution profile: faculty → harness × model × budget. */
export interface ExecutionOrgan {
  routing: { faculty_name: string; harness: string; model: string; budget: number | null }[];
}

/** A faculty library entry — the canonical, shared capability brick. */
export interface FacultyLibraryEntry {
  name: string;
  version: string;
  description: string;
  category: "research" | "outreach" | "analysis" | "content" | "settlement" | "ops";
  /** Mandate types that bind this faculty. */
  used_by: string[];
}

/** A versioned line for a mandate type (semver, like software releases). */
export interface MandateTypeVersion {
  version: string;
  released_at: string;
  status: "live" | "canary" | "draft" | "deprecated";
  changelog: string;
}

export interface MandateType {
  id: string;
  title: string;
  /** e.g. "lead-finder@0.3.1" — the canonical ref. */
  type_ref: string;
  stage: string;
  ring_floor: string;
  /** One-line economics summary. Mirrors legacy `unit_economics` for back-compat. */
  unit_economics: string;
  /** Legacy: faculty names as flat strings (still consumed by some views). */
  commands: string[];
  status: "ready" | "gap" | "locked" | "canary";
  gap_id?: string;
  /** Optional short description rendered under the title. */
  description?: string;
  /** How many instances of this type are currently running (server-derived). */
  instances_count?: number;
  /** Live type_ref list (current + older versions). */
  versions: MandateTypeVersion[];
  charter: CharterOrgan;
  faculties: FacultyBindingView[];
  domain_pack: DomainPackRefView;
  verification: VerificationOrgan;
  settlement: SettlementOrgan;
  gym_ref: GymRefView | null;
  execution: ExecutionOrgan;
  service_ports: string[];
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
  promotion: "blocked" | "eligible" | "needs_review";
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
  facultyLibrary: FacultyLibraryEntry[];
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

// ---------------------------------------------------------------------------
// C7 — Edit-with-diff payload + response shapes.
//
// `/commands/edit` rewrites the parked syscall's args then approves + enqueues
// the resume. The response carries the diff (added/removed/changed keys) so
// the inbox can render an old→new review before the operator commits.
// ---------------------------------------------------------------------------

export interface EditPayload extends ApprovePayload {
  edited_args: Record<string, unknown>;
}

export type EditDiffOp = "added" | "removed" | "changed";

export interface EditDiffKey {
  key: string;
  op: EditDiffOp;
  before: unknown;
  after: unknown;
}

export interface EditDiff {
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  diff_keys: EditDiffKey[];
}

export interface EditResult extends CommandOutcome {
  status?: string;
  edited?: boolean;
  decision?: string;
  syscall?: string;
  edit?: EditDiff;
  workId?: string;
  workEnqueued?: boolean;
}

export interface InstantiatePayload {
  type_ref: string;
  customer_id: string;
  business_name: string;
  ring: string;
  target_override?: Record<string, unknown>;
  /** Per-instance outbound sender identity (invariant #8: never share across instances). */
  sender_identity?: string;
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
  billing_total: number;
  currency: string;
  settled_count: number;
  trust_score: number;
  settlements: Array<{
    run_id: string;
    amount: number;
    ts: string;
  }>;
  missing?: boolean;
}

/** Per-business-unit P&L row. */
export interface BusinessUnitPnL {
  customer_id: string;
  instance_count: number;
  instance_ids: string[];
  billing_total: number;
  settled_count: number;
  trust_score: number;
  currency: string;
}

export interface EconomyTotals {
  billing_total: number;
  settled_count: number;
  currency: string;
}

/** The business-unit rollup payload returned by GET /economy/units. */
export interface EconomyUnitsSnapshot {
  units: BusinessUnitPnL[];
  totals: EconomyTotals;
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

// ============================================================================
// Runs viewer (C6) — Runs list + Trace viewer view models.
// These are DASHBOARD view models, NOT contracts. packages/contracts stays
// frozen. They are the shapes the new Runs UI consumes; the existing
// `fetchRun`/`fetchRunRaw`/`fetchRuns` helpers return JSON that maps here.
// ============================================================================

/** A claimed fact surfaced in the Inspector's "claimed facts" panel. */
export interface ClaimedFact {
  id: string;
  subject: string;
  predicate: string;
  object: string;
  confidence: number;
  run_id: string | null;
  evidence: string[];
  committed_at: string;
}

/** Settlement summary block on the Run detail view. */
export interface SettlementSummary {
  /** Run state, used for the status pill. */
  status: RunSummary["state"];
  /** Cost incurred so far (USD). */
  cost: number;
  /** Expected value the run is targeting (USD). */
  expected_value: number;
  /** 0-100, the run's progress. */
  progress: number;
  /** Optional ISO timestamp of when the run settled, if settled. */
  settled_at: string | null;
  /** Optional billing amount (USD) for the settled run, if any. */
  billing_amount: number | null;
}

/** Filter shape for the Runs list page. */
export interface RunListFilters {
  state?: RunSummary["state"] | string;
  instance_id?: string;
  query?: string;
}

/** The shape consumed by the Runs list view (rows + counts). */
export interface RunsListView {
  runs: RunSummary[];
  total: number;
  filtered: number;
  by_state: Record<RunSummary["state"], number>;
}

// Gym / Eval view models (C8 — UI overhaul).
// These are DASHBOARD view models, NOT contracts. The packages/contracts seam
// stays frozen; these shape derived UI state the Gym view consumes.
//
// EvalCase already lives above; below are the derived analytics + the compiler
// scaffold status (per BLUEPRINT §5: a proposal gated on the same PromotionGate
// — synthetic-only never promotable).
// ============================================================================

/** Origin buckets we count when rendering the distribution panel. */
export type EvalOriginKey = "synthetic" | "real" | "human_reviewed";

/** Aggregate stats derived from a `EvalCase[]` (used by the Gym hero tiles). */
export interface EvalCaseStats {
  total: number;
  byOrigin: Record<EvalOriginKey, number>;
  eligible: number;
  blocked: number;
  needsReview: number;
  /** Average score across all cases with a numeric score. Null when empty. */
  averageScore: number | null;
  /** Average score grouped by origin. Null when the bucket is empty. */
  averageByOrigin: Partial<Record<EvalOriginKey, number>>;
  /** Score samples for the sparkline (sorted oldest → newest). */
  scoreTimeline: number[];
}

/** Compiler scaffold status, derived from the `PromotionGate` health. */
export type CompilerScaffoldState =
  | "ready"
  | "warming_up"
  | "blocked_synthetic_only"
  | "not_started";

export interface CompilerScaffold {
  state: CompilerScaffoldState;
  /** Cumulative real-and-human-reviewed cases accumulated so far. */
  realCases: number;
  /** Real-case threshold the compiler wants before it will propose improvements. */
  threshold: number;
  /** Last proposal ID + timestamp, if any. */
  lastProposal: { id: string; at: string } | null;
  /** Why the state is what it is — for the UI tooltip. */
  note: string;
}

/** Tone for the compiler scaffold pill. */
export function compilerStateTone(
  state: CompilerScaffoldState,
): "good" | "warn" | "hot" | "info" | "neutral" {
  switch (state) {
    case "ready":
      return "good";
    case "warming_up":
      return "info";
    case "blocked_synthetic_only":
      return "hot";
    case "not_started":
      return "warn";
    default:
      return "neutral";
  }
}

/** Human-readable label for a compiler scaffold state. */
export function compilerStateLabel(state: CompilerScaffoldState): string {
  switch (state) {
    case "ready":
      return "ready";
    case "warming_up":
      return "warming up";
    case "blocked_synthetic_only":
      return "blocked · synthetic only";
    case "not_started":
      return "not started";
    default:
      return state;
  }
}

// Providers / Connectors view (C12) — view models for the §5 Providers row.
//
// The C11 backend extends `GET /capabilities` with three new top-level fields:
//   * `providers`         — per-provider reachability + credential presence
//   * `transport`         — outbound email transport configuration + live gate
//   * `model_routing`     — which model the kernel + judge use
//
// These are VIEW models only. `packages/contracts` stays frozen. The dashboard
// maps the raw JSON into these shapes; downstream sections can rely on the
// discriminated `kind` and `configured` flags to render the right pill.
// ============================================================================

/** A single row in the per-provider reachability table. */
export interface ProviderReachability {
  /** Canonical provider name (exa, firecrawl, email, ...). */
  name: string;
  /** "research" (Exa/Firecrawl) or "outbound" (email transport). */
  kind: "research" | "outbound";
  /** Whether the relevant secret/env is present in `Settings`. */
  configured: boolean;
  /** Whether the provider's own `health_check` reports it usable RIGHT NOW. */
  reachable: boolean;
  /** Outbound-only: whether the live-send gate (`RUN_LIVE_EMAIL`) is on. */
  live_gated?: boolean;
  /** Optional error from the most recent health probe. */
  error?: string | null;
}

/** Non-secret shape of the configured outbound email transport. */
export interface EmailTransportDetails {
  host?: string;
  port?: number | string;
  username?: string;
  default_from?: string;
  from_name?: string;
}

/** Outbound email transport configuration + live-send gate. */
export interface TransportStatus {
  configured: boolean;
  /** Transport class name (e.g. `smtp`); null when not configured. */
  name: string | null;
  /** Whether the live-send gate (`RUN_LIVE_EMAIL`) is on. */
  live_gated: boolean;
  /** Non-secret configuration shape. Always present, may be empty. */
  details: EmailTransportDetails;
}

/** Model routing — which model runs faculties, which runs the judge. */
export interface ModelRoutingEntry {
  provider?: string;
  via?: string;
  configured: boolean;
  base_url?: string;
  model_id?: string;
}

export interface ModelRoutingStatus {
  faculty_model: ModelRoutingEntry;
  judge_model: ModelRoutingEntry;
  checked_at: string;
}

/** The full /capabilities response, with the C11 health-detail extensions. */
export interface CapabilitiesWithHealth {
  capabilities: Capability[];
  providers: ProviderReachability[];
  transport: TransportStatus;
  model_routing: ModelRoutingStatus;
}
