import type { CSSProperties, PropsWithChildren, ReactNode } from "react";
import type { ApiSource, CoreGap } from "@/lib/types";

export type ViewId =
  | "floor"
  | "approvals"
  | "catalog"
  | "instance"
  | "run"
  | "capabilities"
  | "ledger"
  | "foundry";

type StaggerStyle = CSSProperties & { "--i"?: number };

export function stagger(index: number): StaggerStyle {
  return { "--i": index };
}

export function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

export function formatClock(value: string) {
  return new Intl.DateTimeFormat("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Kolkata",
  }).format(new Date(value));
}

export function classNames(...items: Array<string | false | null | undefined>) {
  return items.filter(Boolean).join(" ");
}

export function Panel({
  title,
  eyebrow,
  children,
  action,
  className,
}: PropsWithChildren<{
  title: string;
  eyebrow?: string;
  action?: ReactNode;
  className?: string;
}>) {
  return (
    <section className={classNames("panel", className)}>
      <div className="panel-head">
        <div>
          {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
          <h2>{title}</h2>
        </div>
        {action ? <div className="panel-action">{action}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function StatusPill({
  label,
  tone = "neutral",
}: {
  label: string;
  tone?: "neutral" | "good" | "warn" | "hot";
}) {
  return <span className={classNames("status-pill", `tone-${tone}`)}>{label}</span>;
}

export function SourceBadge({ source }: { source: ApiSource | "mixed" | "loading" }) {
  const label =
    source === "api"
      ? "live api"
      : source === "fixture"
        ? "fixture"
        : source === "loading"
          ? "syncing"
          : "mixed";

  return <span className={classNames("source-badge", `source-${source}`)}>{label}</span>;
}

export function MetricTile({
  label,
  value,
  detail,
  tone = "neutral",
}: {
  label: string;
  value: string;
  detail?: string;
  tone?: "neutral" | "good" | "warn" | "hot";
}) {
  return (
    <div className={classNames("metric-tile", `metric-${tone}`)}>
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </div>
  );
}

export function ProgressBar({ value }: { value: number }) {
  return (
    <div className="progress-rail" aria-label={`${value}% complete`}>
      <span style={{ width: `${Math.min(Math.max(value, 0), 100)}%` }} />
    </div>
  );
}

export function GapNotice({ gap }: { gap: CoreGap }) {
  return (
    <div className="gap-notice" role="status">
      <strong>{gap.title}</strong>
      <span>{gap.detail}</span>
    </div>
  );
}

export function EmptyState({ label }: { label: string }) {
  return <div className="empty-state">{label}</div>;
}
