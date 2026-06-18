import { Check, FilePenLine, ShieldAlert, X } from "lucide-react";
import type { CommandResult, CoreGap, DashboardData, ManualTask } from "@/lib/types";
import { GapNotice, Panel, stagger, StatusPill } from "./shared";

interface ApprovalInboxProps {
  data: DashboardData;
  commandResult?: CommandResult;
  onApprove: (task: ManualTask) => void;
  onGap: (gap: CoreGap) => void;
}

const priorityTone = (priority: ManualTask["priority"]) => {
  if (priority === "high") return "hot";
  if (priority === "normal") return "warn";
  return "neutral";
};

export function ApprovalInbox({ data, commandResult, onApprove, onGap }: ApprovalInboxProps) {
  const editRejectGap =
    data.coreGaps.find((gap) => gap.id === "command.edit_approval") ??
    data.coreGaps.find((gap) => gap.id === "gap-edit-reject") ??
    data.coreGaps[0];

  return (
    <div className="view-stack">
      <Panel title="Approval Inbox" eyebrow={`${data.manualQueue.length} packets`}>
        <div className="approval-grid">
          {data.manualQueue.map((task, index) => (
            <article className="approval-card alive-card" key={task.id} style={stagger(index)}>
              <div className="approval-card-top">
                <div>
                  <p className="eyebrow">{task.instance_id}</p>
                  <h3>{task.title}</h3>
                </div>
                <StatusPill label={task.priority} tone={priorityTone(task.priority)} />
              </div>
              <div className="drafted-effect">{task.drafted_effect}</div>
              <ol className="trace-list">
                {task.trace.map((trace) => (
                  <li key={trace}>{trace}</li>
                ))}
              </ol>
              <div className="approval-actions">
                <button className="command-button primary" onClick={() => onApprove(task)} type="button">
                  <Check size={16} />
                  Approve
                </button>
                <button className="command-button" onClick={() => onGap(editRejectGap)} type="button">
                  <FilePenLine size={16} />
                  Edit
                </button>
                <button className="command-button danger" onClick={() => onGap(editRejectGap)} type="button">
                  <X size={16} />
                  Reject
                </button>
              </div>
            </article>
          ))}
        </div>
      </Panel>

      {commandResult?.gap ? (
        <GapNotice gap={commandResult.gap} />
      ) : commandResult ? (
        <div className="command-receipt" role="status">
          <ShieldAlert size={18} />
          <strong>{commandResult.status ?? "accepted"}</strong>
          <span>{commandResult.receipt ?? commandResult.message}</span>
        </div>
      ) : null}
    </div>
  );
}
