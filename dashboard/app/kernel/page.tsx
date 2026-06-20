import StubPage from "../_components/stub-page";

export default function KernelPage() {
  return (
    <StubPage
      title="Kernel"
      cardId="C14"
      cardTitle="C14 — Kernel / System view (journal, scheduler, health, core-gaps)"
      description="JournalEvent stream, scheduler queue, system health, core-gaps."
      blockedFeatures={[{ key: "scheduler_work_list", label: "Scheduler work list (needs C13)" }]}
    />
  );
}