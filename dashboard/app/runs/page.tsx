import { Suspense } from "react";
import { RunsList } from "../../src/components/runs/runs-list";

/**
 * /runs — the cross-instance Runs list (C6).
 *
 * Wrapped in a <Suspense> boundary because the component reads
 * `useSearchParams()` (filter pills / query string), which Next.js
 * disallows in a server component without a Suspense fallback.
 */
export default function RunsPage() {
  return (
    <Suspense fallback={null}>
      <RunsList />
    </Suspense>
  );
}
