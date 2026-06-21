"""F5 — buyer-mapping faculty.

For each surviving mandate candidate, F5 emits a READ intent
(``buyer_channel_discovery``) that the gateway fulfils via sub-reddit discovery,
Discord server search, X audience analysis, Exa people-search, HN user
history. The result populates ``ctx.scratchpad['buyer_channels']`` with:

  - channels (per-candidate)
  - per channel: type, name_or_url, audience_size_estimate, engagement_quality,
    entry_post_strategy, conversion_signal, first_100_prospect_source_query

The deterministic gate (``filter_buyer_channels``) drops any candidate whose
channels list is empty, has no audience>0 entry, or has no first-100-prospect
query (the go-to-market bar).
"""

from __future__ import annotations

from typing import cast

from agentx_contracts.faculty import Faculty, HarnessAdapterSpec
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.syscall import SyscallRequest

from agentx_mandate.harness import Call, FacultyContext, HarnessAction

FACULTY = Faculty(
    name="mandate_discovery_buyer_mapping",
    skill_pack="skill_pack:mandate-discovery/buyer-mapping@0.1.0",
    tool_manifest=["buyer_channel_discovery"],
    eval_slice="gym:mandate-discovery/buyer-mapping",
    harness_adapter=HarnessAdapterSpec(
        harness="hermes",
        native_skills_enabled=["people_search", "audience_analysis", "channel_discovery"],
        effectful_tools_to_gateway=True,
        memory_mode="per_run_scratch",
    ),
)


def propose(ctx: FacultyContext) -> list[HarnessAction]:
    """Emit one ``buyer_channel_discovery`` Call per surviving moat-passing candidate.

    Reads ``ctx.scratchpad['mandate_candidates']`` (after F3 + F4 gates have
    run) and emits a single Call whose args list the candidate_ids to discover
    channels for. The adapter layer does the actual sub-reddit / Discord / X
    work; the playbook reads the result back via ``ctx.scratchpad['buyer_channels']``.
    """
    raw_candidates = ctx.scratchpad.get("mandate_candidates", [])
    candidate_ids: list[str] = []
    if isinstance(raw_candidates, list):
        for c in raw_candidates:
            if isinstance(c, dict):
                cid = c.get("candidate_id") or c.get("mandate_name")
                if isinstance(cid, str) and cid:
                    candidate_ids.append(cid)
    if not candidate_ids:
        return []  # nothing to map
    args = cast(JsonObject, {
        "candidate_ids": candidate_ids,
        "include_subreddit_discovery": True,
        "include_x_audience": True,
        "include_discord_servers": True,
        "max_channels_per_candidate": 5,
    })
    return [
        Call(
            request=SyscallRequest(
                name="buyer_channel_discovery",
                args=args,
                instance_id=ctx.instance_id,
                run_id=ctx.run_id,
                idempotency_key=f"{ctx.run_id}:md:f5:buyer_channel_discovery",
                ring=ctx.ring,
                risk_class="read",
            )
        )
    ]
