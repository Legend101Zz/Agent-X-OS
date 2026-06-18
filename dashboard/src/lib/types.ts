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
  trace: TraceEvent[];
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

export interface DashboardData {
  health: HealthStatus;
  overview: SystemOverview;
  instances: InstanceSummary[];
  runs: RunSummary[];
  mandateTypes: MandateType[];
  journal: JournalEvent[];
  capabilities: Capability[];
  evalCases: EvalCase[];
  manualQueue: ManualTask[];
  coreGaps: CoreGap[];
}

export interface CommandPayload {
  instance_id: string;
  run_id?: string;
  ring?: string;
  actor: string;
}

export interface CommandResult {
  supported: boolean;
  status?: string;
  receipt?: string;
  sent?: boolean;
  message?: string;
  gap?: CoreGap;
}
