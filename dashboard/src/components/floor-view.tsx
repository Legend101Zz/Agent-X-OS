import { Activity, CircleDollarSign, ClipboardCheck, Gauge, RadioTower } from "lucide-react";
import type { DashboardData, RunSummary } from "@/lib/types";
import {
  formatCurrency,
  formatPercent,
  formatClock,
  MetricTile,
  Panel,
  ProgressBar,
  stagger,
  StatusPill,
} from "./shared";

interface FloorViewProps {
  data: DashboardData;
  onSelectRun: (runId: string) => void;
  onSelectInstance: (instanceId: string) => void;
}

const stateTone = (state: RunSummary["state"]) => {
  if (state === "active") return "good";
  if (state === "waiting_approval") return "hot";
  if (state === "parked") return "warn";
  return "neutral";
};

export function FloorView({ data, onSelectRun, onSelectInstance }: FloorViewProps) {
  const activeRuns = data.runs.filter((run) => run.state === "active" || run.state === "waiting_approval");
  const parkedRuns = data.runs.filter((run) => run.state === "parked");

  return (
    <div className="view-stack">
      <div className="metric-grid stagger-floor">
        <div style={stagger(0)}>
          <MetricTile
            label="Active instances"
            value={String(data.overview.active_instances)}
            detail={`${data.overview.active_runs} runs moving`}
            tone="good"
          />
        </div>
        <div style={stagger(1)}>
          <MetricTile
            label="Approvals"
            value={String(data.overview.approvals_waiting)}
            detail={`${data.overview.manual_queue_depth} manual tail`}
            tone="hot"
          />
        </div>
        <div style={stagger(2)}>
          <MetricTile
            label="Automation"
            value={formatPercent(data.overview.automation_coverage)}
            detail={data.overview.gateway_health}
            tone="good"
          />
        </div>
        <div style={stagger(3)}>
          <MetricTile
            label="Monthly net"
            value={formatCurrency(data.overview.monthly_net)}
            detail={`${data.overview.ledger_events_today} ledger events today`}
          />
        </div>
      </div>

      <div className="floor-grid">
        <Panel title="Live Floor" eyebrow={data.overview.system_state}>
          <div className="run-stack">
            {activeRuns.map((run, index) => (
              <button
                className="run-strip alive-strip"
                key={run.id}
                onClick={() => onSelectRun(run.id)}
                style={stagger(index)}
                type="button"
              >
                <div className="strip-icon">
                  {run.state === "waiting_approval" ? <ClipboardCheck size={18} /> : <Activity size={18} />}
                </div>
                <div>
                  <strong>{run.title}</strong>
                  <span>{run.syscall}</span>
                </div>
                <StatusPill label={run.state.replace("_", " ")} tone={stateTone(run.state)} />
                <ProgressBar value={run.progress} />
              </button>
            ))}
          </div>
        </Panel>

        <Panel title="Parked Runs" eyebrow="human-task tail">
          <div className="compact-list">
            {parkedRuns.map((run) => (
              <button className="compact-row" key={run.id} onClick={() => onSelectRun(run.id)} type="button">
                <span>{run.title}</span>
                <StatusPill label={run.state} tone="warn" />
              </button>
            ))}
          </div>
        </Panel>

        <Panel title="Instance Radar" eyebrow="ring / trust">
          <div className="instance-radar">
            {data.instances.map((instance, index) => (
              <button
                className="radar-card"
                key={instance.id}
                onClick={() => onSelectInstance(instance.id)}
                style={stagger(index)}
                type="button"
              >
                <div>
                  <strong>{instance.name}</strong>
                  <span>{instance.business}</span>
                </div>
                <div className="radar-score">
                  <Gauge size={16} />
                  {instance.trust_score}
                </div>
                <StatusPill
                  label={instance.ring}
                  tone={instance.ring === "L2" || instance.ring === "assist" ? "good" : instance.state === "parked" ? "warn" : "neutral"}
                />
              </button>
            ))}
          </div>
        </Panel>

        <Panel title="Ledger Stream" eyebrow={`last commit ${formatClock(data.overview.last_commit_at)}`}>
          <div className="ledger-stream">
            {data.journal.slice(0, 5).map((event, index) => (
              <div className="ledger-line" key={event.id} style={stagger(index)}>
                <RadioTower size={14} />
                <span>{formatClock(event.at)}</span>
                <strong>{event.title}</strong>
                <small>{event.source}</small>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Ring Mix" eyebrow="customer-facing guard">
          <div className="ring-mix">
            {Object.entries(data.overview.ring_mix).map(([ring, count]) => (
              <div className="ring-segment" key={ring}>
                <CircleDollarSign size={16} />
                <span>{ring}</span>
                <strong>{count}</strong>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
