"""Ledger-export faculty (books-prep) — carries the export + review-queue tool-manifest seam.

Thin like ``outreach``: it declares the ``export_ledger`` + ``queue_manual_action`` intents so the
generalized runner derives those tools from the mandate. The deterministic ``books_prep_playbook``
composes the actual export Call + per-row review-queue Calls after categorisation, so this faculty
proposes nothing itself.
"""

from __future__ import annotations

from agentx_contracts.faculty import Faculty, HarnessAdapterSpec

from agentx_mandate.harness import FacultyContext, HarnessAction

FACULTY = Faculty(
    name="ledger-export",
    skill_pack="skill_pack:books-prep/ledger-export@0.1.0",
    tool_manifest=["export_ledger", "queue_manual_action"],
    eval_slice="gym:books-prep/ledger-export",
    harness_adapter=HarnessAdapterSpec(
        harness="hermes",
        native_skills_enabled=["structured_export"],
        effectful_tools_to_gateway=True,
        memory_mode="per_run_scratch",
    ),
)


def propose(ctx: FacultyContext) -> list[HarnessAction]:
    return []
