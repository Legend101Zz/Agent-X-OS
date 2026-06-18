import { Ban, Box, Plus, TerminalSquare } from "lucide-react";
import type { DashboardData } from "@/lib/types";
import { GapNotice, Panel, stagger, StatusPill } from "./shared";

interface CatalogCreateProps {
  data: DashboardData;
}

export function CatalogCreate({ data }: CatalogCreateProps) {
  const createGap =
    data.coreGaps.find((gap) => gap.id === "command.instantiate") ??
    data.coreGaps.find((gap) => gap.id === "gap-create-instance") ??
    data.coreGaps[0];

  return (
    <div className="catalog-layout">
      <Panel title="Mandate Catalog" eyebrow="available operating packs">
        <div className="mandate-grid">
          {data.mandateTypes.map((mandate, index) => (
            <article className="mandate-card" key={mandate.id} style={stagger(index)}>
              <div className="mandate-icon">
                {mandate.status === "ready" ? <Box size={20} /> : <Ban size={20} />}
              </div>
              <div>
                <h3>{mandate.title}</h3>
                <p>{mandate.unit_economics}</p>
              </div>
              <div className="mandate-meta">
                <StatusPill
                  label={mandate.stage}
                  tone={mandate.status === "ready" ? "good" : mandate.status === "gap" ? "warn" : "hot"}
                />
                <span>floor: {mandate.ring_floor}</span>
              </div>
              <div className="command-chip-row">
                {mandate.commands.map((command) => (
                  <span className="command-chip" key={command}>
                    {command}
                  </span>
                ))}
              </div>
            </article>
          ))}
        </div>
      </Panel>

      <Panel title="Create Instance" eyebrow="staged request">
        <form className="create-form">
          <label>
            Business
            <input defaultValue="New customer account" />
          </label>
          <label>
            Mandate
            <select defaultValue="indian_b2b_lead_finder">
              {data.mandateTypes.map((mandate) => (
                <option key={mandate.id} value={mandate.id}>
                  {mandate.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            Ring
            <select defaultValue="L0">
              <option value="L0">L0</option>
              <option value="L1">L1</option>
              <option value="L2">L2</option>
            </select>
          </label>
          <button className="command-button primary disabled" disabled type="button">
            <Plus size={16} />
            Submit
          </button>
        </form>
        <div className="form-terminal">
          <TerminalSquare size={18} />
          <span>command: instantiate_instance</span>
        </div>
        <GapNotice gap={createGap} />
      </Panel>
    </div>
  );
}
