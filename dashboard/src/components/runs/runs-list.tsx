"use client";

/**
 * /runs — the cross-instance Runs list (C6).
 *
 * A filterable, calm table of every run the dashboard knows about, with a
 * drill-down link to the per-run trace page. Filters live in the URL so the
 * view is shareable + back-button-friendly:
 *
 *   /runs                          ← all runs
 *   /runs?state=waiting_approval   ← only parked / waiting-approval runs
 *   /runs?instance_id=inst-kaveri  ← only one customer's runs
 *   /runs?state=active&instance_id=inst-nila
 *
 * Data sources: `fetchRuns({state, instance_id})`. The api helper already
 * degrades to fixtures when the kernel is offline, so the page is always
 * renderable. `useJournalStream` invalidates the `runs` slice when a run
 * settles or parks, so the table quietly updates itself during a session.
 *
 * Counts: stat tiles for `total`, `active`, `waiting_approval`, `parked`
 * (always over the FULL list, so the tiles don't shift as you filter).
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Activity,
  CircleSlash2,
  Filter,
  GitBranch,
  Pause,
  TimerReset,
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
  Row,
  Skeleton,
  Stack,
  StatTile,
  StatusPill,
  Table,
  TableSkeleton,
} from "../ui";
import { useOperator } from "../../providers/operator-provider";
import { useToast } from "../../providers/toast-provider";
import { fetchRuns, fetchInstances } from "../../lib/api";
import { useJournalStream, invalidationsForJournalEvent } from "../../lib/events";
import {
  filterRuns,
  runStateOptions,
  summariseRuns,
} from "../../lib/runs";
import {
  formatCurrency,
  formatRelative,
  formatTime,
  runStateLabel,
  runStateTone,
  shortId,
} from "../../lib/format";
import type { InstanceSummary, RunSummary } from "../../lib/types";

interface RunsListProps {
  initialRuns?: RunSummary[];
  initialInstances?: InstanceSummary[];
}

export function RunsList({
  initialRuns,
  initialInstances,
}: RunsListProps = {}) {
  const router = useRouter();
  const search = useSearchParams();
  const { baseUrl } = useOperator();
  const toast = useToast();

  // --- URL-driven filters -------------------------------------------------
  const filterState = search.get("state") ?? "";
  const filterInstance = search.get("instance_id") ?? "";
  const filterQuery = search.get("q") ?? "";

  // --- Data ---------------------------------------------------------------
  const [allRuns, setAllRuns] = useState<RunSummary[] | null>(
    initialRuns ?? null,
  );
  const [instances, setInstances] = useState<InstanceSummary[] | null>(
    initialInstances ?? null,
  );
  const [loading, setLoading] = useState<boolean>(!initialRuns);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (mode: "initial" | "refresh") => {
      if (mode === "refresh") setRefreshing(true);
      try {
        // The list only needs the unfiltered set — filters apply on the
        // client (small fixture set today; would push server-side once the
        // kernel supports a richer `/runs` query).
        const [runsRes, instancesRes] = await Promise.all([
          fetchRuns({}),
          fetchInstances(),
        ]);
        setAllRuns(runsRes.data);
        setInstances(instancesRes.data);
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
    if (initialRuns) return;
    void load("initial");
  }, [initialRuns, load]);

  // --- SSE → invalidate `runs` on settle / park --------------------------
  const journal = useJournalStream({ baseUrl });
  useEffect(() => {
    if (!journal.latestEvent) return;
    const slices = invalidationsForJournalEvent(journal.latestEvent);
    if (slices.includes("runs") && !refreshing) {
      void load("refresh");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [journal.latestEvent?.event_id]);

  // --- Derived view -------------------------------------------------------
  const instanceNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const inst of instances ?? []) map.set(inst.id, inst.name);
    return map;
  }, [instances]);

  const summary = useMemo(
    () => summariseRuns(allRuns ?? []),
    [allRuns],
  );

  const filtered = useMemo(
    () =>
      filterRuns(allRuns ?? [], {
        state: filterState || undefined,
        instance_id: filterInstance || undefined,
        query: filterQuery || undefined,
      }),
    [allRuns, filterState, filterInstance, filterQuery],
  );

  // --- URL push helpers ---------------------------------------------------
  const updateFilters = useCallback(
    (next: { state?: string; instance_id?: string; q?: string }) => {
      const params = new URLSearchParams(search.toString());
      for (const [k, v] of Object.entries(next)) {
        if (v === undefined || v === "") params.delete(k);
        else params.set(k, v);
      }
      const qs = params.toString();
      router.push(qs ? `/runs?${qs}` : "/runs");
    },
    [router, search],
  );

  const clearFilters = useCallback(() => {
    router.push("/runs");
  }, [router]);

  // --- Render -------------------------------------------------------------
  return (
    <AppShell
      title="Runs"
      crumbs={[
        { href: "/", label: "Mission Control" },
        { label: "Runs" },
      ]}
      onRefresh={() => load("refresh")}
      refreshing={refreshing}
    >
      <Stack gap={4}>
        <HelpPanel id="runs">
          <p>
            Every run across all instances. A run&apos;s state <InfoTip term="run_state" /> tells you
            if it&apos;s working, parked for your approval <InfoTip term="approval" />, settled
            (finished and billed <InfoTip term="settlement" />), or crashed. Click one to see its
            full trace, claimed facts, and settlement.
          </p>
        </HelpPanel>
        {/* Stat tiles — always over the FULL list so they don't shift as the
            user toggles filters. */}
        <Row gap={3} wrap>
          <StatTile
            label="Total"
            value={loading ? "—" : String(summary.total)}
            icon={<Activity size={16} />}
            tone="default"
            hint={loading ? "loading…" : "across all instances"}
          />
          <StatTile
            label="Active"
            value={loading ? "—" : String(summary.by_state.active ?? 0)}
            icon={<GitBranch size={16} />}
            tone="good"
            hint="running right now"
          />
          <StatTile
            label="Waiting approval"
            value={loading ? "—" : String(summary.by_state.waiting_approval ?? 0)}
            icon={<TimerReset size={16} />}
            tone="warn"
            hint="needs a human"
          />
          <StatTile
            label="Parked"
            value={loading ? "—" : String(summary.by_state.parked ?? 0)}
            icon={<Pause size={16} />}
            tone="warn"
            hint="paused / queued"
          />
          <StatTile
            label="Settled today"
            value={loading ? "—" : String(summary.by_state.complete ?? 0)}
            icon={<CircleSlash2 size={16} />}
            tone="good"
            hint="completed"
          />
        </Row>

        {/* Filter bar */}
        <Card padding="sm">
          <CardBody>
            <Row gap={3} wrap align="center">
              <Row gap={1} align="center">
                <Filter size={14} aria-hidden />
                <span className="ax-eyebrow">Filter</span>
              </Row>
              <FilterPills
                current={filterState}
                counts={summary.by_state}
                onChange={(next) => updateFilters({ state: next })}
              />
              <InstancePicker
                instances={instances ?? []}
                current={filterInstance}
                onChange={(next) => updateFilters({ instance_id: next })}
              />
              <QueryInput
                initial={filterQuery}
                onSubmit={(next) => updateFilters({ q: next })}
              />
              {(filterState || filterInstance || filterQuery) ? (
                <button
                  type="button"
                  className="ax-pill ax-pill--neutral"
                  onClick={clearFilters}
                >
                  Clear all
                </button>
              ) : null}
              <span className="ax-eyebrow" style={{ marginLeft: "auto" }}>
                {loading
                  ? "loading…"
                  : `${filtered.length} of ${summary.total}`}
              </span>
            </Row>
          </CardBody>
        </Card>

        {/* Main list */}
        <Card padding="none">
          <CardHeader
            title="All runs"
            subtitle="Every run, latest first. Click a row for the trace timeline."
            eyebrow="Live · cross-instance"
          />
          <CardBody>
            {loading ? (
              <TableSkeleton columns={6} rows={6} />
            ) : error && filtered.length === 0 ? (
              <ErrorState
                title="Couldn't load runs"
                detail={error}
                action={
                  <AsyncButton onClick={() => load("initial")} size="sm">
                    Retry
                  </AsyncButton>
                }
              />
            ) : filtered.length === 0 ? (
              <EmptyState
                icon={<Activity size={20} />}
                title="No runs match these filters"
                detail={
                  summary.total === 0
                    ? "The kernel has no runs yet — once a mandate fires, it'll show up here."
                    : "Loosen the filters or clear them to see more."
                }
                action={
                  summary.total > 0 ? (
                    <AsyncButton onClick={clearFilters} size="sm">
                      Clear filters
                    </AsyncButton>
                  ) : undefined
                }
              />
            ) : (
              <Table<RunSummary>
                columns={[
                  {
                    key: "title",
                    header: "Run",
                    render: (run) => (
                      <Stack gap={1}>
                        <Link
                          href={`/runs/${encodeURIComponent(run.id)}`}
                          className="ax-link"
                        >
                          {run.title}
                        </Link>
                        <span className="ax-eyebrow mono">{shortId(run.id, 8)}</span>
                      </Stack>
                    ),
                  },
                  {
                    key: "instance",
                    header: "Instance",
                    render: (run) => (
                      <Link
                        href={`/instances/${encodeURIComponent(run.instance_id)}`}
                        className="ax-link mono"
                      >
                        {instanceNameById.get(run.instance_id) ?? run.instance_id}
                      </Link>
                    ),
                  },
                  {
                    key: "state",
                    header: "State",
                    render: (run) => (
                      <StatusPill tone={runStateTone(run.state)}>
                        {runStateLabel(run.state)}
                      </StatusPill>
                    ),
                  },
                  {
                    key: "syscall",
                    header: "Syscall",
                    mono: true,
                    render: (run) => (
                      <span className="mono">{run.syscall}</span>
                    ),
                  },
                  {
                    key: "cost",
                    header: "Cost / EV",
                    align: "right",
                    render: (run) => (
                      <Stack gap={1} align="end">
                        <span>
                          <Wallet size={11} aria-hidden />{" "}
                          {formatCurrency(run.cost)}
                        </span>
                        <span className="ax-eyebrow">
                          EV {formatCurrency(run.expected_value)}
                        </span>
                      </Stack>
                    ),
                  },
                  {
                    key: "updated",
                    header: "Updated",
                    render: (run) => (
                      <Stack gap={1}>
                        <span>{formatRelative(run.updated_at)}</span>
                        <span className="ax-eyebrow mono">
                          {formatTime(run.updated_at)}
                        </span>
                      </Stack>
                    ),
                  },
                ]}
                rows={filtered}
                rowKey={(run) => run.id}
                density="compact"
              />
            )}
          </CardBody>
        </Card>
      </Stack>
    </AppShell>
  );
}

// -----------------------------------------------------------------------------
// Filter pills + instance picker + query input — small inline helpers so the
// main component reads top-down. Each accepts the same shape the URL carries.
// -----------------------------------------------------------------------------

function FilterPills({
  current,
  counts,
  onChange,
}: {
  current: string;
  counts: Record<RunSummary["state"], number>;
  onChange: (next: string) => void;
}) {
  const options = runStateOptions();
  return (
    <Row gap={1} wrap role="group" aria-label="Filter by run state">
      <PillButton
        active={!current}
        onClick={() => onChange("")}
        label={`All (${counts.active + (counts.waiting_approval ?? 0) + (counts.parked ?? 0) + (counts.complete ?? 0) + (counts.failed ?? 0)})`}
      />
      {options.map((opt) => (
        <PillButton
          key={opt.value}
          active={current === opt.value}
          onClick={() => onChange(opt.value)}
          label={`${opt.label} (${counts[opt.value] ?? 0})`}
          tone={
            opt.value === "failed"
              ? "hot"
              : opt.value === "complete"
                ? "good"
                : opt.value === "active"
                  ? "info"
                  : opt.value === "waiting_approval" || opt.value === "parked"
                    ? "warn"
                    : "neutral"
          }
        />
      ))}
    </Row>
  );
}

function PillButton({
  active,
  onClick,
  label,
  tone,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  tone?: "good" | "warn" | "hot" | "info" | "neutral";
}) {
  return (
    <button
      type="button"
      className={`ax-pill ${active ? "ax-pill--active" : ""}`}
      data-tone={tone ?? "neutral"}
      aria-pressed={active}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

function InstancePicker({
  instances,
  current,
  onChange,
}: {
  instances: InstanceSummary[];
  current: string;
  onChange: (next: string) => void;
}) {
  return (
    <label className="ax-pill ax-pill--select" data-active={Boolean(current)}>
      <span className="ax-eyebrow">Instance</span>
      <select
        value={current}
        onChange={(event) => onChange(event.target.value)}
        aria-label="Filter by instance"
      >
        <option value="">All</option>
        {instances.map((inst) => (
          <option key={inst.id} value={inst.id}>
            {inst.name} ({shortId(inst.id, 6)})
          </option>
        ))}
      </select>
    </label>
  );
}

function QueryInput({
  initial,
  onSubmit,
}: {
  initial: string;
  onSubmit: (next: string) => void;
}) {
  const [value, setValue] = useState(initial);
  return (
    <form
      role="search"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(value);
      }}
    >
      <input
        type="search"
        className="ax-input"
        placeholder="Search title, syscall, id…"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        aria-label="Search runs"
      />
    </form>
  );
}
