"use client";

/**
 * C7 — Approvals inbox page.
 *
 * Lives at /approvals per BLUEPRINT §5 Approvals row. Three commands —
 * approve / reject / edit-with-diff — drive the first-class gate UX. Every
 * command goes through an `AsyncButton` and surfaces a toast on success or
 * failure. The edit modal previews the diff before the operator commits.
 */

import { AppShell } from "../../src/components/shell/app-shell";
import { ApprovalsInbox } from "../../src/components/approvals-inbox";
import { HelpPanel, InfoTip } from "../../src/components/ui";
import { useOperator } from "../../src/providers/operator-provider";

export default function ApprovalsPage() {
  const { baseUrl, token } = useOperator();

  return (
    <AppShell title="Approvals" crumbs={[{ label: "Approvals" }]}>
      <HelpPanel id="approvals">
        <p>
          This is the approval gate <InfoTip term="approval" />. When an instance wants to take a
          risky action, it parks the run here and waits for you.
        </p>
        <p>
          <strong>Approve</strong> lets it proceed, <strong>Reject</strong> stops it, and{" "}
          <strong>Edit</strong> lets you change the action (you&apos;ll see a diff) before it runs.
          Low-trust instances (rings <InfoTip term="ring" />) park more often.
        </p>
      </HelpPanel>
      <ApprovalsInbox apiBaseUrl={baseUrl} operatorToken={token} />
    </AppShell>
  );
}
