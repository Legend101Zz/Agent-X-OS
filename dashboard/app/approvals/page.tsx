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
import { useOperator } from "../../src/providers/operator-provider";

export default function ApprovalsPage() {
  const { baseUrl, token } = useOperator();

  return (
    <AppShell title="Approvals" crumbs={[{ label: "Approvals" }]}>
      <ApprovalsInbox apiBaseUrl={baseUrl} operatorToken={token} />
    </AppShell>
  );
}
