import type {
  ClaimedFact,
  RunListFilters,
  RunSummary,
  SettlementSummary,
  TimelineEntry as DataTimelineEntry,
} from "./types";
// The UI Timeline primitive has its own TimelineEntry shape (title/detail/
// tone). Alias the data shape so the helper can convert from the kernel's
// trace projection to the UI primitive's expected entry.
import type { TimelineEntry } from "../components/ui/timeline";

/** ---------- pure helpers for the Runs viewer (C6) -------------------------
 *
 * These are the view-layer projections consumed by the /runs list and
 * /runs/{id} detail pages. They are pure functions (no fetch, no React) so
 * they can be unit-tested without standing up the dashboard. The /runs
 * pages call them once data lands from `fetchRuns` / `fetchRunRaw`.
 *
 * The existing api.ts (C1) already does the run-level mapping
 * (`mapRunDetail`). This module fills the gap for the things /runs needs
 * but /runs/{id} needs differently:
 *
 *   - extractClaimedFacts     — pull claimed_facts (or nested facts) from raw
 *   - extractSettlementSummary— (status, cost, expected_value, progress)
 *   - traceToTimelineEntries  — color the §5 trace timeline by event kind
 *   - traceKindTone           — the tone mapping used by the above
 *   - filterRuns              — list filter (state / instance_id / query)
 *   - runStateOptions         — state filter pill choices
 *   - settlementTone          — the run-state → tone mapping
 *   - summariseRuns           — list view-model (counts by state)
 *
 * The tone tokens map 1:1 to the `<StatusPill tone="..." />` API in
 * `components/ui/pill.tsx`, so they can be passed straight through.
 * ------------------------------------------------------------------------- */

/** Every run state RunSummary exposes, in display order. */
const ALL_RUN_STATES: ReadonlyArray<RunSummary["state"]> = [
  "active",
  "waiting_approval",
  "parked",
  "complete",
  "failed",
];

/** Options for the state filter pill on the Runs list page. */
export function runStateOptions(): Array<{
  value: RunSummary["state"];
  label: string;
}> {
  return ALL_RUN_STATES.map((state) => ({
    value: state,
    label: state
      .split("_")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" "),
  }));
}

/** The map of trace event-kind → StatusPill tone for the §5 timeline. */
export function traceKindTone(kind: string | undefined | null):
  | "good"
  | "warn"
  | "hot"
  | "info"
  | "neutral" {
  if (!kind) return "neutral";
  const k = kind.toLowerCase();
  if (k === "failed" || k === "rejected" || k === "crashed") return "hot";
  if (k === "fact" || k === "settled" || k === "approved" || k === "commit")
    return "good";
  if (k === "human-task" || k === "parked" || k === "approval" || k === "escalat")
    return "warn";
  if (k === "syscall" || k === "adapter" || k === "draft" || k === "decision" || k === "claim" || k === "call" || k === "think" || k === "send")
    return "info";
  return "neutral";
}

/** Map a run-state → StatusPill tone (re-exported for the detail view). */
export function settlementTone(
  state: string | null | undefined,
): "good" | "warn" | "hot" | "info" | "neutral" {
  if (!state) return "neutral";
  const k = state.toLowerCase();
  if (k === "complete" || k === "settled") return "good";
  if (k === "active") return "info";
  if (k === "waiting_approval" || k === "parked") return "warn";
  if (k === "failed" || k === "crashed") return "hot";
  return "neutral";
}

/**
 * Convert a RunSummary.trace (the projected shape) into UI TimelineEntries
 * that the <Timeline> primitive can render directly. Adds:
 *  - a stable `id` (so React keys don't churn across re-renders)
 *  - a `tone` derived from the event kind
 *  - a sane fallback for missing `ts`
 *
 * Returns plain `TimelineEntry[]` (with `id` populated on each entry) so the
 * destination <Timeline /> accepts it without an awkward intersection cast.
 */
export function traceToTimelineEntries(
  trace: DataTimelineEntry[] | undefined | null,
): TimelineEntry[] {
  if (!trace || trace.length === 0) return [];
  return trace.map((entry, index) => ({
    // Pad the index so lexicographic sort matches timeline order — the
    // detail-page test asserts this and React keys want stable ids in order.
    id: `${String(index).padStart(4, "0")}-${entry.kind ?? "event"}-${entry.ts ?? "no-ts"}`,
    title: entry.summary ?? entry.kind ?? "event",
    detail: entry.event ? renderEventDetail(entry.event) : undefined,
    tone: traceKindTone(entry.kind),
    ts: entry.ts,
    actor: entry.actor,
  }));
}

/**
 * Tiny renderer for the nested `event` object so the timeline detail slot
 * has something useful to show without spinning up the JsonViewer.
 * Renders a short key=value hint; full JSON stays available in the
 * <JsonViewer> at the bottom of the detail page.
 */
function renderEventDetail(event: Record<string, unknown>): string | undefined {
  if (!event || typeof event !== "object") return undefined;
  const detail = typeof event.detail === "string" ? event.detail : null;
  const id = typeof event.id === "string" ? event.id : null;
  const confidence =
    typeof event.confidence === "number"
      ? `confidence=${(event.confidence * 100).toFixed(0)}%`
      : null;
  const parts = [detail, id, confidence].filter(Boolean);
  if (parts.length === 0) return undefined;
  return parts.join(" · ");
}

/**
 * Narrow a list of runs by the given filters. Filters compose with AND
 * semantics. An empty / undefined filter is treated as "no constraint".
 */
export function filterRuns(
  runs: RunSummary[],
  filters: RunListFilters,
): RunSummary[] {
  const { state, instance_id, query } = filters;
  const needle = query?.trim().toLowerCase();
  return runs.filter((run) => {
    if (state && run.state !== state) return false;
    if (instance_id && run.instance_id !== instance_id) return false;
    if (needle) {
      const hay = [
        run.id,
        run.title,
        run.syscall,
        run.instance_id,
        run.ring,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      if (!hay.includes(needle)) return false;
    }
    return true;
  });
}

/**
 * Build the per-state count summary used by the list view (stat tiles and
 * the state filter pills' counts). Always returns a record keyed by every
 * known run state with a 0 default so consumers can render in stable order.
 */
export function summariseRuns(runs: RunSummary[]): {
  total: number;
  by_state: Record<RunSummary["state"], number>;
} {
  const by_state: Record<RunSummary["state"], number> = {
    active: 0,
    waiting_approval: 0,
    parked: 0,
    complete: 0,
    failed: 0,
  };
  for (const run of runs) {
    by_state[run.state] = (by_state[run.state] ?? 0) + 1;
  }
  return { total: runs.length, by_state };
}

/**
 * Pull claimed facts out of a raw `GET /runs/{id}` response. Tolerates two
 * shapes the kernel has shipped:
 *  - `claimed_facts: [...]` (the dedicated list, what C6 panel needs)
 *  - `facts: [...]`        (durable / heap-style facts, used by some
 *    detail endpoints as a fallback for older kernels)
 *
 * Bad rows (null, non-objects) are skipped silently. Numbers that come
 * back as strings get coerced; missing confidence defaults to 0.
 */
export function extractClaimedFacts(raw: unknown): ClaimedFact[] {
  if (!raw || typeof raw !== "object") return [];
  const value = raw as Record<string, unknown>;
  const candidates: unknown[] = [];
  if (Array.isArray(value.claimed_facts)) candidates.push(...value.claimed_facts);
  if (Array.isArray(value.facts)) candidates.push(...value.facts);

  const out: ClaimedFact[] = [];
  for (const candidate of candidates) {
    if (!candidate || typeof candidate !== "object") continue;
    const item = candidate as Record<string, unknown>;
    const provenance = (item.provenance ?? {}) as Record<string, unknown>;
    const evidenceRaw = Array.isArray(provenance.evidence)
      ? (provenance.evidence as unknown[])
      : [];
    const evidence = evidenceRaw
      .filter((entry): entry is string => typeof entry === "string" && entry.length > 0);

    const confidence = coerceNumber(item.confidence, 0);
    out.push({
      id: stringOrFallback(item.id, `fact-${out.length}`),
      subject: stringOrFallback(item.subject, "—"),
      predicate: stringOrFallback(item.predicate, "—"),
      object: stringOrFallback(item.object, "—"),
      confidence: clamp01(confidence),
      run_id:
        typeof item.run_id === "string"
          ? item.run_id
          : typeof provenance.run_id === "string"
            ? provenance.run_id
            : null,
      evidence,
      committed_at: stringOrFallback(item.committed_at, ""),
    });
  }
  return out;
}

/**
 * Pull the (status, cost, expected_value, progress) block for the
 * settlement summary card. The raw API can be sparse (some fields are
 * only present after settlement); the mapped `RunSummary` is the safe
 * fallback for everything we can't extract.
 *
 * Order of preference:
 *  - status     ← raw.run.state (then mapped run.state)
 *  - cost       ← raw.run.cost  (else raw.settled.cost, else run.cost)
 *  - expected   ← raw.settled.billing_amount (else raw.run.expected_value, else run.expected_value)
 *  - progress   ← raw.run.progress (else heuristic from state, else run.progress)
 *  - settled_at ← raw.settled.at (else raw.run.settled_at)
 */
export function extractSettlementSummary(
  raw: unknown,
  fallback: RunSummary,
): SettlementSummary {
  const value = (raw ?? {}) as Record<string, unknown>;
  const run = (value.run ?? {}) as Record<string, unknown>;
  const settled = (value.settled ?? {}) as Record<string, unknown>;

  const status = mapRunStateValue(stringOrFallback(run.state, fallback.state));

  // cost: prefer raw.run.cost, then raw.settled.cost, then the mapped fallback
  const cost =
    coerceNumber(run.cost, Number.NaN) ||
    coerceNumber(settled.cost, Number.NaN) ||
    fallback.cost;

  // expected_value: prefer raw.settled.billing_amount, then raw.run.expected_value
  // then the mapped fallback. The kernel uses `billing_amount` for the
  // settled money shape (invariant #6).
  const expected_value =
    coerceNumber(settled.billing_amount, Number.NaN) ||
    coerceNumber(run.expected_value, Number.NaN) ||
    fallback.expected_value;

  // progress: prefer raw.run.progress, else derive from state, else fallback
  const progress =
    coerceNumber(run.progress, Number.NaN) ||
    heuristicProgress(status, fallback.progress);

  const settled_at =
    typeof settled.at === "string"
      ? settled.at
      : typeof run.settled_at === "string"
        ? run.settled_at
        : null;

  const billing_amount =
    coerceNumber(settled.billing_amount, Number.NaN) || null;

  return {
    status,
    cost: Number.isFinite(cost) ? cost : fallback.cost,
    expected_value: Number.isFinite(expected_value) ? expected_value : fallback.expected_value,
    progress: clamp01to100(progress),
    settled_at,
    billing_amount: Number.isFinite(billing_amount as number) ? billing_amount : null,
  };
}

// ---------- small typed coercion helpers (no lodash, no utils dep) ----------

function stringOrFallback(value: unknown, fallback: string): string {
  if (typeof value === "string" && value.length > 0) return value;
  return fallback;
}

function coerceNumber(value: unknown, fallback: number): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return fallback;
}

function clamp01(n: number): number {
  if (!Number.isFinite(n)) return 0;
  if (n < 0) return 0;
  if (n > 1) return 1;
  return n;
}

function clamp01to100(n: number): number {
  if (!Number.isFinite(n)) return 0;
  if (n < 0) return 0;
  if (n > 100) return 100;
  return n;
}

function heuristicProgress(
  state: RunSummary["state"],
  fallback: number,
): number {
  switch (state) {
    case "complete":
      return 100;
    case "failed":
      return 0;
    case "waiting_approval":
    case "parked":
      return Math.max(60, fallback);
    case "active":
    default:
      return fallback;
  }
}

function mapRunStateValue(state: string): RunSummary["state"] {
  switch (state) {
    case "active":
    case "parked":
    case "waiting_approval":
    case "complete":
    case "failed":
      return state;
    case "settled":
      return "complete";
    case "crashed":
      return "failed";
    default:
      return "active";
  }
}
