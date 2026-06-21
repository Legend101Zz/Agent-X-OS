"use client";

/**
 * Actions tab — the per-instance syscall journal.
 *
 * Reads ``GET /journal?instance_id={id}`` and filters to the two syscall
 * kinds (``syscall_attempted`` + ``syscall_settled``) per the C4 spec
 * (BLUEPRINT §6 tab 4). Renders the filtered list as a Timeline so the
 * operator can read the intent → effect rhythm at a glance.
 *
 * Each row shows:
 *   - kind pill (Attempted = info, Settled = good)
 *   - syscall name + the kernel's args payload (via JsonViewer primitive)
 *   - actor / run link / timestamp
 *
 * Graceful disable:
 *   - Empty filter result renders an EmptyState ("no syscalls journaled")
 *     with a hint pointing at the activity tab. The two tab surfaces
 *     overlap deliberately — the activity tab is the full stream, the
 *     actions tab is the syscall-scoped lens.
 *   - If the fetch errors, we render an ErrorState with the reason.
 *   - If the user is on a fresh instance with no journal events at all,
 *     the kernel returns 200 with ``{"events": []}`` and we treat that
 *     as a normal empty state — not a failure.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, History } from "lucide-react";

import {
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  Row,
  Skeleton,
  Stack,
  StatusPill,
} from "../../ui";
import { JsonViewer } from "../../ui/json";
import { Timeline, type TimelineEntry } from "../../ui/timeline";
import { fetchJournal } from "../../../lib/api";
import { formatTime, shortId, truncate } from "../../../lib/format";
import { useOperator } from "../../../providers/operator-provider";
import {
  filterSyscallEvents,
  journalActionTone,
  truncateArgs,
} from "../../../lib/inspector-c4";
import type { ApiResult, JournalEvent, RunSummary } from "../../../lib/types";

interface ActionsTabProps {
  instanceId: string;
  /** Optional run list — an event with matching run_id gets a trace badge. */
  runs?: RunSummary[];
  initialEvents?: JournalEvent[];
  loading?: boolean;
}

const LIMIT = 200;

type LoadState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; events: JournalEvent[]; source: "live" | "fixture" | "empty" }
  | { kind: "error"; message: string };

export function ActionsTab({ instanceId, runs, initialEvents, loading }: ActionsTabProps) {
  const { baseUrl, token } = useOperator();
  const [state, setState] = useState<LoadState>(() => {
    if (initialEvents && initialEvents.length > 0) {
      return { kind: "ready", events: initialEvents, source: "fixture" };
    }
    return { kind: "idle" };
  });

  useEffect(() => {
    if (instanceId === "") {
      setState({ kind: "ready", events: [], source: "empty" });
      return;
    }
    // If the parent already provided a non-empty initial list, skip the
    // network call (mirrors the Activity tab's behaviour).
    if (initialEvents && initialEvents.length > 0) {
      setState({ kind: "ready", events: initialEvents, source: "fixture" });
      return;
    }
    let cancelled = false;
    setState({ kind: "loading" });
    fetchJournal(
      { instance_id: instanceId, limit: LIMIT },
      {
        baseUrl: baseUrl || undefined,
        ...(token ? { init: { headers: { Authorization: `Bearer ${token}` } } } : {}),
      },
    )
      .then((result: ApiResult<JournalEvent[]>) => {
        if (cancelled) return;
        if (result.error && result.data.length === 0) {
          setState({
            kind: "error",
            message: result.error,
          });
          return;
        }
        setState({
          kind: "ready",
          events: Array.isArray(result.data) ? result.data : [],
          source: result.source === "api" ? "live" : "fixture",
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setState({
          kind: "error",
          message: err instanceof Error ? err.message : String(err),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [instanceId, baseUrl, token, initialEvents]);

  const runsById = useMemo(() => {
    const map = new Map<string, RunSummary>();
    for (const r of runs ?? []) map.set(r.id, r);
    return map;
  }, [runs]);

  // Spec: filter to the two syscall kinds (attempted + settled). Pure
  // helper, exercised by the inspector-c4 unit tests.
  const syscallEvents = useMemo(() => {
    if (state.kind !== "ready") return [];
    return filterSyscallEvents(state.events);
  }, [state]);

  if (loading || state.kind === "idle" || state.kind === "loading") {
    return (
      <Card>
        <CardHeader
          eyebrow="Actions"
          title="Syscall journal"
          subtitle="Attempted + settled syscalls for this instance."
        />
        <CardBody>
          <Stack gap={2}>
            <Skeleton width="100%" height={48} />
            <Skeleton width="100%" height={48} />
          </Stack>
        </CardBody>
      </Card>
    );
  }

  if (state.kind === "error") {
    return (
      <Card>
        <CardBody>
          <ErrorState
            title="Couldn't load journal"
            detail={state.message}
          />
        </CardBody>
      </Card>
    );
  }

  if (syscallEvents.length === 0) {
    return (
      <Card>
        <CardHeader
          eyebrow="Actions"
          title="Syscall journal"
          subtitle="Attempted + settled syscalls for this instance."
          action={<StatusPill tone="muted">0 syscalls</StatusPill>}
        />
        <CardBody>
          <EmptyState
            icon={<History size={20} />}
            title="No syscalls journaled for this instance"
            detail={
              state.events.length === 0
                ? "This instance hasn't emitted any journal events yet. Once a run starts, its intent and effect will appear here."
                : `Journaled ${state.events.length} event${
                    state.events.length === 1 ? "" : "s"
                  } for this instance, but none are syscall attempts or settlements. See the Activity tab for the full stream.`
            }
            action={
              <Link href={`/instances/${instanceId}?tab=activity`} className="ax-btn ax-btn--secondary">
                Open Activity <ArrowRight size={12} />
              </Link>
            }
          />
        </CardBody>
      </Card>
    );
  }

  // Build the Timeline entries. Newest at the bottom matches the activity
  // tab; the spec doesn't mandate either ordering.
  const entries: TimelineEntry[] = syscallEvents.map((ev) => {
    const run = ev.run_id ? runsById.get(ev.run_id) : undefined;
    const syscall = (ev as unknown as { syscall?: string }).syscall ?? "syscall";
    const args = (ev as unknown as { args?: unknown }).args;
    const fulfilledBy = (ev as unknown as { fulfilled_by?: string }).fulfilled_by;
    const titleText = `${syscall}${fulfilledBy ? ` → ${fulfilledBy}` : ""}`;
    return {
      id: ev.id,
      ts: ev.at ? formatTime(ev.at) : undefined,
      title: (
        <span className="inspector-actions__title">
          <span className="mono">{titleText}</span>
          <StatusPill tone={journalActionTone(ev.kind) as TimelineEntry["tone"]} size="sm">
            {ev.kind === "syscall_attempted" ? "Attempted" : "Settled"}
          </StatusPill>
          {run ? (
            <StatusPill tone="muted" size="sm" title={`run ${run.id}`}>
              {run.title}
            </StatusPill>
          ) : null}
        </span>
      ),
      detail:
        typeof args === "string"
          ? truncate(args, 240)
          : truncateArgs(args, 200),
      tone: journalActionTone(ev.kind) as TimelineEntry["tone"],
      actor: typeof ev.actor === "string" ? ev.actor : undefined,
      meta: ev.run_id ? (
        <span className="dim mono">
          seq {shortId(ev.run_id)}
          {ev.id ? ` · ${shortId(ev.id)}` : ""}
        </span>
      ) : ev.id ? (
        <span className="dim mono">{shortId(ev.id)}</span>
      ) : undefined,
    };
  });

  return (
    <Stack gap={4}>
      <Card>
        <CardHeader
          eyebrow="Actions"
          title="Syscall journal"
          subtitle="Attempted + settled syscalls — the kernel's intent → effect rhythm."
          action={
            <Row gap={1}>
              <StatusPill tone="info">
                {syscallEvents.filter((e) => e.kind === "syscall_attempted").length} attempted
              </StatusPill>
              <StatusPill tone="good">
                {syscallEvents.filter((e) => e.kind === "syscall_settled").length} settled
              </StatusPill>
            </Row>
          }
        />
        <CardBody>
          <Timeline
            entries={entries}
            empty={
              <EmptyState
                icon={<History size={20} />}
                title="No syscalls to show"
                detail="Filter excluded everything in the journal."
              />
            }
          />
        </CardBody>
      </Card>
      <Card>
        <CardHeader
          eyebrow="Raw"
          title="Filtered journal payload"
          subtitle="The same events as the timeline above, in JSON, for copy-pasting into a support ticket."
        />
        <CardBody>
          <JsonViewer value={syscallEvents} title="syscall events" />
        </CardBody>
      </Card>
    </Stack>
  );
}
