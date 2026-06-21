"use client";

import { cx } from "../../lib/cx";

export interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  tone?: "good" | "warn" | "hot" | "info" | "accent" | "muted";
  className?: string;
  /** Optional accessible label. */
  ariaLabel?: string;
}

const TONE_COLOR: Record<NonNullable<SparklineProps["tone"]>, string> = {
  good: "var(--success)",
  warn: "var(--warning)",
  hot: "var(--destructive)",
  info: "var(--info)",
  accent: "var(--accent)",
  muted: "var(--foreground-dim)",
};

export function Sparkline({
  values,
  width = 120,
  height = 32,
  tone = "accent",
  className,
  ariaLabel,
}: SparklineProps) {
  if (values.length === 0) {
    return <div className={cx("ax-sparkline", className)} style={{ width, height }} aria-hidden />;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const stepX = width / Math.max(values.length - 1, 1);
  const points = values
    .map((v, i) => {
      const x = i * stepX;
      const y = height - ((v - min) / span) * (height - 4) - 2;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  const stroke = TONE_COLOR[tone];
  const areaPath = `M0,${height} L${points.split(" ").join(" L")} L${width},${height} Z`;
  return (
    <svg
      className={cx("ax-sparkline", className)}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={ariaLabel ?? "sparkline"}
    >
      <path d={areaPath} fill={stroke} opacity="0.14" />
      <polyline points={points} fill="none" stroke={stroke} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}