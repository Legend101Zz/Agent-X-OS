"use client";

/**
 * TopBar — env chip, live SSE status, refresh, operator token indicator.
 * Reads the operator + journal stream context.
 */
import { useEffect, useState } from "react";
import { Activity, RefreshCw, Settings } from "lucide-react";
import { useJournalStream } from "../../lib/events";
import { useOperator } from "../../providers/operator-provider";
import { AsyncButton, Button, StatusPill } from "../ui";
import { cx } from "../../lib/cx";
import { OperatorSettingsModal } from "./operator-settings";

export interface TopBarProps {
  title: string;
  crumbs?: Array<{ href?: string; label: string }>;
  /** Optional refresh callback (called from the refresh button). */
  onRefresh?: () => void;
  /** Show a "refreshing" spinner. */
  refreshing?: boolean;
}

export function TopBar({ title, crumbs, onRefresh, refreshing }: TopBarProps) {
  const { baseUrl, isLive } = useOperator();
  const { connected } = useJournalStream({ baseUrl: baseUrl || undefined });
  const [openSettings, setOpenSettings] = useState(false);
  const [mounted, setMounted] = useState(false);

  // SSR-safe indicator (don't render SSE state until after hydration).
  useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <header className="app-topbar">
      <div className="app-topbar__crumbs">
        {crumbs?.map((crumb, index) => (
          <span key={`${crumb.label}-${index}`} className="ax-row" style={{ gap: 4 }}>
            {index > 0 ? <span className="app-topbar__crumb-sep">/</span> : null}
            <span className={cx(index === crumbs.length - 1 && "muted")}>{crumb.label}</span>
          </span>
        )) ?? <span className="app-topbar__title">{title}</span>}
      </div>
      <div className="app-topbar__title" style={{ marginLeft: crumbs ? 0 : undefined }}>{title}</div>

      <div className="app-topbar__right">
        <span className="app-topbar__env mono" title={baseUrl || "no API base URL set"}>
          {baseUrl ? new URL(baseUrl).host : "no-api"}
        </span>
        {mounted ? (
          <StatusPill tone={connected ? "good" : "muted"} dot pulse={connected}>
            {connected ? "LIVE" : "OFFLINE"}
          </StatusPill>
        ) : (
          <StatusPill tone="muted" dot>—</StatusPill>
        )}
        <AsyncButton
          variant="ghost"
          size="sm"
          icon={<RefreshCw size={14} />}
          onClick={() => onRefresh?.()}
          disabled={refreshing}
          loading={refreshing}
        >
          Refresh
        </AsyncButton>
        <Button
          variant={isLive ? "success" : "secondary"}
          size="sm"
          icon={<Settings size={14} />}
          onClick={() => setOpenSettings(true)}
          title={isLive ? "Operator connected" : "Connect to the API"}
        >
          {isLive ? <Activity size={12} /> : null}
          {isLive ? "Connected" : "Connect"}
        </Button>
      </div>

      <OperatorSettingsModal open={openSettings} onClose={() => setOpenSettings(false)} />
    </header>
  );
}