"use client";

/**
 * InstanceInspector — the host for /instances/{id}.
 *
 * Composes the header, the tab strip, and the seven tab content components:
 * Overview · Live Activity · Runs · Approvals · Trust & Ring · Memory · Actions.
 *
 * Memory + Actions landed in C4 — they consume the C3 heap read API
 * (/instances/{id}/memory) and the per-instance journal slice
 * (/journal?instance_id=) respectively, both filtered through the
 * ``inspector-c4`` pure helpers and rendered via the C1 JsonViewer + Timeline
 * primitives.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Boxes,
  CheckCircle2,
  Database,
  Radio,
  ShieldAlert,
  ShieldCheck,
  Workflow,
  Zap,
} from "lucide-react";

import { AppShell } from "../shell/app-shell";
import {
  AsyncButton,
  Badge,
  ErrorState,
  Skeleton,
  Stack,
  Tabs,
  type TabItem,
} from "../ui";
import { useOperator } from "../../providers/operator-provider";
import { useToast } from "../../providers/toast-provider";
import { fetchApprovals, fetchInstance, fetchRuns } from "../../lib/api";
import { useJournalStream, type JournalStreamEvent } from "../../lib/events";
import { shortId, runStateTone, runStateLabel } from "../../lib/format";
import type { ApprovalCard, InstanceSummary, RunSummary } from "../../lib/types";

import { InspectorHeader } from "./inspector-header";
import { OverviewTab } from "./tabs/overview-tab";
import { ActivityTab } from "./tabs/activity-tab";
import { RunsTab } from "./tabs/runs-tab";
import { ApprovalsTab } from "./tabs/approvals-tab";
import { TrustTab } from "./tabs/trust-tab";
import { MemoryTab } from "./tabs/memory-tab";
import { ActionsTab } from "./tabs/actions-tab";

export type InspectorTabKey =
  | "overview"
  | "activity"
  | "runs"
  | "approvals"
  | "trust"
  | "memory"
  | "actions";

interface InstanceInspectorProps {
  instanceId: string;
  initialInstance?: InstanceSummary;
  initialRuns?: RunSummary[];
  initialApprovals?: ApprovalCard[];
  initialEvents?: JournalStreamEvent[];
  /** Optional override of the active tab (e.g. via deep link query string). */
  initialTab?: InspectorTabKey;
}

const TAB_DEFS: Array<{
  key: InspectorTabKey;
  label: string;
  icon: React.ReactNode;
}> = [
  { key: "overview", label: "Overview", icon: <Boxes size={13} /> },
  { key: "activity", label: "Live Activity", icon: <Radio size={13} /> },
  { key: "runs", label: "Runs", icon: <Workflow size={13} /> },
  { key: "approvals", label: "Approvals", icon: <ShieldAlert size={13} /> },
  { key: "trust", label: "Trust & Ring", icon: <ShieldCheck size={13} /> },
  { key: "memory", label: "Memory", icon: <Database size={13} /> },
  { key: "actions", label: "Actions", icon: <Zap size={13} /> },
];

// Older doc comments referenced the now-removed placeholder list. Memory +
// Actions are now first-class tabs (C4 — see BLUEPRINT §6 tabs 3 + 4).

export function InstanceInspector({
  instanceId,
  initialInstance,
  initialRuns,
  initialApprovals,
  initialEvents,
  initialTab = "overview",
}: InstanceInspectorProps) {
  const { baseUrl } = useOperator();
  const toast = useToast();
  const [instance, setInstance] = useState<InstanceSummary | null>(initialInstance ?? null);
  const [runs, setRuns] = useState<RunSummary[] | null>(initialRuns ?? null);
  const [approvals, setApprovals] = useState<ApprovalCard[] | null>(initialApprovals ?? null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(!initialInstance);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<InspectorTabKey>(initialTab);
  const [livePulseKey, setLivePulseKey] = useState<string>("");
  const { latestEvent } = useJournalStream({ baseUrl: baseUrl || undefined });

  // Pulse the header when an SSE event lands for this instance.
  useEffect(() => {
    if (!latestEvent) return;
    if (!latestEvent.instance_id || latestEvent.instance_id === instanceId) {
      setLivePulseKey(`${latestEvent.event_id}-${Date.now()}`);
    }
  }, [latestEvent, instanceId]);

  const load = useCallback(
    async (mode: "initial" | "refresh" = "initial") => {
      if (mode === "refresh") setRefreshing(true);
      try {
        const [instRes, runsRes, approvalsRes] = await Promise.all([
          fetchInstance(instanceId),
          fetchRuns({ instance_id: instanceId }),
          fetchApprovals({ instance_id: instanceId }),
        ]);
        setInstance(instRes.data);
        setRuns(runsRes.data);
        setApprovals(approvalsRes.data);
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
    [instanceId, toast],
  );

  useEffect(() => {
    if (initialInstance && initialRuns && initialApprovals) return;
    void load("initial");
  }, [initialInstance, initialRuns, initialApprovals, load]);

  // Pick the featured run: active > parked > most-recent.
  const featuredRun = useMemo<RunSummary | null>(() => {
    if (!runs || runs.length === 0) return null;
    const active = runs.find((r) => r.state === "active");
    if (active) return active;
    const parked = runs.find((r) => r.state === "parked" || r.state === "waiting_approval");
    if (parked) return parked;
    return [...runs].sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1))[0];
  }, [runs]);

  // Build the tab items. Approvals tab gets a count badge; activity tab
  // gets a "live" pulse when the SSE stream is up.
  const activityConnected = Boolean(latestEvent);
  const parkedCount = (approvals ?? []).length;
  const tabItems: TabItem[] = TAB_DEFS.map((def) => {
    let badge: React.ReactNode = undefined;
    if (def.key === "approvals" && parkedCount > 0) {
      badge = <Badge tone="warn">{parkedCount}</Badge>;
    }
    if (def.key === "activity" && activityConnected) {
      badge = <Badge tone="good">live</Badge>;
    }
    if (def.key === "runs" && runs && runs.length > 0) {
      badge = <Badge tone="muted">{runs.length}</Badge>;
    }
    return {
      key: def.key,
      label: (
        <span className="ax-row" style={{ gap: 6 }}>
          {def.icon}
          <span>{def.label}</span>
          {badge}
        </span>
      ),
    };
  });

  return (
    <AppShell
      title={instance?.name ?? `Instance ${shortId(instanceId)}`}
      crumbs={[
        { label: "Instances", href: "/instances" },
        { label: instance?.name ?? shortId(instanceId) },
      ]}
      onRefresh={() => void load("refresh")}
      refreshing={refreshing}
    >
      <div className="instance-inspector">
        {error && !loading && !instance ? (
          <ErrorState
            title="Couldn't load instance"
            detail={error}
            action={
              <AsyncButton variant="secondary" onClick={() => void load("refresh")}>
                Retry
              </AsyncButton>
            }
          />
        ) : loading || !instance ? (
          <Stack gap={4}>
            <Skeleton width="60%" height={140} />
            <Skeleton width="100%" height={48} />
            <Skeleton width="100%" height={200} />
          </Stack>
        ) : (
          <Stack gap={4}>
            <InspectorHeader
              instance={instance}
              featuredRun={featuredRun}
              livePulseKey={livePulseKey}
              isRefreshing={refreshing}
              onAfterCommand={() => void load("refresh")}
            />

            <Tabs
              items={tabItems}
              active={activeTab}
              onChange={(key) => setActiveTab(key as InspectorTabKey)}
            />

            {activeTab === "overview" ? (
              <OverviewTab instance={instance} runs={runs ?? []} />
            ) : null}
            {activeTab === "activity" ? (
              <ActivityTab
                instanceId={instanceId}
                initialEvents={initialEvents}
                runs={runs ?? []}
              />
            ) : null}
            {activeTab === "runs" ? (
              <RunsTab instanceId={instanceId} initialRuns={runs ?? undefined} />
            ) : null}
            {activeTab === "approvals" ? (
              <ApprovalsTab
                instanceId={instanceId}
                initialApprovals={approvals ?? undefined}
                onAfterCommand={() => void load("refresh")}
              />
            ) : null}
            {activeTab === "trust" ? <TrustTab instance={instance} /> : null}
            {activeTab === "memory" ? (
              <MemoryTab instanceId={instanceId} />
            ) : null}
            {activeTab === "actions" ? (
              <ActionsTab instanceId={instanceId} runs={runs ?? []} />
            ) : null}
          </Stack>
        )}
      </div>
    </AppShell>
  );
}

// Avoid an unused-import warning in some build configurations.
void CheckCircle2;
void runStateTone;
void runStateLabel;
