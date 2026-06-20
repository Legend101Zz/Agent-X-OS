"use client";

import type { ReactNode } from "react";
import { cx } from "../../lib/cx";

export interface EmptyStateProps {
  title?: string;
  detail?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({
  title = "Nothing here yet",
  detail,
  icon,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div className={cx("ax-state", className)}>
      {icon ? <div className="ax-state__icon">{icon}</div> : null}
      <div className="ax-state__title">{title}</div>
      {detail ? <div className="ax-state__detail">{detail}</div> : null}
      {action}
    </div>
  );
}

export interface ErrorStateProps {
  title?: string;
  detail?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function ErrorState({
  title = "Something went wrong",
  detail,
  action,
  className,
}: ErrorStateProps) {
  return (
    <div className={cx("ax-state ax-state--error", className)}>
      <div className="ax-state__title">{title}</div>
      {detail ? <div className="ax-state__detail">{detail}</div> : null}
      {action}
    </div>
  );
}

export interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  block?: boolean;
  className?: string;
}

export function Skeleton({ width, height, block, className }: SkeletonProps) {
  return (
    <span
      className={cx("ax-skel", block && "ax-skel--block", className)}
      style={{
        width: typeof width === "number" ? `${width}px` : width ?? "100%",
        height: typeof height === "number" ? `${height}px` : height,
      }}
    />
  );
}