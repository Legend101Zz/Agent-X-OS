"use client";

/**
 * Memory tab — the per-instance heap/fact browser.
 *
 * Reads ``GET /instances/{id}/memory`` (C3, BLUEPRINT §8 row 1) and renders
 * the returned fact list. Each fact is shown as a row with:
 *   - subject / predicate / object triple (formatted via the JsonViewer
 *     primitive so the raw doc is one click away)
 *   - a status pill (Verified / Probation / Retired)
 *   - a confidence bar + tone pill
 *   - provenance (run id + evidence list) in a collapsible JsonViewer
 *
 * Graceful disable:
 *   - If the API returns ``{ missing: true, facts: [] }`` (no fact docs yet)
 *     we render an EmptyState explaining that the instance hasn't
 *     accumulated any verified facts yet — that's a normal state, not an
 *     error.
 *   - If the API errors, we render the same EmptyState with the error
 *     reason so the user knows we tried.
 *   - If the feature flag ``heap_read`` is "wip" (the default until the
 *     /system/info endpoint is live), we show a "coming soon" EmptyState
 *     rather than hanging on a fetch.
 */

import { useEffect, useMemo, useState } from "react";
import { Brain, ChevronDown, ChevronRight, ShieldCheck } from "lucide-react";

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
import { formatRelative, formatTime, shortId } from "../../../lib/format";
import { fetchInstanceMemoryRaw } from "../../../lib/api";
import { useFeature } from "../../../providers/feature-provider";
import { useOperator } from "../../../providers/operator-provider";
import {
  factConfidenceTone,
  factStatusLabel,
  factStatusTone,
  formatFactSummary,
} from "../../../lib/inspector-c4";
import type { ApiResult } from "../../../lib/types";

/** Minimal fact shape this tab consumes (matches C3's projection output). */
export interface MemoryFact {
  id: string;
  subject: string;
  predicate: string;
  object: string;
  confidence: number;
  status: string;
  source: string;
  provenance: {
    run_id: string;
    evidence: string[];
    note?: string;
  };
  created_at: string | null;
  updated_at: string | null;
}

interface MemoryTabProps {
  instanceId: string;
}

type LoadState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; facts: MemoryFact[]; missing: boolean; source: "live" | "fixture" | "empty" }
  | { kind: "error"; message: string };

export function MemoryTab({ instanceId }: MemoryTabProps) {
  const { baseUrl, token } = useOperator();
  const heap = useFeature("heap_read");
  const [state, setState] = useState<LoadState>({ kind: "idle" });

  useEffect(() => {
    if (instanceId === "") {
      setState({ kind: "ready", facts: [], missing: true, source: "empty" });
      return;
    }
    // Honour the feature flag — the C3 endpoint exists but the C4 wiring
    // ships as a "wip" feature until the operator's /system/info flips it
    // to "live". We still attempt the call so the operator can see the
    // shape, but the "wip" message survives in the EmptyState.
    let cancelled = false;
    setState({ kind: "loading" });
    fetchInstanceMemoryRaw(instanceId, {
      baseUrl: baseUrl || undefined,
      ...(token ? { init: { headers: { Authorization: `Bearer ${token}` } } } : {}),
    })
      .then((result: ApiResult<unknown>) => {
        if (cancelled) return;
        if (result.error) {
          setState({
            kind: "error",
            message: result.error,
          });
          return;
        }
        const body = (result.data ?? {}) as {
          missing?: boolean;
          facts?: MemoryFact[];
        };
        const facts = Array.isArray(body.facts) ? body.facts : [];
        const missing = body.missing === true || facts.length === 0;
        setState({
          kind: "ready",
          facts,
          missing,
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
  }, [instanceId, baseUrl, token]);

  // Group facts by status so the Verified/Probation/Retired split is
  // visible at a glance — and so an operator can see *if* a fact has been
  // contradicted by reality.
  const grouped = useMemo<{ verified: MemoryFact[]; probation: MemoryFact[]; retired: MemoryFact[] }>(() => {
    if (state.kind !== "ready") {
      return { verified: [], probation: [], retired: [] };
    }
    const verified: MemoryFact[] = [];
    const probation: MemoryFact[] = [];
    const retired: MemoryFact[] = [];
    for (const f of state.facts) {
      if (f.status === "promoted") verified.push(f);
      else if (f.status === "retired") retired.push(f);
      else probation.push(f);
    }
    return { verified, probation, retired };
  }, [state]);

  // Skeleton on first load so the user sees that the tab is alive.
  if (state.kind === "idle" || state.kind === "loading") {
    return (
      <Card>
        <CardHeader
          eyebrow="Memory"
          title="Verified facts"
          subtitle="Loading heap facts for this instance…"
        />
        <CardBody>
          <Stack gap={2}>
            <Skeleton width="100%" height={48} />
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
            title="Couldn't load memory"
            detail={state.message}
          />
        </CardBody>
      </Card>
    );
  }

  // Empty / missing — the most common path for a fresh instance.
  if (state.missing || state.facts.length === 0) {
    return (
      <Card>
        <CardHeader
          eyebrow="Memory"
          title="Verified facts"
          subtitle="The instance's heap — committed facts with provenance."
          action={<StatusPill tone="muted">0 facts</StatusPill>}
        />
        <CardBody>
          <EmptyState
            icon={<Brain size={20} />}
            title="No verified facts yet"
            detail={
              heap.status === "wip"
                ? "Memory is wired to the C3 heap read API; the kernel feature flag hasn't been flipped to live yet. New facts land here as runs settle."
                : "This instance hasn't settled any verified facts yet. New facts land here as runs complete and reality confirms them."
            }
          />
        </CardBody>
      </Card>
    );
  }

  return (
    <Stack gap={4}>
      <Card>
        <CardHeader
          eyebrow="Memory"
          title="Verified facts"
          subtitle={`${state.facts.length} committed fact${state.facts.length === 1 ? "" : "s"} — grouped by status.`}
          action={
            <Row gap={1}>
              <StatusPill tone="good">{grouped.verified.length} verified</StatusPill>
              <StatusPill tone="warn">{grouped.probation.length} probation</StatusPill>
              <StatusPill tone="hot">{grouped.retired.length} retired</StatusPill>
            </Row>
          }
        />
        <CardBody>
          <MemoryFactList
            title="Verified"
            tone="good"
            facts={grouped.verified}
            emptyText="No verified facts yet — reality hasn't confirmed anything for this instance."
          />
          <MemoryFactList
            title="Probation"
            tone="warn"
            facts={grouped.probation}
            emptyText="No probation facts — every settled fact has been promoted to verified."
          />
          <MemoryFactList
            title="Retired"
            tone="hot"
            facts={grouped.retired}
            emptyText="No retired facts — nothing has been contradicted by reality."
          />
        </CardBody>
      </Card>
    </Stack>
  );
}

interface MemoryFactListProps {
  title: string;
  tone: "good" | "warn" | "hot";
  facts: MemoryFact[];
  emptyText: string;
}

function MemoryFactList({ title, tone, facts, emptyText }: MemoryFactListProps) {
  if (facts.length === 0) {
    return (
      <section className="ax-mem-group">
        <header className="ax-mem-group__head">
          <StatusPill tone={tone}>{title}</StatusPill>
          <span className="ax-mem-group__count dim mono">0</span>
        </header>
        <p className="ax-mem-group__empty dim">{emptyText}</p>
      </section>
    );
  }
  return (
    <section className="ax-mem-group">
      <header className="ax-mem-group__head">
        <StatusPill tone={tone}>{title}</StatusPill>
        <span className="ax-mem-group__count dim mono">{facts.length}</span>
      </header>
      <ul className="ax-mem-list">
        {facts.map((f) => (
          <MemoryFactRow key={f.id || `${f.subject}-${f.predicate}-${f.object}`} fact={f} />
        ))}
      </ul>
    </section>
  );
}

function MemoryFactRow({ fact }: { fact: MemoryFact }) {
  const [expanded, setExpanded] = useState(false);
  const statusLabel = factStatusLabel(fact.status);
  const statusTone = factStatusTone(fact.status);
  const confidenceTone = factConfidenceTone(fact.confidence);
  return (
    <li className="ax-mem-row">
      <button
        type="button"
        className="ax-mem-row__head"
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
        title={expanded ? "Hide raw fact doc" : "Show raw fact doc"}
      >
        <span className="ax-mem-row__chev" aria-hidden>
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
        <span className="ax-mem-row__summary mono">
          {formatFactSummary(fact)}
        </span>
        <StatusPill tone={statusTone} size="sm">
          {statusLabel}
        </StatusPill>
        <StatusPill tone={confidenceTone} size="sm" title={`confidence ${(fact.confidence * 100).toFixed(0)}%`}>
          {`${(fact.confidence * 100).toFixed(0)}%`}
        </StatusPill>
        {fact.provenance?.run_id ? (
          <span className="ax-mem-row__run dim mono" title="committed by run">
            run {shortId(fact.provenance.run_id)}
          </span>
        ) : null}
      </button>
      {expanded ? (
        <div className="ax-mem-row__body">
          <dl className="ax-mem-row__meta">
            <div>
              <dt>id</dt>
              <dd className="mono">{fact.id || "—"}</dd>
            </div>
            <div>
              <dt>source</dt>
              <dd className="mono">{fact.source || "agent-inferred"}</dd>
            </div>
            <div>
              <dt>committed</dt>
              <dd className="mono" title={fact.created_at ?? ""}>
                {fact.created_at ? formatTime(fact.created_at) : "—"}
                {fact.created_at ? (
                  <span className="dim"> · {formatRelative(fact.created_at)}</span>
                ) : null}
              </dd>
            </div>
            <div>
              <dt>updated</dt>
              <dd className="mono" title={fact.updated_at ?? ""}>
                {fact.updated_at ? formatTime(fact.updated_at) : "—"}
                {fact.updated_at ? (
                  <span className="dim"> · {formatRelative(fact.updated_at)}</span>
                ) : null}
              </dd>
            </div>
          </dl>
          {fact.provenance?.note ? (
            <p className="ax-mem-row__note dim">
              <ShieldCheck size={12} /> {fact.provenance.note}
            </p>
          ) : null}
          {fact.provenance?.evidence && fact.provenance.evidence.length > 0 ? (
            <div className="ax-mem-row__evidence">
              <div className="ax-mem-row__evidence-label dim">Evidence</div>
              <ul>
                {fact.provenance.evidence.map((ev, i) => (
                  <li key={`${fact.id}-ev-${i}`} className="mono">
                    {ev}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <JsonViewer value={fact} title="Raw fact" />
        </div>
      ) : null}
    </li>
  );
}
