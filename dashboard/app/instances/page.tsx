import { InstancesList } from "../../src/components/instances/instances-list";

/**
 * `/instances` — the entry point to the per-instance deep Inspector (C2).
 * Click a row to navigate to `/instances/{id}` and see the Overview /
 * Live Activity / Runs / Approvals / Trust tabs (Memory + Actions land in
 * C4 once the C3 heap API ships).
 */
export default function InstancesPage() {
  return <InstancesList />;
}
