"use client";

/**
 * Mission Control — the founder's exception-review board.
 * Stat tiles + "Needs you" approval queue + live event ribbon + recent settles.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  CircleDollarSign,
  Cpu,
  Radio,
  TrendingUp,
} from "lucide-react";
import Link from "next/link";
import { AppShell } from "../src/components/shell/app-shell";
import {
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  Section,
  Skeleton,
  Stack,
  StatTile,
  StatusPill,
  Table,
  TableSkeleton,
  AsyncButton,
} from "../src/components/ui";
import { useJournalStream } from "../src/lib/events";
import {
  fetchApprovals,
  fetchInstances,
  fetchRuns,
  fetchSystemOverview,
} from "../src/lib/api";
import { formatCurrency, formatRelative, runStateLabel, runStateTone } from "../src/lib/format";
import { journalKindTone } from "../src/lib/format";
import { useOperator } from "../src/providers/operator-provider";
import { useFeature } from "../src/providers/feature-provider";
import { useToast } from "../src/providers/toast-provider";
import type {
  ApprovalCard,
  InstanceSummary,
  RunSummary,
  SystemOverview,
} from "../src/lib/types";
import type { JournalStreamEvent } from "../src/lib/events";
import { shortId } from "../src/lib/format";

export default function HomePage() {
  const { baseUrl } = useOperator();
  const [overview, setOverview] = useState<SystemOverview | null>(null);
  const [instances, setInstances] = useState<InstanceSummary[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [approvals, setApprovals] = useState<ApprovalCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();
  const economy = useFeature("economy_pnl");
  const { events: liveEvents, connected } = useJournalStream({
    baseUrl: baseUrl || undefined,
  });

  const load = useCallback(
    async (mode: "initial" | "refresh" = "initial") => {
      if (mode === "refresh") setRefreshing(true);
      try {
        const [ov, ins, ru, ap] = await Promise.all([
          fetchSystemOverview(),
          fetchInstances(),
          fetchRuns({}),
          fetchApprovals(),
        ]);
        setOverview(ov.data);
        setInstances(ins.data);
        setRuns(ru.data);
        setApprovals(ap.data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [],
  );

  useEffect(() => {
    void load("initial");
  }, [load]);

  const activeRuns = useMemo(
    () => runs.filter((r) => r.state === "active" || r.state === "parked" || r.state === "waiting_approval"),
    [runs],
  );

  const pendingApprovals = useMemo(
    () => approvals.slice(0, 8),
    [approvals],
  );

  return (
    <AppShell
      title="Mission Control"
      crumbs={[{ label: "Home" }]}
      onRefresh={() => load("refresh")}
      refreshing={refreshing}
    >
      <div className="mc-page">
        {error ? (
          <ErrorState
            title="Couldn't load dashboard"
            detail={error}
            action={
              <AsyncButton onClick={() => load("refresh")} loading={refreshing}>
                Retry
              </AsyncButton>
            }
          />
        ) : null}

        <Section title="System" eyebrow="Overview" density="comfortable">
          <div className="mc-stats">
            <StatTile
              label="Active runs"
              value={overview?.active_runs ?? (loading ? <Skeleton width={40} /> : "—")}
              tone={activeRuns.length > 0 ? "warn" : "good"}
              icon={<Activity size={14} />}
              hint={activeRuns.length > 0 ? `${activeRuns.filter((r) => r.state === "waiting_approval").length} awaiting approval` : "No active runs"}
              to="/runs"
            />
            <StatTile
              label="Pending approvals"
              value={overview?.approvals_waiting ?? (loading ? <Skeleton width={40} /> : "—")}
              tone={(overview?.approvals_waiting ?? 0) > 0 ? "hot" : "default"}
              icon={<AlertCircle size={14} />}
              hint="L0/L1 inbox"
              to="/approvals"
            />
            <StatTile
              label="Monthly net"
              value={
                economy.live
                  ? formatCurrency(overview?.monthly_net, { sign: true })
                  : "—"
              }
              tone={(overview?.monthly_net ?? 0) >= 0 ? "good" : "hot"}
              icon={<CircleDollarSign size={14} />}
              hint={economy.live ? "P&L (C15 wired)" : "P&L API not wired yet (C15)"}
              to="/economy"
            />
            <StatTile
              label="Settles today"
              value={overview?.ledger_events_today ?? (loading ? <Skeleton width={40} /> : "—")}
              tone="good"
              icon={<TrendingUp size={14} />}
              hint={overview?.last_commit_at ? `Last: ${formatRelative(overview.last_commit_at)}` : "—"}
            />
            <StatTile
              label="Instances"
              value={overview?.active_instances ?? (loading ? <Skeleton width={40} /> : "—")}
              icon={<Cpu size={14} />}
              hint={`${instances.length} total`}
              to="/instances"
            />
            <StatTile
              label="SSE"
              value={connected ? "LIVE" : "OFFLINE"}
              tone={connected ? "good" : "warn"}
              icon={<Radio size={14} />}
              hint={connected ? "streaming /events" : "polling fallback"}
            />
          </div>
        </Section>

        <div className="mc-columns">
          <Section
            title="Needs you"
            subtitle="L0/L1 approvals waiting on the operator"
            eyebrow="Inbox"
            action={
              <Link href="/approvals" className="dim" style={{ fontSize: 12 }}>
                View all →
              </Link>
            }
          >
            {loading ? (
              <TableSkeleton columns={4} rows={4} />
            ) : pendingApprovals.length === 0 ? (
              <EmptyState
                title="Inbox is clear"
                detail="No parked approvals. The system is acting without intervention."
                icon={<CheckCircle2 size={20} />}
              />
            ) : (
              <Table
                density="compact"
                rowKey={(row) => row.run_id}
                columns={[
                  {
                    key: "instance",
                    header: "Instance",
                    render: (row) => (
                      <Link href={`/instances/${row.instance_id}`} className="mono">
                        {shortId(row.instance_id)}
                      </Link>
                    ),
                  },
                  {
                    key: "syscall",
                    header: "Syscall",
                    render: (row) => (
                      <span className="mono">
                        {(row.drafted_effect as { syscall?: string })?.syscall ?? "—"}
                      </span>
                    ),
                  },
                  {
                    key: "reason",
                    header: "Reason",
                    render: (row) => <span className="muted">{row.reason || "—"}</span>,
                  },
                  {
                    key: "ring",
                    header: "Ring",
                    render: (row) => (
                      <StatusPill tone={(row.required_ring?.toLowerCase() as "l0" | "l1" | "l2" | "l3" | "l4" | "neutral") ?? "neutral"}>
                        {row.required_ring ?? "—"}
                      </StatusPill>
                    ),
                  },
                ]}
                rows={pendingApprovals}
              />
            )}
          </Section>

          <Section
            title="Live"
            subtitle="Streaming from /events"
            eyebrow="SSE"
            action={<StatusPill tone={connected ? "good" : "warn"} dot pulse={connected}>{connected ? "LIVE" : "OFFLINE"}</StatusPill>}
          >
            <LiveRibbon events={liveEvents} />
          </Section>
        </div>

        <Section title="Recent settles" eyebrow="Runs" action={<Link href="/runs" className="dim" style={{ fontSize: 12 }}>View all →</Link>}>
          {loading ? (
            <TableSkeleton columns={5} rows={5} />
          ) : runs.length === 0 ? (
            <EmptyState title="No runs yet" detail="Trigger a run from an Instance detail page to populate this feed." />
          ) : (
            <Table
              density="comfortable"
              rowKey={(row) => row.id}
              columns={[
                {
                  key: "title",
                  header: "Run",
                  render: (row) => (
                    <Link href={`/runs/${row.id}`} className="mono">
                      {row.title}
                    </Link>
                  ),
                },
                {
                  key: "state",
                  header: "State",
                  render: (row) => (
                    <StatusPill tone={runStateTone(row.state)} dot>
                      {runStateLabel(row.state)}
                    </StatusPill>
                  ),
                },
                {
                  key: "syscall",
                  header: "Syscall",
                  render: (row) => <span className="mono">{row.syscall}</span>,
                  mono: true,
                },
                {
                  key: "ring",
                  header: "Ring",
                  render: (row) => (
                    <StatusPill tone={(row.ring?.toLowerCase() as "l0" | "l1" | "l2" | "l3" | "l4" | "neutral") ?? "neutral"}>
                      {row.ring ?? "—"}
                    </StatusPill>
                  ),
                },
                {
                  key: "started",
                  header: "Started",
                  render: (row) => <span className="mono dim">{formatRelative(row.started_at)}</span>,
                  align: "right",
                },
              ]}
              rows={runs.slice(0, 10)}
            />
          )}
        </Section>
      </div>
    </AppShell>
  );
}

function LiveRibbon({ events }: { events: JournalStreamEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="mc-ribbon">
        <span className="mc-ribbon__item">no live events yet</span>
      </div>
    );
  }
  return (
    <div className="mc-ribbon">
      {events.slice(-12).reverse().map((event) => (
        <span key={event.event_id} className="mc-ribbon__item">
          <span className="mc-ribbon__kind">{event.kind}</span>
          <span className="mc-ribbon__title">{(event as { title?: string }).title ?? ""}</span>
          <StatusPill size="sm" tone={journalKindTone(event.kind)} dot pulse>
            {event.kind.split("_").slice(-1)[0] ?? event.kind}
          </StatusPill>
        </span>
      ))}
    </div>
  );
}