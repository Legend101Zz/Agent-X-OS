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
  fetchInstance,
  fetchRun,
  fetchSystemInfo,
  loadDashboardData,
} from "@/lib/api";
import { invalidationsForJournalEvent, useJournalStream } from "@/lib/events";
import type {
  ApiResult,
  ApprovalCard,
  CommandResult,
  CoreGap,
  DashboardData,
  InstanceSummary,
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
import {
  classNames,
  SourceBadge,
  StatusPill,
  ToastStack,
  useToasts,
  type ToastTone,
  type ViewId,
} from "./shared";

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

const OPERATOR_TOKEN_STORAGE_KEY = "agentx.operatorToken";

interface RecentCommand {
  id: string;
  label: string;
  message: string;
  status: string;
  timestamp: string;
  tone: ToastTone;
}

function getOperatorToken(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(OPERATOR_TOKEN_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

function setOperatorToken(value: string) {
  if (typeof window === "undefined") return;
  try {
    if (value) {
      window.localStorage.setItem(OPERATOR_TOKEN_STORAGE_KEY, value);
    } else {
      window.localStorage.removeItem(OPERATOR_TOKEN_STORAGE_KEY);
    }
  } catch {
    /* ignore — localStorage may be unavailable */
  }
}

export function OperatorDashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [sources, setSources] = useState<SourceMap | undefined>();
  const [activeView, setActiveView] = useState<ViewId>("floor");
  const [selectedInstanceId, setSelectedInstanceId] = useState<string>("");
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [instanceDetails, setInstanceDetails] = useState<Record<string, InstanceSummary>>({});
  const [runDetails, setRunDetails] = useState<Record<string, RunSummary>>({});
  const [commandResult, setCommandResult] = useState<CommandResult | undefined>();
  const [recentCommands, setRecentCommands] = useState<RecentCommand[]>([]);
  const { dismissToast, pushToast, toasts } = useToasts();
  const [loading, setLoading] = useState(true);
  const [clock, setClock] = useState("--:--:--");
  const [operatorToken, setOperatorTokenState] = useState<string>("");
  const [liveMode, setLiveMode] = useState<boolean>(true);
  const [apiBaseUrl, setApiBaseUrl] = useState<string>(
    process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000",
  );
  const { connected: journalConnected, latestEvent } = useJournalStream({ baseUrl: apiBaseUrl });

  useEffect(() => {
    setOperatorTokenState(getOperatorToken());
    const stored = getOperatorToken();
    setOperatorTokenState(stored);
  }, []);

  const refresh = useCallback(
    async (options: { silent?: boolean } = {}) => {
      if (!options.silent) setLoading(true);
      try {
        const info = await fetchSystemInfo({ baseUrl: apiBaseUrl });
        if (info.source === "api" && typeof info.data === "object" && info.data !== null) {
          setLiveMode(Boolean((info.data as { internal_only?: boolean }).internal_only));
        }
      } catch {
        /* ignore — keep current mode */
      }
      const snapshot = await loadDashboardData({ baseUrl: apiBaseUrl });
      setData(snapshot.data);
      setSources(snapshot.sources);
      setSelectedInstanceId((current) =>
        snapshot.data.instances.some((item) => item.id === current)
          ? current
          : snapshot.data.instances[0]?.id ?? current,
      );
      setSelectedRunId((current) =>
        snapshot.data.runs.some((item) => item.id === current)
          ? current
          : snapshot.data.runs[0]?.id ?? current,
      );
      if (!options.silent) setLoading(false);
    },
    [apiBaseUrl],
  );

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
    if (!latestEvent || invalidationsForJournalEvent(latestEvent).length === 0) return;
    void refresh({ silent: true });
  }, [latestEvent, refresh]);

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

  // Live-mode fail-closed: if the dashboard is in live mode and ANY critical endpoint returns
  // a fixture, surface a blocking disconnected state instead of pretending the operator can use
  // fake data. The fixture/fallback path is only acceptable when AGENTX_API_ALLOW_FIXTURES=1.
  const disconnected = !data || (liveMode && sourceMode !== "api");

  const safeData: DashboardData = data ?? {
    health: { status: "disconnected", service: "agentx-api", checked_at: new Date().toISOString() },
    overview: {
      system_state: "disconnected",
      active_instances: 0,
      active_runs: 0,
      parked_runs: 0,
      approvals_waiting: 0,
      manual_queue_depth: 0,
      ledger_events_today: 0,
      automation_coverage: 0,
      monthly_net: 0,
      gateway_health: "unknown",
      ring_mix: {},
      last_commit_at: new Date().toISOString(),
    },
    instances: [],
    runs: [],
    mandateTypes: [],
    journal: [],
    capabilities: [],
    evalCases: [],
    approvals: [],
    manualQueue: [],
    coreGaps: [],
  };

  const selectedInstance =
    instanceDetails[selectedInstanceId] ??
    safeData.instances.find((instance) => instance.id === selectedInstanceId) ??
    safeData.instances[0];

  const selectedRun =
    runDetails[selectedRunId] ??
    safeData.runs.find((run) => run.id === selectedRunId) ??
    safeData.runs[0];

  const selectInstance = useCallback(
    async (instanceId: string) => {
      setSelectedInstanceId(instanceId);
      setActiveView("instance");
      const result = await fetchInstance(instanceId, { baseUrl: apiBaseUrl });
      setInstanceDetails((current) => ({ ...current, [instanceId]: result.data }));
    },
    [apiBaseUrl],
  );

  const selectRun = useCallback(
    async (runId: string) => {
      setSelectedRunId(runId);
      setActiveView("run");
      const result = await fetchRun(runId, { baseUrl: apiBaseUrl });
      setRunDetails((current) => ({ ...current, [runId]: result.data }));
    },
    [apiBaseUrl],
  );

  const postCommand = useCallback(
    async (path: string, payload: CommandResult | Record<string, unknown>): Promise<CommandResult> => {
      if (!operatorToken) {
        return { supported: false, message: "Set AGENTX_OPERATOR_TOKEN in the dashboard to enable writes." };
      }
      try {
        const response = await fetch(`${apiBaseUrl}${path}`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${operatorToken}`,
          },
          body: JSON.stringify(payload),
        });
        const body = await response.json();
        if (!response.ok) {
          const message = typeof body?.detail === "string" ? body.detail : response.statusText;
          return { supported: false, message };
        }
        return {
          supported: true,
          status: body.status ?? body.decision ?? "accepted",
          message: body.message,
          work_id: body.work_id,
          work_enqueued: body.work_enqueued,
        };
      } catch (error) {
        return {
          supported: false,
          message: error instanceof Error ? error.message : "Network error",
        };
      }
    },
    [apiBaseUrl, operatorToken],
  );

  const recordCommand = useCallback(
    (label: string, result: CommandResult) => {
      setCommandResult(result);
      const status = result.status ?? result.decision ?? (result.supported ? "accepted" : "failed");
      const message =
        result.message
        ?? result.receipt
        ?? result.gap?.detail
        ?? (result.supported ? "Command accepted." : "Command failed.");
      const tone: ToastTone = result.supported ? "good" : result.gap ? "warn" : "hot";
      const timestamp = new Date().toISOString();
      setRecentCommands((current) => [
        {
          id: `${label}:${timestamp}`,
          label,
          message,
          status,
          timestamp,
          tone,
        },
        ...current,
      ].slice(0, 5));
      pushToast({
        key: result.work_id ? `${label}:${result.work_id}` : `${label}:${status}:${message}`,
        title: label,
        message: `${status} — ${message}`,
        tone,
      });
    },
    [pushToast],
  );

  const approve = useCallback(
    async (card: ApprovalCard) => {
      setCommandResult(undefined);
      const result = await postCommand("/commands/approve", {
        instance_id: card.instance_id,
        run_id: card.run_id,
        actor: "dashboard/operator",
      });
      recordCommand("approve", result);
      await refresh({ silent: true });
    },
    [postCommand, recordCommand, refresh],
  );

  const reject = useCallback(
    async (card: ApprovalCard) => {
      setCommandResult(undefined);
      const result = await postCommand("/commands/reject", {
        instance_id: card.instance_id,
        run_id: card.run_id,
        actor: "dashboard/operator",
      });
      recordCommand("reject", result);
      await refresh({ silent: true });
    },
    [postCommand, recordCommand, refresh],
  );

  const setRing = useCallback(
    async (instanceId: string, ring: string) => {
      setCommandResult(undefined);
      const result = await postCommand("/commands/set-ring", {
        instance_id: instanceId,
        ring,
        actor: "dashboard/operator",
      });
      recordCommand(`set-ring ${ring}`, result);
      if (result.supported) {
        setInstanceDetails((current) => {
          const detail = current[instanceId];
          return detail ? { ...current, [instanceId]: { ...detail, ring } } : current;
        });
      }
      await refresh({ silent: true });
    },
    [postCommand, recordCommand, refresh],
  );

  const handleInstantiate = useCallback(
    (result: CommandResult) => {
      recordCommand("instantiate", result);
    },
    [recordCommand],
  );

  const handleTriggerRun = useCallback(
    (result: CommandResult) => {
      recordCommand("trigger-run", result);
    },
    [recordCommand],
  );

  if (disconnected) {
    return (
      <main className="operator-shell disconnected">
        <div className="atmosphere" />
        <aside className="nav-rail" aria-label="Dashboard views">
          <div className="brand-mark">
            <Command size={24} />
            <span>Agent-X</span>
          </div>
          <p className="disconnected-message">
            API unreachable at <code>{apiBaseUrl}</code>. The dashboard is in live mode and
            refuses to display fake data. Set <code>AGENTX_API_ALLOW_FIXTURES=1</code> on the
            API to fall back to fixtures while debugging, or check <code>MONGODB_URI</code>.
          </p>
          <button className="command-button primary" onClick={() => void refresh()} type="button">
            <RefreshCw size={16} /> Retry
          </button>
        </aside>
      </main>
    );
  }

  const content = (() => {
    switch (activeView) {
      case "approvals":
        return (
          <ApprovalInbox
            data={safeData}
            commandResult={commandResult}
            operatorToken={operatorToken}
            apiBaseUrl={apiBaseUrl}
            onApprove={approve}
            onReject={reject}
            onRefresh={() => void refresh()}
          />
        );
      case "catalog":
        return (
          <CatalogCreate
            data={safeData}
            operatorToken={operatorToken}
            apiBaseUrl={apiBaseUrl}
            commandResult={commandResult}
            onCommandResult={handleInstantiate}
            onRefresh={() => void refresh()}
          />
        );
      case "instance":
        return (
          <InstanceFile
            commandResult={commandResult}
            data={safeData}
            operatorToken={operatorToken}
            apiBaseUrl={apiBaseUrl}
            onSelectInstance={selectInstance}
            onSelectRun={selectRun}
            onSetRing={setRing}
            onCommandResult={handleTriggerRun}
            onRefresh={() => void refresh()}
            selectedInstance={selectedInstance as InstanceSummary}
          />
        );
      case "run":
        return <RunDetail data={safeData} onSelectRun={selectRun} selectedRun={selectedRun as RunSummary} />;
      case "capabilities":
        return <CapabilityRegistry data={safeData} />;
      case "ledger":
        return <LedgerView data={safeData} />;
      case "foundry":
        return <FoundryView data={safeData} />;
      case "floor":
      default:
        return <FloorView data={safeData} onSelectInstance={selectInstance} onSelectRun={selectRun} />;
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
            .filter((item) => item.id !== "foundry" || safeData.evalCases.length > 0)
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
        <div className="token-panel">
          <label htmlFor="operator-token" className="eyebrow">
            Operator Token
          </label>
          <input
            id="operator-token"
            type="password"
            placeholder="AGENTX_OPERATOR_TOKEN"
            defaultValue={operatorToken}
            onChange={(event) => {
              const next = event.target.value.trim();
              setOperatorToken(next);
              setOperatorTokenState(next);
            }}
          />
          <p className="token-help">
            Stored locally. Without it, every command button is disabled. Match the value the
            API was started with.
          </p>
          <label htmlFor="api-base-url" className="eyebrow">
            API base URL
          </label>
          <input
            id="api-base-url"
            type="url"
            defaultValue={apiBaseUrl}
            onChange={(event) => setApiBaseUrl(event.target.value.trim() || apiBaseUrl)}
          />
        </div>
      </aside>

      <section className="dashboard-stage">
        <header className="top-bar">
          <div>
            <p className="eyebrow">operator console</p>
            <h1>Business OS Control Room</h1>
          </div>
          <div className="top-actions">
            <StatusPill label={safeData.health.status} tone={safeData.health.status === "ok" ? "good" : "warn"} />
            <SourceBadge source={sourceMode} />
            <span className="clock">{clock}</span>
            <button className="icon-button" onClick={() => void refresh()} title="Refresh" type="button">
              {loading ? <Loader2 className="spin" size={17} /> : <RefreshCw size={17} />}
            </button>
          </div>
        </header>

        {content}
      </section>

      <ToastStack onDismiss={dismissToast} toasts={toasts} />

      <div className="bottom-ledger">
        <div className="ledger-summary">
          <GitBranchPlus size={15} />
          <span>{safeData.overview.last_commit_at}</span>
          <strong>{safeData.journal[0]?.title}</strong>
          <span className={classNames("journal-stream-status", journalConnected && "connected")}>
            {journalConnected ? "SSE live" : "8s fallback"}
          </span>
        </div>
        <div className="recent-command-log" aria-label="Recent manager commands">
          {recentCommands.length === 0 ? (
            <span>No manager commands in this session.</span>
          ) : recentCommands.map((command) => (
            <span className={classNames("recent-command", `toast-${command.tone}`)} key={command.id}>
              <time dateTime={command.timestamp}>
                {new Date(command.timestamp).toLocaleTimeString("en-IN", { hour12: false })}
              </time>
              <strong>{command.label}</strong>
              <span>{command.status}</span>
            </span>
          ))}
        </div>
      </div>
    </main>
  );
}
