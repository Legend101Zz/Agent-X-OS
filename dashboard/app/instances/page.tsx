import StubPage from "../_components/stub-page";

export default function InstancesPage() {
  return (
    <StubPage
      title="Instances"
      cardId="C2"
      cardTitle="C2 — Instances list + Instance Inspector (Overview/Activity/Runs/Approvals/Trust)"
      description="Every mandate instance in one place. Drill into the deep Inspector for live trace, memory, actions, runs, and trust."
      blockedFeatures={[{ key: "heap_read", label: "Memory / Heap (needs C3)" }]}
    />
  );
}