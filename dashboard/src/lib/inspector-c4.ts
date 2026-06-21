/**
 * Pure helpers for the Inspector's Memory + Actions tabs (C4, BLUEPRINT §6
 * tabs 3 + 4).
 *
 * These functions are deliberately framework-agnostic (no React, no fetch)
 * so they're trivially unit-testable with `node:test`. The tab components
 * call into them, the tests pin their behaviour, and the tabs stay focused
 * on rendering.
 *
 * Why split these out?
 *
 *   - `isSyscallKind` / `filterSyscallEvents` — the Actions tab's whole job
 *     is to surface *syscall* journal rows (intent + effect), filtering
 *     out run-level / approval-level noise. A pure function is the obvious
 *     shape for that filter, and easy to test against fixtures.
 *
 *   - `factConfidenceTone` / `factStatusTone` / `factStatusLabel` — the
 *     Memory tab shows the heap as a fact list; the visual emphasis
 *     (Verified vs Probation vs Retired, plus confidence bin) is the
 *     Memory tab's information design. Pinning the bin edges here keeps
 *     the colour decisions consistent with the C1 pill primitive.
 *
 *   - `formatFactSummary` / `truncateArgs` — small UI helpers used inside
 *     the row + JsonViewer headers. Not interesting enough to ship as a
 *     primitive; useful enough to test.
 */
import type { JournalEvent } from "./types";

/** The two journal event kinds the Actions tab surfaces. */
export const SYSCALL_KINDS = ["syscall_attempted", "syscall_settled"] as const;
export type SyscallKind = (typeof SYSCALL_KINDS)[number];

/** True for the journal kinds the Actions tab is scoped to. */
export function isSyscallKind(kind: string | undefined | null): kind is SyscallKind {
  if (!kind) return false;
  return (SYSCALL_KINDS as readonly string[]).includes(kind);
}

/**
 * Filter a journal-event list to just the syscall rows. Preserves the
 * original ordering (newest-at-end, matching the C2 activity tab's
 * convention).
 *
 * Defensive: tolerates undefined / null / non-array input so the tab can
 * render an EmptyState before data has loaded.
 */
export function filterSyscallEvents(events: JournalEvent[] | null | undefined): JournalEvent[] {
  if (!Array.isArray(events)) return [];
  return events.filter((e) => isSyscallKind(e?.kind));
}

/**
 * Tone for a syscall journal entry. Settled = "good" (the effect happened);
 * attempted = "info" (intent, not yet resolved). Everything else falls
 * back to "neutral" so the Actions tab's timeline dots stay consistent with
 * the Activity tab.
 */
export function journalActionTone(kind: string | undefined | null): "good" | "info" | "neutral" {
  if (kind === "syscall_settled") return "good";
  if (kind === "syscall_attempted") return "info";
  return "neutral";
}

/**
 * Bin a fact's confidence (0..1) into a pill tone. Edges chosen to match
 * the rest of the dashboard's status language:
 *   - ≥0.7  → good   (a trustworthy fact)
 *   - 0.3..0.7 → warn (a hedged fact)
 *   - <0.3  → hot    (a low-confidence fact worth scrutinising)
 * Inputs outside 0..1 are clamped so a buggy kernel write can't crash the UI.
 */
export function factConfidenceTone(confidence: number | null | undefined): "good" | "warn" | "hot" {
  if (confidence === null || confidence === undefined || Number.isNaN(confidence)) return "warn";
  if (confidence >= 0.7) return "good";
  if (confidence >= 0.3) return "warn";
  return "hot";
}

/**
 * Tone for a fact's promotion status. Matches the spec's three-state life
 * cycle: probation → promoted (after reality confirms) → retired (after
 * reality contradicts). Anything unrecognised degrades to neutral rather
 * than throwing, so a forward-compatible kernel write doesn't break the UI.
 */
export function factStatusTone(status: string | null | undefined): "good" | "warn" | "hot" | "neutral" {
  if (status === "promoted") return "good";
  if (status === "probation") return "warn";
  if (status === "retired") return "hot";
  return "neutral";
}

/**
 * Display label for a fact's status. The kernel's three-state vocabulary
 * is domain language; the dashboard surfaces friendlier labels.
 */
export function factStatusLabel(status: string | null | undefined): string {
  if (status === "promoted") return "Verified";
  if (status === "probation") return "Probation";
  if (status === "retired") return "Retired";
  return status ?? "—";
}

/**
 * Render a fact's triple as a one-line subject-predicate-object string for
 * the Memory tab's row label. Empty / missing fields degrade to a
 * placeholder rather than blowing up — the kernel may emit a partial fact
 * during a settling run.
 */
export function formatFactSummary(fact: {
  subject?: string | null;
  predicate?: string | null;
  object?: string | null;
}): string {
  const subject = (fact.subject ?? "").toString().trim() || "(unknown)";
  const predicate = (fact.predicate ?? "").toString().trim() || "is";
  const object = (fact.object ?? "").toString().trim() || "?";
  return `${subject} ${predicate} ${object}`;
}

/**
 * Truncate a JSON arg payload (from SyscallAttempted.args) to a short
 * preview for the Actions tab's collapsed timeline entries. Returns a
 * single line with an ellipsis if the payload was too big to fit.
 *
 * The cap is in characters of *serialised* output, not bytes — close
 * enough for a UI preview and keeps the function sync (no async JSON
 * serialisation). `max` defaults to ~80 chars which is a comfortable one
 * line in the timeline row.
 */
export function truncateArgs(args: unknown, max = 80): string {
  let serialised: string;
  try {
    serialised = JSON.stringify(args ?? {});
  } catch {
    serialised = String(args);
  }
  if (serialised.length <= max) return serialised;
  return `${serialised.slice(0, Math.max(0, max - 1))}…`;
}
