"use client";

/**
 * Overview tab — the "what is this thing" surface.
 *
 * Shows:
 *   - Charter / target (from type_ref) + a small type chip strip
 *   - Ring & trust ladder (current vs history)
 *   - Latest run (one-card; deeper list lives on the Runs tab)
 *   - P&L summary (mirror of the header, but in-card for non-header contexts)
 *   - Resume — the verified facts that make up the instance's memory-craft
 *
 * Memory/heap is deferred to C4 (needs the C3 read API).
 */

import { useMemo } from "react";
import Link from "next/link";
import { ArrowRight, FileText, KeyRound, ShieldCheck, Wallet } from "lucide-react";

import {
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  Row,
  Skeleton,
  Stack,
  StatusPill,
} from "../../ui";
import {
  formatCurrency,
  formatRelative,
  formatTime,
  ringLabel,
  ringTone,
  runStateLabel,
  runStateTone,
  shortId,
} from "../../../lib/format";
import type { InstanceSummary, RunSummary } from "../../../lib/types";

interface OverviewTabProps {
  instance: InstanceSummary;
  runs: RunSummary[];
  loading?: boolean;
}

export function OverviewTab({ instance, runs, loading }: OverviewTabProps) {
  const latestRun = useMemo(() => {
    if (runs.length === 0) return null;
    return [...runs].sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1))[0];
  }, [runs]);

  return (
    <Stack gap={4}>
      <div className="grid-2">
        <Card>
          <CardHeader
            eyebrow="Charter"
            title={instance.name}
            subtitle={instance.business}
          />
          <CardBody>
            <dl className="ax-tab-panel__meta">
              <div>
                <dt>type_ref</dt>
                <dd className="mono">{instance.mandate_type ?? "—"}</dd>
              </div>
              <div>
                <dt>ring (current)</dt>
                <dd>
                  <StatusPill tone={ringTone(instance.ring)}>
                    {ringLabel(instance.ring)}
                  </StatusPill>
                </dd>
              </div>
              <div>
                <dt>trust</dt>
                <dd className="mono">{instance.trust_score.toFixed(2)}</dd>
              </div>
              <div>
                <dt>health</dt>
                <dd>
                  <StatusPill tone={instance.health === "green" ? "good" : instance.health === "amber" ? "warn" : "muted"}>
                    {instance.health}
                  </StatusPill>
                </dd>
              </div>
              <div>
                <dt>state</dt>
                <dd>
                  <StatusPill tone={instance.state === "parked" ? "warn" : instance.state === "live" ? "good" : "muted"}>
                    {instance.state}
                  </StatusPill>
                </dd>
              </div>
              <div>
                <dt>monthly net</dt>
                <dd className="mono">
                  <Wallet size={11} /> {formatCurrency(instance.monthly_net)}
                </dd>
              </div>
            </dl>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            eyebrow="Latest run"
            title={latestRun ? latestRun.title : "No runs yet"}
            action={
              latestRun ? (
                <Link
                  href={`/runs/${encodeURIComponent(latestRun.id)}`}
                  className="inspector-tab__link"
                >
                  Open <ArrowRight size={12} />
                </Link>
              ) : null
            }
          />
          <CardBody>
            {loading ? (
              <Stack gap={2}>
                <Skeleton width="60%" />
                <Skeleton width="40%" />
                <Skeleton width="80%" />
              </Stack>
            ) : !latestRun ? (
              <EmptyState
                title="No runs yet"
                detail="When this instance triggers a run, it will appear here and on the Runs tab."
              />
            ) : (
              <dl className="ax-tab-panel__meta">
                <div>
                  <dt>id</dt>
                  <dd className="mono">{shortId(latestRun.id, 12)}</dd>
                </div>
                <div>
                  <dt>syscall</dt>
                  <dd className="mono">{latestRun.syscall}</dd>
                </div>
                <div>
                  <dt>state</dt>
                  <dd>
                    <StatusPill tone={runStateTone(latestRun.state)} dot={latestRun.state === "active"} pulse={latestRun.state === "active"}>
                      {runStateLabel(latestRun.state)}
                    </StatusPill>
                  </dd>
                </div>
                <div>
                  <dt>started</dt>
                  <dd>{formatRelative(latestRun.started_at)}</dd>
                </div>
                <div>
                  <dt>updated</dt>
                  <dd>{formatTime(latestRun.updated_at)}</dd>
                </div>
                <div>
                  <dt>cost</dt>
                  <dd className="mono">{formatCurrency(latestRun.cost)}</dd>
                </div>
              </dl>
            )}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          eyebrow="P&L summary"
          title="This period"
          action={
            <StatusPill tone="muted">
              <ShieldCheck size={11} /> derived from settled runs
            </StatusPill>
          }
        />
        <CardBody>
          <Row gap={6} wrap>
            <PnLFigure label="Revenue" value={instance.pnl.revenue} />
            <PnLFigure label="Cost" value={instance.pnl.cost} />
            <PnLFigure label="Margin" value={instance.pnl.margin} emphasis />
          </Row>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          eyebrow="Resume"
          title={`Verified facts (${instance.facts.length})`}
          action={
            <StatusPill tone="muted" title="Memory / Heap arrives in C4 (C3 heap API)">
              <FileText size={11} /> full heap: C4
            </StatusPill>
          }
        />
        <CardBody>
          {instance.facts.length === 0 ? (
            <EmptyState
              title="No facts yet"
              detail="As the instance settles runs, verified facts accumulate here with provenance."
            />
          ) : (
            <div className="inspector-facts">
              {instance.facts.map((fact) => (
                <div className="inspector-facts__row" key={fact.id}>
                  <div className="inspector-facts__main">
                    <div className="inspector-facts__label">{fact.label}</div>
                    <div className="inspector-facts__value mono">{fact.value}</div>
                  </div>
                  <div className="inspector-facts__source">
                    <KeyRound size={12} />
                    <span className="mono dim">{fact.source}</span>
                  </div>
                  <div className="inspector-facts__provenance">
                    {fact.provenance ? (
                      <span className="dim" title={fact.provenance}>
                        {fact.provenance}
                      </span>
                    ) : (
                      <span className="dim">no provenance</span>
                    )}
                  </div>
                  <div className="inspector-facts__confidence">
                    <StatusPill
                      tone={fact.confidence >= 0.8 ? "good" : fact.confidence >= 0.5 ? "warn" : "hot"}
                    >
                      {Math.round(fact.confidence * 100)}%
                    </StatusPill>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardBody>
      </Card>
    </Stack>
  );
}

function PnLFigure({
  label,
  value,
  emphasis,
}: {
  label: string;
  value: number;
  emphasis?: boolean;
}) {
  return (
    <div className={`inspector-pnl__figure${emphasis ? " inspector-pnl__figure--emphasis" : ""}`}>
      <div className="ax-tab-panel__eyebrow">{label}</div>
      <div className="inspector-pnl__value mono">{formatCurrency(value)}</div>
    </div>
  );
}
