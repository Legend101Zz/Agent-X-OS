"use client";

import { Ban, Box, Plus, TerminalSquare } from "lucide-react";
import { useState } from "react";
import type { CommandResult, CoreGap, DashboardData } from "@/lib/types";
import { GapNotice, Panel, stagger, StatusPill } from "./shared";

interface CatalogCreateProps {
  data: DashboardData;
  operatorToken: string;
  apiBaseUrl: string;
  commandResult?: CommandResult;
  onCommandResult: (result: CommandResult) => void;
  onRefresh: () => void;
}

interface SubmitState {
  status: "idle" | "submitting" | "ok" | "error";
  message?: string;
  instanceId?: string;
}

const EMPTY_TARGET: { icp: string; location: string; count: string } = {
  icp: "",
  location: "",
  count: "",
};

export function CatalogCreate({
  data,
  operatorToken,
  apiBaseUrl,
  commandResult,
  onCommandResult,
  onRefresh,
}: CatalogCreateProps) {
  const [businessName, setBusinessName] = useState("Acme Dental Co");
  const [typeRef, setTypeRef] = useState<string>(
    data.mandateTypes[0]?.id ? `${data.mandateTypes[0].title.toLowerCase().replace(/\s+/g, "_")}@${data.mandateTypes[0].stage}` : "lead-finder@0.1.0"
  );
  const [ring, setRing] = useState("L1");
  const [target, setTarget] = useState(EMPTY_TARGET);
  const [submit, setSubmit] = useState<SubmitState>({ status: "idle" });

  // Find the matching mandate type by name@version (data.mandateTypes.id is the catalog id).
  const selectedMandate = data.mandateTypes.find((m) => {
    const id = `${m.title.toLowerCase().replace(/\s+/g, "_")}@${m.stage}`;
    return id === typeRef;
  });

  const submitEnabled = submit.status !== "submitting" && Boolean(operatorToken);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!operatorToken) {
      setSubmit({ status: "error", message: "Set AGENTX_OPERATOR_TOKEN in the API to enable writes." });
      return;
    }
    setSubmit({ status: "submitting" });
    const targetOverride: Record<string, unknown> = {};
    if (target.icp.trim()) targetOverride.icp = target.icp.trim();
    if (target.location.trim()) targetOverride.location = target.location.trim();
    if (target.count.trim()) {
      const parsed = Number.parseInt(target.count, 10);
      if (Number.isFinite(parsed)) targetOverride.count = parsed;
    }
    const payload = {
      type_ref: typeRef,
      customer_id: businessName.trim(),
      business_name: businessName.trim(),
      ring,
      target_override: Object.keys(targetOverride).length > 0 ? targetOverride : null,
      actor: "dashboard/operator",
    };
    try {
      const response = await fetch(`${apiBaseUrl}/commands/instantiate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${operatorToken}`,
        },
        body: JSON.stringify(payload),
      });
      const body = await response.json();
      if (!response.ok) {
        const message = typeof body?.detail === "string" ? body.detail : response.statusText;
        const result: CommandResult = { supported: false, message };
        setSubmit({ status: "error", message });
        onCommandResult(result);
        return;
      }
      const result: CommandResult = {
        supported: true,
        status: "created",
        message: `instance ${body.instance?.id} created`,
      };
      setSubmit({ status: "ok", instanceId: body.instance?.id, message: result.message });
      onCommandResult(result);
      onRefresh();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Network error";
      const result: CommandResult = { supported: false, message };
      setSubmit({ status: "error", message });
      onCommandResult(result);
    }
  }

  const errorGap: CoreGap | undefined = submit.status === "error"
    ? {
        id: "dashboard.command_failed",
        title: "Command failed",
        detail: submit.message ?? "instantiate rejected",
      }
    : undefined;

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
        <form className="create-form" onSubmit={handleSubmit}>
          <label>
            Business
            <input
              value={businessName}
              onChange={(event) => setBusinessName(event.target.value)}
              placeholder="Acme Dental Co"
              required
            />
          </label>
          <label>
            Mandate
            <select value={typeRef} onChange={(event) => setTypeRef(event.target.value)}>
              {data.mandateTypes.map((mandate) => {
                const id = `${mandate.title.toLowerCase().replace(/\s+/g, "_")}@${mandate.stage}`;
                return (
                  <option key={mandate.id} value={id}>
                    {mandate.title} @ {mandate.stage}
                  </option>
                );
              })}
              {!selectedMandate && <option value="lead-finder@0.1.0">lead-finder @ 0.1.0</option>}
            </select>
          </label>
          <label>
            Ring
            <select value={ring} onChange={(event) => setRing(event.target.value)}>
              <option value="L0">L0</option>
              <option value="L1">L1</option>
              <option value="L2">L2</option>
            </select>
          </label>
          <fieldset className="target-fields">
            <legend>Target (optional ICP overrides)</legend>
            <label>
              ICP
              <input
                value={target.icp}
                onChange={(event) => setTarget((prev) => ({ ...prev, icp: event.target.value }))}
                placeholder="dental clinics in Pune"
              />
            </label>
            <label>
              Location
              <input
                value={target.location}
                onChange={(event) => setTarget((prev) => ({ ...prev, location: event.target.value }))}
                placeholder="Pune, India"
              />
            </label>
            <label>
              Count
              <input
                value={target.count}
                onChange={(event) => setTarget((prev) => ({ ...prev, count: event.target.value }))}
                placeholder="3"
                inputMode="numeric"
              />
            </label>
          </fieldset>
          <button
            className={submitEnabled ? "command-button primary" : "command-button primary disabled"}
            disabled={!submitEnabled}
            type="submit"
          >
            <Plus size={16} />
            {submit.status === "submitting" ? "Submitting…" : "Submit"}
          </button>
        </form>
        <div className="form-terminal">
          <TerminalSquare size={18} />
          <span>command: instantiate_instance → {businessName || "(unnamed)"}</span>
        </div>
        {submit.status === "ok" && submit.instanceId && (
          <p className="receipt-line">
            instance <code>{submit.instanceId}</code> persisted — go to Instance File to trigger a run.
          </p>
        )}
        {commandResult && <p className="receipt-line">{commandResult.message ?? commandResult.receipt}</p>}
        {errorGap ? <GapNotice gap={errorGap} /> : null}
      </Panel>
    </div>
  );
}
