import StubPage from "../_components/stub-page";

export default function EconomyPage() {
  return (
    <StubPage
      title="Economy"
      cardId="C16"
      cardTitle="C16 — Economy / P&L view (per-instance + per business unit)"
      description="P&L per instance and per business unit."
      blockedFeatures={[{ key: "economy_pnl", label: "Economy API (needs C15)" }]}
    />
  );
}