"use client";

/**
 * Runs tab — every run for this instance, drillable.
 *
 * Sourced from `/runs?instance_id=`. C6 ("Runs & Trace") ships a richer
 * per-run page; this tab is the *list* of runs that belong to *this instance*,
 * so the founder can scan a single mandate's history without leaving the
 * Inspector.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Activity, ArrowRight } from "lucide-react";

import {
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  Row,
  Skeleton,
  Stack,
  StatusPill,
  Table,
  TableSkeleton,
} from "../../ui";
import {
  fetchRuns,
} from "../../../lib/api";
import { useToast } from "../../../providers/toast-provider";
import { useOperator } from "../../../providers/operator-provider";
import {
  formatCurrency,
  formatRelative,
  formatTime,
  runStateLabel,
  runStateTone,
  shortId,
} from "../../../lib/format";
import type { RunSummary } from "../../../lib/types";

interface RunsTabProps {
  instanceId: string;
  initialRuns?: RunSummary[];
  loading?: boolean;
}

export function RunsTab({ instanceId, initialRuns, loading }: RunsTabProps) {
  const { baseUrl } = useOperator();
  const toast = useToast();
  const [runs, setRuns] = useState<RunSummary[] | null>(initialRuns ?? null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    if (initialRuns) return;
    let cancelled = false;
    void (async () => {
      try {
        const result = await fetchRuns({ instance_id: instanceId });
        if (cancelled) return;
        setRuns(result.data);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        if (!cancelled) {
          setError(message);
          toast.push({ title: "Couldn't load runs", message, tone: "hot" });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [instanceId, initialRuns, baseUrl, toast]);

  async function refresh() {
    setRefreshing(true);
    try {
      const result = await fetchRuns({ instance_id: instanceId });
      setRuns(result.data);
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      toast.push({ title: "Refresh failed", message, tone: "hot" });
    } finally {
      setRefreshing(false);
    }
  }

  const sorted = useMemo(
    () => (runs ?? []).slice().sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1)),
    [runs],
  );

  const counts = useMemo(() => {
    const acc = { active: 0, parked: 0, complete: 0, failed: 0, other: 0 };
    for (const r of sorted) {
      if (r.state === "active") acc.active++;
      else if (r.state === "parked" || r.state === "waiting_approval") acc.parked++;
      else if (r.state === "complete") acc.complete++;
      else if (r.state === "failed") acc.failed++;
      else acc.other++;
    }
    return acc;
  }, [sorted]);

  return (
    <Stack gap={4}>
      <Card>
        <CardHeader
          eyebrow="Runs"
          title={`${sorted.length} run${sorted.length === 1 ? "" : "s"} for this instance`}
          action={
            <Row gap={2} wrap>
              <StatusPill tone="info" dot={counts.active > 0} pulse={counts.active > 0}>
                {counts.active} active
              </StatusPill>
              {counts.parked > 0 ? (
                <StatusPill tone="warn">{counts.parked} parked</StatusPill>
              ) : null}
              {counts.failed > 0 ? (
                <StatusPill tone="hot">{counts.failed} failed</StatusPill>
              ) : null}
              <button
                type="button"
                className="ax-btn ax-btn--ghost ax-btn--sm"
                onClick={() => void refresh()}
                disabled={refreshing}
                title="Refresh runs"
              >
                {refreshing ? "Refreshing…" : "Refresh"}
              </button>
            </Row>
          }
        />
        <CardBody>
          {error ? (
            <ErrorState
              title="Couldn't load runs"
              detail={error}
              action={
                <button
                  type="button"
                  className="ax-btn ax-btn--secondary"
                  onClick={() => void refresh()}
                >
                  Retry
                </button>
              }
            />
          ) : loading || !runs ? (
            <TableSkeleton columns={5} rows={3} />
          ) : sorted.length === 0 ? (
            <EmptyState
              icon={<Activity size={20} />}
              title="No runs yet"
              detail="When this instance is triggered (manually or by the scheduler), runs land here."
            />
          ) : (
            <Table
              columns={[
                {
                  key: "title",
                  header: "Title",
                  render: (row) => (
                    <Link
                      href={`/runs/${encodeURIComponent(row.id)}`}
                      className="inspector-runs__title"
                    >
                      <span>{row.title}</span>
                      <span className="mono dim">{shortId(row.id, 10)}</span>
                      <ArrowRight size={11} />
                    </Link>
                  ),
                },
                {
                  key: "state",
                  header: "State",
                  render: (row) => (
                    <StatusPill
                      tone={runStateTone(row.state)}
                      dot={row.state === "active"}
                      pulse={row.state === "active"}
                    >
                      {runStateLabel(row.state)}
                    </StatusPill>
                  ),
                },
                {
                  key: "syscall",
                  header: "Syscall",
                  mono: true,
                  render: (row) => <span className="mono dim">{row.syscall}</span>,
                },
                {
                  key: "started",
                  header: "Started",
                  render: (row) => (
                    <span title={row.started_at}>
                      {formatRelative(row.started_at)}
                      <span className="dim mono" style={{ marginLeft: 6 }}>
                        {formatTime(row.started_at)}
                      </span>
                    </span>
                  ),
                },
                {
                  key: "cost",
                  header: "Cost",
                  align: "right",
                  mono: true,
                  render: (row) => (
                    <span title={`expected ${formatCurrency(row.expected_value)}`}>
                      {formatCurrency(row.cost)}
                    </span>
                  ),
                },
              ]}
              rows={sorted}
              rowKey={(row) => row.id}
              density="comfortable"
            />
          )}
        </CardBody>
      </Card>
    </Stack>
  );
}
