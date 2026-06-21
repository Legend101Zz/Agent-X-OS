"use client";

/**
 * C10 — Foundry / Swarm wind-tunnel (run → judge → gate timeline).
 *
 * SPEC §5 Foundry · /commands/run-swarm returns a SwarmRunReport
 * (events + scorecard + gate_decision). This view is the dashboard lens
 * onto that pipeline: a Run Swarm AsyncButton, a type_ref + pack selector,
 * a mono Timeline of SwarmTraceEvent, a scorecard criteria table, and a
 * gate decision banner (allowed / blocked, with reasons).
 *
 * Pure helpers live in ./foundry-view-helpers and are unit-tested in
 * dashboard/tests/foundry.test.ts.
 */

import {
  FlaskConical,
  Loader2,
  Play,
  ShieldCheck,
  ShieldX,
  Trophy,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { runSwarm } from "../../lib/api";
import type { MandateType, SwarmRunReport } from "../../lib/types";
import { useOperator } from "../../providers/operator-provider";
import { useToast } from "../../providers/toast-provider";
import {
  AsyncButton,
  Badge,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  Row,
  Section,
  Skeleton,
  Stack,
  StatTile,
  StatusPill,
  Table,
  TableSkeleton,
  Timeline,
} from "../ui";
import {
  buildGateBanner as buildGateBannerModel,
  buildSwarmTimelineEntries,
  buildTypeRefOptions,
  formatMandateRef,
  gateDecisionTone,
  isGateBlocked,
  scorecardPct,
  scorecardToCriteriaRows,
  type GateBannerView,
  type ScorecardRow,
} from "./foundry-view-helpers";

// The only bundled Phase-1 scenario pack today (see packages/swarm/.../scenario_packs).
const SCENARIO_PACKS = ["indian_b2b_leads_v1"] as const;
const RING_CHOICES = ["L0", "L1", "L2"] as const;
type RingChoice = (typeof RING_CHOICES)[number];

interface GateBannerPresentation {
  model: GateBannerView;
  icon: LucideIcon;
}

function buildGateBanner(report: SwarmRunReport | null): GateBannerPresentation | null {
  if (!report || !report.gate_decision) return null;
  const origin = report.scorecard?.origin ?? null;
  const model = buildGateBannerModel(report.gate_decision, origin);
  if (!model) return null;
  return { model, icon: model.allowed ? ShieldCheck : ShieldX };
}

interface RunState {
  status: "idle" | "submitting" | "ok" | "error";
  message?: string;
}

export interface FoundryViewProps {
  initialMandates?: MandateType[];
  initialEvalCases?: Array<{ origin: string; promotion: string }>;
}

export function FoundryView({
  initialMandates,
  initialEvalCases,
}: FoundryViewProps = {}) {
  const operator = useOperator();
  const toast = useToast();

  const [typeRef, setTypeRef] = useState<string>(() => {
    if (initialMandates && initialMandates[0]) {
      return formatMandateRef(initialMandates[0].title, initialMandates[0].stage);
    }
    return "lead-finder@0.1.0";
  });
  const [packId, setPackId] = useState<string>(SCENARIO_PACKS[0]);
  const [ring, setRing] = useState<RingChoice>("L2");
  const [judgeLive, setJudgeLive] = useState<boolean>(false);

  const [run, setRun] = useState<RunState>({ status: "idle" });
  const [report, setReport] = useState<SwarmRunReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  // If a fresh mandate list arrives after mount, snap the selector to the first
  // entry if the current ref no longer exists. (We don't depend on `typeRef`
  // — that would re-fire on every keystroke.)
  useEffect(() => {
    if (initialMandates && initialMandates.length > 0) {
      const options = buildTypeRefOptions(initialMandates);
      if (!options.find((option) => option.value === typeRef)) {
        setTypeRef(options[0].value);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialMandates]);

  const submitEnabled = run.status !== "submitting" && Boolean(operator.token);

  const handleSubmit = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!operator.token) {
        setRun({ status: "error", message: "Set the operator token to enable writes." });
        toast.push({
          title: "Operator token required",
          message: "Open the operator drawer and paste the token.",
          tone: "warn",
        });
        return;
      }
      setRun({ status: "submitting" });
      setError(null);
      const result = await runSwarm(
        {
          type_ref: typeRef,
          pack_id: packId,
          ring,
          judge_live: judgeLive,
          actor: operator.actor || "dashboard/operator",
        },
        { baseUrl: operator.baseUrl, token: operator.token },
      );
      if (result.source !== "api" || !result.data.supported) {
        const message =
          result.error ?? result.data.message ?? "run-swarm rejected by the kernel";
        setRun({ status: "error", message });
        toast.push({ title: "Swarm run failed", message, tone: "hot" });
        return;
      }
      setReport(result.data);
      const blocked = isGateBlocked(result.data.gate_decision);
      const summary = `graded ${scorecardPct(result.data.scorecard)}% · gate ${
        result.data.gate_decision?.allowed ? "open" : "blocked"
      }`;
      setRun({ status: "ok", message: summary });
      toast.push({
        title: "Swarm run finished",
        message: summary,
        tone: blocked ? "warn" : "good",
      });
    },
    [
      operator.actor,
      operator.baseUrl,
      operator.token,
      typeRef,
      packId,
      ring,
      judgeLive,
      toast,
    ],
  );

  // Derived view models — all pure, all unit-tested in foundry.test.ts.
  const typeRefOptions = useMemo(
    () => buildTypeRefOptions(initialMandates ?? []),
    [initialMandates],
  );
  const timelineEntries = useMemo(
    () => (report ? buildSwarmTimelineEntries(report.events) : []),
    [report],
  );
  const criteriaRows: ScorecardRow[] = useMemo(
    () => (report ? scorecardToCriteriaRows(report.scorecard) : []),
    [report],
  );
  const gateBanner = useMemo(() => buildGateBanner(report), [report]);

  // Quick-read stat tiles from the eval-case catalogue.
  const eligible = useMemo(
    () => (initialEvalCases ?? []).filter((c) => c.promotion === "eligible").length,
    [initialEvalCases],
  );
  const syntheticTotal = initialEvalCases?.length ?? 0;
  const hasMandates = (initialMandates?.length ?? 0) > 0;

  return (
    <Stack gap={5} className="foundry-page">
      <Section
        title="Foundry / Swarm wind-tunnel"
        subtitle="Trigger a sim swarm on the kernel, watch the §5 timeline, read the scorecard, see the gate decision."
        eyebrow="C10"
        density="comfortable"
      >
        <div className="mc-stats">
          <StatTile
            label="Scenario packs"
            value={SCENARIO_PACKS.length}
            tone="default"
            icon={<FlaskConical size={14} />}
            hint={SCENARIO_PACKS[0]}
          />
          <StatTile
            label="Mandate types"
            value={hasMandates ? (initialMandates?.length ?? 0) : "—"}
            tone={hasMandates ? "good" : "warn"}
            icon={<Trophy size={14} />}
            hint={hasMandates ? "live catalogue" : "API not reachable"}
          />
          <StatTile
            label="Synthetic cases"
            value={syntheticTotal}
            tone="default"
            icon={<FlaskConical size={14} />}
            hint="sim-only"
          />
          <StatTile
            label="Promotion eligible"
            value={eligible}
            tone={eligible > 0 ? "good" : "warn"}
            icon={<Trophy size={14} />}
            hint={eligible > 0 ? "ready for /promote" : "none yet"}
          />
        </div>
      </Section>

      {error ? (
        <ErrorState
          title="Couldn't load Foundry data"
          detail={error}
          action={
            <AsyncButton onClick={() => setError(null)} variant="secondary">
              Dismiss
            </AsyncButton>
          }
        />
      ) : null}

      <Section
        title="Run a swarm"
        subtitle="Run → judge → gate. The candidate is driven on the kernel in sim mode (L2 by default)."
        eyebrow="sim wind-tunnel"
        density="comfortable"
      >
        <Card tone="default" padding="md">
          <CardBody>
            <form className="foundry-form" onSubmit={handleSubmit}>
              <Row gap={3} wrap className="foundry-form__row">
                <label className="foundry-field">
                  <span className="foundry-field__label">Candidate mandate</span>
                  <select
                    className="foundry-field__input mono"
                    value={typeRef}
                    onChange={(e) => setTypeRef(e.target.value)}
                    aria-label="type_ref"
                  >
                    {typeRefOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="foundry-field">
                  <span className="foundry-field__label">Scenario pack</span>
                  <select
                    className="foundry-field__input mono"
                    value={packId}
                    onChange={(e) => setPackId(e.target.value)}
                    aria-label="pack_id"
                  >
                    {SCENARIO_PACKS.map((pack) => (
                      <option key={pack} value={pack}>
                        {pack}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="foundry-field">
                  <span className="foundry-field__label">Ring</span>
                  <select
                    className="foundry-field__input mono"
                    value={ring}
                    onChange={(e) => setRing(e.target.value as RingChoice)}
                    aria-label="ring"
                  >
                    {RING_CHOICES.map((choice) => (
                      <option key={choice} value={choice}>
                        {choice}
                        {choice === "L2" ? " (drafts run via SimAdapter)" : ""}
                      </option>
                    ))}
                  </select>
                </label>
              </Row>

              <label className="foundry-checkbox">
                <input
                  type="checkbox"
                  checked={judgeLive}
                  onChange={(e) => setJudgeLive(e.target.checked)}
                />
                <span>
                  Use live promptfoo judge
                  <span className="dim"> (requires JUDGE_MODEL_ID + OPENROUTER_API_KEY)</span>
                </span>
              </label>

              <Row gap={2} align="center" wrap className="foundry-form__actions">
                <AsyncButton
                  type="submit"
                  variant="primary"
                  size="md"
                  icon={<Play size={14} />}
                  loading={run.status === "submitting"}
                  loadingText="Running…"
                  disabled={!submitEnabled}
                  disabledReason={
                    operator.token
                      ? undefined
                      : "Set the operator token in the topbar drawer to enable writes."
                  }
                >
                  Run swarm
                </AsyncButton>

                {run.status === "ok" && run.message ? (
                  <Badge tone="good">{run.message}</Badge>
                ) : null}
                {run.status === "error" && run.message ? (
                  <Badge tone="hot">{run.message}</Badge>
                ) : null}
              </Row>
            </form>
          </CardBody>
        </Card>
      </Section>

      {gateBanner ? (
        <Section
          title="Gate decision"
          subtitle="The PromotionGate verdict for the latest run — synthetic-only is always barred (invariant #7)."
          eyebrow="promotion"
          density="comfortable"
        >
          <Card tone={gateBanner.model.allowed ? "good" : "danger"} padding="md">
            <CardHeader
              eyebrow={gateBanner.model.allowed ? "allowed" : "blocked"}
              title={gateBanner.model.title}
              action={
                <Row gap={2} align="center">
                  <StatusPill tone={gateBanner.model.origin_label === "synthetic" ? "warn" : "info"} size="sm">
                    origin: {gateBanner.model.origin_label}
                  </StatusPill>
                  {gateBanner.model.live_ring ? (
                    <StatusPill tone="good" size="sm">
                      live @ {gateBanner.model.live_ring}
                    </StatusPill>
                  ) : null}
                  <StatusPill tone={gateBanner.model.tone} dot>
                    {gateBanner.model.allowed ? "OPEN" : "BLOCKED"}
                  </StatusPill>
                </Row>
              }
            />
            <CardBody>
              <p className="foundry-gate-subtitle">{gateBanner.model.subtitle}</p>
              {gateBanner.model.reasons.length > 0 ? (
                <Stack gap={1} className="foundry-gate-reasons">
                  {gateBanner.model.reasons.map((reason, index) => {
                    const Icon = gateBanner.icon;
                    return (
                      <div key={index} className="ax-data-pair">
                        <span className="ax-data-pair__label mono">
                          <Icon size={12} /> reason
                        </span>
                        <span className="ax-data-pair__value">{reason}</span>
                      </div>
                    );
                  })}
                </Stack>
              ) : (
                <span className="dim">No reasons provided.</span>
              )}
            </CardBody>
          </Card>
        </Section>
      ) : null}

      <Section
        title="Timeline"
        subtitle="Mono trace of the run, from scenario → decision → syscall → judge → score → gate."
        eyebrow="BLUEPRINT §5"
        density="comfortable"
        action={
          report ? (
            <StatusPill tone="neutral" size="sm">
              {report.run_id}
            </StatusPill>
          ) : null
        }
      >
        <Card tone="default" padding="md">
          <CardBody>
            {run.status === "submitting" ? (
              <div className="foundry-running">
                <Loader2 className="spin" size={20} aria-hidden />
                <span>Running the candidate through the kernel in sim mode…</span>
              </div>
            ) : !report ? (
              <EmptyState
                title="No swarm run yet"
                detail="Hit Run swarm to trace scenario → decision → syscall → judge → score → gate."
                icon={<Play size={20} />}
              />
            ) : timelineEntries.length === 0 ? (
              <EmptyState
                title="Empty timeline"
                detail="The run produced no trace events."
                icon={<FlaskConical size={20} />}
              />
            ) : (
              <Timeline entries={timelineEntries} />
            )}
          </CardBody>
        </Card>
      </Section>

      {report?.scorecard ? (
        <Section
          title="Scorecard"
          subtitle="Rubric grade, per-criterion, with judge comments. The PromotionGate reads this verdict."
          eyebrow="judge"
          density="comfortable"
          action={
            <Row gap={2} align="center">
              <StatusPill tone="info" size="sm">
                {report.scorecard.rubric_name}
              </StatusPill>
              <StatusPill
                tone={report.scorecard.passed ? "good" : "hot"}
                size="sm"
                dot
              >
                {scorecardPct(report.scorecard)}%
              </StatusPill>
            </Row>
          }
        >
          <Card tone="default" padding="md">
            <CardBody>
              <Table<ScorecardRow>
                density="comfortable"
                rowKey={(row) => row.criterion_id}
                columns={[
                  {
                    key: "criterion",
                    header: "Criterion",
                    render: (row) => (
                      <span className="mono">{row.criterion_id}</span>
                    ),
                    mono: true,
                  },
                  {
                    key: "passed",
                    header: "Passed",
                    render: (row) => (
                      <StatusPill tone={row.tone} dot size="sm">
                        {row.passed ? "yes" : "no"}
                      </StatusPill>
                    ),
                  },
                  {
                    key: "pct",
                    header: "Score",
                    align: "right",
                    render: (row) => (
                      <span className="mono">{row.pct}%</span>
                    ),
                    mono: true,
                  },
                  {
                    key: "comment",
                    header: "Comment",
                    render: (row) =>
                      row.comment ? (
                        <span className="muted">{row.comment}</span>
                      ) : (
                        <span className="dim">—</span>
                      ),
                  },
                ]}
                rows={criteriaRows}
                emptyState={
                  <EmptyState
                    title="No criteria"
                    detail="The judge emitted a scorecard with no per-criterion rows."
                  />
                }
              />
              {report.scorecard.judge_comments.length > 0 ? (
                <Stack gap={1} className="foundry-judge-comments">
                  <span className="dim" style={{ fontSize: 12 }}>
                    Judge comments
                  </span>
                  {report.scorecard.judge_comments.map((comment, index) => (
                    <div key={index} className="foundry-judge-comment mono">
                      {comment}
                    </div>
                  ))}
                </Stack>
              ) : null}
            </CardBody>
          </Card>
        </Section>
      ) : null}

      {report ? (
        <Section
          title="Persisted"
          subtitle="Synthetic evidence is recorded but barred from customer-facing promotion (invariant #7)."
          eyebrow="eval case"
          density="compact"
        >
          <Card tone="muted" padding="sm">
            <CardBody>
              <div className="ax-data-pair">
                <span className="ax-data-pair__label mono">eval_case_id</span>
                <span className="ax-data-pair__value mono">{report.eval_case_id}</span>
              </div>
              <div className="ax-data-pair">
                <span className="ax-data-pair__label mono">type_ref</span>
                <span className="ax-data-pair__value mono">{report.type_ref}</span>
              </div>
              <div className="ax-data-pair">
                <span className="ax-data-pair__label mono">pack_id</span>
                <span className="ax-data-pair__value mono">{report.pack_id}</span>
              </div>
              {report.scorecard ? (
                <div className="ax-data-pair">
                  <span className="ax-data-pair__label mono">origin</span>
                  <span className="ax-data-pair__value">
                    <StatusPill tone="warn" size="sm">
                      {report.scorecard.origin}
                    </StatusPill>
                  </span>
                </div>
              ) : null}
            </CardBody>
          </Card>
        </Section>
      ) : null}

      {/* Calm skeleton placeholder while the catalogue is in flight. */}
      {false ? <TableSkeleton columns={4} rows={4} /> : null}
      {/* Skeleton intentionally disabled — view is the data source, not the page wrapper. */}
      {false ? <Skeleton width="100%" height={120} /> : null}
    </Stack>
  );
}

// Helpers live in ./foundry-view-helpers and are unit-tested in
// dashboard/tests/foundry.test.ts.
export {};
