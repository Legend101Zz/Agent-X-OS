import StubPage from "../_components/stub-page";

export default function GymPage() {
  return (
    <StubPage
      title="Gym"
      cardId="C8"
      cardTitle="C8 — Gym & Evals (cases, scores, promote gate, compiler scaffold)"
      description="Eval cases, scores, promotion gate, compiler scaffold status."
      blockedFeatures={[{ key: "eval_case_detail", label: "Eval-case detail (needs C9)" }]}
    />
  );
}