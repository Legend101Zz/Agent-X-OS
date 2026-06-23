"""Outreach faculty — owns the lead-finder ``draft_email`` intent.

Thin by design: it declares the ``draft_email`` syscall in its ``tool_manifest`` so the generalized
Hermes runner derives the ``draft_email`` tool from the mandate's faculties (rather than hard-coding
it). The deterministic sim trajectory still composes the outreach draft in ``lead_finder_playbook``
(``build_outreach_call`` → ``send_email``), so this faculty proposes nothing itself — it exists to
carry the tool-manifest seam, mirroring books-prep's thin ``ledger-export`` faculty.
"""

from __future__ import annotations

from agentx_contracts.faculty import Faculty, HarnessAdapterSpec

from agentx_mandate.harness import FacultyContext, HarnessAction

FACULTY = Faculty(
    name="outreach",
    skill_pack="skill_pack:lead-finder/outreach@0.1.0",
    tool_manifest=["draft_email"],
    eval_slice="gym:lead-finder/outreach",
    harness_adapter=HarnessAdapterSpec(
        harness="hermes",
        native_skills_enabled=["personalised_outreach"],
        effectful_tools_to_gateway=True,
        memory_mode="per_run_scratch",
    ),
)


def propose(ctx: FacultyContext) -> list[HarnessAction]:
    # The sim playbook composes the outreach draft itself (build_outreach_call); this faculty only
    # carries the draft_email tool-manifest seam for the live runner. Nothing to propose here.
    return []
