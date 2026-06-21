"use client";

/**
 * Live Activity tab — the BLUEPRINT §5 trace "oscilloscope" for an instance.
 *
 * Renders the SSE journal stream (`/events`) filtered to this instance,
 * showing only the events that touch this mandate. Auto-scrolls when new
 * events arrive; pauses on user scroll (to keep the user in control).
 *
 * The page header above this tab renders the same stream in a compact
 * ribbon; this tab is the deep, scrollable, per-run timeline.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Pause, Play, Radio, Trash2 } from "lucide-react";

import { Card, CardBody, CardHeader, EmptyState, Row, Skeleton, Stack, StatusPill } from "../../ui";
import { Timeline, type TimelineEntry } from "../../ui/timeline";
import { journalKindTone, formatTime, formatRelative, truncate } from "../../../lib/format";
import { useJournalStream, type JournalStreamEvent } from "../../../lib/events";
import { useOperator } from "../../../providers/operator-provider";
import type { RunSummary } from "../../../lib/types";

interface ActivityTabProps {
  instanceId: string;
  /** Initial events already loaded by the parent (so we don't double-fetch on mount). */
  initialEvents?: JournalStreamEvent[];
  /** Runs to cross-reference; an event with matching run_id gets a "trace" badge. */
  runs?: RunSummary[];
  loading?: boolean;
}

const MAX_EVENTS = 200;

export function ActivityTab({ instanceId, initialEvents = [], runs = [], loading }: ActivityTabProps) {
  const { baseUrl } = useOperator();
  const { events: liveEvents, connected } = useJournalStream({ baseUrl: baseUrl || undefined });
  const [paused, setPaused] = useState(false);
  const [clearedAt, setClearedAt] = useState<number | null>(null);
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const stickToBottomRef = useRef<boolean>(true);

  // Merge live + initial into a single deduped timeline (newest at bottom).
  const filtered = useMemo(() => {
    const out: JournalStreamEvent[] = [...initialEvents];
    for (const ev of liveEvents) {
      if (out.find((x) => x.event_id === ev.event_id)) continue;
      out.push(ev);
    }
    return out
      .filter((ev) => !ev.instance_id || ev.instance_id === instanceId)
      .filter((ev) => clearedAt === null || new Date(ev.ts ?? 0).getTime() >= clearedAt)
      .slice(-MAX_EVENTS);
  }, [initialEvents, liveEvents, instanceId, clearedAt]);

  // Track whether the user has scrolled away; only auto-scroll when pinned to bottom.
  useEffect(() => {
    const node = scrollerRef.current;
    if (!node) return;
    const handleScroll = () => {
      const distance = node.scrollHeight - node.scrollTop - node.clientHeight;
      stickToBottomRef.current = distance < 24;
    };
    node.addEventListener("scroll", handleScroll, { passive: true });
    return () => node.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    if (paused) return;
    if (!stickToBottomRef.current) return;
    const node = scrollerRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [filtered, paused]);

  const runsById = useMemo(() => {
    const map = new Map<string, RunSummary>();
    for (const r of runs) map.set(r.id, r);
    return map;
  }, [runs]);

  const entries: TimelineEntry[] = filtered.map((ev) => {
    const run = ev.run_id ? runsById.get(String(ev.run_id)) : undefined;
    const titleText = ev.title || (typeof ev.summary === "string" ? ev.summary : ev.kind);
    const detailText = typeof ev.detail === "string"
      ? ev.detail
      : typeof ev.reason === "string"
        ? ev.reason
        : "";
    return {
      id: ev.event_id,
      ts: ev.ts ? formatTime(ev.ts) : undefined,
      title: (
        <span className="inspector-activity__title">
          {String(titleText)}
          {run ? (
            <StatusPill tone="muted" size="sm" title={`run ${run.id}`}>
              {run.title}
            </StatusPill>
          ) : null}
        </span>
      ),
      detail: truncate(String(detailText), 240),
      tone: journalKindTone(ev.kind) as TimelineEntry["tone"],
      actor: typeof ev.actor === "string" ? ev.actor : undefined,
      meta: ev.seq !== undefined ? <span className="dim mono">seq {ev.seq}</span> : undefined,
    };
  });

  return (
    <Card>
      <CardHeader
        eyebrow="Live"
        title="Activity stream"
        subtitle={
          connected
            ? "Subscribed to /events — new events appear at the bottom."
            : "SSE disconnected — showing cached events. Reconnect from the top bar."
        }
        action={
          <Row gap={2} wrap>
            <StatusPill tone={connected ? "good" : "muted"} dot pulse={connected}>
              <Radio size={11} /> {connected ? "LIVE" : "OFFLINE"}
            </StatusPill>
            <button
              type="button"
              className="ax-btn ax-btn--ghost ax-btn--sm"
              onClick={() => setPaused((p) => !p)}
              title={paused ? "Resume auto-scroll" : "Pause auto-scroll"}
            >
              {paused ? <Play size={12} /> : <Pause size={12} />}
              {paused ? "Resume" : "Pause"}
            </button>
            <button
              type="button"
              className="ax-btn ax-btn--ghost ax-btn--sm"
              onClick={() => setClearedAt(Date.now())}
              title="Hide events older than now"
              disabled={filtered.length === 0}
            >
              <Trash2 size={12} /> Clear
            </button>
          </Row>
        }
      />
      <CardBody>
        {loading ? (
          <Stack gap={2}>
            <Skeleton width="80%" />
            <Skeleton width="60%" />
            <Skeleton width="70%" />
          </Stack>
        ) : entries.length === 0 ? (
          <EmptyState
            title="No activity yet"
            detail={
              connected
                ? `Subscribed to /events for ${instanceId}. As the instance runs, events stream here in real time.`
                : "SSE is disconnected. When the API is reachable, events will appear here as the instance runs."
            }
            icon={<Radio size={20} />}
          />
        ) : (
          <div className="inspector-activity" ref={scrollerRef}>
            <Timeline entries={entries} />
            <div className="dim" style={{ fontSize: 12, marginTop: 8 }}>
              {filtered.length} event{filtered.length === 1 ? "" : "s"} ·{" "}
              {filtered.length > 0 && filtered[filtered.length - 1].ts
                ? `last ${formatRelative(filtered[filtered.length - 1].ts as string)}`
                : "no timestamps"}
              {paused ? " · auto-scroll paused" : " · auto-scroll on"}
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
