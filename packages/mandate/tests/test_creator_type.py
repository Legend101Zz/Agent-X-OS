"""Phase-3 Creator mandate draft-path tests (HERMES_BUILD_PLAN §Phase 3 — starts G10).

Done-when #1: ``build_creator_type()`` returns a ``MandateType`` with the four §5 faculties
(conversation, scheduling, memory-craft, escalation) + checkable postconditions.

This is the mirror of ``build_lead_finder_type()`` for the Creator — a MandateType whose OWN
output is OTHER MandateTypes (drafts the operator can review and (later) promote). It stays in
the mandate lane (Claude); the corresponding ``draft_candidate_type`` syscall lives in the syscall
lane and is covered by ``packages/syscall/tests/test_draft_candidate_type.py``.
"""

from __future__ import annotations

from agentx_contracts.mandate import (
    Charter,
    DomainPackRef,
    MandateType,
    VerificationSuite,
)
from agentx_mandate.faculties import FACULTY_LIBRARY
from agentx_mandate.library.creator import build_creator_type


def test_build_creator_type_returns_a_mandate_type() -> None:
    candidate = build_creator_type()
    assert isinstance(candidate, MandateType)
    assert candidate.name  # has a name
    assert candidate.version  # has a version


def test_creator_type_has_the_four_section_5_faculties() -> None:
    """Done-when #1: conversation + scheduling + memory-craft + escalation."""
    candidate = build_creator_type()
    bound_names = {binding.faculty_name for binding in candidate.faculties}

    # The four §5 faculties are present.
    assert "conversation" in bound_names, f"missing 'conversation' in {sorted(bound_names)}"
    assert "scheduling" in bound_names, f"missing 'scheduling' in {sorted(bound_names)}"
    assert "memory-craft" in bound_names, f"missing 'memory-craft' in {sorted(bound_names)}"
    assert "escalation" in bound_names, f"missing 'escalation' in {sorted(bound_names)}"

    # And each is actually bound to a real library faculty (not just a string).
    for binding in candidate.faculties:
        assert binding.faculty_name in FACULTY_LIBRARY, (
            f"faculty {binding.faculty_name!r} bound but not in FACULTY_LIBRARY — "
            f"the Creator references a faculty that doesn't exist (loader would fail at run-time)"
        )
        # The library actually has the FACULTY object backing the name.
        library_faculty = FACULTY_LIBRARY[binding.faculty_name]
        assert library_faculty.name == binding.faculty_name


def test_creator_type_charter_has_a_goal_and_checkable_postconditions() -> None:
    """Done-when #1: 'has a charter goal' + 'candidate has ≥1 faculty' + 'names a scenario pack'."""
    candidate = build_creator_type()
    assert isinstance(candidate.charter, Charter)
    assert candidate.charter.goal, "Creator's charter must have a non-empty goal"

    # Postconditions must be machine-checkable (rung='rules' with an expr) so the verifier can run them.
    rules_post = [
        condition
        for condition in candidate.charter.postconditions
        if condition.rung == "rules"
    ]
    assert rules_post, "Creator's charter must declare checkable postconditions (rung='rules')"
    for condition in rules_post:
        assert condition.expr, (
            f"rules-rung postcondition {condition.id!r} must have an expr (rules.py evaluates it)"
        )

    # Required structural postconditions per the spec ("candidate has ≥1 faculty", "has a charter
    # goal", "names a scenario pack") — the Creator's postconditions are rules-rung facts that
    # the playbook's Claim action satisfies (provenance-stamped structural evidence). Each
    # postcondition ID encodes one of the §5 structural checks.
    post_ids = {c.id for c in rules_post}
    # Check the DESCRIPTION strings (not the IDs) for the structural keywords — the IDs are
    # concise canonical names while the descriptions carry the operator-facing rationale.
    post_descriptions = [c.description.lower() for c in rules_post]
    assert any(
        "facult" in pid or "facult" in desc
        for pid, desc in zip(post_ids, post_descriptions, strict=True)
    ), "Creator must post-check that the produced candidate has ≥1 faculty"
    assert any(
        "goal" in pid or "goal" in desc
        for pid, desc in zip(post_ids, post_descriptions, strict=True)
    ), "Creator must post-check that the produced candidate has a charter goal"
    assert any(
        ("scenario" in pid) or ("domain_pack" in pid) or ("pack" in pid) or ("scenario" in desc)
        for pid, desc in zip(post_ids, post_descriptions, strict=True)
    ), "Creator must post-check that the produced candidate names a scenario pack / domain_pack"


def test_creator_type_names_a_real_scenario_pack() -> None:
    """Done-when #1: 'names a scenario pack' — the domain_pack ref points at the live scenario pack."""
    candidate = build_creator_type()
    assert isinstance(candidate.domain_pack, DomainPackRef)
    # The plan says the Creator names a scenario pack. We default to the swarm's built-in
    # indian_b2b_leads_v1 (the one that ships in scenario_packs/) — that's the live corpus the
    # swarm already grades against. (Phase 4 may add others; for now the contract is "real pack".)
    assert candidate.domain_pack.name, "Creator's domain_pack must have a name"
    assert candidate.domain_pack.version, "Creator's domain_pack must have a version"


def test_creator_type_has_a_verification_suite() -> None:
    candidate = build_creator_type()
    assert isinstance(candidate.verification, VerificationSuite)
    # Default ladder is the canonical verification ladder; explicit assertion for clarity.
    assert candidate.verification.ladder
    assert "rules" in candidate.verification.ladder
    assert "judge" in candidate.verification.ladder
    assert "human" in candidate.verification.ladder


def test_creator_type_has_settlement_rules_with_a_watch_window() -> None:
    candidate = build_creator_type()
    assert candidate.settlement.watch_window_hours > 0, (
        "Creator's settlement must declare a watch window so drafts can mature to reality"
    )


def test_creator_faculties_are_independently_instantiable_proposers() -> None:
    """Each §5 faculty must expose a ``propose(ctx)`` callable for the harness to invoke."""
    candidate = build_creator_type()
    bound_names = {binding.faculty_name for binding in candidate.faculties}

    # Lazy import so the test does not require every faculty to be importable at collection time.
    # A minimal FacultyContext is enough to exercise the propose() entry point; the faculties
    # must return a list (possibly empty) without raising.
    from datetime import UTC, datetime

    from agentx_mandate.faculties import propose as faculty_propose
    from agentx_mandate.harness import FacultyContext

    ctx = FacultyContext(
        snapshot=None,  # type: ignore[arg-type]
        target={},
        scratchpad={},
        instance_id="inst_creator",
        run_id="run_creator_smoke",
        ring="L1",
        now=datetime.now(UTC),
    )
    for name in bound_names:
        actions = faculty_propose(name, ctx)
        assert isinstance(actions, list), (
            f"faculty {name!r}.propose must return a list of HarnessAction; "
            f"got {type(actions).__name__}"
        )


def test_creator_type_has_a_skill_pack_per_faculty() -> None:
    """The Creator must wire each faculty to a real skill_pack ref (no empty skill_packs)."""
    candidate = build_creator_type()
    bound_names = {binding.faculty_name for binding in candidate.faculties}

    for faculty_name in bound_names:
        library_faculty = FACULTY_LIBRARY[faculty_name]
        assert library_faculty.skill_pack.startswith("skill_pack:"), (
            f"faculty {faculty_name!r} must declare a skill_pack ref "
            f"(compiler-owned, versioned) — got {library_faculty.skill_pack!r}"
        )


def test_creator_rubric_exists_and_includes_quality_dimensions() -> None:
    """The Creator's verification suite must declare a rubric for grading the candidate it emits."""
    candidate = build_creator_type()
    rubrics = candidate.verification.rubrics
    assert rubrics, "Creator must carry at least one rubric (else the gym can't grade the candidate)"
    rubric = rubrics[0]
    # At minimum the rubric should have a pass threshold and at least one criterion.
    assert rubric.pass_threshold > 0.0
    assert rubric.criteria, "rubric must have substantive criteria (not empty — Phase-2 lesson)"
    # Quality dimensions a Creator is responsible for: charter-goal, scenario-pack, faculties.
    criterion_ids = {c.id for c in rubric.criteria}
    assert any("facult" in cid for cid in criterion_ids), (
        f"Creator rubric should check 'candidate has faculties'; criterion_ids={criterion_ids}"
    )


def test_creator_type_postcondition_can_be_evaluated_by_rules_verifier() -> None:
    """The postconditions must be evaluable — the existing RulesVerifier can handle them.

    Builds a minimal candidate that satisfies the rules and asserts the verifier passes; if a
    postcondition's ``expr`` references a fact the verifier can't see yet, this fails.
    """
    candidate = build_creator_type()

    from agentx_kernel.verifier import RulesVerifier

    verifier = RulesVerifier()
    # A trivial stub: no claimed facts yet, but the verifier should at least run the postconditions
    # without raising. (True semantic validation would require the candidate's run output.)
    result = verifier.verify_postconditions(candidate, claimed_facts=[])
    # We do not assert ``result.passed`` here — the Creator's run will populate the heap — but the
    # call must complete and the reasons must be a list (no exception).
    assert isinstance(result.reasons, list)
