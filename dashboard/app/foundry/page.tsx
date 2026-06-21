"use client";

/**
 * C10 — Foundry / Swarm wind-tunnel (SPEC §5).
 *
 * Thin route shell: mounts AppShell + the FoundryView. The view itself
 * holds the type_ref / pack / ring selectors, the Run Swarm AsyncButton,
 * the mono timeline of SwarmTraceEvent, the scorecard criteria table,
 * and the gate decision banner. All helpers are unit-tested in
 * dashboard/tests/foundry.test.ts.
 */
import { AppShell } from "../../src/components/shell/app-shell";
import { FoundryView } from "../../src/components/foundry/foundry-view";
import { HelpPanel, InfoTip } from "../../src/components/ui";

export default function FoundryPage() {
  return (
    <AppShell title="Foundry" crumbs={[{ label: "Foundry" }]}>
      <HelpPanel id="foundry">
        <p>
          The swarm wind-tunnel <InfoTip term="swarm" />. Run a blueprint against synthetic
          scenarios and a judge to see how it behaves <em>before</em> it touches a real customer.
          Watch the trace, the scorecard, and the gate decision.
        </p>
        <p>
          Synthetic results <InfoTip term="origin" /> can train a blueprint but can never promote a
          customer-facing version — only real cases can.
        </p>
      </HelpPanel>
      <FoundryView />
    </AppShell>
  );
}
