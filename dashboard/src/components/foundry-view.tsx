import { FlaskConical, LockKeyhole, Trophy } from "lucide-react";
import type { DashboardData } from "@/lib/types";
import { EmptyState, Panel, ProgressBar, StatusPill } from "./shared";

interface FoundryViewProps {
  data: DashboardData;
}

export function FoundryView({ data }: FoundryViewProps) {
  if (data.evalCases.length === 0) {
    return <EmptyState label="No eval cases available." />;
  }

  const eligible = data.evalCases.filter((testCase) => testCase.promotion === "eligible").length;

  return (
    <div className="view-stack">
      <Panel title="Foundry" eyebrow="swarm eval cases">
        <div className="foundry-score">
          <div>
            <FlaskConical size={28} />
            <strong>{data.evalCases[0]?.pack}</strong>
            <span>{data.evalCases.length} cases loaded</span>
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

      <Panel title="Eval Cases" eyebrow="judge scorecard">
        <div className="eval-grid">
          {data.evalCases.map((testCase) => (
            <article className="eval-card" key={testCase.id}>
              <div>
                <p className="eyebrow">{testCase.origin}</p>
                <h3>{testCase.title}</h3>
              </div>
              <ProgressBar value={Math.round(testCase.score * 100)} />
              <div className="eval-footer">
                <StatusPill label={testCase.status} tone="good" />
                <StatusPill label={testCase.promotion} tone={testCase.promotion === "eligible" ? "good" : "hot"} />
              </div>
            </article>
          ))}
        </div>
      </Panel>
    </div>
  );
}
