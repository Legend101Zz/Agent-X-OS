import { Cable, Route, Shield } from "lucide-react";
import type { DashboardData } from "@/lib/types";
import { Panel, StatusPill } from "./shared";

interface CapabilityRegistryProps {
  data: DashboardData;
}

export function CapabilityRegistry({ data }: CapabilityRegistryProps) {
  return (
    <Panel title="Capability Registry" eyebrow="syscall ladder">
      <div className="capability-grid">
        {data.capabilities.map((capability) => (
          <article className="capability-card" key={capability.id}>
            <div className="capability-title">
              <Cable size={18} />
              <div>
                <h3>{capability.title}</h3>
                <span>{capability.syscall}</span>
              </div>
            </div>
            <div className="capability-meta">
              <StatusPill label={capability.maturity} tone={capability.maturity === "live" ? "good" : "neutral"} />
              <StatusPill label={capability.health} tone={capability.health === "healthy" ? "good" : "warn"} />
            </div>
            <div className="registry-line">
              <Route size={14} />
              <span>{capability.queue_volume} queued</span>
            </div>
            <div className="registry-line">
              <Shield size={14} />
              <span>{capability.credential_boundary}</span>
            </div>
            <div className="terminal-fallback">
              terminal fallback: {capability.terminal_fallback ? "yes" : "no"}
            </div>
          </article>
        ))}
      </div>
    </Panel>
  );
}
