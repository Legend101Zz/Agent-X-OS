"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { DEFAULT_API_BASE_URL } from "./api";

export type DashboardSlice =
  | "overview"
  | "instances"
  | "runs"
  | "journal"
  | "evalCases"
  | "approvals";

export interface JournalStreamEvent {
  event_id: string;
  kind: string;
  seq: number;
  ts?: string;
  instance_id?: string;
  run_id?: string | null;
  actor?: string;
  [key: string]: unknown;
}

export function parseJournalFrame(data: string): JournalStreamEvent {
  const parsed: unknown = JSON.parse(data);
  if (
    typeof parsed !== "object"
    || parsed === null
    || Array.isArray(parsed)
    || typeof (parsed as Record<string, unknown>).event_id !== "string"
    || typeof (parsed as Record<string, unknown>).kind !== "string"
    || typeof (parsed as Record<string, unknown>).seq !== "number"
  ) {
    throw new Error("Invalid journal SSE frame");
  }
  return parsed as JournalStreamEvent;
}

export function invalidationsForJournalEvent(event: JournalStreamEvent): DashboardSlice[] {
  if (event.kind === "run_settled") {
    return ["overview", "instances", "runs", "journal", "evalCases"];
  }
  if (event.kind === "run_parked") {
    return ["overview", "runs", "journal", "approvals"];
  }
  return ["overview", "journal"];
}

export function useJournalStream({
  baseUrl = DEFAULT_API_BASE_URL,
}: {
  baseUrl?: string;
} = {}) {
  const [events, setEvents] = useState<JournalStreamEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const seenEventIds = useRef(new Set<string>());

  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    seenEventIds.current.clear();
    setEvents([]);
    setConnected(false);

    // `baseUrl` is empty on first render (before the operator settings hydrate
    // from localStorage). Fall back to the default backend so `new URL` never
    // throws "Invalid base URL".
    const resolvedBase = baseUrl || DEFAULT_API_BASE_URL;
    const streamUrl = new URL(
      "/events",
      resolvedBase.endsWith("/") ? resolvedBase : `${resolvedBase}/`,
    );
    const source = new EventSource(streamUrl);
    const handleJournal = (rawEvent: Event) => {
      if (!(rawEvent instanceof MessageEvent)) return;
      try {
        const event = parseJournalFrame(String(rawEvent.data));
        if (seenEventIds.current.has(event.event_id)) return;
        seenEventIds.current.add(event.event_id);
        setEvents((current) => [...current.slice(-49), event]);
      } catch {
        // Ignore malformed frames; polling remains the dashboard's fallback floor.
      }
    };

    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.addEventListener("journal", handleJournal);

    return () => {
      source.removeEventListener("journal", handleJournal);
      source.close();
      setConnected(false);
    };
  }, [baseUrl]);

  const latestEvent = events.at(-1);
  return useMemo(
    () => ({ connected, events, latestEvent }),
    [connected, events, latestEvent],
  );
}
