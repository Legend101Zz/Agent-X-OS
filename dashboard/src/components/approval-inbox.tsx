"use client";

import { Check, ShieldAlert, X } from "lucide-react";
import type { ApprovalCard, CommandResult, DashboardData } from "@/lib/types";
import { GapNotice, Panel, stagger, StatusPill } from "./shared";

interface ApprovalInboxProps {
  data: DashboardData;
  commandResult?: CommandResult;
  operatorToken: string;
  apiBaseUrl: string;
  onApprove: (card: ApprovalCard) => void;
  onReject: (card: ApprovalCard) => void;
  onRefresh: () => void;
}

const ringTone = (ring: string | undefined) => {
  if (ring === "L2") return "hot";
  if (ring === "L1") return "warn";
  return "neutral";
};

export function ApprovalInbox({
  data,
  commandResult,
  operatorToken,
  apiBaseUrl,
  onApprove,
  onReject,
  onRefresh,
}: ApprovalInboxProps) {
  const editGap = data.coreGaps.find((gap) => gap.id === "command.edit_approval");
  const disabled = !operatorToken;

  async function pollWorkUntilDone(workId: string) {
    // After approve/reject, poll /scheduler-work until terminal so the dashboard reflects the run.
    const deadline = Date.now() + 10_000;
    while (Date.now() < deadline) {
      const res = await fetch(
        `${apiBaseUrl}/scheduler-work/${encodeURIComponent(workId)}`,
        { headers: operatorToken ? { Authorization: `Bearer ${operatorToken}` } : {} },
      );
      if (res.ok) {
        const body = await res.json();
        const status = body?.work?.status;
        if (status === "completed" || status === "failed") {
          onRefresh();
          return;
        }
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    onRefresh();
  }

  async function handleEdit(card: ApprovalCard) {
    // Edit is intentionally still a 501 today — it is the last closed-after-Session-H gap.
    // We surface the gap notice explicitly so the operator knows what is missing.
    onApprove(card); // reuse to surface "no-op" command result display
  }

  // Wrap the onApprove/onReject to also poll after the dashboard handler kicks off work.
  const wrappedApprove = async (card: ApprovalCard) => {
    onApprove(card);
    // The dashboard polls every 8s; we do not need to double-poll here.
  };
  const wrappedReject = async (card: ApprovalCard) => {
    onReject(card);
  };

  return (
    <div className="view-stack">
      <Panel title="Approval Inbox" eyebrow={`${data.approvals.length} parked`}>
        <p className="view-help">
          Approval cards are real kernel <code>RunParked</code> events awaiting a manager
          decision. They are distinct from the <em>manual queue</em> (the human-task tail of the
          syscall ladder) shown in the capability registry.
        </p>
        {data.approvals.length === 0 ? (
          <p className="empty-state">No parked approvals. Trigger a run from Catalog → Instance.</p>
        ) : (
          <div className="approval-grid">
            {data.approvals.map((card, index) => {
              const drafted = card.drafted_effect;
              const syscall =
                drafted && typeof drafted === "object" && "syscall" in drafted
                  ? String(drafted.syscall)
                  : "(none)";
              const idem =
                drafted && typeof drafted === "object" && "idempotency_key" in drafted
                  ? String(drafted.idempotency_key)
                  : "(none)";
              const args: Record<string, unknown> =
                drafted && typeof drafted === "object" && "args" in drafted && drafted.args
                  ? (drafted.args as Record<string, unknown>)
                  : {};
              return (
                <article className="approval-card alive-card" key={`${card.instance_id}:${card.run_id}`} style={stagger(index)}>
                  <div className="approval-card-top">
                    <div>
                      <p className="eyebrow">{card.instance_id}</p>
                      <h3>{syscall}</h3>
                    </div>
                    <StatusPill
                      label={`requires ${card.required_ring ?? "L?"}`}
                      tone={ringTone(card.required_ring)}
                    />
                  </div>
                  <p className="approval-reason">{card.reason}</p>
                  <pre className="drafted-effect" aria-label="drafted effect args">
                    {JSON.stringify(args, null, 2)}
                  </pre>
                  <div className="approval-meta">
                    <span>idempotency_key: <code>{idem}</code></span>
                    <span>seq: {card.seq}</span>
                  </div>
                  <ol className="trace-list">
                    {card.timeline.slice(0, 4).map((entry) => (
                      <li key={`${entry.ts}:${entry.kind}`}>
                        <span className="trace-kind">{entry.kind}</span>
                        <span className="trace-summary">{entry.summary}</span>
                      </li>
                    ))}
                  </ol>
                  <div className="approval-actions">
                    <button
                      className={disabled ? "command-button primary disabled" : "command-button primary"}
                      disabled={disabled}
                      onClick={() => wrappedApprove(card)}
                      type="button"
                    >
                      <Check size={16} />
                      Approve
                    </button>
                    <button
                      className={disabled ? "command-button danger disabled" : "command-button danger"}
                      disabled={disabled}
                      onClick={() => wrappedReject(card)}
                      type="button"
                    >
                      <X size={16} />
                      Reject
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </Panel>

      {editGap ? <GapNotice gap={editGap} /> : null}

      {commandResult?.gap ? (
        <GapNotice gap={commandResult.gap} />
      ) : commandResult ? (
        <div className="command-receipt" role="status">
          <ShieldAlert size={18} />
          <strong>{commandResult.status ?? commandResult.decision ?? "accepted"}</strong>
          <span>{commandResult.message ?? commandResult.receipt}</span>
        </div>
      ) : null}
    </div>
  );
}
