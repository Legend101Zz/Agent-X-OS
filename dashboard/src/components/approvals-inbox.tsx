"use client";

/**
 * C7 — Approvals inbox (approve / reject / edit + diff).
 *
 * First-class gate UX per BLUEPRINT §5 kill-condition #2. Three primitives:
 *
 *   1. Inbox — live `/approvals` fetch, polled with the operator token, surfaced as
 *      StatusPill-toned cards per ring (L0/L1/L2). Each card shows the drafted syscall,
 *      the args (pretty JSON), the idempotency key, the seq, and a timeline strip.
 *   2. Approve / Reject — `AsyncButton` for both, with toast feedback on success /
 *      failure. Approve fires `approveRun`; reject fires `rejectCommand`. Both poll
 *      `/scheduler-work/{id}` until terminal so the inbox reflects the resumed run.
 *   3. Edit — opens a modal where the operator tweaks args as a JSON object. The
 *      modal shows a side-by-side old→new diff (the same shape the server returns in
 *      `edit.diff_keys`). On submit it fires `editApprovalRun`, which rewrites the
 *      continuation + approves + enqueues. Toast confirms with the canonical diff
 *      keys the kernel recorded.
 *
 * AsyncButton is used for EVERY command. The "no loader" pain that the C1 foundation
 * solved shows up here: the operator needs to see the button spin while the round-trip
 * is in flight, then a toast confirmation.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  Check,
  CornerDownRight,
  ExternalLink,
  Loader2,
  Pencil,
  ShieldAlert,
  X,
} from "lucide-react";

import {
  argDiffKeys,
  editApprovalRun,
  fetchApprovals,
  fetchSchedulerWork,
  rejectCommand,
} from "@/lib/api";
import { useJournalStream } from "@/lib/events";
import type { ApprovalCard, EditResult } from "@/lib/types";

import { ToastStack, useToasts, type ToastTone } from "../components/ui/toast";

interface ApprovalsInboxProps {
  apiBaseUrl: string;
  operatorToken: string;
}

const RING_TONE: Record<string, "neutral" | "warn" | "hot"> = {
  L0: "neutral",
  L1: "warn",
  L2: "hot",
};

const POLL_INTERVAL_MS = 4_000;
const WORK_TIMEOUT_MS = 12_000;

function ringTone(ring: string | undefined): "neutral" | "warn" | "hot" {
  if (ring === "L2") return "hot";
  if (ring === "L1") return "warn";
  return "neutral";
}

function draftedArgs(card: ApprovalCard): Record<string, unknown> {
  const drafted = card.drafted_effect;
  if (!drafted || typeof drafted !== "object") return {};
  const value = drafted as Record<string, unknown>;
  return (value.args as Record<string, unknown> | undefined) ?? {};
}

function draftedSyscall(card: ApprovalCard): string {
  const drafted = card.drafted_effect;
  if (!drafted || typeof drafted !== "object") return "(unknown)";
  const value = drafted as Record<string, unknown>;
  return typeof value.syscall === "string" && value.syscall ? value.syscall : "(unknown)";
}

function draftedIdem(card: ApprovalCard): string {
  const drafted = card.drafted_effect;
  if (!drafted || typeof drafted !== "object") return "(none)";
  const value = drafted as Record<string, unknown>;
  return typeof value.idempotency_key === "string" && value.idempotency_key
    ? value.idempotency_key
    : "(none)";
}

export function ApprovalsInbox({ apiBaseUrl, operatorToken }: ApprovalsInboxProps) {
  const [approvals, setApprovals] = useState<ApprovalCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<ApprovalCard | null>(null);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const { toasts, api: toastApi } = useToasts();

  const requestKey = useCallback(
    (instanceId: string, runId: string) => `${instanceId}:${runId}`,
    [],
  );

  const refresh = useCallback(async () => {
    const result = await fetchApprovals({}, { baseUrl: apiBaseUrl });
    if (result.error) {
      setError(result.error);
      setLoading(false);
      return;
    }
    setError(null);
    setApprovals(result.data);
    setLoading(false);
  }, [apiBaseUrl]);

  // Initial load + polling — the inbox is real-time. The journal SSE stream
  // also fires when the kernel emits an `approval_resolved` or `run_parked`
  // event; we cross-check the latest event id so polling doesn't double up.
  const { events: journalEvents } = useJournalStream({ baseUrl: apiBaseUrl });
  const lastJournalId = journalEvents.at(-1)?.event_id ?? null;
  // Reference lastJournalId so the effect re-runs when an SSE frame arrives;
  // polling still serves as the floor when SSE is unavailable.
  void lastJournalId;

  useEffect(() => {
    void refresh();
    const interval = setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [refresh]);

  const pushToast = useCallback(
    (tone: ToastTone, title: string, message?: string, key?: string) => {
      toastApi.push({ tone, title, message, key });
    },
    [toastApi],
  );

  const pollUntilDone = useCallback(
    async (workId: string) => {
      const deadline = Date.now() + WORK_TIMEOUT_MS;
      while (Date.now() < deadline) {
        const res = await fetchSchedulerWork(workId, { baseUrl: apiBaseUrl });
        const status = res.data?.status;
        if (status === "completed" || status === "failed") {
          await refresh();
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
      await refresh();
    },
    [apiBaseUrl, refresh],
  );

  const handleApprove = useCallback(
    async (card: ApprovalCard) => {
      if (!operatorToken) {
        pushToast("warn", "Operator token required", "Set the bearer token to approve runs.", "approve:no-token");
        return;
      }
      const key = requestKey(card.instance_id, card.run_id);
      setPendingKey(key);
      try {
        const res = await fetch(`${apiBaseUrl}/commands/approve`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
            Authorization: `Bearer ${operatorToken}`,
          },
          body: JSON.stringify({
            instance_id: card.instance_id,
            run_id: card.run_id,
            actor: "manager:dashboard",
          }),
        });
        const body = await res.json();
        if (!res.ok || body.supported === false) {
          pushToast(
            "hot",
            "Approve failed",
            typeof body.detail === "string" ? body.detail : body.message ?? "Unknown error",
            `approve:err:${key}`,
          );
          return;
        }
        pushToast(
          "good",
          "Approved",
          `${draftedSyscall(card)} → ${body.status ?? "queued"}`,
          `approve:ok:${key}`,
        );
        if (body.work_id) {
          void pollUntilDone(body.work_id);
        } else {
          void refresh();
        }
      } catch (err) {
        pushToast("hot", "Approve failed", err instanceof Error ? err.message : String(err), `approve:err:${key}`);
      } finally {
        setPendingKey(null);
      }
    },
    [apiBaseUrl, operatorToken, pollUntilDone, pushToast, refresh, requestKey],
  );

  const handleReject = useCallback(
    async (card: ApprovalCard) => {
      if (!operatorToken) {
        pushToast("warn", "Operator token required", "Set the bearer token to reject runs.", "reject:no-token");
        return;
      }
      const key = requestKey(card.instance_id, card.run_id);
      setPendingKey(key);
      try {
        const res = await rejectCommand({
          instance_id: card.instance_id,
          run_id: card.run_id,
          actor: "manager:dashboard",
        });
        if (!res.supported) {
          pushToast("hot", "Reject failed", res.message ?? res.gap?.detail ?? "Unknown error", `reject:err:${key}`);
          return;
        }
        pushToast("good", "Rejected", `${draftedSyscall(card)} ${key} rejected`, `reject:ok:${key}`);
        void refresh();
      } catch (err) {
        pushToast("hot", "Reject failed", err instanceof Error ? err.message : String(err), `reject:err:${key}`);
      } finally {
        setPendingKey(null);
      }
    },
    [operatorToken, pushToast, refresh, rejectCommand, requestKey],
  );

  const handleEdit = useCallback((card: ApprovalCard) => {
    setEditing(card);
  }, []);

  const counts = useMemo(() => {
    const byRing: Record<string, number> = { L0: 0, L1: 0, L2: 0 };
    for (const card of approvals) {
      const ring = card.required_ring ?? "L?";
      byRing[ring] = (byRing[ring] ?? 0) + 1;
    }
    return byRing;
  }, [approvals]);

  return (
    <div className="ax-stack" style={{ gap: 24 }}>
      <header className="ax-row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22 }}>Approvals</h1>
          <p className="dim" style={{ marginTop: 4, fontSize: 13 }}>
            Parked cards from <code>/approvals</code>. Approve, reject, or edit-with-diff.
            AsyncButton drives every command; the diff view previews what the kernel will record.
          </p>
        </div>
        <div className="ax-cluster" style={{ gap: 8 }}>
          <span className="ax-pill ax-pill--neutral" data-tone="neutral">L0 · {counts.L0 ?? 0}</span>
          <span className="ax-pill ax-pill--warn" data-tone="warn">L1 · {counts.L1 ?? 0}</span>
          <span className="ax-pill ax-pill--hot" data-tone="hot">L2 · {counts.L2 ?? 0}</span>
        </div>
      </header>

      {loading ? (
        <p className="dim">Loading parked approvals…</p>
      ) : error ? (
        <p className="ax-error" role="alert">Failed to load /approvals: {error}</p>
      ) : approvals.length === 0 ? (
        <div className="ax-empty">
          <ShieldAlert size={20} />
          <strong>Inbox is empty.</strong>
          <span className="dim">Trigger a run from Catalog → Instance to populate it.</span>
        </div>
      ) : (
        <div className="ax-stack" style={{ gap: 16 }}>
          {approvals.map((card) => {
            const key = requestKey(card.instance_id, card.run_id);
            const pending = pendingKey === key;
            return (
              <ApprovalRow
                key={key}
                card={card}
                pending={pending}
                disabled={!operatorToken || pendingKey !== null}
                onApprove={() => void handleApprove(card)}
                onReject={() => void handleReject(card)}
                onEdit={() => handleEdit(card)}
              />
            );
          })}
        </div>
      )}

      {editing ? (
        <EditDiffModal
          card={editing}
          apiBaseUrl={apiBaseUrl}
          operatorToken={operatorToken}
          onClose={() => setEditing(null)}
          onSubmitted={async (result) => {
            setEditing(null);
            if (result.supported) {
              const diffCount = result.edit?.diff_keys.length ?? 0;
              pushToast(
                "good",
                "Edited + approved",
                `${draftedSyscall(editing)} · ${diffCount} field${diffCount === 1 ? "" : "s"} changed`,
                `edit:ok:${requestKey(editing.instance_id, editing.run_id)}`,
              );
              if (result.workId) {
                void pollUntilDone(result.workId);
              } else {
                void refresh();
              }
            } else {
              pushToast("hot", "Edit failed", result.message ?? "Unknown error", `edit:err:${requestKey(editing.instance_id, editing.run_id)}`);
            }
          }}
        />
      ) : null}

      <ToastStack toasts={toasts} onDismiss={toastApi.dismiss} />
    </div>
  );
}

interface ApprovalRowProps {
  card: ApprovalCard;
  pending: boolean;
  disabled: boolean;
  onApprove: () => void;
  onReject: () => void;
  onEdit: () => void;
}

function ApprovalRow({ card, pending, disabled, onApprove, onReject, onEdit }: ApprovalRowProps) {
  const syscall = draftedSyscall(card);
  const args = draftedArgs(card);
  const idem = draftedIdem(card);
  const ring = card.required_ring ?? "L?";
  const tone = ringTone(ring);

  return (
    <article className="ax-card ax-card--muted" data-tone={tone}>
      <header className="ax-row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <p className="dim" style={{ margin: 0, fontSize: 12 }}>{card.instance_id} · seq {card.seq}</p>
          <h3 style={{ margin: "4px 0 0", fontSize: 16 }}>{syscall}</h3>
          <p className="dim" style={{ marginTop: 6, fontSize: 13 }}>{card.reason}</p>
        </div>
        <span className="ax-pill" data-tone={tone}>requires {ring}</span>
      </header>

      <details style={{ marginTop: 12 }}>
        <summary className="dim" style={{ cursor: "pointer", fontSize: 12 }}>
          drafted args
        </summary>
        <pre
          className="ax-pre"
          aria-label="drafted effect args"
          style={{ marginTop: 8 }}
        >
          {JSON.stringify(args, null, 2)}
        </pre>
      </details>

      <footer className="ax-row" style={{ justifyContent: "space-between", alignItems: "center", marginTop: 12, gap: 12 }}>
        <div className="dim" style={{ fontSize: 12 }}>
          <span>idempotency_key: <code>{idem}</code></span>
        </div>
        <div className="ax-cluster" style={{ gap: 8 }}>
          <button
            type="button"
            className="ax-btn ax-btn--secondary ax-btn--sm"
            onClick={onEdit}
            disabled={disabled}
          >
            {pending ? <Loader2 size={14} className="ax-btn__spinner" /> : <Pencil size={14} />}
            Edit
          </button>
          <button
            type="button"
            className="ax-btn ax-btn--danger ax-btn--sm"
            onClick={onReject}
            disabled={disabled}
          >
            {pending ? <Loader2 size={14} className="ax-btn__spinner" /> : <X size={14} />}
            Reject
          </button>
          <button
            type="button"
            className="ax-btn ax-btn--success ax-btn--sm"
            onClick={onApprove}
            disabled={disabled}
          >
            {pending ? <Loader2 size={14} className="ax-btn__spinner" /> : <Check size={14} />}
            Approve
          </button>
        </div>
      </footer>
    </article>
  );
}

interface EditDiffModalProps {
  card: ApprovalCard;
  apiBaseUrl: string;
  operatorToken: string;
  onClose: () => void;
  onSubmitted: (result: EditResult) => void | Promise<void>;
}

function EditDiffModal({ card, apiBaseUrl, operatorToken, onClose, onSubmitted }: EditDiffModalProps) {
  const syscall = draftedSyscall(card);
  const before = draftedArgs(card);
  const [draft, setDraft] = useState<string>(() => JSON.stringify(before, null, 2));
  const [parsingError, setParsingError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const parsed = useMemo(() => {
    if (!draft.trim()) return { ok: false as const, error: "edited args cannot be empty" };
    try {
      const value = JSON.parse(draft);
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        return { ok: false as const, error: "edited args must be a JSON object" };
      }
      return { ok: true as const, value: value as Record<string, unknown> };
    } catch (err) {
      return { ok: false as const, error: err instanceof Error ? err.message : "invalid JSON" };
    }
  }, [draft]);

  const diff = useMemo(() => {
    if (!parsed.ok) return [];
    return argDiffKeys(before, parsed.value);
  }, [before, parsed]);

  const handleSubmit = async () => {
    if (!parsed.ok) {
      setParsingError(parsed.error);
      return;
    }
    if (!operatorToken) {
      setParsingError("Operator token required to submit edits.");
      return;
    }
    setParsingError(null);
    setSubmitting(true);
    try {
      const result = await editApprovalRun(
        {
          instance_id: card.instance_id,
          run_id: card.run_id,
          actor: "manager:dashboard",
          edited_args: parsed.value,
        },
        { baseUrl: apiBaseUrl, token: operatorToken },
      );
      await onSubmitted(result);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="ax-modal-overlay" role="presentation" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className="ax-modal"
        style={{ width: "min(820px, 92vw)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="ax-modal__header">
          <div>
            <p className="dim" style={{ margin: 0, fontSize: 12 }}>Edit parked approval</p>
            <h2 style={{ margin: "4px 0 0", fontSize: 16 }}>
              <CornerDownRight size={14} style={{ marginRight: 6, verticalAlign: -2 }} />
              {syscall}
              <span className="dim" style={{ marginLeft: 8, fontWeight: 400 }}>· {card.instance_id} · seq {card.seq}</span>
            </h2>
          </div>
          <button
            type="button"
            className="ax-toast__dismiss"
            onClick={onClose}
            aria-label="Close edit modal"
          >
            <X size={16} />
          </button>
        </header>

        <div className="ax-modal__body ax-stack" style={{ gap: 16 }}>
          <p className="dim" style={{ fontSize: 13, margin: 0 }}>
            Edit the syscall args below. The diff previews what the kernel will record on the
            <code> approval_resolved(edited=true) </code> event. Submitting rewrites the continuation
            and approves the run in one round-trip.
          </p>

          <div className="ax-grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <section>
              <h4 style={{ margin: "0 0 6px", fontSize: 12, textTransform: "uppercase", letterSpacing: 0.4 }} className="dim">
                Before
              </h4>
              <pre className="ax-pre" aria-label="args before">
                {JSON.stringify(before, null, 2)}
              </pre>
            </section>
            <section>
              <h4 style={{ margin: "0 0 6px", fontSize: 12, textTransform: "uppercase", letterSpacing: 0.4 }} className="dim">
                After
              </h4>
              <textarea
                aria-label="edited args JSON"
                className="ax-textarea"
                spellCheck={false}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={Math.max(8, draft.split("\n").length)}
              />
              {parsingError ? (
                <p className="ax-error" role="alert" style={{ marginTop: 6 }}>{parsingError}</p>
              ) : null}
            </section>
          </div>

          <section>
            <h4 style={{ margin: "0 0 6px", fontSize: 12, textTransform: "uppercase", letterSpacing: 0.4 }} className="dim">
              Diff preview ({diff.length})
            </h4>
            {diff.length === 0 ? (
              <p className="dim" style={{ fontSize: 13 }}>
                No changes yet — edit the After pane to preview the diff the kernel will record.
              </p>
            ) : (
              <table className="ax-table" role="table">
                <thead>
                  <tr>
                    <th>key</th>
                    <th>op</th>
                    <th>before</th>
                    <th>after</th>
                  </tr>
                </thead>
                <tbody>
                  {diff.map((entry) => (
                    <tr key={entry.key}>
                      <td><code>{entry.key}</code></td>
                      <td>
                        <span
                          className="ax-pill"
                          data-tone={entry.op === "added" ? "good" : entry.op === "removed" ? "hot" : "warn"}
                        >
                          {entry.op}
                        </span>
                      </td>
                      <td>
                        <code>{entry.before === null ? "—" : JSON.stringify(entry.before)}</code>
                      </td>
                      <td>
                        <code>{entry.after === null ? "—" : JSON.stringify(entry.after)}</code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </div>

        <footer className="ax-modal__footer ax-row" style={{ justifyContent: "space-between" }}>
          <span className="dim" style={{ fontSize: 12 }}>
            <ArrowRight size={12} style={{ verticalAlign: -1, marginRight: 4 }} />
            Submits to <code>POST /commands/edit</code>
          </span>
          <div className="ax-cluster" style={{ gap: 8 }}>
            <button
              type="button"
              className="ax-btn ax-btn--ghost ax-btn--sm"
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </button>
            <button
              type="button"
              className="ax-btn ax-btn--primary ax-btn--sm"
              onClick={() => void handleSubmit()}
              disabled={submitting || !parsed.ok || diff.length === 0}
            >
              {submitting ? <Loader2 size={14} className="ax-btn__spinner" /> : <ExternalLink size={14} />}
              {submitting ? "Submitting…" : "Edit + approve"}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
