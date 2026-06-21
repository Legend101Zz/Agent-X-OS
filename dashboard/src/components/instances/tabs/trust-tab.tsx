"use client";

/**
 * Trust tab — ring history, trust score, and the set-ring ladder.
 *
 * The set-ring buttons live in the header too (most-glanced path); this tab
 * is the audit trail: who changed the ring, when, and why, plus the trust
 * score over time.
 */

import { useMemo } from "react";
import { ArrowUp, History, ShieldAlert, ShieldCheck, TrendingUp } from "lucide-react";

import {
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  Row,
  Sparkline,
  Stack,
  StatusPill,
} from "../../ui";
import {
  formatDateTime,
  formatRelative,
  ringLabel,
  ringTone,
} from "../../../lib/format";
import type { InstanceSummary } from "../../../lib/types";

interface TrustTabProps {
  instance: InstanceSummary;
}

export function TrustTab({ instance }: TrustTabProps) {
  // Trust ladder visualisation: L0 -> L4 with the current ring highlighted.
  const rungs = ["L0", "L1", "L2", "L3", "L4"];
  const currentRungIndex = Math.max(
    0,
    rungs.indexOf((instance.ring ?? "L0").toUpperCase()),
  );

  // Sparkline data — synthesise a 12-point trust history from trust_history
  // + the current score. C1 fixtures carry trust_history[0] only; we surface
  // what we have and label the rest "synthesised" so it isn't presented as
  // ground truth.
  const sparkData = useMemo(() => {
    const score = instance.trust_score;
    const series: number[] = [];
    for (let i = 0; i < 12; i++) {
      // A simple synthesised arc: gradually climb toward the current score.
      const factor = i / 11;
      const noise = ((i * 7) % 5) / 100; // small wobble so the line isn't dead-flat
      series.push(Math.max(0, Math.min(1, score * factor + noise - 0.02)));
    }
    series.push(score);
    return series;
  }, [instance.trust_score]);

  return (
    <Stack gap={4}>
      <Card>
        <CardHeader
          eyebrow="Ring ladder"
          title="Current trust + ring"
          subtitle="The ring controls which syscalls auto-run vs. park for approval (L0 = observe, L4 = autopilot)."
        />
        <CardBody>
          <div className="inspector-trust-ladder">
            {rungs.map((rung, idx) => {
              const isCurrent = idx === currentRungIndex;
              const isPast = idx < currentRungIndex;
              return (
                <div
                  key={rung}
                  className={`inspector-trust-ladder__rung${isCurrent ? " is-current" : ""}${isPast ? " is-past" : ""}`}
                >
                  <div className="inspector-trust-ladder__rung-dot" />
                  <div className="inspector-trust-ladder__rung-label">
                    <StatusPill tone={isCurrent ? ringTone(rung) : isPast ? "good" : "muted"}>
                      {ringLabel(rung)}
                    </StatusPill>
                    {isCurrent ? (
                      <span className="inspector-trust-ladder__current">
                        <ShieldCheck size={11} /> current
                      </span>
                    ) : null}
                    {isPast ? (
                      <span className="inspector-trust-ladder__past dim">
                        <ArrowUp size={11} /> passed
                      </span>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        </CardBody>
      </Card>

      <div className="grid-2">
        <Card>
          <CardHeader
            eyebrow="Trust score"
            title={instance.trust_score.toFixed(2)}
            action={
              <StatusPill tone={instance.trust_score >= 0.8 ? "good" : instance.trust_score >= 0.5 ? "warn" : "hot"}>
                <TrendingUp size={11} /> {instance.trust_score >= 0.8 ? "ready to climb" : instance.trust_score >= 0.5 ? "growing" : "fresh"}
              </StatusPill>
            }
          />
          <CardBody>
            <div className="inspector-trust-sparkline">
              <Sparkline values={sparkData} width={240} height={48} />
            </div>
            <Row gap={3} wrap>
              <Stat label="Trust points" value={instance.trust_score.toFixed(2)} />
              <Stat
                label="Trust delta"
                value={
                  instance.trust_history[0]?.delta
                    ? instance.trust_history[0].delta.toFixed(2)
                    : "—"
                }
              />
              <Stat label="Facts on file" value={String(instance.facts.length)} />
            </Row>
            <div className="dim" style={{ fontSize: 12, marginTop: 8 }}>
              Trust climbs as settled runs verify. Synthesised trajectory shown until the journal exposes the full series.
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            eyebrow="Ring history"
            title={`${instance.ring_history.length} change${instance.ring_history.length === 1 ? "" : "s"}`}
            action={
              <StatusPill tone="muted">
                <History size={11} /> audit
              </StatusPill>
            }
          />
          <CardBody>
            {instance.ring_history.length === 0 ? (
              <EmptyState
                title="No ring changes yet"
                detail="When an operator changes the ring, the change and the reason land here."
                icon={<ShieldAlert size={20} />}
              />
            ) : (
              <ol className="inspector-trust-history">
                {instance.ring_history.map((entry, idx) => (
                  <li key={`${entry.at}-${entry.ring}-${idx}`} className="inspector-trust-history__row">
                    <div className="inspector-trust-history__dot" data-tone={ringTone(entry.ring)} />
                    <div className="inspector-trust-history__body">
                      <Row gap={2} wrap>
                        <StatusPill tone={ringTone(entry.ring)}>{ringLabel(entry.ring)}</StatusPill>
                        <span className="dim mono" style={{ fontSize: 12 }}>
                          {formatDateTime(entry.at)} · {formatRelative(entry.at)}
                        </span>
                      </Row>
                      <div className="inspector-trust-history__reason">{entry.reason}</div>
                      <div className="dim mono inspector-trust-history__actor">
                        by {entry.actor}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </CardBody>
        </Card>
      </div>
    </Stack>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="inspector-trust-stat">
      <div className="ax-tab-panel__eyebrow">{label}</div>
      <div className="inspector-trust-stat__value mono">{value}</div>
    </div>
  );
}
