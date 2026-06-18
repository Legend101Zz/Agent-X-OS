import { History, KeyRound, PlayCircle, ShieldCheck } from "lucide-react";
import { useState } from "react";
import type { CommandResult, DashboardData, InstanceSummary } from "@/lib/types";
import { formatCurrency, formatClock, GapNotice, Panel, ProgressBar, StatusPill } from "./shared";

interface InstanceFileProps {
  data: DashboardData;
  selectedInstance: InstanceSummary;
  commandResult?: CommandResult;
  operatorToken: string;
  apiBaseUrl: string;
  onSelectInstance: (instanceId: string) => void;
  onSelectRun: (runId: string) => void;
  onSetRing: (instanceId: string, ring: string) => void;
  onCommandResult: (result: CommandResult) => void;
  onRefresh: () => void;
}

type RunState = "idle" | "submitting" | "ok" | "error";

export function InstanceFile({
  data,
  selectedInstance,
  commandResult,
  operatorToken,
  apiBaseUrl,
  onSelectInstance,
  onSelectRun,
  onSetRing,
  onCommandResult,
  onRefresh,
}: InstanceFileProps) {
  const instanceRuns = data.runs.filter((run) => run.instance_id === selectedInstance.id);
  const [runState, setRunState] = useState<RunState>("idle");
  const [runMessage, setRunMessage] = useState<string | null>(null);
  const disabled = !operatorToken || runState === "submitting";

  async function handleRunMandate() {
    if (!operatorToken) return;
    setRunState("submitting");
    setRunMessage(null);
    try {
      const response = await fetch(`${apiBaseUrl}/commands/trigger-run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${operatorToken}`,
        },
        body: JSON.stringify({
          instance_id: selectedInstance.id,
          mode: "sim",
          actor: "dashboard/operator",
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        const message = typeof body?.detail === "string" ? body.detail : response.statusText;
        setRunState("error");
        setRunMessage(message);
        onCommandResult({ supported: false, message });
        return;
      }
      const message = `triggered (work_id=${body.work_id})`;
      setRunState("ok");
      setRunMessage(message);
      onCommandResult({ supported: true, status: "queued", message, work_id: body.work_id });
      onRefresh();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network error";
      setRunState("error");
      setRunMessage(message);
      onCommandResult({ supported: false, message });
    }
  }

  return (
    <div className="instance-layout">
      <aside className="instance-list" aria-label="Instances">
        {data.instances.map((instance) => (
          <button
            className={instance.id === selectedInstance.id ? "instance-tab active" : "instance-tab"}
            key={instance.id}
            onClick={() => onSelectInstance(instance.id)}
            type="button"
          >
            <strong>{instance.name}</strong>
            <span>{instance.ring} / {instance.trust_score}</span>
          </button>
        ))}
      </aside>

      <div className="instance-main">
        <Panel title={selectedInstance.name} eyebrow={selectedInstance.business}>
          <div className="instance-header-grid">
            <div className="trust-dial">
              <span>{selectedInstance.trust_score}</span>
              <ProgressBar value={selectedInstance.trust_score} />
              <small>trust score</small>
            </div>
            <div className="ring-controls">
              {["L0", "L1", "L2"].map((ring) => (
                <button
                  className={ring === selectedInstance.ring ? "ring-button active" : "ring-button"}
                  key={ring}
                  onClick={() => onSetRing(selectedInstance.id, ring)}
                  type="button"
                >
                  <ShieldCheck size={15} />
                  {ring}
                </button>
              ))}
            </div>
            <div className="pnl-block">
              <span>Revenue {formatCurrency(selectedInstance.pnl.revenue)}</span>
              <span>Cost {formatCurrency(selectedInstance.pnl.cost)}</span>
              <strong>Margin {formatCurrency(selectedInstance.pnl.margin)}</strong>
            </div>
          </div>
          <div className="run-mandate-row">
            <button
              className={disabled ? "command-button primary disabled" : "command-button primary"}
              disabled={disabled}
              onClick={() => void handleRunMandate()}
              type="button"
            >
              <PlayCircle size={16} />
              {runState === "submitting" ? "Triggering…" : "Run Mandate (sim)"}
            </button>
            {runMessage && <span className={`run-status tone-${runState}`}>{runMessage}</span>}
          </div>
          {commandResult?.gap ? <GapNotice gap={commandResult.gap} /> : null}
        </Panel>

        <Panel title="Facts" eyebrow="provenance / confidence">
          <div className="fact-table">
            {selectedInstance.facts.map((fact) => (
              <div className="fact-row" key={fact.id}>
                <div>
                  <strong>{fact.label}</strong>
                  <span>{fact.value}</span>
                </div>
                <div className="fact-source">
                  <KeyRound size={14} />
                  <span>{fact.source}</span>
                  <small>{fact.provenance}</small>
                </div>
                <StatusPill label={`${Math.round(fact.confidence * 100)}%`} tone="good" />
              </div>
            ))}
          </div>
        </Panel>

        <div className="two-column">
          <Panel title="Ring History" eyebrow="operator changes">
            <div className="history-list">
              {selectedInstance.ring_history.map((entry) => (
                <div className="history-row" key={`${entry.at}-${entry.ring}`}>
                  <History size={14} />
                  <div>
                    <strong>{entry.ring}</strong>
                    <span>{entry.reason}</span>
                  </div>
                  <small>{formatClock(entry.at)}</small>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Runs / Threads" eyebrow={`${instanceRuns.length} runs`}>
            <div className="compact-list">
              {instanceRuns.map((run) => (
                <button className="compact-row" key={run.id} onClick={() => onSelectRun(run.id)} type="button">
                  <span>{run.title}</span>
                  <StatusPill label={run.state.replace("_", " ")} tone={run.state === "active" ? "good" : "warn"} />
                </button>
              ))}
            </div>
            <div className="thread-stack">
              {selectedInstance.threads.map((thread) => (
                <div className="thread-row" key={thread.id}>
                  <strong>{thread.subject}</strong>
                  <span>{thread.channel} / {thread.state}</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
