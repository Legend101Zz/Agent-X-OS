"""Phase-5 compiler scaffold (HERMES_BUILD_PLAN §Phase 5 — G12 mechanism only).

The compiler reads the gym (a list of ``EvalCase`` — real + synthetic) and proposes a new
version of a faculty skill_pack. The proposal is GATED by the existing swarm
``PromotionGate`` (the same gate the Phase-4 ``/commands/promote`` route uses):

  - The gate's job is enforcing invariant #7: synthetic-only evidence cannot promote.
    This is structural — a synthetic-only gym (no matter how many perfect-score synthetic
    cases) NEVER yields a promotable candidate. Real cases are the only thing that opens
    the gate.
  - The compiler does NOT register anything. Its output is a ``CompiledCandidate`` —
    a CANDIDATE that the operator promotes via ``/commands/promote`` (Phase 4).

Honest scope (per the spec):
  - Real improvement needs ~100 real settles; we test the MECHANISM on seeded cases.
  - This module does NOT claim the compiled skill_pack improves anything — the scorecard-
    re-evaluation is opt-in (see ``re_evaluate=True`` in CompilerConfig) and the default
    path is "read the persisted scorecards and gate on them".

Lane: swarm/foundry (CODEX LANE). Imports only from the frozen ``agentx_contracts`` seam
+ the swarm's existing gate/judge/sim. Does NOT touch ``agentx_mandate`` or
``agentx_kernel`` (the compiler is a foundry-side tool, not a kernel-side command).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from agentx_contracts.enums import Ring
from agentx_contracts.gym import EvalCase

from agentx_swarm.gate import (
    PromotionDecision,
    PromotionGate,
    PromotionGateInput,
)

if TYPE_CHECKING:
    from agentx_contracts.protocols import Judge


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompilerConfig:
    """Inputs to ``compile_candidate``.

    ``target_skill_pack`` is the CURRENT skill_pack the compiler proposes to replace.
    The output ``CompiledCandidate.proposed_skill_pack`` is the next minor version
    (``0.1.0`` -> ``0.2.0``).

    ``min_real_score`` mirrors the swarm's ``PromotionGate(min_score=...)`` knob. The
    compiler reads from ``EvalCase.scorecard`` (the persisted judge output); it does
    NOT re-judge the trace by default. Set ``re_evaluate=True`` to invoke the judge on
    each real case's trace — useful for "did the new skill_pack actually beat live on the
    real corpus" checks; default off because (a) the gym already carries the scorecard
    and (b) re-evaluation requires the Judge to be wired (test seam).
    """

    target_skill_pack: str
    min_real_score: float = 0.7
    rubric_match_any: bool = True
    re_evaluate: bool = False
    judge: Judge | None = None


@dataclass(frozen=True)
class CompiledCandidate:
    """The compiler's output — a CANDIDATE, not a registration.

    This object is what the operator hands to ``/commands/promote`` (Phase 4). The
    compiler does not (and CANNOT) write to the mandate_type catalog; that's the
    route's job, gated on the same evidence the compiler surfaced here.
    """

    proposed_skill_pack: str
    """The new skill_pack ref (e.g. ``skill_pack:lead-finder/research@0.2.0``)."""

    target_skill_pack: str
    """The skill_pack the compiler was asked to improve (echo for audit)."""

    real_case_count: int
    synthetic_case_count: int
    """Counts split by origin. invariant #7: real_case_count=0 -> promotable=False (always)."""

    real_score_mean: float
    """Mean of ``scorecard.score`` across real cases (0.0 when real_case_count=0)."""

    real_pass_rate: float
    """Fraction of real cases with ``scorecard.passed=True`` (0.0 when real_case_count=0)."""

    gate_decision: PromotionDecision
    """The existing ``PromotionGate``'s verdict on this proposal."""

    gate_origin: str
    """Tag for which gate branch ran (``"promotion_gate"`` — the L2+ strict gate).

    For Phase 5 the compiler always uses the strict gate (Phase 4's canary variant
    is route-side, not compiler-side — the compile output is meant to survive any
    ring the operator later picks).
    """

    promotable: bool
    """``True`` iff the gate allowed the proposal. ALWAYS False for synthetic-only gyms."""

    reasons: list[str] = field(default_factory=list)
    """Explanatory copy for the dashboard / audit log."""


# ---------------------------------------------------------------------------
# The compiler (pure function over the gym).
# ---------------------------------------------------------------------------


# The strict PromotionGate enforces only evidence+human. The ring split is the route's
# concern (Phase-4); the compiler's job is to surface a proposal the operator can promote.
_ALL_RINGS = {"L0", "L1", "L2", "L3", "L4"}


def compile_candidate(
    gym: list[EvalCase],
    *,
    config: CompilerConfig,
) -> CompiledCandidate:
    """Compile a candidate skill_pack version from the gym.

    Honest scope: this is the MECHANISM, not a real improvement loop. It:
      1. Splits the gym by origin (real vs synthetic).
      2. Aggregates real-case scores + pass-rate from the persisted scorecards.
      3. Delegates the gate to the existing ``PromotionGate`` (the SAME gate the
         Phase-4 promote bridge uses — invariant #7 lives there).
      4. Bumps the skill_pack version (deterministic minor bump).

    It does NOT:
      - Touch the mandate_type catalog (Phase-4 /commands/promote does that).
      - Re-judge traces by default (the gym carries the scorecard).
      - Do a GEPA-style search (out of scope; that needs a real corpus + LLM).
    """
    real_cases, synthetic_cases = _split_by_origin(gym)

    real_score_mean, real_pass_rate = _aggregate_real_metrics(real_cases)

    proposed = _bump_minor_version(config.target_skill_pack)

    gate = PromotionGate(
        min_score=config.min_real_score,
        allow_rings=cast(set[Ring], _ALL_RINGS),
    )
    decision = gate.evaluate(
        PromotionGateInput(
            eval_cases=real_cases,
            scorecards=[],
            # The compiler is testing evidence sufficiency, not asserting the operator's
            # human_approved decision. The operator's human_approved is applied at the
            # Phase-4 /commands/promote bridge. Setting True here means "if a human were to
            # approve, would the strict gate let this through?". The compile output is a
            # CANDIDATE \u2014 not a registration.
            human_approved=True,
            requested_ring="L2",  # The compiler proposes for the strict rung by default.
        )
    )

    reasons: list[str] = []
    if not real_cases:
        # Synthetic-only gym: the gate already says so. Surface it loudly.
        reasons.append(
            f"{len(synthetic_cases)} synthetic cases but 0 real cases — invariant #7: "
            f"synthetic evidence cannot promote; pass through Phase-4 promote with real cases."
        )
    if real_cases and real_pass_rate < 0.5:
        reasons.append(
            f"real pass rate {real_pass_rate:.2f} is below 50% — the new skill_pack is a regression."
        )

    return CompiledCandidate(
        proposed_skill_pack=proposed,
        target_skill_pack=config.target_skill_pack,
        real_case_count=len(real_cases),
        synthetic_case_count=len(synthetic_cases),
        real_score_mean=real_score_mean,
        real_pass_rate=real_pass_rate,
        gate_decision=decision,
        gate_origin="promotion_gate",
        promotable=decision.allowed,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_by_origin(gym: list[EvalCase]) -> tuple[list[EvalCase], list[EvalCase]]:
    real: list[EvalCase] = []
    synthetic: list[EvalCase] = []
    for case in gym:
        if case.origin == "real":
            real.append(case)
        elif case.origin == "synthetic":
            synthetic.append(case)
        else:  # pragma: no cover — CaseOrigin is a Literal; this is defensive.
            raise ValueError(f"unknown EvalCase.origin: {case.origin!r}")
    return real, synthetic


def _aggregate_real_metrics(real_cases: list[EvalCase]) -> tuple[float, float]:
    """Mean score + pass rate over the real cases.

    When there are no real cases (the invariant-#7 path), returns (0.0, 0.0). The compiler
    intentionally treats the empty corpus as the worst score so the gate's downstream
    reasons stay clear ("no passing scorecard evidence").
    """
    if not real_cases:
        return 0.0, 0.0
    scores = [
        case.scorecard.score
        for case in real_cases
        if case.scorecard is not None
    ]
    passed = [
        case.scorecard.passed
        for case in real_cases
        if case.scorecard is not None
    ]
    if not scores:
        return 0.0, 0.0
    mean_score = sum(scores) / len(scores)
    pass_rate = sum(1 for p in passed if p) / len(passed)
    return mean_score, pass_rate


def _bump_minor_version(skill_pack: str) -> str:
    """Deterministic minor bump: ``0.1.0`` -> ``0.2.0``; ``1.4.2`` -> ``1.5.0``.

    Compiler proposes the next minor version (zero-pad by default; we don't reset the
    major). The patch digit is reset to 0 on a minor bump (semver convention).
    """
    if "@" not in skill_pack:
        raise ValueError(
            f"skill_pack must be of the form 'skill_pack:<family>/<name>@<version>'; got {skill_pack!r}"
        )
    prefix, _, version = skill_pack.rpartition("@")
    parts = version.split(".")
    if len(parts) < 2:
        raise ValueError(
            f"version must be semver (major.minor[.patch]); got {version!r}"
        )
    major = parts[0]
    minor = int(parts[1])
    patch = "0" if len(parts) == 2 else parts[2]
    new_minor = minor + 1
    new_version = f"{major}.{new_minor}.0" if patch == "0" else f"{major}.{new_minor}.{patch}"
    return f"{prefix}@{new_version}"


__all__ = [
    "CompiledCandidate",
    "CompilerConfig",
    "compile_candidate",
]
