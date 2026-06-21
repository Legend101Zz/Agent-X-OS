/**
 * Formatting helpers — currency, dates, ring labels, ring colors. Stable across
 * the dashboard so every place that formats a price / ring renders identically.
 */

import type {
  Capability,
  EvalCase,
  JournalEvent,
  RunSummary,
} from "./types";

// ---------- Currency ----------
export function formatCurrency(
  amount: number | null | undefined,
  opts: { currency?: string; sign?: boolean; decimals?: number } = {},
): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return "—";
  const { currency = "USD", sign = false, decimals = 2 } = opts;
  const value = decimals === 0 ? Math.round(amount) : amount;
  const formatter = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  const text = formatter.format(Math.abs(value));
  if (sign) return value >= 0 ? `+${text}` : `−${text}`;
  return value < 0 ? `−${text}` : text;
}

// ---------- Date / time ----------
export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return iso;
  const now = Date.now();
  const diffMs = ts - now;
  const absMs = Math.abs(diffMs);
  const minutes = Math.round(absMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${diffMs < 0 ? "" : "in "}${minutes}m${diffMs < 0 ? " ago" : ""}`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${diffMs < 0 ? "" : "in "}${hours}h${diffMs < 0 ? " ago" : ""}`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${diffMs < 0 ? "" : "in "}${days}d${diffMs < 0 ? " ago" : ""}`;
  const months = Math.round(days / 30);
  if (months < 12) return `${diffMs < 0 ? "" : "in "}${months}mo${diffMs < 0 ? " ago" : ""}`;
  return new Date(iso).toLocaleDateString();
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return iso;
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return iso;
  return new Date(iso).toLocaleDateString();
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return iso;
  return `${formatDate(iso)} ${formatTime(iso)}`;
}

// ---------- Ring ----------
export type Ring = "L0" | "L1" | "L2" | "L3" | "L4" | string;

export function ringLabel(ring: string | null | undefined): string {
  if (!ring) return "—";
  return ring.toUpperCase();
}

export function ringTone(ring: string | null | undefined): "l0" | "l1" | "l2" | "l3" | "l4" | "neutral" {
  if (!ring) return "neutral";
  const r = ring.toUpperCase();
  if (r === "L0") return "l0";
  if (r === "L1") return "l1";
  if (r === "L2") return "l2";
  if (r === "L3") return "l3";
  if (r === "L4") return "l4";
  return "neutral";
}

// ---------- Run state ----------
export type RunState = RunSummary["state"];

export function runStateLabel(state: RunState | string | undefined): string {
  if (!state) return "—";
  return state
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function runStateTone(
  state: RunState | string | undefined,
): "good" | "warn" | "hot" | "info" | "neutral" {
  switch (state) {
    case "active":
      return "info";
    case "complete":
      return "good";
    case "parked":
    case "waiting_approval":
      return "warn";
    case "failed":
      return "hot";
    default:
      return "neutral";
  }
}

// ---------- Health ----------
export function healthTone(
  health: string | undefined,
): "good" | "warn" | "hot" | "neutral" {
  if (!health) return "neutral";
  const h = health.toLowerCase();
  if (h === "ok" || h === "healthy" || h === "live") return "good";
  if (h === "degraded" || h === "queued" || h === "warn") return "warn";
  if (h === "down" || h === "failed" || h === "offline") return "hot";
  return "neutral";
}

// ---------- Capability ----------
export function capabilityMaturity(c: Capability | undefined): "manual" | "fixture" | "api" | "live" | "neutral" {
  if (!c) return "neutral";
  return c.maturity;
}

// ---------- Eval origin ----------
export function evalOriginTone(
  origin: EvalCase["origin"] | undefined,
): "good" | "warn" | "info" | "neutral" {
  switch (origin) {
    case "synthetic":
      return "info";
    case "real":
      return "warn";
    case "human_reviewed":
      return "good";
    default:
      return "neutral";
  }
}

/** Human-readable label for an eval-case origin (used in the UI). */
export function evalOriginLabel(origin: EvalCase["origin"] | string | undefined): string {
  if (!origin) return "—";
  switch (origin) {
    case "synthetic":
      return "synthetic";
    case "real":
      return "real";
    case "human_reviewed":
      return "human-reviewed";
    default:
      return origin;
  }
}

/** Tone for a promotion-state pill on an eval case. */
export function promotionTone(
  promotion: EvalCase["promotion"] | string | undefined,
): "good" | "warn" | "hot" | "info" | "neutral" {
  switch (promotion) {
    case "eligible":
      return "good";
    case "blocked":
      return "hot";
    case "needs_review":
      return "warn";
    default:
      return "neutral";
  }
}

/** Human-readable label for the eval-case promotion state. */
export function promotionLabel(
  promotion: EvalCase["promotion"] | string | undefined,
): string {
  if (!promotion) return "—";
  switch (promotion) {
    case "eligible":
      return "eligible";
    case "blocked":
      return "blocked · synthetic";
    case "needs_review":
      return "needs review";
    default:
      return promotion;
  }
}

/** Tone for the eval-case run-state pill (graded | passed | failed | pending). */
export function evalStatusTone(
  status: string | undefined,
): "good" | "warn" | "hot" | "info" | "neutral" {
  switch (status) {
    case "passed":
      return "good";
    case "graded":
      return "info";
    case "failed":
      return "hot";
    case "pending":
    case "queued":
      return "warn";
    default:
      return "neutral";
  }
}

/** Score → tone band (0..1). Higher is better. */
export function scoreTone(score: number | null | undefined): "good" | "info" | "warn" | "hot" | "neutral" {
  if (score === null || score === undefined || Number.isNaN(score)) return "neutral";
  if (score >= 0.8) return "good";
  if (score >= 0.6) return "info";
  if (score >= 0.4) return "warn";
  return "hot";
}

/** Two-decimal score formatter. Returns "—" for nullish / NaN. */
export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined || Number.isNaN(score)) return "—";
  return score.toFixed(2);
}

// ---------- Journal kind ----------
export function journalKindTone(kind: string | undefined): "good" | "warn" | "hot" | "info" | "neutral" {
  if (!kind) return "neutral";
  const k = kind.toLowerCase();
  if (k.endsWith("settled") || k.endsWith("committed") || k.endsWith("approved")) return "good";
  if (k.includes("park") || k.includes("approval") || k.includes("escalat")) return "warn";
  if (k.includes("failed") || k.includes("reject") || k.includes("crash")) return "hot";
  if (k.includes("claim") || k.includes("send") || k.includes("think") || k.includes("call")) return "info";
  return "neutral";
}

// ---------- Numbers ----------
export function formatInt(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("en-US").format(n);
}

export function formatPercent(n: number | null | undefined, decimals = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(decimals)}%`;
}

// ---------- Stable short id ----------
export function shortId(id: string | null | undefined, head = 6): string {
  if (!id) return "—";
  const cleaned = id.replace(/^(inst_|run_|evt_|fact_|case_|pack_|cmd_|job_|wkr_|cap_|mt_)/, "");
  if (cleaned.length <= head) return cleaned || id;
  return `${cleaned.slice(0, head)}…`;
}

// ---------- Truncate ----------
export function truncate(text: string | null | undefined, max = 80): string {
  if (!text) return "";
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}…`;
}

// ---------- Type guards ----------
export function isJournalEvent(value: unknown): value is JournalEvent {
  return (
    typeof value === "object" &&
    value !== null &&
    "kind" in value &&
    typeof (value as { kind: unknown }).kind === "string"
  );
}

// ---------- Kernel / scheduler helpers (C14) ----------
export type StatusTone = "good" | "warn" | "hot" | "info" | "neutral" | "muted";

export function schedulerStatusTone(status: string | undefined): StatusTone {
  switch (status) {
    case "pending":
      return "info";
    case "claimed":
      return "warn";
    case "completed":
      return "good";
    case "failed":
      return "hot";
    default:
      return "neutral";
  }
}

export function schedulerStatusLabel(status: string | undefined): string {
  if (!status) return "—";
  return status.charAt(0).toUpperCase() + status.slice(1).replaceAll("_", " ");
}

export function schedulerKindTone(kind: string | undefined): StatusTone {
  if (kind === "trigger") return "info";
  if (kind === "approval") return "warn";
  return "neutral";
}

export function formatAttempts(attempts: number | null | undefined): string {
  if (attempts === null || attempts === undefined) return "—";
  return `${attempts} ${attempts === 1 ? "attempt" : "attempts"}`;
}

export function healthStatusTone(status: string | undefined): StatusTone {
  return healthTone(status);
}

export function backendTone(backend: string | undefined): StatusTone {
  if (!backend) return "muted";
  const b = backend.toLowerCase();
  if (b === "memory" || b === "mongo") return "good";
  return "neutral";
}

export function kernelHealthTone(input: { ok?: boolean; backend?: string; mode?: string } | undefined): StatusTone {
  if (!input) return "neutral";
  if (input.ok && input.backend) return "good";
  if (input.mode === "disconnected" && input.backend) return "warn";
  if (!input.backend) return "hot";
  return input.ok ? "good" : "warn";
}
