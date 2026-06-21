"""F1 — community-source faculty.

Proposes a READ intent (``community_source_sample``) that the gateway fulfils
via the read adapters — Reddit, Hacker News, X, Discord, forums (Firecrawl),
ProductHunt, G2, IndieHackers. The faculty is the WHAT (which sources, how
many posts, what segment), the adapter layer is the HOW (which credentials,
which rate limits).

Sampling rule: at least 80 posts across 4+ distinct sources before the next
faculty fires (F2 needs enough signal to be meaningful). Hard cap: 300 posts
(cost control). The playbook enforces both via a Think action that records
the sample plan in the trace.

The LLM-on-scratchpad proposal happens in F2 (pain-extraction), not here.
F1 is purely the read-intent emitter: "go sample 80+ posts about this
segment from these sources". The actual posts are produced by the
gateway, then handed to F2 via ``ctx.scratchpad['community_posts']``.
"""

from __future__ import annotations

from typing import cast

from agentx_contracts.faculty import Faculty, HarnessAdapterSpec
from agentx_contracts.jsontypes import JsonObject
from agentx_contracts.syscall import SyscallRequest

from agentx_mandate.harness import Call, FacultyContext, HarnessAction

# Default sources to sample (the F1 minimum-4 rule). In live mode the gateway
# routes per source to the right adapter; in sim mode the kernel fulfils the
# intent with the synthetic fixture.
DEFAULT_SOURCES: tuple[str, ...] = (
    "reddit",
    "hackernews",
    "x",
    "indiehackers",
    "producthunt",
    "g2_reviews",
    "discord",
    "forum",
)

# F1 sampling: the constitution.
F1_MIN_POSTS: int = 80
F1_HARD_CAP_POSTS: int = 300
F1_MIN_DISTINCT_SOURCES: int = 4


FACULTY = Faculty(
    name="mandate_discovery_community_source",
    skill_pack="skill_pack:mandate-discovery/community-source@0.1.0",
    tool_manifest=["community_source_sample"],
    eval_slice="gym:mandate-discovery/community-source",
    harness_adapter=HarnessAdapterSpec(
        harness="hermes",
        native_skills_enabled=["web_research", "mcp_tools", "structured_sampling"],
        effectful_tools_to_gateway=True,
        memory_mode="per_run_scratch",
    ),
)


def _target(target: JsonObject) -> JsonObject:
    """Pull the discovery target — segment / geography / time_window / seed_mandates."""
    return {key: value for key, value in target.items() if key in {"segment", "geography", "time_window", "seed_mandates"}}  # noqa: E501


def _post_count(target: JsonObject) -> int:
    """F1's min-80 / cap-300 sampling rule (clamped)."""
    raw = target.get("sample_size")
    if isinstance(raw, int) and raw > 0:
        return min(max(raw, F1_MIN_POSTS), F1_HARD_CAP_POSTS)
    return F1_MIN_POSTS


def _sources(target: JsonObject) -> list[str]:
    """The source set — target override, else the default 8."""
    raw = target.get("sources")
    if isinstance(raw, list):
        chosen = [str(s) for s in raw if isinstance(s, str) and s]
        if len(chosen) >= F1_MIN_DISTINCT_SOURCES:
            return chosen[:8]  # cap to the platform's 8 known adapters
    return list(DEFAULT_SOURCES)


def propose(ctx: FacultyContext) -> list[HarnessAction]:
    """Emit ONE community_source_sample Call — the read intent for the gateway.

    The gateway routes this to per-source adapters (Reddit adapter, HN adapter,
    X adapter, etc.). In sim mode the kernel fulfils it with a synthetic
    fixture pack that mimics community posts (clearly tagged ``origin: "synthetic"``).
    """
    target = ctx.target if isinstance(ctx.target, dict) else {}
    seed = target.get("seed_mandates")
    seed_list: list[object] = list(seed) if isinstance(seed, list) else []
    args_dict: dict[str, object] = {
        "segment": str(target.get("segment", "")).strip(),
        "geography": str(target.get("geography", "")).strip(),
        "time_window": str(target.get("time_window", "last_12_months")).strip(),
        "seed_mandates": seed_list,
        "sources": _sources(target),
        "post_count": _post_count(target),
        "min_distinct_sources": F1_MIN_DISTINCT_SOURCES,
        "min_post_age_months": 12,  # structural-shift exception
    }
    args = cast(JsonObject, args_dict)
    return [
        Call(
            request=SyscallRequest(
                name="community_source_sample",
                args=args,
                instance_id=ctx.instance_id,
                run_id=ctx.run_id,
                idempotency_key=f"{ctx.run_id}:md:f1:community_source_sample",
                ring=ctx.ring,
                risk_class="read",
            )
        )
    ]
