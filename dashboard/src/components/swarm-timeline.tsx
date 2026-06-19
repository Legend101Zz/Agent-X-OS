"use client";

import {
  Activity,
  CheckCircle2,
  Cpu,
  Gauge,
  Loader2,
  LockKeyhole,
  MessageSquare,
  PauseCircle,
  Play,
  ShieldCheck,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import type { SwarmRunReport, SwarmTraceEvent } from "@/lib/types";
import { EmptyState, Panel, ProgressBar, StatusPill } from "./shared";

interface SwarmTimelineProps {
  report: SwarmRunReport | null;
  running: boolean;
}

const KIND_META: Record<string, { icon: LucideIcon; label: string }> = {
  thought: { icon: MessageSquare, label: "mandate decision" },
  syscall_attempt: { icon: Cpu, label: "syscall attempt" },
  syscall_result: { icon: CheckCircle2, label: "syscall result" },
  parked: { icon: PauseCircle, label: "parked / manual step" },
  resumed: { icon: Play, label: "resumed" },
  verify: { icon: ShieldCheck, label: "verify" },
  judge_comment: { icon: MessageSquare, label: "judge comment" },
  decision: { icon: Activity, label: "decision" },
  error: { icon: XCircle, label: "error" },
};

function metaFor(kind: string): { icon: LucideIcon; label: string } {
  return KIND_META[kind] ?? { icon: Activity, label: kind };
}

function detailSummary(event: SwarmTraceEvent): string | null {
  const fulfilledBy = event.detail.fulfilled_by;
  if (typeof fulfilledBy === "string") return `fulfilled by ${fulfilledBy}`;
  const ring = event.detail.required_ring ?? event.detail.ring;
  if (typeof ring === "string") return `ring ${ring}`;
  return null;
}

export function SwarmTimeline({ report, running }: SwarmTimelineProps) {
  if (running) {
    return (
      <Panel title="Swarm Timeline" eyebrow="BLUEPRINT §5 wind tunnel">
        <div className="swarm-running">
          <Loader2 className="spin" size={20} />
          <span>Running the candidate through the kernel in sim mode…</span>
        </div>
      </Panel>
    );
  }

  if (!report) {
    return (
      <Panel title="Swarm Timeline" eyebrow="BLUEPRINT §5 wind tunnel">
        <EmptyState label="Run a swarm to trace scenario → decision → syscall → judge → score → gate." />
      </Panel>
    );
  }

  const { scorecard, gate_decision: gate } = report;
  const scorePct = scorecard ? Math.round(scorecard.score * 100) : 0;

  return (
    <Panel
      title="Swarm Timeline"
      eyebrow="BLUEPRINT §5 wind tunnel"
      action={<StatusPill label={report.run_id} tone="neutral" />}
    >
      <ol className="swarm-timeline">
        <li className="swarm-event scenario">
          <span className="swarm-event-icon">
            <Activity size={16} />
          </span>
          <div className="swarm-event-body">
            <p className="eyebrow">scenario · {report.pack_id}</p>
            <strong>{report.type_ref}</strong>
            <span>candidate driven on the kernel in sim mode</span>
          </div>
        </li>

        {report.events.map((event) => {
          const meta = metaFor(event.kind);
          const Icon = meta.icon;
          const extra = detailSummary(event);
          return (
            <li className={`swarm-event ${event.kind}`} key={`${event.seq}-${event.kind}`}>
              <span className="swarm-event-icon">
                <Icon size={16} />
              </span>
              <div className="swarm-event-body">
                <p className="eyebrow">{meta.label}</p>
                <strong>{event.summary || meta.label}</strong>
                {extra ? <span>{extra}</span> : null}
              </div>
            </li>
          );
        })}

        {scorecard ? (
          <li className="swarm-event score">
            <span className="swarm-event-icon">
              <Gauge size={16} />
            </span>
            <div className="swarm-event-body">
              <p className="eyebrow">
                judge score · {scorecard.rubric_name} · {scorecard.origin}
              </p>
              <ProgressBar value={scorePct} />
              <div className="swarm-criteria">
                {scorecard.criteria.map((criterion) => (
                  <StatusPill
                    key={criterion.criterion_id}
                    label={`${criterion.criterion_id} ${Math.round(criterion.score * 100)}%`}
                    tone={criterion.passed ? "good" : "hot"}
                  />
                ))}
              </div>
              {scorecard.judge_comments.map((comment, index) => (
                <span className="swarm-judge-comment" key={index}>
                  {comment}
                </span>
              ))}
            </div>
          </li>
        ) : null}

        {gate ? (
          <li className="swarm-event gate">
            <span className="swarm-event-icon">
              {gate.allowed ? <ShieldCheck size={16} /> : <LockKeyhole size={16} />}
            </span>
            <div className="swarm-event-body">
              <p className="eyebrow">promotion gate</p>
              <StatusPill
                label={gate.allowed ? "promotable" : "synthetic-only · blocked"}
                tone={gate.allowed ? "good" : "hot"}
              />
              {gate.reasons.map((reason, index) => (
                <span className="swarm-gate-reason" key={index}>
                  {reason}
                </span>
              ))}
            </div>
          </li>
        ) : null}
      </ol>

      <p className="swarm-receipt">
        persisted eval case <code>{report.eval_case_id}</code> — synthetic evidence is recorded but
        barred from customer-facing promotion (invariant #7).
      </p>
    </Panel>
  );
}
