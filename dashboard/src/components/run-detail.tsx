import { GitCommitHorizontal, TimerReset } from "lucide-react";
import type { DashboardData, RunSummary } from "@/lib/types";
import { formatCurrency, formatClock, Panel, ProgressBar, StatusPill } from "./shared";

interface RunDetailProps {
  data: DashboardData;
  selectedRun: RunSummary;
  onSelectRun: (runId: string) => void;
}

export function RunDetail({ data, selectedRun, onSelectRun }: RunDetailProps) {
  const instance = data.instances.find((item) => item.id === selectedRun.instance_id);

  return (
    <div className="run-detail-layout">
      <aside className="instance-list" aria-label="Runs">
        {data.runs.map((run) => (
          <button
            className={run.id === selectedRun.id ? "instance-tab active" : "instance-tab"}
            key={run.id}
            onClick={() => onSelectRun(run.id)}
            type="button"
          >
            <strong>{run.title}</strong>
            <span>{run.state.replace("_", " ")}</span>
          </button>
        ))}
      </aside>

      <div className="run-main">
        <Panel title={selectedRun.title} eyebrow={instance?.name ?? selectedRun.instance_id}>
          <div className="run-summary-grid">
            <div>
              <span>Syscall</span>
              <strong>{selectedRun.syscall}</strong>
            </div>
            <div>
              <span>Commits</span>
              <strong>{selectedRun.ledger_commits}</strong>
            </div>
            <div>
              <span>Cost</span>
              <strong>{formatCurrency(selectedRun.cost)}</strong>
            </div>
            <div>
              <span>Expected value</span>
              <strong>{formatCurrency(selectedRun.expected_value)}</strong>
            </div>
          </div>
          <div className="run-progress-line">
            <StatusPill label={selectedRun.state.replace("_", " ")} tone={selectedRun.state === "active" ? "good" : "hot"} />
            <ProgressBar value={selectedRun.progress} />
          </div>
        </Panel>

        <Panel title="Timeline" eyebrow={`updated ${formatClock(selectedRun.updated_at)}`}>
          <div className="timeline">
            {selectedRun.trace.map((event, index) => (
              <article className="timeline-event" key={`${event.ts}:${event.kind}:${index}`}>
                <div className="timeline-pin">
                  {event.kind === "syscall_attempted" || event.kind === "syscall_settled" ? (
                    <GitCommitHorizontal size={16} />
                  ) : (
                    <TimerReset size={16} />
                  )}
                </div>
                <div>
                  <p className="eyebrow">{formatClock(event.ts)} / {event.actor}</p>
                  <h3>{event.summary}</h3>
                </div>
              </article>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
