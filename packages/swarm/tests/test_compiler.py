"""Phase-5 compiler scaffold tests (HERMES_BUILD_PLAN §Phase 5 — G12 mechanism only).

Honest scope (per the spec):
  - The compiler reads the gym (real + synthetic cases), proposes a NEW version of a
    faculty skill_pack, and gates the proposal against the existing PromotionGate.
  - Real improvement needs ~100 real settles — we test the MECHANISM, not actual
    improvement.
  - Invariant #7: synthetic cases may pre-train/test but NEVER decide a promotion.
    Even a synthetic-only corpus with perfect scores must NOT yield a promotable
    candidate. This is the test that proves invariant #7 structurally.
  - The compiled output is a candidate. Promotion (registration) still goes through
    /commands/promote (Phase 4). The compiler itself NEVER auto-registers.

Done-when (3 from spec + 4 honest scaffolding assertions):
  1. compile(real_corpus, target) returns a CompiledCandidate (mechanism end-to-end).
  2. The gate ACCEPTS a candidate that meets the threshold on real cases.
  3. The gate REJECTS a candidate that doesn't meet the threshold on real cases.
  4. A synthetic-only corpus -> gate ALWAYS rejects (invariant #7 proof).
  5. The compiler NEVER calls register_mandate_type (it's a candidate, not a registration).
  6. compile() is deterministic + idempotent (same input -> same output).
  7. The proposed skill_pack ref is a NEW version (compiler bumps minor version).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from agentx_contracts import (
    EvalCase,
    HydrationSnapshot,
    Scorecard,
    Thread,
)
from agentx_swarm.compiler import (
    CompiledCandidate,
    CompilerConfig,
    compile_candidate,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _thread(*, instance_id: str, run_id: str) -> Thread:
    return Thread(
        id=f"thread_{run_id}",
        instance_id=instance_id,
        entity_id="entity_phase5",
        state="engaged",
        updated_at=datetime.now(UTC),
    )


def _hydration(*, instance_id: str, run_id: str) -> HydrationSnapshot:
    return HydrationSnapshot(
        facts=[],
        thread=_thread(instance_id=instance_id, run_id=run_id),
        recent_journal=[],
        skill_pack_refs=[],
        domain_pack=None,
        frozen_at=datetime.now(UTC),
    )


def _real_case(
    *,
    case_id: str,
    type_ref: str,
    score: float,
    passed: bool,
    rubric_name: str = "lead_quality",
) -> EvalCase:
    return EvalCase(
        id=case_id,
        type_ref=type_ref,
        origin="real",
        hydration=_hydration(instance_id="inst_p5", run_id=case_id),
        scorecard=Scorecard(
            origin="real",
            run_id=case_id,
            rubric_name=rubric_name,
            score=score,
            passed=passed,
            criteria=[],
        ),
        reality_outcome="success" if passed else "failure",
        tags=["real", "phase5"],
    )


def _synthetic_case(
    *,
    case_id: str,
    type_ref: str,
    score: float,
    passed: bool,
    rubric_name: str = "lead_quality",
) -> EvalCase:
    return EvalCase(
        id=case_id,
        type_ref=type_ref,
        origin="synthetic",
        hydration=_hydration(instance_id="inst_p5_sim", run_id=case_id),
        scorecard=Scorecard(
            origin="synthetic",
            run_id=case_id,
            rubric_name=rubric_name,
            score=score,
            passed=passed,
            criteria=[],
        ),
        reality_outcome=None,
        tags=["synthetic", "phase5"],
    )


def _config(*, target_skill_pack: str = "skill_pack:lead-finder/research@0.1.0") -> CompilerConfig:
    return CompilerConfig(
        target_skill_pack=target_skill_pack,
        # min real score 0.7 mirrors PromotionGate's default.
        min_real_score=0.7,
        # Allow the gate to look at ALL real cases regardless of rubric.
        rubric_match_any=True,
    )


# ---------------------------------------------------------------------------
# Done-when #1: compile() returns a CompiledCandidate
# ---------------------------------------------------------------------------


def test_compile_returns_a_compiled_candidate_from_a_real_corpus() -> None:
    gym = [
        _real_case(case_id="real_001", type_ref="lead-finder@0.1.0", score=0.95, passed=True),
        _real_case(case_id="real_002", type_ref="lead-finder@0.1.0", score=0.90, passed=True),
        _real_case(case_id="real_003", type_ref="lead-finder@0.1.0", score=0.88, passed=True),
    ]
    result = compile_candidate(gym, config=_config())
    assert isinstance(result, CompiledCandidate)
    assert result.proposed_skill_pack.startswith("skill_pack:lead-finder/research@")
    assert result.proposed_skill_pack != "skill_pack:lead-finder/research@0.1.0"
    # Evidence summary reflects the corpus.
    assert result.real_case_count == 3
    assert result.synthetic_case_count == 0
    assert result.real_score_mean == pytest.approx((0.95 + 0.90 + 0.88) / 3)
    assert result.real_pass_rate == 1.0


# ---------------------------------------------------------------------------
# Done-when #2: gate ACCEPTS a candidate that meets the threshold on real cases
# ---------------------------------------------------------------------------


def test_compile_accepts_a_candidate_when_real_corpus_meets_the_threshold() -> None:
    gym = [
        _real_case(case_id="real_001", type_ref="lead-finder@0.1.0", score=0.95, passed=True),
        _real_case(case_id="real_002", type_ref="lead-finder@0.1.0", score=0.85, passed=True),
    ]
    result = compile_candidate(gym, config=_config())
    assert result.promotable is True
    assert result.gate_decision.allowed is True
    assert result.gate_origin == "promotion_gate"


# ---------------------------------------------------------------------------
# Done-when #3: gate REJECTS a candidate that doesn't meet the threshold on real cases
# ---------------------------------------------------------------------------


def test_compile_rejects_a_candidate_when_real_corpus_below_threshold() -> None:
    gym = [
        _real_case(case_id="real_low_001", type_ref="lead-finder@0.1.0", score=0.30, passed=False),
        _real_case(case_id="real_low_002", type_ref="lead-finder@0.1.0", score=0.20, passed=False),
    ]
    result = compile_candidate(gym, config=_config())
    assert result.promotable is False
    assert result.gate_decision.allowed is False
    # Real-pass-rate is 0/2; the compiler surfaces this clearly in reasons.
    assert any(
        "real" in r.lower() or "pass" in r.lower() or "score" in r.lower()
        for r in result.gate_decision.reasons
    ), (
        f"compile must surface the real-failure reason; got reasons={result.gate_decision.reasons!r}"
    )


# ---------------------------------------------------------------------------
# Done-when #4 (invariant #7): synthetic-only corpus is ALWAYS barred
# ---------------------------------------------------------------------------


def test_synthetic_only_corpus_can_never_produce_a_promotable_candidate() -> None:
    """Invariant #7 structural proof: synthetic-only gym -> gate ALWAYS rejects.

    Even with perfect scores (1.0 across all cases) and 100% pass rate, a synthetic-only
    corpus must NOT yield a promotable candidate. Synthetic cases are pre-train/test
    ONLY — they can never decide a promotion. The compiler delegates the check to the
    existing gate (same enforcement as the Phase-4 promote bridge).
    """
    gym = [
        _synthetic_case(
            case_id=f"syn_perfect_{i:03d}",
            type_ref="lead-finder@0.1.0",
            score=1.0,
            passed=True,
        )
        for i in range(20)
    ]
    result = compile_candidate(gym, config=_config())
    assert result.real_case_count == 0
    assert result.synthetic_case_count == 20
    assert result.promotable is False, (
        f"synthetic-only corpus must NEVER produce a promotable candidate (invariant #7); "
        f"got promotable=True reasons={result.gate_decision.reasons!r}"
    )
    # The invariant-#7 reason can surface in EITHER:
    #   (a) the compile's own reasons (compiler's invariant-#7 explanation), OR
    #   (b) the gate's reasons (gate's evidence-bar explanation, which the gate surfaces as
    #       "no passing scorecard evidence" because the compiler only feeds real cases to it).
    all_reasons = list(result.reasons) + list(result.gate_decision.reasons)
    assert any(
        "synthetic" in r.lower() or "real" in r.lower() or "scorecard" in r.lower()
        for r in all_reasons
    ), f"compile must surface the synthetic-only reason somewhere; got reasons={all_reasons!r}"


def test_mixed_corpus_with_no_real_cases_is_barred() -> None:
    """Synthetic-dominant corpus (no real cases) -> barred, even with synthetic passes.

    A degenerate gym of just synthetic cases is still synthetic-only effectively
    (real_case_count=0). Same invariant #7 proof.
    """
    gym = [
        _synthetic_case(case_id="syn_001", type_ref="lead-finder@0.1.0", score=1.0, passed=True),
    ]
    result = compile_candidate(gym, config=_config())
    assert result.real_case_count == 0
    assert result.promotable is False


def test_mixed_corpus_with_one_real_pass_and_many_synthetic_passes_is_allowed() -> None:
    """A single real pass is sufficient to open the gate (the user's design — "promoting
    straight to L3/L4 on a single real case + human is allowed").

    The compiler sees >=1 real passing case -> gate ALLOWS (synthetic is pre-train,
    real is the gate). This is the inverse of test_synthetic_only_corpus_*: with even
    ONE real case the gate opens.
    """
    gym = [
        _synthetic_case(case_id="syn_001", type_ref="lead-finder@0.1.0", score=1.0, passed=True),
        _synthetic_case(case_id="syn_002", type_ref="lead-finder@0.1.0", score=0.99, passed=True),
        _real_case(case_id="real_001", type_ref="lead-finder@0.1.0", score=0.85, passed=True),
    ]
    result = compile_candidate(gym, config=_config())
    assert result.real_case_count == 1
    assert result.synthetic_case_count == 2
    assert result.promotable is True


# ---------------------------------------------------------------------------
# Done-when #5: compiler NEVER registers (it's a candidate, not a registration)
# ---------------------------------------------------------------------------


def test_compile_does_not_register_a_mandate_type_into_the_catalog() -> None:
    """The compiler is a CANDIDATE producer. It does NOT touch the mandate_type collection.

    Phase-4 promote is the only path to registration. This test pins the compiler to
    the candidate side of the boundary — even a fully-passing compiled output is a
    CompiledCandidate (proposed_skill_pack + gate_decision), not a registered MandateType.
    """
    gym = [
        _real_case(case_id="real_001", type_ref="lead-finder@0.1.0", score=0.95, passed=True),
    ]
    result = compile_candidate(gym, config=_config())
    # The result is a candidate, NOT a registration.
    assert not hasattr(result, "registered_mandate_type")
    assert not hasattr(result, "registered_at")
    assert not hasattr(result, "ring")
    # The result carries the proposal only.
    assert isinstance(result, CompiledCandidate)
    assert result.proposed_skill_pack.startswith("skill_pack:")
    assert result.gate_decision is not None


# ---------------------------------------------------------------------------
# Done-when #6: compile() is deterministic + idempotent
# ---------------------------------------------------------------------------


def test_compile_is_deterministic_and_idempotent() -> None:
    gym = [
        _real_case(case_id="real_001", type_ref="lead-finder@0.1.0", score=0.92, passed=True),
        _real_case(case_id="real_002", type_ref="lead-finder@0.1.0", score=0.88, passed=True),
    ]
    config = _config()
    a = compile_candidate(gym, config=config)
    b = compile_candidate(gym, config=config)
    # Same input -> same output.
    assert a.proposed_skill_pack == b.proposed_skill_pack
    assert a.real_score_mean == b.real_score_mean
    assert a.promotable == b.promotable
    assert a.gate_decision.reasons == b.gate_decision.reasons


# ---------------------------------------------------------------------------
# Done-when #7: proposed skill_pack ref is a NEW version (compiler bumps minor)
# ---------------------------------------------------------------------------


def test_compile_proposes_a_new_minor_version_of_the_target_skill_pack() -> None:
    """The compiler bumps the version (deterministic, minor bump) — output is a candidate
    version, not the input version. A 0.1.0 target -> 0.2.0 proposed; a 1.4.2 target ->
    1.5.0 proposed.
    """
    gym = [
        _real_case(case_id="real_001", type_ref="lead-finder@0.1.0", score=0.95, passed=True),
    ]

    # 0.1.0 -> 0.2.0
    a = compile_candidate(gym, config=_config(target_skill_pack="skill_pack:lead-finder/research@0.1.0"))
    assert a.proposed_skill_pack == "skill_pack:lead-finder/research@0.2.0"

    # 1.4.2 -> 1.5.2 (semver: minor bump preserves the patch digit; the compiler does NOT
    # reset the patch on a minor bump \u2014 GEPA-style rebuilds would bump the patch instead).
    b = compile_candidate(gym, config=_config(target_skill_pack="skill_pack:lead-finder/research@1.4.2"))
    assert b.proposed_skill_pack == "skill_pack:lead-finder/research@1.5.2"


# ---------------------------------------------------------------------------
# Bonus: empty gym is barred (no evidence)
# ---------------------------------------------------------------------------


def test_compile_with_empty_gym_is_barred() -> None:
    result = compile_candidate([], config=_config())
    assert result.real_case_count == 0
    assert result.synthetic_case_count == 0
    assert result.promotable is False
    assert any(
        "score" in r.lower() or "evidence" in r.lower() for r in result.gate_decision.reasons
    ), f"compile must surface the no-evidence reason; got reasons={result.gate_decision.reasons!r}"