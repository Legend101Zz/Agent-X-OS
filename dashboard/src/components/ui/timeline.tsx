"use client";

import type { ReactNode } from "react";
import { cx } from "../../lib/cx";

export interface TimelineEntry {
  id?: string;
  ts?: string;
  title: ReactNode;
  detail?: ReactNode;
  tone?: "good" | "warn" | "hot" | "info" | "neutral";
  actor?: ReactNode;
  meta?: ReactNode;
}

export function Timeline({ entries, className, empty }: { entries: TimelineEntry[]; className?: string; empty?: ReactNode }) {
  if (entries.length === 0 && empty) return <div className={cx("ax-timeline-empty", className)}>{empty}</div>;
  return (
    <ol className={cx("ax-timeline", className)}>
      {entries.map((entry, index) => (
        <li key={entry.id ?? index} className="ax-timeline__item">
          <span className="ax-timeline__dot" data-tone={entry.tone ?? "neutral"} aria-hidden />
          <div className="ax-timeline__head">
            <span className="ax-timeline__title">{entry.title}</span>
            {entry.ts ? <span className="ax-timeline__ts mono">{entry.ts}</span> : null}
            {entry.actor ? (
              <span className="ax-timeline__ts mono" title="actor">
                · {entry.actor}
              </span>
            ) : null}
          </div>
          {entry.detail ? <div className="ax-timeline__detail">{entry.detail}</div> : null}
          {entry.meta ? <div className="ax-timeline__meta">{entry.meta}</div> : null}
        </li>
      ))}
    </ol>
  );
}