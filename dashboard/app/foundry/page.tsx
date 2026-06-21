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

export default function FoundryPage() {
  return (
    <AppShell title="Foundry" crumbs={[{ label: "Foundry" }]}>
      <FoundryView />
    </AppShell>
  );
}
