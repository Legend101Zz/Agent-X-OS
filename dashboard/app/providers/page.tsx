import StubPage from "../_components/stub-page";

export default function ProvidersPage() {
  return (
    <StubPage
      title="Providers"
      cardId="C12"
      cardTitle="C12 — Providers / Connectors view"
      description="Adapters + Exa / Firecrawl / email / IMAP / model routing with health + credential pills."
      blockedFeatures={[{ key: "capability_health", label: "Capability health detail (needs C11)" }]}
    />
  );
}