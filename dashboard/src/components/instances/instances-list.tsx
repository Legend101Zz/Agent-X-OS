"use client";

/**
 * Instances list — the entry point to every mandate instance.
 *
 * Each row is a deep-link to `/instances/{id}` (the Inspector). Pills carry
 * the most-glanced attributes (ring, run state, parked count, P&L); the table
 * itself is the body, the parent `AppShell` is the chrome.
 *
 * Source: `/instances` (C1 dashboard already had this; C2 elevates it to a
 * real route-based list rather than the previous C1 stub).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  CheckCircle2,
  CircleSlash2,
  Pause,
  Wallet,
} from "lucide-react";

import { AppShell } from "../shell/app-shell";
import {
  AsyncButton,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  HelpPanel,
  InfoTip,
  RingPill,
  Row,
  Skeleton,
  Stack,
  StatusPill,
  Table,
  TableSkeleton,
} from "../ui";
import { useOperator } from "../../providers/operator-provider";
import { useToast } from "../../providers/toast-provider";
import { fetchInstances, fetchRuns } from "../../lib/api";
import {
  formatCurrency,
  formatRelative,
  runStateLabel,
  runStateTone,
  shortId,
} from "../../lib/format";
import type { InstanceSummary, RunSummary } from "../../lib/types";

interface InstancesListProps {
  initialInstances?: InstanceSummary[];
  initialRuns?: RunSummary[];
}

interface RowData extends InstanceSummary {
  parkedCount: number;
  activeRunId: string | null;
  activeRunState: string | null;
  activeRunTitle: string | null;
}

export function InstancesList({ initialInstances, initialRuns }: InstancesListProps = {}) {
  const { baseUrl, isLive } = useOperator();
  const toast = useToast();
  const router = useRouter();
  const [instances, setInstances] = useState<InstanceSummary[] | null>(
    initialInstances ?? null,
  );
  const [runs, setRuns] = useState<RunSummary[] | null>(initialRuns ?? null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(!initialInstances);
  const [refreshing, setRefreshing] = useState<boolean>(false);

  const load = useCallback(
    async (mode: "initial" | "refresh" = "initial") => {
      if (mode === "refresh") setRefreshing(true);
      try {
        const [insRes, runsRes] = await Promise.all([
          fetchInstances(),
          // The list doesn't need every run — only counts and the "latest" per
          // instance. fetchRuns returns the list (fixture or live); we aggregate
          // on the client. A future backend could expose `/runs?instance_id=`
          // aggregated server-side, but the existing endpoint is enough.
          fetchRuns({}),
        ]);
        setInstances(insRes.data);
        setRuns(runsRes.data);
        setError(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
        if (mode === "refresh") {
          toast.push({ title: "Refresh failed", message, tone: "hot" });
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [toast],
  );

  useEffect(() => {
    if (initialInstances) return;
    void load("initial");
  }, [initialInstances, load]);

  // Aggregate run state per instance (parked / active / latest).
  const rows: RowData[] = useMemo(() => {
    if (!instances) return [];
    const runsByInstance = new Map<string, RunSummary[]>();
    for (const run of runs ?? []) {
      const list = runsByInstance.get(run.instance_id) ?? [];
      list.push(run);
      runsByInstance.set(run.instance_id, list);
    }
    return instances.map((instance) => {
      const instanceRuns = runsByInstance.get(instance.id) ?? [];
      const parked = instanceRuns.filter(
        (r) => r.state === "parked" || r.state === "waiting_approval",
      );
      // Pick the "most interesting" run: active first, then parked, then the
      // most-recently-updated. Keeps the list scannable.
      const active = instanceRuns.find((r) => r.state === "active");
      const recent = instanceRuns
        .filter((r) => r.state !== "active" && r.state !== "parked" && r.state !== "waiting_approval")
        .sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1))[0];
      const featured = active ?? parked[0] ?? recent ?? null;
      return {
        ...instance,
        parkedCount: parked.length,
        activeRunId: featured?.id ?? null,
        activeRunState: featured?.state ?? null,
        activeRunTitle: featured?.title ?? null,
      };
    });
  }, [instances, runs]);

  return (
    <AppShell
      title="Instances"
      crumbs={[{ label: "Instances" }]}
      onRefresh={() => void load("refresh")}
      refreshing={refreshing}
    >
      <div className="instances-page">
        <HelpPanel id="instances">
          <p>
            Every running instance <InfoTip term="instance" /> across your blueprints. Each row shows
            its ring <InfoTip term="ring" /> (how much it can do alone), trust{" "}
            <InfoTip term="trust" />, and run state <InfoTip term="run_state" />. Click one to open
            its deep Inspector.
          </p>
        </HelpPanel>
        <Card>
          <CardHeader
            eyebrow="Mandate instances"
            title="Every mandate instance in one place"
            subtitle="Click an instance to open the Inspector — overview, live activity, runs, approvals, and trust."
            action={
              <AsyncButton
                variant="secondary"
                size="sm"
                icon={<CircleSlash2 size={14} />}
                onClick={() => void load("refresh")}
                loading={refreshing}
                disabled={!isLive && !baseUrl}
                disabledReason={
                  !isLive && !baseUrl
                    ? "Set the API base URL in operator settings to load live data."
                    : undefined
                }
              >
                Refresh
              </AsyncButton>
            }
          />
          <CardBody>
            {error && !loading ? (
              <ErrorState
                title="Couldn't load instances"
                detail={error}
                action={
                  <AsyncButton variant="secondary" onClick={() => void load("refresh")}>
                    Retry
                  </AsyncButton>
                }
              />
            ) : loading || !instances ? (
              <TableSkeleton columns={6} rows={4} />
            ) : rows.length === 0 ? (
              <EmptyState
                title="No instances yet"
                detail="When you instantiate a mandate (from Blueprints), it appears here."
                action={
                  <Link href="/blueprints">
                    <AsyncButton variant="primary">Browse Blueprints</AsyncButton>
                  </Link>
                }
              />
            ) : (
              <Table
                columns={[
                  {
                    key: "name",
                    header: "Name",
                    render: (row) => (
                      <Link
                        href={`/instances/${encodeURIComponent(row.id)}`}
                        className="instances-row__name"
                      >
                        <span className="h3">{row.name}</span>
                        <span className="mono dim">{shortId(row.id)}</span>
                      </Link>
                    ),
                  },
                  {
                    key: "type",
                    header: "Type",
                    mono: true,
                    render: (row) => (
                      <span className="mono dim" title={row.mandate_type}>
                        {row.mandate_type ?? "—"}
                      </span>
                    ),
                  },
                  {
                    key: "ring",
                    header: "Ring",
                    render: (row) => <RingPill ring={row.ring} />,
                  },
                  {
                    key: "trust",
                    header: "Trust",
                    align: "right",
                    render: (row) => (
                      <span className="mono">
                        {row.trust_score >= 0 ? row.trust_score.toFixed(2) : "—"}
                      </span>
                    ),
                  },
                  {
                    key: "state",
                    header: "Live state",
                    render: (row) => {
                      if (row.parkedCount > 0) {
                        return (
                          <StatusPill
                            tone="warn"
                            dot
                            title={`${row.parkedCount} parked run${row.parkedCount === 1 ? "" : "s"}`}
                          >
                            <Pause size={11} /> {row.parkedCount} parked
                          </StatusPill>
                        );
                      }
                      if (row.activeRunState) {
                        return (
                          <StatusPill
                            tone={runStateTone(row.activeRunState)}
                            dot={row.activeRunState === "active"}
                            pulse={row.activeRunState === "active"}
                          >
                            {runStateLabel(row.activeRunState)}
                            {row.activeRunTitle ? (
                              <span className="dim" style={{ marginLeft: 6 }}>
                                · {row.activeRunTitle}
                              </span>
                            ) : null}
                          </StatusPill>
                        );
                      }
                      return <StatusPill tone="muted">idle</StatusPill>;
                    },
                  },
                  {
                    key: "pnl",
                    header: "Net (P&L)",
                    align: "right",
                    mono: true,
                    render: (row) => (
                      <span title={`revenue ${formatCurrency(row.pnl.revenue)} − cost ${formatCurrency(row.pnl.cost)}`}>
                        {formatCurrency(row.pnl.margin)}
                      </span>
                    ),
                  },
                ]}
                rows={rows}
                rowKey={(row) => row.id}
                onRowClick={(row) => router.push(`/instances/${encodeURIComponent(row.id)}`)}
                density="comfortable"
              />
            )}
          </CardBody>
        </Card>

        <Stack gap={4}>
          <div className="dim" style={{ fontSize: 12 }}>
            HEADER &nbsp;·&nbsp; Inspector opens at <code>/instances/&lt;id&gt;</code> · Live activity streams from <code>/events</code> · Memory / Heap is stubbed (awaiting C3).
          </div>
          <Stack gap={3}>
            <Row gap={4} className="instances-summary" wrap>
              <SummaryTile
                label="Active"
                value={rows.filter((r) => r.activeRunState === "active").length}
                icon={<CheckCircle2 size={14} />}
                tone="good"
              />
              <SummaryTile
                label="Parked"
                value={rows.reduce((n, r) => n + r.parkedCount, 0)}
                icon={<AlertCircle size={14} />}
                tone="warn"
              />
              <SummaryTile
                label="Idle"
                value={rows.filter((r) => !r.activeRunState).length}
                icon={<Pause size={14} />}
                tone="muted"
              />
              <SummaryTile
                label="Monthly net"
                value={formatCurrency(rows.reduce((n, r) => n + r.pnl.margin, 0))}
                icon={<Wallet size={14} />}
                tone="default"
              />
            </Row>
            {instances ? (
              <div className="dim" style={{ fontSize: 12 }}>
                Last refresh: {formatRelative(new Date().toISOString())} · {instances.length}{" "}
                instance{instances.length === 1 ? "" : "s"} loaded.
              </div>
            ) : (
              <Skeleton width="40%" />
            )}
          </Stack>
        </Stack>
      </div>
    </AppShell>
  );
}

interface SummaryTileProps {
  label: string;
  value: number | string;
  icon?: React.ReactNode;
  tone?: "default" | "good" | "warn" | "muted";
}

function SummaryTile({ label, value, icon, tone = "default" }: SummaryTileProps) {
  return (
    <div className={`instances-summary__tile instances-summary__tile--${tone}`}>
      <div className="instances-summary__label">
        {icon}
        <span>{label}</span>
      </div>
      <div className="instances-summary__value mono">{value}</div>
    </div>
  );
}
