"""The lead-finder PLAYBOOK — the deterministic trajectory the ``own`` harness double follows (G1).

This is the sim-mode counterpart to the live Hermes runner: instead of MiniMax choosing each step, the
playbook composes the faculties' proposals into an ordered Think/Call/Claim/draft/Finish trajectory.

It is a GENERATOR over the shared-by-reference ``FacultyContext``. Each yielded read Call suspends the
generator; the run-loop disposes it (fulfils the read natively in sim / via the gateway in live) by
MUTATING ``ctx.scratchpad``; when the generator resumes, the next faculty's ``propose`` sees the leads.
That coroutine interleaving is what lets a precomputed playbook express a read-dependent trajectory.

The hardcoded outreach draft used to live in the kernel run-loop; it now lives here as
``build_outreach_call`` (LLM/playbook proposes; the kernel gateway still disposes — ring-checks + journals).
"""

from __future__ import annotations

from collections.abc import Iterator

from agentx_contracts.faculty import Faculty
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.syscall import SyscallRequest

from agentx_mandate.faculties import propose
from agentx_mandate.harness import Call, FacultyContext, Finish, HarnessAction, Think
from agentx_mandate.lead_quality import is_actionable_lead


def lead_finder_playbook(ctx: FacultyContext, faculties: list[Faculty]) -> Iterator[HarnessAction]:
    """Yield the lead-finder trajectory one action at a time (read Calls suspend for fulfilment)."""

    target = dict(ctx.target)
    yield Think(
        summary="Plan the lead-finder run for the target ICP.",
        detail={"icp": target.get("icp", ""), "location": target.get("location", "")},
    )
    for faculty in faculties:
        yield from propose(faculty.name, ctx)
    draft = build_outreach_call(ctx)
    if draft is not None:
        yield draft
    yield Finish(output={"actionable_leads": _actionable_lead_count(ctx)})


def first_actionable_lead_id(ctx: FacultyContext) -> str | None:
    """Pick the highest-scored ACTIONABLE lead in the scratchpad (non-actionable candidates are ignored)."""

    leads = ctx.scratchpad.get("leads")
    if not isinstance(leads, list) or not leads:
        return None
    scores = ctx.scratchpad.get("scores")
    scored: list[tuple[float, str]] = []
    for lead in leads:
        if not isinstance(lead, dict) or not is_actionable_lead(lead):
            continue
        lead_id = lead.get("id")
        if not isinstance(lead_id, str):
            continue
        score = 0.0
        if isinstance(scores, dict):
            raw_score = scores.get(lead_id)
            if isinstance(raw_score, dict):
                value = raw_score.get("score")
                if isinstance(value, int | float):
                    score = float(value)
        scored.append((score, lead_id))
    return max(scored, default=(0.0, ""))[1] or None


def build_outreach_call(ctx: FacultyContext) -> Call | None:
    """Build the per-lead ``send_email`` Call for the best actionable lead, or None if there is none.

    The effect is a GATED real send: ``send_email`` is external_message at L2, so at an instance ring
    below L2 the gateway PARKS it for human approval (the approval card shows this composed email);
    only on Approve does the resumed run perform the real send via the configured transport. With no
    transport configured the registry resolves it to the human_task tail (invariant #5). The kernel
    run-loop stamps the From from the instance's ``ChannelBinding.sender_identity`` (invariant #8) and
    defaults an unset recipient to that same sender (review-in-your-own-inbox dogfood).
    """

    lead_id = first_actionable_lead_id(ctx)
    if lead_id is None:
        return None
    return Call(
        request=SyscallRequest(
            name="send_email",
            args=_outreach_args(ctx, lead_id),
            instance_id=ctx.instance_id,
            run_id=ctx.run_id,
            idempotency_key=f"{ctx.run_id}:send_email",
            ring=ctx.ring,
            risk_class="external_message",
        )
    )


def _outreach_args(ctx: FacultyContext, lead_id: str) -> JsonObject:
    company = _lead_value(ctx, lead_id, "company", "name") or lead_id
    contact_name = _lead_value(ctx, lead_id, "contact_name")
    contact_role = _lead_value(ctx, lead_id, "contact_role") or "business owner"
    contact_url = _lead_value(ctx, lead_id, "contact_url") or _lead_value(ctx, lead_id, "url") or ""
    signal = _lead_value(ctx, lead_id, "buying_signal") or "an active growth initiative"
    greeting = contact_name or contact_role
    # An optional explicit recipient (e.g. a shared ops inbox). When absent, the kernel run-loop fills
    # ``to`` with the instance's own sender (send-to-self) so the founder reviews/forwards from their
    # inbox — a real send can then only ever reach the operator, never an unverified address.
    recipient = ctx.target.get("review_recipient")
    return {
        "lead_id": lead_id,
        "to": recipient if isinstance(recipient, str) and recipient.strip() else "",
        "subject": f"Quick idea for {company}",
        "body": (
            f"Hi {greeting},\n\n"
            f"I noticed this signal at {company}: {signal.rstrip('.')}. "
            "We help teams act on prospect signals like this with researched, evidence-cited outreach. "
            f"If lead follow-up is a priority right now, I'd value a short conversation. Reference: {contact_url}"
        ),
    }


def _lead_value(ctx: FacultyContext, lead_id: str, *keys: str) -> str | None:
    leads = ctx.scratchpad.get("leads")
    if not isinstance(leads, list):
        return None
    for lead in leads:
        if not isinstance(lead, dict) or lead.get("id") != lead_id:
            continue
        for key in keys:
            value = lead.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _actionable_lead_count(ctx: FacultyContext) -> int:
    leads = ctx.scratchpad.get("leads")
    if not isinstance(leads, list):
        return 0
    return sum(1 for lead in leads if isinstance(lead, dict) and is_actionable_lead(lead))
