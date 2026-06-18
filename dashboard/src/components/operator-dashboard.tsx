"use client";

import {
  Boxes,
  ClipboardList,
  Command,
  DatabaseZap,
  Factory,
  FileClock,
  Gauge,
  GitBranchPlus,
  Inbox,
  Loader2,
  Network,
  RefreshCw,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  approveCommand,
  fetchInstance,
  fetchRun,
  loadDashboardData,
  setRingCommand,
} from "@/lib/api";
import { fixtureDashboardData } from "@/lib/fixtures";
import type {
  ApiResult,
  CommandResult,
  CoreGap,
  DashboardData,
  InstanceSummary,
  ManualTask,
  RunSummary,
} from "@/lib/types";
import { ApprovalInbox } from "./approval-inbox";
import { CapabilityRegistry } from "./capability-registry";
import { CatalogCreate } from "./catalog-create";
import { FloorView } from "./floor-view";
import { FoundryView } from "./foundry-view";
import { InstanceFile } from "./instance-file";
import { LedgerView } from "./ledger-view";
import { RunDetail } from "./run-detail";
import { classNames, SourceBadge, StatusPill, type ViewId } from "./shared";

const navItems: Array<{
  id: ViewId;
  label: string;
  icon: typeof Gauge;
}> = [
  { id: "floor", label: "Floor", icon: Gauge },
  { id: "approvals", label: "Approvals", icon: Inbox },
  { id: "catalog", label: "Catalog", icon: Boxes },
  { id: "instance", label: "Instance", icon: ClipboardList },
  { id: "run", label: "Run", icon: FileClock },
  { id: "capabilities", label: "Capabilities", icon: Network },
  { id: "ledger", label: "Ledger", icon: DatabaseZap },
  { id: "foundry", label: "Foundry", icon: Factory },
];

type SourceMap = Record<keyof DashboardData, ApiResult<unknown>>;

export function OperatorDashboard() {
  const [data, setData] = useState<DashboardData>(fixtureDashboardData);
  const [sources, setSources] = useState<SourceMap | undefined>();
  const [activeView, setActiveView] = useState<ViewId>("floor");
  const [selectedInstanceId, setSelectedInstanceId] = useState(fixtureDashboardData.instances[0].id);
  const [selectedRunId, setSelectedRunId] = useState(fixtureDashboardData.runs[0].id);
  const [instanceDetails, setInstanceDetails] = useState<Record<string, InstanceSummary>>({});
  const [runDetails, setRunDetails] = useState<Record<string, RunSummary>>({});
  const [commandResult, setCommandResult] = useState<CommandResult | undefined>();
  const [loading, setLoading] = useState(true);
  const [clock, setClock] = useState("--:--:--");

  const refresh = useCallback(async (options: { silent?: boolean } = {}) => {
    if (!options.silent) setLoading(true);
    const snapshot = await loadDashboardData();
    setData(snapshot.data);
    setSources(snapshot.sources);
    setSelectedInstanceId((current) => snapshot.data.instances.some((item) => item.id === current)
      ? current
      : snapshot.data.instances[0]?.id ?? current);
    setSelectedRunId((current) => snapshot.data.runs.some((item) => item.id === current)
      ? current
      : snapshot.data.runs[0]?.id ?? current);
    if (!options.silent) setLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const poller = window.setInterval(() => {
      void refresh({ silent: true });
    }, 8000);
    return () => window.clearInterval(poller);
  }, [refresh]);

  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString("en-IN", { hour12: false }));
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const sourceMode = useMemo(() => {
    if (loading || !sources) return "loading";
    const values = Object.values(sources).map((result) => result.source);
    if (values.every((source) => source === "api")) return "api";
    if (values.every((source) => source === "fixture")) return "fixture";
    return "mixed";
  }, [loading, sources]);

  const selectedInstance =
    instanceDetails[selectedInstanceId] ??
    data.instances.find((instance) => instance.id === selectedInstanceId) ??
    data.instances[0];

  const selectedRun =
    runDetails[selectedRunId] ??
    data.runs.find((run) => run.id === selectedRunId) ??
    data.runs[0];

  const selectInstance = useCallback(async (instanceId: string) => {
    setSelectedInstanceId(instanceId);
    setActiveView("instance");
    const result = await fetchInstance(instanceId);
    setInstanceDetails((current) => ({ ...current, [instanceId]: result.data }));
  }, []);

  const selectRun = useCallback(async (runId: string) => {
    setSelectedRunId(runId);
    setActiveView("run");
    const result = await fetchRun(runId);
    setRunDetails((current) => ({ ...current, [runId]: result.data }));
  }, []);

  const approve = useCallback(async (task: ManualTask) => {
    setCommandResult(undefined);
    const result = await approveCommand({
      instance_id: task.instance_id,
      run_id: task.run_id,
      actor: "dashboard/operator",
    });

    setCommandResult(result);
    if (result.supported) {
      setData((current) => ({
        ...current,
        manualQueue: current.manualQueue.map((item) =>
          item.id === task.id ? { ...item, status: "approved" } : item,
        ),
      }));
    }
  }, []);

  const showGap = useCallback((gap: CoreGap) => {
    setCommandResult({ supported: false, gap });
  }, []);

  const setRing = useCallback(async (instanceId: string, ring: string) => {
    setCommandResult(undefined);
    const result = await setRingCommand({
      instance_id: instanceId,
      ring,
      actor: "dashboard/operator",
    });

    setCommandResult(result);
    if (result.supported) {
      setData((current) => ({
        ...current,
        instances: current.instances.map((instance) =>
          instance.id === instanceId ? { ...instance, ring } : instance,
        ),
      }));
      setInstanceDetails((current) => {
        const detail = current[instanceId];
        return detail ? { ...current, [instanceId]: { ...detail, ring } } : current;
      });
    }
  }, []);

  const content = (() => {
    switch (activeView) {
      case "approvals":
        return (
          <ApprovalInbox
            commandResult={commandResult}
            data={data}
            onApprove={approve}
            onGap={showGap}
          />
        );
      case "catalog":
        return <CatalogCreate data={data} />;
      case "instance":
        return (
          <InstanceFile
            commandResult={commandResult}
            data={data}
            onSelectInstance={selectInstance}
            onSelectRun={selectRun}
            onSetRing={setRing}
            selectedInstance={selectedInstance}
          />
        );
      case "run":
        return <RunDetail data={data} onSelectRun={selectRun} selectedRun={selectedRun} />;
      case "capabilities":
        return <CapabilityRegistry data={data} />;
      case "ledger":
        return <LedgerView data={data} />;
      case "foundry":
        return <FoundryView data={data} />;
      case "floor":
      default:
        return <FloorView data={data} onSelectInstance={selectInstance} onSelectRun={selectRun} />;
    }
  })();

  return (
    <main className="operator-shell">
      <div className="atmosphere" />
      <aside className="nav-rail" aria-label="Dashboard views">
        <div className="brand-mark">
          <Command size={24} />
          <span>Agent-X</span>
        </div>
        <nav>
          {navItems
            .filter((item) => item.id !== "foundry" || data.evalCases.length > 0)
            .map((item) => {
              const Icon = item.icon;
              return (
                <button
                  className={classNames("nav-button", activeView === item.id && "active")}
                  key={item.id}
                  onClick={() => setActiveView(item.id)}
                  title={item.label}
                  type="button"
                >
                  <Icon size={18} />
                  <span>{item.label}</span>
                </button>
              );
            })}
        </nav>
      </aside>

      <section className="dashboard-stage">
        <header className="top-bar">
          <div>
            <p className="eyebrow">operator console</p>
            <h1>Business OS Control Room</h1>
          </div>
          <div className="top-actions">
            <StatusPill label={data.health.status} tone={data.health.status === "ok" ? "good" : "warn"} />
            <SourceBadge source={sourceMode} />
            <span className="clock">{clock}</span>
            <button className="icon-button" onClick={() => void refresh()} title="Refresh" type="button">
              {loading ? <Loader2 className="spin" size={17} /> : <RefreshCw size={17} />}
            </button>
          </div>
        </header>

        {content}
      </section>

      <div className="bottom-ledger">
        <GitBranchPlus size={15} />
        <span>{data.overview.last_commit_at}</span>
        <strong>{data.journal[0]?.title}</strong>
      </div>
    </main>
  );
}
