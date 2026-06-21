"use client";

/**
 * /runs/{id} — the per-run "trace oscilloscope" (C6).
 *
 * The §5 timeline is the centerpiece: the BLUEPRINT describes a run's
 * lifecycle as Think / Call / Claim / park / send events streamed over
 * `/events`. We render that exact stream as a `<Timeline>` (a primitive
 * from C1) with each entry coloured by `traceKindTone` (kind → tone
 * mapping in `lib/runs.ts`).
 *
 * Layout, top to bottom:
 *   1. Header       — run title, state pill, ring, link to instance
 *   2. Settlement   — status / cost / EV / progress / billing (if settled)
 *   3. Timeline     — the "oscilloscope" (CLSpec §5)
 *   4. Claimed facts— facts the run committed (subject/predicate/object +
 *                    confidence + provenance)
 *   5. Raw payload  — `<JsonViewer>` over the unprocessed GET /runs/{id}
 *                    payload, for when the projections don't surface
 *                    something the operator wants to read.
 *
 * SSE: the `runs` slice is invalidated on `run_settled` and `run_parked`;
 * we refresh on those events so a long-lived detail view reflects
 * settling without a manual reload.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import Link from "next/link";
import {
  Activity,
  ArrowLeft,
  CircleDollarSign,
  CircleSlash2,
  ExternalLink,
  GitBranch,
  ListTree,
  Sigma,
  TimerReset,
} from "lucide-react";

import { AppShell } from "../shell/app-shell";
import {
  AsyncButton,
  Card,
  CardBody,
  CardFooter,
  CardHeader,
  EmptyState,
  ErrorState,
  JsonViewer,
  Row,
  Skeleton,
  Stack,
  StatusPill,
  Timeline,
  TimelineEntry,
} from "../ui";
import { useOperator } from "../../providers/operator-provider";
import { useToast } from "../../providers/toast-provider";
import { fetchInstance, fetchRun, fetchRunRaw } from "../../lib/api";
import { useJournalStream, invalidationsForJournalEvent } from "../../lib/events";
import {
  extractClaimedFacts,
  extractSettlementSummary,
  settlementTone,
  traceToTimelineEntries,
} from "../../lib/runs";
import {
  formatCurrency,
  formatDateTime,
  formatRelative,
  runStateLabel,
  shortId,
} from "../../lib/format";
import type { InstanceSummary, RunSummary } from "../../lib/types";

interface RunDetailProps {
  runId: string;
  initialRun?: RunSummary;
  initialRaw?: unknown;
}

export function RunDetail({ runId, initialRun, initialRaw }: RunDetailProps) {
  const { baseUrl } = useOperator();
  const toast = useToast();

  const [run, setRun] = useState<RunSummary | null>(initialRun ?? null);
  const [raw, setRaw] = useState<unknown>(initialRaw ?? null);
  const [instance, setInstance] = useState<InstanceSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(!initialRun);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (mode: "initial" | "refresh") => {
      if (mode === "refresh") setRefreshing(true);
      try {
        const [runRes, rawRes] = await Promise.all([
          fetchRun(runId),
          fetchRunRaw(runId),
        ]);
        setRun(runRes.data);
        setRaw(rawRes.data);
        // Instance lookup is best-effort — degrade silently if 404.
        if (runRes.data?.instance_id) {
          try {
            const instRes = await fetchInstance(runRes.data.instance_id);
            setInstance(instRes.data);
          } catch {
            setInstance(null);
          }
        }
        setError(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
        if (mode === "refresh") {
          toast.push({ title: "Refresh failed", message, tone: "hot" });
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [runId, toast],
  );

  useEffect(() => {
    if (initialRun) return;
    void load("initial");
  }, [initialRun, load]);

  // --- SSE → refresh on settle / park ------------------------------------
  const journal = useJournalStream({ baseUrl });
  useEffect(() => {
    if (!journal.latestEvent) return;
    const slices = invalidationsForJournalEvent(journal.latestEvent);
    if (slices.includes("runs") && !refreshing) {
      void load("refresh");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [journal.latestEvent?.event_id]);

  // --- Projections --------------------------------------------------------
  const timelineEntries: TimelineEntry[] = useMemo(() => {
    if (!run) return [];
    return traceToTimelineEntries(run.trace);
  }, [run]);

  const claimedFacts = useMemo(() => extractClaimedFacts(raw ?? run ?? {}), [raw, run]);

  const settlement = useMemo(() => {
    if (!run) return null;
    return extractSettlementSummary(raw ?? {}, run);
  }, [raw, run]);

  // --- Render -------------------------------------------------------------
  return (
    <AppShell
      title="Run detail"
      crumbs={[
        { href: "/", label: "Mission Control" },
        { href: "/runs", label: "Runs" },
        { label: run?.title ?? shortId(runId, 8) },
      ]}
      onRefresh={() => load("refresh")}
      refreshing={refreshing}
    >
      <Stack gap={4}>
        {/* Back link */}
        <Row gap={1} align="center">
          <Link href="/runs" className="ax-link" aria-label="Back to runs">
            <ArrowLeft size={14} /> All runs
          </Link>
        </Row>

        {loading || !run ? (
          <Skeleton height={120} />
        ) : error ? (
          <ErrorState
            title="Couldn't load this run"
            detail={error}
            action={
              <AsyncButton onClick={() => load("initial")} size="sm">
                Retry
              </AsyncButton>
            }
          />
        ) : (
          <>
            {/* 1. Header -------------------------------------------------------*/}
            <Card padding="md">
              <Row gap={3} align="start" wrap>
                <Stack gap={1} style={{ flex: "1 1 320px", minWidth: 280 }}>
                  <span className="ax-eyebrow">
                    <Activity size={11} aria-hidden /> Run · {run.syscall}
                  </span>
                  <h1 className="ax-h2" style={{ margin: 0 }}>
                    {run.title}
                  </h1>
                  <Row gap={3} wrap>
                    <span className="mono ax-eyebrow">{shortId(run.id, 12)}</span>
                    {instance ? (
                      <Link
                        href={`/instances/${encodeURIComponent(instance.id)}`}
                        className="ax-link"
                      >
                        <ExternalLink size={11} /> {instance.name}
                      </Link>
                    ) : (
                      <Link
                        href={`/instances/${encodeURIComponent(run.instance_id)}`}
                        className="ax-link mono"
                      >
                        {run.instance_id}
                      </Link>
                    )}
                    <span className="ax-eyebrow">
                      ring {run.ring}
                    </span>
                    <span className="ax-eyebrow">
                      started {formatRelative(run.started_at)}
                    </span>
                    <span className="ax-eyebrow">
                      updated {formatRelative(run.updated_at)}
                    </span>
                  </Row>
                </Stack>
                <Stack gap={1} align="end">
                  <StatusPill tone={settlementTone(run.state)}>
                    {runStateLabel(run.state)}
                  </StatusPill>
                  <span className="ax-eyebrow">
                    {run.ledger_commits} ledger commits
                  </span>
                </Stack>
              </Row>
            </Card>

            {/* 2. Settlement ----------------------------------------------------*/}
            {settlement ? <SettlementCard settlement={settlement} /> : null}

            {/* 3. Timeline (oscilloscope) --------------------------------------*/}
            <Card padding="none">
              <CardHeader
                title="Trace timeline"
                subtitle="§5 oscilloscope — Think / Call / Claim / park / send events, in order."
                eyebrow={`${timelineEntries.length} event${timelineEntries.length === 1 ? "" : "s"}`}
                action={<GitBranch size={14} aria-hidden />}
              />
              <CardBody>
                {timelineEntries.length === 0 ? (
                  <EmptyState
                    icon={<TimerReset size={20} />}
                    title="No trace events yet"
                    detail="Once the run starts committing, each syscall + claim + adapter step lands here in order."
                  />
                ) : (
                  <Timeline entries={timelineEntries} />
                )}
              </CardBody>
              <CardFooter>
                <span className="ax-eyebrow">
                  Last updated {formatDateTime(run.updated_at)}
                </span>
              </CardFooter>
            </Card>

            {/* 4. Claimed facts -------------------------------------------------*/}
            <Card padding="none">
              <CardHeader
                title="Claimed facts"
                subtitle="Every fact the run committed to the heap, with provenance."
                eyebrow={`${claimedFacts.length} fact${claimedFacts.length === 1 ? "" : "s"}`}
                action={<ListTree size={14} aria-hidden />}
              />
              <CardBody>
                {claimedFacts.length === 0 ? (
                  <EmptyState
                    icon={<Sigma size={20} />}
                    title="No facts claimed"
                    detail="Once the run verifies evidence and writes to the heap, the facts show up here with their subject/predicate/object and confidence."
                  />
                ) : (
                  <Stack gap={2}>
                    {claimedFacts.map((fact) => (
                      <Card key={fact.id} tone="default" padding="sm" block>
                        <Row gap={3} wrap align="start">
                          <Stack gap={1} style={{ flex: "1 1 320px", minWidth: 280 }}>
                            <span className="ax-eyebrow mono">{fact.id}</span>
                            <div className="ax-mono-line">
                              <strong>{fact.subject}</strong>{" "}
                              <span className="ax-eyebrow">
                                {fact.predicate}
                              </span>{" "}
                              <code className="mono">{fact.object}</code>
                            </div>
                            {fact.evidence.length > 0 ? (
                              <span className="ax-eyebrow mono">
                                evidence: {fact.evidence.join(", ")}
                              </span>
                            ) : null}
                          </Stack>
                          <Stack gap={1} align="end" style={{ minWidth: 140 }}>
                            <span
                              className="mono"
                              title={`confidence ${(fact.confidence * 100).toFixed(0)}%`}
                            >
                              {(fact.confidence * 100).toFixed(0)}%
                            </span>
                            {fact.committed_at ? (
                              <span className="ax-eyebrow">
                                {formatRelative(fact.committed_at)}
                              </span>
                            ) : null}
                          </Stack>
                        </Row>
                      </Card>
                    ))}
                  </Stack>
                )}
              </CardBody>
            </Card>

            {/* 5. Raw payload ---------------------------------------------------*/}
            <Card padding="none">
              <CardHeader
                title="Raw payload"
                subtitle="The unprocessed GET /runs/{id} response, for debugging."
                eyebrow="JSON"
                action={<CircleSlash2 size={14} aria-hidden />}
              />
              <CardBody>
                <JsonViewer value={raw ?? {}} />
              </CardBody>
            </Card>
          </>
        )}
      </Stack>
    </AppShell>
  );
}

// -----------------------------------------------------------------------------
// Settlement — the summary card. Extracted because it's its own coherent
// "answer" to "is this run worth it?" and it carries its own little state
// machine (running vs. settled vs. failed).
// -----------------------------------------------------------------------------

interface SettlementCardProps {
  settlement: ReturnType<typeof extractSettlementSummary>;
}

function SettlementCard({ settlement }: SettlementCardProps) {
  const tone = settlementTone(settlement.status);
  const ratio =
    settlement.expected_value > 0
      ? settlement.cost / settlement.expected_value
      : null;
  const evDisplay = formatCurrency(settlement.expected_value);
  const costDisplay = formatCurrency(settlement.cost);

  return (
    <Card padding="md" tone={tone === "hot" ? "danger" : tone === "good" ? "success" : tone === "warn" ? "warn" : "default"}>
      <Row gap={3} wrap align="start">
        <Stack gap={1} style={{ minWidth: 140 }}>
          <span className="ax-eyebrow">
            <CircleDollarSign size={11} aria-hidden /> Status
          </span>
          <StatusPill tone={tone}>{runStateLabel(settlement.status)}</StatusPill>
          {settlement.settled_at ? (
            <span className="ax-eyebrow">
              settled {formatRelative(settlement.settled_at)}
            </span>
          ) : null}
        </Stack>

        <Stack gap={1} style={{ minWidth: 140 }}>
          <span className="ax-eyebrow">Cost so far</span>
          <span className="ax-h3" style={{ margin: 0 }}>{costDisplay}</span>
          {settlement.billing_amount !== null ? (
            <span className="ax-eyebrow">
              billed {formatCurrency(settlement.billing_amount)}
            </span>
          ) : null}
        </Stack>

        <Stack gap={1} style={{ minWidth: 140 }}>
          <span className="ax-eyebrow">Expected value</span>
          <span className="ax-h3" style={{ margin: 0 }}>{evDisplay}</span>
          {ratio !== null ? (
            <span className="ax-eyebrow">
              {(ratio * 100).toFixed(1)}% cost/EV
            </span>
          ) : null}
        </Stack>

        <Stack gap={1} style={{ flex: "1 1 200px", minWidth: 200 }}>
          <span className="ax-eyebrow">Progress</span>
          <ProgressBar value={settlement.progress} tone={tone} />
          <span className="ax-eyebrow">
            {settlement.progress.toFixed(0)}% complete
          </span>
        </Stack>
      </Row>
    </Card>
  );
}

// Inline progress bar — the design system has one but lives in
// components/shared.tsx for the OLD pre-C1 view; for the C1 design system
// we render the same shape with a small CSS-driven bar so we don't depend
// on the legacy import.
function ProgressBar({
  value,
  tone,
}: {
  value: number;
  tone: "good" | "warn" | "hot" | "info" | "neutral";
}) {
  const clamped = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
  return (
    <div
      className="ax-progress"
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className="ax-progress__fill"
        data-tone={tone}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
