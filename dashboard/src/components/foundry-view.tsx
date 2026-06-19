"use client";

import { FlaskConical, LockKeyhole, Play, Trophy } from "lucide-react";
import { useState } from "react";
import { runSwarm } from "@/lib/api";
import type { DashboardData, SwarmRunReport } from "@/lib/types";
import { GapNotice, Panel, ProgressBar, StatusPill } from "./shared";
import { SwarmTimeline } from "./swarm-timeline";

interface FoundryViewProps {
  data: DashboardData;
  operatorToken: string;
  apiBaseUrl: string;
  onRefresh: () => void;
}

interface SubmitState {
  status: "idle" | "submitting" | "ok" | "error";
  message?: string;
}

// indian_b2b_leads_v1 is the only bundled Phase-1 scenario pack (packages/swarm/.../scenario_packs).
const SCENARIO_PACKS = ["indian_b2b_leads_v1"];

function mandateTypeRef(title: string, stage: string): string {
  return `${title.toLowerCase().replace(/\s+/g, "_")}@${stage}`;
}

export function FoundryView({ data, operatorToken, apiBaseUrl, onRefresh }: FoundryViewProps) {
  const firstMandate = data.mandateTypes[0];
  const [typeRef, setTypeRef] = useState<string>(
    firstMandate ? mandateTypeRef(firstMandate.title, firstMandate.stage) : "lead-finder@0.1.0",
  );
  const [packId, setPackId] = useState<string>(SCENARIO_PACKS[0]);
  const [ring, setRing] = useState<string>("L2");
  const [judgeLive, setJudgeLive] = useState<boolean>(false);
  const [submit, setSubmit] = useState<SubmitState>({ status: "idle" });
  const [report, setReport] = useState<SwarmRunReport | null>(null);

  const submitEnabled = submit.status !== "submitting" && Boolean(operatorToken);
  const eligible = data.evalCases.filter((testCase) => testCase.promotion === "eligible").length;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!operatorToken) {
      setSubmit({ status: "error", message: "Set AGENTX_OPERATOR_TOKEN in the dashboard to enable writes." });
      return;
    }
    setSubmit({ status: "submitting" });
    const result = await runSwarm(
      { type_ref: typeRef, pack_id: packId, ring, judge_live: judgeLive, actor: "dashboard/operator" },
      { baseUrl: apiBaseUrl, token: operatorToken },
    );
    if (result.source !== "api" || !result.data.supported) {
      const message = result.error ?? result.data.message ?? "run-swarm rejected";
      setSubmit({ status: "error", message });
      return;
    }
    setReport(result.data);
    setSubmit({
      status: "ok",
      message: `graded ${result.data.scorecard ? Math.round(result.data.scorecard.score * 100) : 0}% · gate ${
        result.data.gate_decision?.allowed ? "open" : "blocked"
      }`,
    });
    onRefresh();
  }

  return (
    <div className="view-stack">
      <Panel title="Foundry" eyebrow="swarm REPL">
        <div className="foundry-score">
          <div>
            <FlaskConical size={28} />
            <strong>{data.evalCases.length}</strong>
            <span>synthetic cases</span>
          </div>
          <div>
            <Trophy size={28} />
            <strong>{eligible}</strong>
            <span>promotion eligible</span>
          </div>
          <div>
            <LockKeyhole size={28} />
            <strong>synthetic-only blocked</strong>
            <span>PromotionGate active</span>
          </div>
        </div>
      </Panel>

      <div className="swarm-repl">
        <Panel title="Run a swarm" eyebrow="sim wind tunnel">
          <form className="create-form" onSubmit={handleSubmit}>
            <label>
              Candidate mandate
              <select value={typeRef} onChange={(event) => setTypeRef(event.target.value)}>
                {data.mandateTypes.map((mandate) => {
                  const id = mandateTypeRef(mandate.title, mandate.stage);
                  return (
                    <option key={mandate.id} value={id}>
                      {mandate.title} @ {mandate.stage}
                    </option>
                  );
                })}
                {data.mandateTypes.length === 0 && (
                  <option value="lead-finder@0.1.0">lead-finder @ 0.1.0</option>
                )}
              </select>
            </label>
            <label>
              Scenario pack
              <select value={packId} onChange={(event) => setPackId(event.target.value)}>
                {SCENARIO_PACKS.map((pack) => (
                  <option key={pack} value={pack}>
                    {pack}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Ring
              <select value={ring} onChange={(event) => setRing(event.target.value)}>
                <option value="L0">L0</option>
                <option value="L1">L1</option>
                <option value="L2">L2 (drafts run via SimAdapter)</option>
              </select>
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={judgeLive}
                onChange={(event) => setJudgeLive(event.target.checked)}
              />
              Use live promptfoo judge (requires JUDGE_MODEL_ID + OPENROUTER_API_KEY)
            </label>
            <button
              className={submitEnabled ? "command-button primary" : "command-button primary disabled"}
              disabled={!submitEnabled}
              type="submit"
            >
              <Play size={16} />
              {submit.status === "submitting" ? "Running…" : "Run swarm"}
            </button>
          </form>
          {submit.status === "ok" && submit.message && <p className="receipt-line">{submit.message}</p>}
          {submit.status === "error" && submit.message ? (
            <GapNotice
              gap={{ id: "dashboard.run_swarm_failed", title: "Run swarm failed", detail: submit.message }}
            />
          ) : null}
          {!operatorToken && (
            <p className="token-help">
              No operator token set — the run button is disabled until you provide one in the rail.
            </p>
          )}
        </Panel>

        <SwarmTimeline report={report} running={submit.status === "submitting"} />
      </div>

      {data.evalCases.length > 0 ? (
        <Panel title="Eval Cases" eyebrow="judge scorecards">
          <div className="eval-grid">
            {data.evalCases.map((testCase) => (
              <article className="eval-card" key={testCase.id}>
                <div>
                  <p className="eyebrow">
                    {testCase.origin} · {testCase.pack}
                  </p>
                  <h3>{testCase.title}</h3>
                </div>
                <ProgressBar value={Math.round(testCase.score * 100)} />
                <div className="eval-footer">
                  <StatusPill label={testCase.status} tone="good" />
                  <StatusPill
                    label={testCase.promotion}
                    tone={testCase.promotion === "eligible" ? "good" : "hot"}
                  />
                </div>
              </article>
            ))}
          </div>
        </Panel>
      ) : (
        <Panel title="Eval Cases" eyebrow="judge scorecards">
          <p className="receipt-line">
            No eval cases yet — run your first swarm above to persist a synthetic scorecard.
          </p>
        </Panel>
      )}
    </div>
  );
}
