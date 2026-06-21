"use client";

/**
 * C12 — Providers / Connectors view page.
 *
 * Per BLUEPRINT §5 row "Providers": adapters, Exa / Firecrawl, email transport,
 * and model routing with health + credential pills. Renders the
 * `<ProvidersView>` inside the AppShell (so the left rail / top bar from C1
 * are mounted). The view itself is responsible for graceful disable, the
 * loading / empty / error states, and the AsyncButton feedback contract.
 */

import { AppShell } from "../../src/components/shell/app-shell";
import { ProvidersView } from "../../src/components/providers/providers-view";

export default function ProvidersPage() {
  return (
    <AppShell title="Providers" crumbs={[{ label: "Providers" }]}>
      <ProvidersView />
    </AppShell>
  );
}
