"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type PropsWithChildren,
  type ReactNode,
} from "react";
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

export type ToastTone = "good" | "warn" | "hot";

export interface ToastItem {
  id: string;
  key: string;
  title: string;
  message: string;
  tone: ToastTone;
  createdAt: number;
  durationMs: number;
}

export interface ToastInput {
  key?: string;
  title: string;
  message: string;
  tone?: ToastTone;
  durationMs?: number;
}

export function upsertToast(
  current: ToastItem[],
  next: ToastItem,
  limit = 5,
): ToastItem[] {
  return [...current.filter((toast) => toast.key !== next.key), next].slice(-limit);
}

export function useToasts() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());

  const dismissToast = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
    const timer = timers.current.get(id);
    if (timer) clearTimeout(timer);
    timers.current.delete(id);
  }, []);

  const pushToast = useCallback(
    (input: ToastInput) => {
      const createdAt = Date.now();
      const key = input.key ?? `${input.title}:${input.message}`;
      const id = `${key}:${createdAt}`;
      const toast: ToastItem = {
        id,
        key,
        title: input.title,
        message: input.message,
        tone: input.tone ?? "warn",
        createdAt,
        durationMs: input.durationMs ?? 5000,
      };
      setToasts((current) => upsertToast(current, toast));
      for (const existing of toasts) {
        if (existing.key === key) dismissToast(existing.id);
      }
      timers.current.set(id, setTimeout(() => dismissToast(id), toast.durationMs));
      return id;
    },
    [dismissToast, toasts],
  );

  useEffect(
    () => () => {
      for (const timer of timers.current.values()) clearTimeout(timer);
      timers.current.clear();
    },
    [],
  );

  return { dismissToast, pushToast, toasts };
}

export function ToastStack({
  toasts,
  onDismiss,
}: {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
}) {
  return (
    <aside className="toast-stack" aria-label="Command notifications" aria-live="polite">
      {toasts.map((toast) => (
        <button
          className={classNames("command-toast", `toast-${toast.tone}`)}
          key={toast.id}
          onClick={() => onDismiss(toast.id)}
          type="button"
        >
          <strong>{toast.title}</strong>
          <span>{toast.message}</span>
          <small>dismiss</small>
        </button>
      ))}
    </aside>
  );
}
