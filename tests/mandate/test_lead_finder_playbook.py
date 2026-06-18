"""G1 — the lead-finder PLAYBOOK: the deterministic trajectory the OwnHarness double follows.

The playbook is a generator over the shared-by-reference FacultyContext: each yielded read Call
suspends until the run-loop fulfils it (mutating ctx.scratchpad), so downstream faculties see leads.
The hardcoded draft moves OUT of the kernel run-loop and INTO this playbook (build_outreach_call).
"""

from datetime import UTC, datetime

from agentx_contracts import HydrationSnapshot
from agentx_contracts.faculty import Faculty
from agentx_mandate.faculties import get_faculty
from agentx_mandate.harness import Call, FacultyContext, Finish, Think
from agentx_mandate.library.lead_finder_playbook import build_outreach_call, lead_finder_playbook

NOW = datetime(2026, 6, 17, tzinfo=UTC)
_FACULTY_NAMES = ["research", "enrichment", "judgment", "memory-craft", "escalation"]


def _ctx(scratchpad: dict[str, object] | None = None) -> FacultyContext:
    return FacultyContext(
        snapshot=HydrationSnapshot(frozen_at=NOW),
        target={"icp": "independent dental clinics", "location": "Pune", "count": 1},
        scratchpad=scratchpad if scratchpad is not None else {},
        instance_id="inst_a",
        run_id="run_1",
        ring="L1",
        now=NOW,
    )


def _faculties() -> list[Faculty]:
    return [get_faculty(name) for name in _FACULTY_NAMES]


def test_playbook_opens_with_think_then_a_research_read_intent() -> None:
    gen = lead_finder_playbook(_ctx(), _faculties())
    first = next(gen)
    second = next(gen)
    assert isinstance(first, Think)
    assert isinstance(second, Call)
    assert second.request.name == "lead_research_batch"
    assert second.request.risk_class == "read"


def test_playbook_finishes_when_no_leads_get_fulfilled() -> None:
    # Driven without the run-loop, the research read is never fulfilled, so downstream faculties see
    # an empty scratchpad: no Claim, no draft, terminate with Finish.
    actions = list(lead_finder_playbook(_ctx(), _faculties()))
    assert isinstance(actions[-1], Finish)
    assert not any(isinstance(a, Call) and a.request.name == "draft_email" for a in actions)


def test_build_outreach_call_targets_best_actionable_lead_with_grounded_body() -> None:
    ctx = _ctx(
        scratchpad={
            "leads": [
                {"id": "article", "company": "10 Best Clinics", "url": "https://youtube.com/watch/1"},
                {
                    "id": "clinic",
                    "company": "Galaxy Dental Clinic",
                    "url": "https://galaxy.example",
                    "contact_name": "Dr. Asha Kulkarni",
                    "contact_role": "Practice owner",
                    "contact_url": "https://galaxy.example/contact",
                    "buying_signal": "accepting new patients",
                    "buying_signal_evidence": "accepting new patients",
                    "evidence": ["accepting new patients", "https://galaxy.example"],
                },
            ],
            "scores": {"clinic": {"score": 1.0, "reason": "actionable"}},
        }
    )
    call = build_outreach_call(ctx)
    assert call is not None
    assert call.request.name == "draft_email"
    assert call.request.risk_class == "external_message"
    body = str(call.request.args["body"])
    assert "Hi Dr. Asha Kulkarni" in body
    assert "accepting new patients" in body
    assert "https://galaxy.example/contact" in body
    assert "10 Best Clinics" not in body


def test_build_outreach_call_returns_none_without_an_actionable_lead() -> None:
    assert build_outreach_call(_ctx()) is None
    ctx = _ctx(scratchpad={"leads": [{"id": "x", "company": "Article", "url": "https://youtube.com/1"}]})
    assert build_outreach_call(ctx) is None
