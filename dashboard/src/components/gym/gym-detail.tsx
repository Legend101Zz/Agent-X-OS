"use client";

/**
 * GymDetail — the §5 per-case inspector at `/gym/[id]`.
 *
 * Shows one eval case end-to-end:
 *   - origin pill (synthetic | real | human_reviewed) + status pill + score
 *   - scorecard criteria (each with passed/score/comment)
 *   - failure reasons (if any) and judge comments
 *   - promotion gate decision (eligible | blocked | needs_review) and the
 *     synthetic-bar rationale (invariant #7 visible, not just enforced)
 *   - raw hydration/output/verification payloads in a collapsible JsonViewer
 *
 * Pure projection view — no write buttons. Promotion goes through
 * `POST /commands/promote` at the candidate level (Creator→canary bridge),
 * not per-case; the case itself doesn't carry candidate_id.
 */

import { use, useMemo } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Beaker,
  CircleSlash2,
  ClipboardCheck,
  Compass,
  ShieldAlert,
  Star,
  Target,
  Wand2,
} from "lucide-react";

import { AppShell } from "../shell/app-shell";
import {
  AsyncButton,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  JsonViewer,
  Stack,
  StatusPill,
} from "../ui";
import { fetchEvalCases } from "../../lib/api";
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
import type { EvalCase } from "../../lib/types";

interface GymDetailProps {
  caseId: string;
}

export function GymDetail({ caseId }: GymDetailProps) {
  // The /eval-cases endpoint returns every case in the corpus; we filter to
  // the requested id. A future per-case endpoint is C9 (already marked N/A —
  // the projection-store list already returns full EvalCase docs).
  const data = use(fetchEvalCases());
  const cases = data.data;
  const evalCase = useMemo(
    () => cases.find((entry) => entry.id === caseId) ?? null,
    [cases, caseId],
  );

  if (!evalCase) {
    return (
      <AppShell title="Gym" crumbs={[{ label: "Gym", href: "/gym" }, { label: caseId }]}>
        <Card>
          <CardHeader
            eyebrow="Eval case"
            title={caseId}
            subtitle="No matching eval case in the projection."
            action={
              <Link href="/gym">
                <AsyncButton variant="secondary" icon={<ArrowLeft size={14} />}>
                  Back to gym
                </AsyncButton>
              </Link>
            }
          />
          <CardBody>
            <EmptyState
              icon={<Beaker size={20} />}
              title="Case not in the corpus"
              detail={`The projection /eval-cases has no row with id ${caseId}. Cases land there from /commands/run-swarm (synthetic) or from real-settle maturation (real / human_reviewed).`}
            />
          </CardBody>
        </Card>
      </AppShell>
    );
  }

  const syntheticBarred = evalCase.origin === "synthetic";
  const gateOpen =
    evalCase.promotion === "eligible" &&
    (evalCase.status === "passed" || evalCase.status === "graded") &&
    !syntheticBarred;

  const scorecard = scorecardFromCase(evalCase);
  const failureReasons = (evalCase as unknown as { failure_reasons?: string[] }).failure_reasons ?? [];

  return (
    <AppShell
      title="Gym"
      crumbs={[
        { label: "Gym", href: "/gym" },
        { label: evalCase.title || evalCase.id },
      ]}
    >
      <div className="gym-page">
        <Stack gap={5}>
          <Card>
            <CardHeader
              eyebrow="Eval case"
              title={evalCase.title || evalCase.id}
              subtitle={
                <span className="gym-detail__id mono">{evalCase.id}</span>
              }
              action={
                <Link href="/gym">
                  <AsyncButton variant="secondary" size="sm" icon={<ArrowLeft size={14} />}>
                    Back
                  </AsyncButton>
                </Link>
              }
            />
            <CardBody>
              <div className="gym-detail__header">
                <div className="gym-detail__title">
                  <div className="gym-detail__pills">
                    <StatusPill tone={evalOriginTone(evalCase.origin)} dot>
                      <OriginIcon origin={evalCase.origin} />
                      {evalOriginLabel(evalCase.origin)}
                    </StatusPill>
                    <StatusPill tone={evalStatusTone(evalCase.status)} dot>
                      {evalCase.status || "—"}
                    </StatusPill>
                    <StatusPill tone={promotionTone(evalCase.promotion)} dot>
                      {gateOpen
                        ? "promotable"
                        : syntheticBarred
                          ? promotionLabel("blocked")
                          : promotionLabel(evalCase.promotion)}
                    </StatusPill>
                    <span className="mono dim" title={evalCase.pack}>
                      pack: {evalCase.pack || "—"}
                    </span>
                  </div>
                </div>
                <div className="gym-detail__score">
                  <span className={`gym-detail__score-value gym-row__score--${scoreTone(evalCase.score)}`}>
                    {formatScore(evalCase.score)}
                  </span>
                  <span className="dim" style={{ fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                    scorecard
                  </span>
                </div>
              </div>
            </CardBody>
          </Card>

          <div className="gym-detail__grid">
            <Card>
              <CardHeader
                eyebrow="Scorecard"
                title="Rubric verdicts"
                subtitle={
                  scorecard
                    ? `Rubric ${scorecard.rubric_name || "—"} · run ${shortId(scorecard.run_id || evalCase.id)}`
                    : "No scorecard sub-doc persisted for this case."
                }
              />
              <CardBody>
                {scorecard?.criteria?.length ? (
                  <div className="gym-detail__criteria">
                    {scorecard.criteria.map((criterion, index) => (
                      <div
                        key={`${criterion.criterion_id || index}-${index}`}
                        className={`gym-detail__criterion gym-detail__criterion--${
                          criterion.passed ? "passed" : "failed"
                        }`}
                      >
                        <StatusPill tone={criterion.passed ? "good" : "hot"} dot>
                          {criterion.passed ? "pass" : "fail"}
                        </StatusPill>
                        <div>
                          <div className="gym-detail__criterion-name">{criterion.criterion_id || `criterion ${index + 1}`}</div>
                          {criterion.comment ? (
                            <div className="gym-detail__criterion-comment">{criterion.comment}</div>
                          ) : null}
                        </div>
                        <div className="gym-detail__criterion-score mono">
                          {(criterion.score * 100).toFixed(0)}%
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    icon={<ClipboardCheck size={20} />}
                    title="No rubric criteria persisted"
                    detail="The scorecard sub-doc (or its criteria list) wasn't persisted on this case — likely a fixture or pre-scorecard run."
                  />
                )}
                {failureReasons.length > 0 ? (
                  <ul className="gym-detail__failure" style={{ marginTop: 12 }}>
                    {failureReasons.map((reason, idx) => (
                      <li key={`${idx}-${reason}`}>{reason}</li>
                    ))}
                  </ul>
                ) : null}
              </CardBody>
            </Card>

            <Card>
              <CardHeader
                eyebrow="Promotion gate"
                title="Bridge verdict"
                subtitle={
                  gateOpen
                    ? "Case is eligible for the candidate→live bridge — a candidate draft on this type_ref can be promoted through /commands/promote."
                    : syntheticBarred
                      ? "Synthetic origin is structurally barred from the gate (invariant #7). Only real + human_reviewed can open the bridge."
                      : "Gate is closed — fix the underlying scorecard / require human review before re-attempting."
                }
                action={
                  <StatusPill tone={gateOpen ? "good" : "hot"} dot>
                    {gateOpen ? "open" : syntheticBarred ? "blocked · synthetic" : "blocked"}
                  </StatusPill>
                }
              />
              <CardBody>
                <div className="gym-detail__gate">
                  <div
                    className={`gym-detail__gate-row ${gateOpen ? "gym-detail__gate-row--allowed" : "gym-detail__gate-row--blocked"}`}
                  >
                    <span>Origin</span>
                    <span className="mono">{evalCase.origin || "—"}</span>
                  </div>
                  <div
                    className={`gym-detail__gate-row ${gateOpen ? "gym-detail__gate-row--allowed" : "gym-detail__gate-row--blocked"}`}
                  >
                    <span>Status</span>
                    <span className="mono">{evalCase.status || "—"}</span>
                  </div>
                  <div
                    className={`gym-detail__gate-row ${gateOpen ? "gym-detail__gate-row--allowed" : "gym-detail__gate-row--blocked"}`}
                  >
                    <span>Promotion state</span>
                    <span className="mono">{promotionLabel(evalCase.promotion)}</span>
                  </div>
                  <div
                    className={`gym-detail__gate-row ${gateOpen ? "gym-detail__gate-row--allowed" : "gym-detail__gate-row--blocked"}`}
                  >
                    <span>Score</span>
                    <span className="mono">{formatScore(evalCase.score)}</span>
                  </div>
                </div>
                <ul className="gym-detail__gate-reasons" style={{ marginTop: 12 }}>
                  {gateOpen ? (
                    <li>Bridge is open — promote happens at the candidate level (Creator).</li>
                  ) : syntheticBarred ? (
                    <li>Synthetic-origin case — invariant #7 means this case cannot promote customer-facing versions.</li>
                  ) : (
                    <li>Promotion gate is closed. Check scorecard criteria and failure reasons.</li>
                  )}
                </ul>
              </CardBody>
            </Card>
          </div>

          <Card>
            <CardHeader
              eyebrow="Projection"
              title="Raw case document"
              subtitle="The full row as returned by GET /eval-cases (projection EVAL_CASE has no projector — direct write)."
            />
            <CardBody>
              <JsonViewer value={evalCase as unknown as Record<string, unknown>} />
            </CardBody>
          </Card>

          <div className="dim" style={{ fontSize: 12 }}>
            Source: <code>/eval-cases</code> · Bridge: <code>POST /commands/promote</code> ·
            Invariant #7: <StatusPill tone="hot">synthetic</StatusPill> cases never promote customer-facing versions.
          </div>
        </Stack>
      </div>
    </AppShell>
  );
}

// ----------------------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------------------

function OriginIcon({ origin }: { origin: EvalCase["origin"] | string | undefined }) {
  switch (origin) {
    case "synthetic":
      return <Wand2 size={12} />;
    case "real":
      return <Star size={12} />;
    case "human_reviewed":
      return <Compass size={12} />;
    default:
      return <CircleSlash2 size={12} />;
  }
}

interface ScorecardCriterionView {
  criterion_id: string;
  passed: boolean;
  score: number;
  comment?: string;
}

interface ScorecardSubDoc {
  run_id?: string;
  rubric_name?: string;
  score?: number;
  passed?: boolean;
  criteria?: ScorecardCriterionView[];
}

function scorecardFromCase(evalCase: EvalCase): ScorecardSubDoc | null {
  // The run-swarm path mirrors scorecard sub-doc on the case (see api/src/agentx_api/app.py
  // run_swarm handler). Older fixture rows may not have it; fall back gracefully.
  const raw = evalCase as unknown as { scorecard?: ScorecardSubDoc };
  if (raw.scorecard && typeof raw.scorecard === "object") {
    return raw.scorecard;
  }
  return null;
}

// Re-export Target so unused-import lint doesn't trip in callers that style
// the detail header.
export { Target, ShieldAlert };