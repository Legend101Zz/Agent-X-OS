import { RunDetail } from "../../../src/components/runs/run-detail";

/**
 * /runs/{id} — per-run trace timeline (C6).
 *
 * The route is intentionally a thin wrapper around the client component
 * so Next.js's static prerender keeps working. Filtering / SSE / JSON
 * inspector all live in `run-detail.tsx`.
 */
export default async function RunDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <RunDetail runId={id} />;
}
