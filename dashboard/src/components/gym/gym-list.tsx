"use client";

/**
 * GymList — the §5 "Gym & Evals" entry view.
 *
 * Shows every persisted EvalCase (`GET /eval-cases`), grouped by origin
 * (synthetic | real | human_reviewed) with:
 *   - origin pill on every row (invariant #7 surface)
 *   - score + status pills (graded | passed | failed | pending)
 *   - promotion pill (eligible | blocked | needs_review)
 *   - a hero strip with summary stats (total / eligible / avg score / timeline)
 *   - compiler scaffold status indicator (warming up / ready / blocked)
 *
 * Each row deep-links to `/gym/[id]` for the scorecard + gate decision
 * inspector (BLUEPRINT §5 row "Gym" — cases, scores, promote gate).
 *
 * Synthetic-only case rows get a "blocked · synthetic" pill — invariant #7
 * is *visible* here, not just enforced in the gate.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Beaker,
  CircleSlash2,
  Compass,
  Sparkles,
  Star,
  Target,
  TimerReset,
  TrendingUp,
  Trophy,
  Wand2,
} from "lucide-react";

import { AppShell } from "../shell/app-shell";
import {
  AsyncButton,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  HelpPanel,
  InfoTip,
  Sparkline,
  Stack,
  StatusPill,
  Table,
  TableSkeleton,
} from "../ui";
import { useToast } from "../../providers/toast-provider";
import { fetchEvalCases } from "../../lib/api";
import { deriveCompilerScaffold, summariseEvalCases } from "../../lib/eval-stats";
import {
  evalOriginLabel,
  evalOriginTone,
  evalStatusTone,
  formatScore,
  promotionLabel,
  promotionTone,
  scoreTone,
  shortId,
} from "../../lib/format";
import {
  compilerStateLabel,
  compilerStateTone,
  type EvalCase,
} from "../../lib/types";

interface GymListProps {
  initialEvalCases?: EvalCase[];
}

export function GymList({ initialEvalCases }: GymListProps = {}) {
  const toast = useToast();
  const router = useRouter();
  const [cases, setCases] = useState<EvalCase[] | null>(initialEvalCases ?? null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(!initialEvalCases);
  const [refreshing, setRefreshing] = useState<boolean>(false);

  const load = useCallback(
    async (mode: "initial" | "refresh" = "initial") => {
      if (mode === "refresh") setRefreshing(true);
      try {
        const result = await fetchEvalCases();
        setCases(result.data);
        setError(null);
        if (mode === "refresh" && result.source === "fixture" && result.error) {
          toast.push({
            title: "Showing fixture eval cases",
            message: result.error,
            tone: "hot",
          });
        }
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
    [toast],
  );

  useEffect(() => {
    if (initialEvalCases) return;
    void load("initial");
  }, [initialEvalCases, load]);

  const stats = useMemo(() => summariseEvalCases(cases ?? []), [cases]);
  const scaffold = useMemo(() => deriveCompilerScaffold(stats), [stats]);

  return (
    <AppShell
      title="Gym"
      crumbs={[{ label: "Gym" }]}
      onRefresh={() => void load("refresh")}
      refreshing={refreshing}
    >
      <div className="gym-page">
        <Stack gap={5}>
          <HelpPanel id="gym">
            <p>
              Graded tests of how your blueprints behave. Each eval case{" "}
              <InfoTip term="eval_case" /> carries a score and an origin{" "}
              <InfoTip term="origin" /> — only real cases can promote{" "}
              <InfoTip term="promotion" /> a customer-facing version.
            </p>
          </HelpPanel>
          <Card>
            <CardHeader
              eyebrow="Eval gym"
              title="Cases, scores, and the promotion gate"
              subtitle="Every graded case in the corpus — synthetic from the swarm, real from settled runs, human-reviewed after operator eyes. Each row opens an inspector with the scorecard, gate decision, and the synthetic-bar rationale (invariant #7)."
              action={
                <AsyncButton
                  variant="secondary"
                  size="sm"
                  icon={<CircleSlash2 size={14} />}
                  onClick={() => void load("refresh")}
                  loading={refreshing}
                >
                  Refresh
                </AsyncButton>
              }
            />
            <CardBody>
              {error && !loading ? (
                <ErrorState
                  title="Couldn't load eval cases"
                  detail={error}
                  action={
                    <AsyncButton variant="secondary" onClick={() => void load("refresh")}>
                      Retry
                    </AsyncButton>
                  }
                />
              ) : loading || !cases ? (
                <TableSkeleton columns={6} rows={5} />
              ) : cases.length === 0 ? (
                <EmptyState
                  icon={<Beaker size={20} />}
                  title="The gym is empty"
                  detail="Run the swarm via Foundry to seed synthetic cases, or let a real mandate settle to land a real case. Cases persist under projection EVAL_CASE."
                />
              ) : (
                <Table
                  columns={[
                    {
                      key: "case",
                      header: "Case",
                      render: (row) => (
                        <Link
                          href={`/gym/${encodeURIComponent(row.id)}`}
                          className="gym-row__name"
                        >
                          <span className="h3">{row.title || row.id}</span>
                          <span className="mono dim">{shortId(row.id)}</span>
                        </Link>
                      ),
                    },
                    {
                      key: "origin",
                      header: "Origin",
                      render: (row) => (
                        <OriginPill origin={row.origin as EvalCase["origin"]} />
                      ),
                    },
                    {
                      key: "pack",
                      header: "Pack",
                      mono: true,
                      render: (row) => (
                        <span className="mono dim" title={row.pack}>
                          {row.pack || "—"}
                        </span>
                      ),
                    },
                    {
                      key: "status",
                      header: "Status",
                      render: (row) => (
                        <StatusPill tone={evalStatusTone(row.status)} dot>
                          {row.status || "—"}
                        </StatusPill>
                      ),
                    },
                    {
                      key: "score",
                      header: "Score",
                      mono: true,
                      align: "right",
                      render: (row) => (
                        <ScoreCell value={typeof row.score === "number" ? row.score : null} />
                      ),
                    },
                    {
                      key: "promotion",
                      header: "Promotion",
                      render: (row) => (
                        <PromotionPill
                          promotion={row.promotion as EvalCase["promotion"]}
                          origin={row.origin as EvalCase["origin"]}
                        />
                      ),
                    },
                  ]}
                  rows={cases}
                  rowKey={(row) => row.id}
                  onRowClick={(row) => router.push(`/gym/${encodeURIComponent(row.id)}`)}
                  density="comfortable"
                />
              )}
            </CardBody>
          </Card>

          <div className="gym-summary" data-state={loading ? "loading" : "ready"}>
            <SummaryTile
              label="Total cases"
              value={stats.total}
              icon={<Beaker size={14} />}
              tone="default"
            />
            <SummaryTile
              label="Synthetic"
              value={stats.byOrigin.synthetic}
              icon={<Wand2 size={14} />}
              tone={stats.byOrigin.synthetic > 0 ? "muted" : "default"}
            />
            <SummaryTile
              label="Real"
              value={stats.byOrigin.real}
              icon={<Star size={14} />}
              tone="info"
            />
            <SummaryTile
              label="Human-reviewed"
              value={stats.byOrigin.human_reviewed}
              icon={<Compass size={14} />}
              tone="good"
            />
            <SummaryTile
              label="Eligible"
              value={stats.eligible}
              icon={<Trophy size={14} />}
              tone="good"
            />
            <SummaryTile
              label="Needs review"
              value={stats.needsReview}
              icon={<Target size={14} />}
              tone="warn"
            />
            <SummaryTile
              label="Blocked · synthetic"
              value={stats.blocked}
              icon={<CircleSlash2 size={14} />}
              tone="muted"
            />
            <SummaryTile
              label="Avg score"
              value={stats.averageScore === null ? "—" : stats.averageScore.toFixed(2)}
              icon={<TrendingUp size={14} />}
              tone={scoreTone(stats.averageScore)}
            />
          </div>

          <Card>
            <CardHeader
              eyebrow="Compiler scaffold"
              title="Growth-loop status"
              subtitle={
                scaffold.note +
                " The compiler only emits candidates when the corpus has enough real cases — synthetic-only is structurally barred from the PromotionGate (invariant #7)."
              }
              action={
                <StatusPill tone={compilerStateTone(scaffold.state)} dot>
                  {compilerStateLabel(scaffold.state)}
                </StatusPill>
              }
            />
            <CardBody>
              <div className="gym-compiler">
                <div className="gym-compiler__meter">
                  <div className="gym-compiler__meter-label">
                    <Sparkles size={14} />
                    <span>Real cases accumulated</span>
                  </div>
                  <div className="gym-compiler__meter-bar">
                    <div
                      className="gym-compiler__meter-fill"
                      data-state={scaffold.state}
                      style={{
                        width:
                          scaffold.threshold === 0
                            ? "0%"
                            : `${Math.min(100, (scaffold.realCases / scaffold.threshold) * 100)}%`,
                      }}
                    />
                  </div>
                  <div className="gym-compiler__meter-readout mono">
                    {scaffold.realCases} / {scaffold.threshold}
                  </div>
                </div>
                <div className="gym-compiler__spark">
                  <span className="dim" style={{ fontSize: 12 }}>
                    Score timeline
                  </span>
                  <Sparkline
                    values={stats.scoreTimeline}
                    height={36}
                    tone={sparkTone(stats.averageScore)}
                  />
                </div>
              </div>
            </CardBody>
          </Card>

          <div className="dim" style={{ fontSize: 12 }}>
            Source: <code>/eval-cases</code> · Inspector opens at <code>/gym/&lt;id&gt;</code> ·
            Promotion bridge: <code>POST /commands/promote</code> (auth required, candidate_id + ring).
            Synthetic cases carry a <StatusPill tone="hot">blocked · synthetic</StatusPill> pill by
            design — the gate never opens on synthetic evidence (invariant #7).
          </div>
        </Stack>
      </div>
    </AppShell>
  );
}

// ----------------------------------------------------------------------------
// Local presentational bits — kept inline because they're gym-specific.
// ----------------------------------------------------------------------------

function OriginPill({ origin }: { origin: EvalCase["origin"] | undefined }) {
  return (
    <StatusPill tone={evalOriginTone(origin)} dot>
      {evalOriginLabel(origin)}
    </StatusPill>
  );
}

function PromotionPill({
  promotion,
  origin,
}: {
  promotion: EvalCase["promotion"] | undefined;
  origin: EvalCase["origin"] | undefined;
}) {
  // Surface the synthetic-bar rule in the UI even when the API didn't
  // explicitly tag the case as "blocked": a synthetic-origin case is, by
  // invariant #7, never promotable.
  const effective =
    promotion === "blocked" || origin === "synthetic" ? "blocked" : promotion;
  return (
    <StatusPill tone={promotionTone(effective)} dot={effective !== undefined}>
      {effective === "blocked" && origin === "synthetic"
        ? promotionLabel("blocked")
        : promotionLabel(promotion)}
    </StatusPill>
  );
}

function ScoreCell({ value }: { value: number | null }) {
  const display = formatScore(value);
  return (
    <span className={`gym-row__score mono gym-row__score--${scoreTone(value)}`}>
      {display}
    </span>
  );
}

interface SummaryTileProps {
  label: string;
  value: number | string;
  icon?: React.ReactNode;
  tone?: "default" | "good" | "warn" | "hot" | "muted" | "info" | "neutral";
}

function SummaryTile({ label, value, icon, tone = "default" }: SummaryTileProps) {
  return (
    <div className={`gym-summary__tile gym-summary__tile--${tone}`}>
      <div className="gym-summary__label">
        {icon}
        <span>{label}</span>
      </div>
      <div className="gym-summary__value mono">{value}</div>
    </div>
  );
}

/** Sparkline doesn't accept "neutral" — coerce to "muted" so the timeline reads as inert when there are no scores. */
function sparkTone(
  score: number | null,
): "good" | "warn" | "hot" | "info" | "muted" | "accent" {
  const t = scoreTone(score);
  if (t === "neutral") return "muted";
  return t;
}

// Unused-but-exported so future tiles can re-use the "needs review" tone without
// re-importing lucide-react. (Keeps tree-shaking happy.)
export { TimerReset };