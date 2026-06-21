"""F2 — pain-extraction faculty (LLM-on-scratchpad).

The LLM is the LLM, the kernel is the kernel. F2 emits a ``Think`` that
*records* the LLM-on-scratchpad analysis: it reads ``ctx.scratchpad['community_posts']``
(produced by the F1 gateway call), invokes the LLM to PROPOSE pain signals,
and stores the proposed signals in ``ctx.scratchpad['pain_signals']``.

The deterministic gate (``filter_pain_signals``) is in
``mandate_discovery_quality.py`` — F2 NEVER applies the gate. F2 proposes;
the playbook (after F2 yields) runs the gate; only surviving signals flow
to F3 (clustering).

In the OwnHarness (sim mode) the LLM is a deterministic test double: the
playbook reads pre-seeded pain signals from the test fixture. The "LLM
proposes" line is satisfied structurally — the proposal lives in scratchpad,
the gate runs deterministically, the playbook's Claim commits only the
gate-survivors.
"""

from __future__ import annotations

from agentx_contracts.faculty import Faculty, HarnessAdapterSpec, RoutingHint

from agentx_mandate.harness import FacultyContext, HarnessAction, Think

FACULTY = Faculty(
    name="mandate_discovery_pain_extraction",
    skill_pack="skill_pack:mandate-discovery/pain-extraction@0.1.0",
    tool_manifest=["llm_propose_pain_signals"],
    eval_slice="gym:mandate-discovery/pain-extraction",
    routing_hint=RoutingHint(strong_model=True, latency_tolerance="tolerant"),
    harness_adapter=HarnessAdapterSpec(
        harness="hermes",
        native_skills_enabled=["structured_extraction", "semantic_clustering"],
        effectful_tools_to_gateway=True,
        memory_mode="per_run_scratch",
    ),
)


def propose(ctx: FacultyContext) -> list[HarnessAction]:
    """Record the F2 invocation in the trace; the LLM work happens in scratchpad.

    In live mode the harness's native structured_extraction skill reads
    ``ctx.scratchpad['community_posts']`` and writes
    ``ctx.scratchpad['pain_signals']``. In sim mode the fixture pre-populates
    the same scratchpad key. The deterministic gate (F2 filter) runs
    AFTER this Think yields — the playbook does the wiring.
    """
    return [
        Think(
            summary="F2 pain-extraction: LLM proposes pain signals from community posts",
            detail={
                "input_key": "community_posts",
                "output_key": "pain_signals",
                "instance_id": ctx.instance_id,
                "run_id": ctx.run_id,
            },
        )
    ]
