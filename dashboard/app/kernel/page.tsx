"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Database,
  KeyRound,
  Radio,
  ServerCog,
  ShieldCheck,
} from "lucide-react";
import { AppShell } from "../../src/components/shell/app-shell";
import {
  AsyncButton,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  HelpPanel,
  InfoTip,
  Section,
  Stack,
  StatTile,
  StatusPill,
  Table,
  TableSkeleton,
  TabPanel,
  Tabs,
} from "../../src/components/ui";
import {
  fetchJson,
  fetchKernelSnapshot,
  fetchSystemInfo,
  fetchSystemJournal,
} from "../../src/lib/api";
import { useJournalStream } from "../../src/lib/events";
import {
  backendTone,
  formatAttempts,
  formatRelative,
  journalKindTone,
  kernelHealthTone,
  schedulerKindTone,
  schedulerStatusLabel,
  schedulerStatusTone,
  shortId,
} from "../../src/lib/format";
import type {
  ApiSource,
  JournalEvent,
  KernelSnapshot,
  SchedulerWorkItem,
  SystemInfo,
} from "../../src/lib/types";
import { useOperator } from "../../src/providers/operator-provider";

interface KernelHealth {
  ok: boolean;
  backend?: string;
  mode?: string;
  detail?: string;
}

interface KernelData {
  health: KernelHealth;
  healthSource: ApiSource;
  info: SystemInfo;
  infoSource: ApiSource;
  snapshot: KernelSnapshot;
  journal: JournalEvent[];
  journalSource: ApiSource;
  errors: string[];
}

const EMPTY_SNAPSHOT: KernelSnapshot = {
  overview: {
    system_state: "unavailable",
    active_instances: 0,
    active_runs: 0,
    parked_runs: 0,
    approvals_waiting: 0,
    manual_queue_depth: 0,
    ledger_events_today: 0,
    automation_coverage: 0,
    monthly_net: 0,
    gateway_health: "unavailable",
    ring_mix: {},
    last_commit_at: "",
  },
  schedulerWork: [],
  coreGaps: [],
  overviewAvailable: false,
  schedulerAvailable: false,
  coreGapsAvailable: false,
  fetchedAt: "",
};

export default function KernelPage() {
  return (
    <AppShell title="Kernel" crumbs={[{ label: "System" }, { label: "Kernel" }]}>
      <KernelContent />
    </AppShell>
  );
}

function KernelContent() {
  const { baseUrl } = useOperator();
  const [data, setData] = useState<KernelData | null>(null);
  const [tab, setTab] = useState("journal");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const { connected, events: liveEvents, latestEvent } = useJournalStream({
    baseUrl: baseUrl || undefined,
  });

  const load = useCallback(
    async (mode: "initial" | "refresh" = "initial") => {
      if (mode === "refresh") setRefreshing(true);
      const options = baseUrl ? { baseUrl } : {};
      const [health, info, snapshot, journal] = await Promise.all([
        fetchJson<KernelHealth>(
          "/health",
          { ok: false, mode: "disconnected", detail: "Health endpoint unavailable." },
          options,
        ),
        fetchSystemInfo(options),
        fetchKernelSnapshot(options),
        fetchSystemJournal({ limit: 40 }, options),
      ]);

      setData({
        health: health.data,
        healthSource: health.source,
        info: info.data,
        infoSource: info.source,
        snapshot: snapshot.data ?? EMPTY_SNAPSHOT,
        journal: journal.source === "api" ? journal.data : [],
        journalSource: journal.source,
        errors: [health.error, info.error, snapshot.error, journal.error].filter(
          (error): error is string => Boolean(error),
        ),
      });
      setLoading(false);
      setRefreshing(false);
    },
    [baseUrl],
  );

  useEffect(() => {
    void load("initial");
  }, [load]);

  useEffect(() => {
    if (latestEvent) void load("refresh");
  }, [latestEvent, load]);

  const scheduler = data?.snapshot.schedulerWork ?? [];
  const pendingWork = scheduler.filter((item) => item.status === "pending" || item.status === "claimed");
  const journal = useMemo(() => data?.journal ?? [], [data?.journal]);
  const unavailable = Boolean(data && data.healthSource !== "api" && data.infoSource !== "api");
  const healthTone = kernelHealthTone(
    data
      ? {
          ...data.health,
          backend: data.healthSource === "api" ? data.health.backend : undefined,
        }
      : undefined,
  );

  return (
    <Stack gap={5}>
      <HelpPanel id="kernel">
        <p>
          The engine room. The journal <InfoTip term="journal" /> is the append-only record of
          everything that happened; the scheduler <InfoTip term="scheduler_work" /> holds queued
          work; core gaps <InfoTip term="core_gap" /> are known missing pieces the kernel flagged.
        </p>
      </HelpPanel>
      {unavailable ? (
        <ErrorState
          title="Kernel API unavailable"
          detail="Live system data could not be reached. Empty states are shown instead of fixture success."
          action={
            <AsyncButton onClick={() => load("refresh")} loading={refreshing}>
              Retry
            </AsyncButton>
          }
        />
      ) : data?.errors.length ? (
        <Card tone="warn">
          <CardHeader
            eyebrow="Degraded"
            title="Some Kernel endpoints are unavailable"
            subtitle="Available endpoints remain live; unavailable sections are empty."
            action={<StatusPill tone="warn">{data.errors.length} endpoint errors</StatusPill>}
          />
        </Card>
      ) : null}

      <Section
        title="Kernel posture"
        subtitle="Live health, storage posture, scheduler pressure, and journal connectivity."
        eyebrow="System"
        action={
          <AsyncButton variant="secondary" onClick={() => load("refresh")} loading={refreshing}>
            Refresh
          </AsyncButton>
        }
      >
        <div className="mc-stats">
          <StatTile
            label="Kernel"
            value={loading ? "…" : data?.health.ok ? "ONLINE" : "DEGRADED"}
            tone={healthTone === "good" ? "good" : healthTone === "hot" ? "hot" : "warn"}
            icon={<ServerCog size={14} />}
            hint={data?.healthSource === "api" ? data.health.mode ?? "reachable" : "endpoint unavailable"}
          />
          <StatTile
            label="Backend"
            value={data?.infoSource === "api" ? data.info.backend.toUpperCase() : "—"}
            tone={data?.infoSource === "api" && backendTone(data.info.backend) === "good" ? "good" : "warn"}
            icon={<Database size={14} />}
            hint={data?.infoSource === "api" ? data.info.service : "system info unavailable"}
          />
          <StatTile
            label="Scheduler"
            value={loading ? "…" : pendingWork.length}
            tone={pendingWork.length > 0 ? "warn" : "good"}
            icon={<Activity size={14} />}
            hint={`${scheduler.length} work items loaded`}
          />
          <StatTile
            label="Journal SSE"
            value={connected ? "LIVE" : "OFFLINE"}
            tone={connected ? "good" : "warn"}
            icon={<Radio size={14} />}
            hint={connected ? `${liveEvents.length} recent frames` : "HTTP journal remains available"}
          />
          <StatTile
            label="Command auth"
            value={data?.infoSource === "api" ? (data.info.commandAuthConfigured ? "ON" : "OFF") : "—"}
            tone={data?.info.commandAuthConfigured ? "good" : "warn"}
            icon={<KeyRound size={14} />}
            hint={data?.infoSource === "api" ? data.info.posture : "system info unavailable"}
          />
          <StatTile
            label="Core gaps"
            value={loading ? "…" : data?.snapshot.coreGaps.length ?? 0}
            tone={(data?.snapshot.coreGaps.length ?? 0) > 0 ? "warn" : "good"}
            icon={<AlertTriangle size={14} />}
            hint="Explicitly unsupported or incomplete paths"
          />
        </div>
      </Section>

      <Tabs
        active={tab}
        onChange={setTab}
        items={[
          { key: "journal", label: "Journal", badge: journal.length },
          { key: "scheduler", label: "Scheduler", badge: scheduler.length },
          { key: "diagnostics", label: "Diagnostics", badge: data?.snapshot.coreGaps.length ?? 0 },
        ]}
      />

      <TabPanel activeKey={tab} tabKey="journal">
        <JournalPanel
          journal={journal}
          source={data?.journalSource ?? "fixture"}
          loading={loading}
          connected={connected}
        />
      </TabPanel>

      <TabPanel activeKey={tab} tabKey="scheduler">
        <SchedulerPanel
          rows={scheduler}
          loading={loading}
          available={data?.snapshot.schedulerAvailable ?? false}
        />
      </TabPanel>

      <TabPanel activeKey={tab} tabKey="diagnostics">
        <DiagnosticsPanel data={data} loading={loading} />
      </TabPanel>
    </Stack>
  );
}

function JournalPanel({
  journal,
  source,
  loading,
  connected,
}: {
  journal: JournalEvent[];
  source: ApiSource;
  loading: boolean;
  connected: boolean;
}) {
  return (
    <Section
      title="System journal"
      subtitle="Append-only kernel events from /journal; SSE only signals live invalidation."
      eyebrow="Source of truth"
      action={
        <StatusPill tone={source === "api" ? (connected ? "good" : "warn") : "hot"} dot pulse={connected}>
          {source === "api" ? (connected ? "streaming" : "polling") : "unavailable"}
        </StatusPill>
      }
    >
      {loading ? (
        <TableSkeleton columns={5} rows={7} />
      ) : journal.length === 0 ? (
        <EmptyState
          icon={<Radio size={20} />}
          title={source === "api" ? "No journal events" : "Journal unavailable"}
          detail={
            source === "api"
              ? "The live journal returned no events."
              : "The dashboard will not show fixture events when the kernel is offline."
          }
        />
      ) : (
        <Table
          density="compact"
          rows={journal}
          rowKey={(event) => event.id}
          columns={[
            {
              key: "time",
              header: "When",
              width: 150,
              mono: true,
              render: (event) => <span className="dim">{formatRelative(event.at)}</span>,
            },
            {
              key: "kind",
              header: "Kind",
              render: (event) => (
                <StatusPill tone={journalKindTone(event.kind)}>{event.kind}</StatusPill>
              ),
            },
            {
              key: "event",
              header: "Event",
              render: (event) => (
                <Stack gap={1}>
                  <span>{event.title}</span>
                  <span className="dim">{event.detail}</span>
                </Stack>
              ),
            },
            {
              key: "instance",
              header: "Instance",
              mono: true,
              render: (event) => shortId(event.instance_id),
            },
            {
              key: "run",
              header: "Run",
              mono: true,
              render: (event) => shortId(event.run_id),
            },
          ]}
        />
      )}
    </Section>
  );
}

function SchedulerPanel({
  rows,
  loading,
  available,
}: {
  rows: SchedulerWorkItem[];
  loading: boolean;
  available: boolean;
}) {
  return (
    <Section
      title="Scheduler work"
      subtitle="Trigger and approval work from the durable scheduler queue."
      eyebrow="C13 read model"
    >
      {loading ? (
        <TableSkeleton columns={6} rows={6} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={<ShieldCheck size={20} />}
          title={available ? "No scheduler work" : "Scheduler unavailable"}
          detail={
            available
              ? "The live scheduler queue is empty."
              : "/scheduler-work could not be reached. No fixture rows are shown."
          }
        />
      ) : (
        <Table
          density="compact"
          rows={rows}
          rowKey={(item) => item.workId}
          columns={[
            {
              key: "work",
              header: "Work",
              mono: true,
              render: (item) => shortId(item.workId),
            },
            {
              key: "kind",
              header: "Kind",
              render: (item) => (
                <StatusPill tone={schedulerKindTone(item.kind)}>{item.kind}</StatusPill>
              ),
            },
            {
              key: "status",
              header: "Status",
              render: (item) => (
                <StatusPill tone={schedulerStatusTone(item.status)} dot>
                  {schedulerStatusLabel(item.status)}
                </StatusPill>
              ),
            },
            {
              key: "attempts",
              header: "Attempts",
              render: (item) => formatAttempts(item.attempts),
            },
            {
              key: "target",
              header: "Target",
              mono: true,
              render: (item) => item.runId ? shortId(item.runId) : shortId(item.instanceId),
            },
            {
              key: "updated",
              header: "Updated",
              mono: true,
              render: (item) => <span className="dim">{formatRelative(item.updatedAt)}</span>,
            },
          ]}
        />
      )}
    </Section>
  );
}

function DiagnosticsPanel({ data, loading }: { data: KernelData | null; loading: boolean }) {
  if (loading) return <TableSkeleton columns={2} rows={4} />;

  return (
    <Stack gap={4}>
      <Card>
        <CardHeader
          eyebrow="/system/info"
          title="Runtime posture"
          subtitle={data?.infoSource === "api" ? "Live system metadata." : "System metadata unavailable."}
          action={
            <StatusPill tone={data?.infoSource === "api" ? "good" : "hot"}>
              {data?.infoSource === "api" ? "live" : "unavailable"}
            </StatusPill>
          }
        />
        <CardBody>
          <Stack gap={2}>
            <DataPair label="Service" value={data?.infoSource === "api" ? data.info.service : "—"} />
            <DataPair label="Backend" value={data?.infoSource === "api" ? data.info.backend : "—"} />
            <DataPair label="Posture" value={data?.infoSource === "api" ? data.info.posture : "—"} />
            <DataPair
              label="Internal only"
              value={data?.infoSource === "api" ? String(data.info.internalOnly) : "—"}
            />
            <DataPair
              label="Fixtures allowed"
              value={data?.infoSource === "api" ? String(data.info.fixturesAllowed) : "—"}
            />
          </Stack>
        </CardBody>
      </Card>

      <Section title="Core gaps" subtitle="Known unsupported paths; these are not rendered as successes.">
        {(data?.snapshot.coreGaps.length ?? 0) === 0 ? (
          <EmptyState
            title={data?.snapshot.coreGapsAvailable ? "No reported core gaps" : "Core gaps unavailable"}
            detail={
              data?.snapshot.coreGapsAvailable
                ? `Last checked ${formatRelative(data.snapshot.fetchedAt)}.`
                : "The core-gaps endpoint is unavailable."
            }
          />
        ) : (
          <Stack gap={3}>
            {data?.snapshot.coreGaps.map((gap) => (
              <Card key={gap.id} tone="warn">
                <CardHeader
                  eyebrow={gap.id}
                  title={gap.title}
                  subtitle={gap.detail}
                  action={<StatusPill tone="warn">gap</StatusPill>}
                />
              </Card>
            ))}
          </Stack>
        )}
      </Section>
    </Stack>
  );
}

function DataPair({ label, value }: { label: string; value: string }) {
  return (
    <div className="ax-data-pair">
      <span className="ax-data-pair__label">{label}</span>
      <span className="ax-data-pair__value mono">{value}</span>
    </div>
  );
}
