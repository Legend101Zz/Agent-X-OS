"use client";

/**
 * Status / Badge pills — single source of truth for visual vocabulary across
 * the dashboard. Use these everywhere instead of inline color spans.
 */
import type { ReactNode } from "react";
import { cx } from "../../lib/cx";

export type PillTone =
  | "good"
  | "warn"
  | "hot"
  | "info"
  | "accent"
  | "muted"
  | "l0"
  | "l1"
  | "l2"
  | "l3"
  | "l4"
  | "neutral";

export interface StatusPillProps {
  tone?: PillTone;
  children: ReactNode;
  /** Optional leading dot — for live/health indicators. */
  dot?: boolean;
  /** Optional pulse animation on the leading dot — for "just updated" indicators. */
  pulse?: boolean;
  size?: "sm" | "md";
  className?: string;
  title?: string;
}

export function StatusPill({
  tone = "neutral",
  children,
  dot,
  pulse,
  size = "sm",
  className,
  title,
}: StatusPillProps) {
  return (
    <span
      data-tone={tone}
      data-size={size}
      title={title}
      className={cx("ax-pill", `ax-pill--${tone}`, `ax-pill--${size}`, className)}
    >
      {dot ? <span className={cx("ax-pill__dot", pulse && "ax-pill__dot--pulse")} aria-hidden /> : null}
      <span className="ax-pill__label">{children}</span>
    </span>
  );
}

export interface BadgeProps {
  children: ReactNode;
  tone?: PillTone;
  className?: string;
}
export function Badge({ children, tone = "muted", className }: BadgeProps) {
  return (
    <span data-tone={tone} className={cx("ax-badge", `ax-badge--${tone}`, className)}>
      {children}
    </span>
  );
}

/** Pre-bound ring pills (L0..L4) for the most-used entity attribute. */
export function RingPill({ ring, className }: { ring: string | null | undefined; className?: string }) {
  if (!ring) return <StatusPill tone="neutral">—</StatusPill>;
  const tone = (() => {
    const r = ring.toUpperCase();
    if (r === "L0") return "l0";
    if (r === "L1") return "l1";
    if (r === "L2") return "l2";
    if (r === "L3") return "l3";
    if (r === "L4") return "l4";
    return "neutral";
  })();
  return (
    <StatusPill tone={tone} className={className} title={`Ring ${ring.toUpperCase()}`}>
      {ring.toUpperCase()}
    </StatusPill>
  );
}