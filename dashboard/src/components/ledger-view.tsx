import { Filter } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { fetchJournal } from "@/lib/api";
import type { ApiSource, DashboardData, JournalEvent } from "@/lib/types";
import { formatClock, Panel, SourceBadge, StatusPill } from "./shared";

interface LedgerViewProps {
  data: DashboardData;
}

export function LedgerView({ data }: LedgerViewProps) {
  const [instanceId, setInstanceId] = useState("");
  const [runId, setRunId] = useState("");
  const [kind, setKind] = useState("");
  const [events, setEvents] = useState<JournalEvent[]>(data.journal);
  const [source, setSource] = useState<ApiSource>("fixture");

  const kinds = Array.from(new Set(data.journal.map((event) => event.kind)));

  useEffect(() => {
    setEvents(data.journal);
  }, [data.journal]);

  useEffect(() => {
    let cancelled = false;

    void fetchJournal({
      instance_id: instanceId,
      run_id: runId,
      kind,
      limit: 30,
    }).then((result) => {
      if (cancelled) return;
      setEvents(result.data);
      setSource(result.source);
    });

    return () => {
      cancelled = true;
    };
  }, [instanceId, kind, runId]);

  const filtered = useMemo(
    () =>
      events
        .filter((event) => !instanceId || event.instance_id === instanceId)
        .filter((event) => !runId || event.run_id === runId)
        .filter((event) => !kind || event.kind === kind),
    [events, instanceId, kind, runId],
  );

  return (
    <div className="view-stack">
      <Panel
        title="Ledger"
        eyebrow={`${filtered.length} events`}
        action={
          <div className="filter-action">
            <SourceBadge source={source} />
            <div className="filter-icon">
              <Filter size={16} />
            </div>
          </div>
        }
      >
        <div className="filter-bar">
          <select onChange={(event) => setInstanceId(event.target.value)} value={instanceId}>
            <option value="">all instances</option>
            {data.instances.map((instance) => (
              <option key={instance.id} value={instance.id}>
                {instance.name}
              </option>
            ))}
          </select>
          <select onChange={(event) => setRunId(event.target.value)} value={runId}>
            <option value="">all runs</option>
            {data.runs.map((run) => (
              <option key={run.id} value={run.id}>
                {run.title}
              </option>
            ))}
          </select>
          <select onChange={(event) => setKind(event.target.value)} value={kind}>
            <option value="">all kinds</option>
            {kinds.map((journalKind) => (
              <option key={journalKind} value={journalKind}>
                {journalKind}
              </option>
            ))}
          </select>
        </div>

        <div className="ledger-table">
          {filtered.map((event) => (
            <article className="ledger-row" key={event.id}>
              <div>
                <span>{formatClock(event.at)}</span>
                <StatusPill label={event.kind} tone={event.kind === "approval" ? "hot" : "neutral"} />
              </div>
              <div>
                <strong>{event.title}</strong>
                <p>{event.detail}</p>
              </div>
              <small>{event.actor}</small>
              <small>{event.source}</small>
            </article>
          ))}
        </div>
      </Panel>
    </div>
  );
}
