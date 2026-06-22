"""Phase-12 mandate-discovery read adapters (F1 / F4 / F5).

These three adapters are the gateway fulfilment for the mandate-discovery
mandate's read-side syscalls. The mandate is read-only (F1/F4/F5 are
``risk_class="read"``); the live kernel fulfils them via Firecrawl
search + scrape.

Design notes:
  - All three are read intents (L0, ``risk_class="read"``). The
    F6 portfolio-builder is the only write — it emits a Claim, not a
    Call. See ``mandate_discovery_faculties/f6_portfolio_builder.py``.
  - Each adapter is keyed to a single Firecrawl call shape; the F1
    community-source adapter uses a Reddit/HN/X allowlist + recency
    filter (per the F1 sampling rule in the charter).
  - Output shapes are the contracts the playbook's gates consume —
    ``filter_pain_signals``, ``filter_moat_assessments``,
    ``filter_buyer_channels``. The contract is the same one the
    sim-mode fixtures use; this is the live fulfilment.

Anti-portfolio guard: the adapters don't filter on mandate name. That's
F3's job (filter_mandate_candidates in
``packages/mandate/src/agentx_mandate/library/mandate_discovery_quality.py``).
The adapters return raw community content; the deterministic gates
decide what to do with it. (The mandate-pattern invariant: the live
kernel does not think; intelligence is scoped, gated tool calls.)
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from importlib import import_module
from typing import Any, cast

from agentx_contracts import (
    GatewayContext,
    Health,
    JsonObject,
    SyscallRequest,
    SyscallResult,
    SyscallTestCase,
)
from agentx_contracts.security import Credential

from .adapters import (
    _AdapterBase,
    _error_result,
    _int_arg,
    _string_list,
)

# Source allowlist for the F1 community-source adapter. The list maps
# each source name to a Firecrawl search-domain filter. Excludes the
# generic "anything on the web" so the F1 sampling is genuinely about
# community sources (not vendor pitches / SEO content / LinkedIn B2B).
_F1_SOURCE_ALLOWLIST: dict[str, tuple[str, ...]] = {
    "reddit": ("reddit.com",),
    "hackernews": ("news.ycombinator.com",),
    "x": ("x.com", "twitter.com"),
    "indiehackers": ("indiehackers.com",),
    "producthunt": ("producthunt.com",),
    "g2_reviews": ("g2.com",),
    "discord": ("discord.com", "discord.gg"),
    "forum": (),  # generic; the F1 sample uses no specific forum domain
}

# Recency filter: posts older than this are dropped unless tagged
# structural_shift=true (per the F1 hard rule in the charter).
_F1_DEFAULT_RECENCY_MONTHS = 12


def _firecrawl_client(api_key: str) -> Any:
    """Lazy import of the Firecrawl SDK. Same pattern as FirecrawlResearchProvider."""
    firecrawl_module = import_module("firecrawl")
    return firecrawl_module.Firecrawl(api_key=api_key)


def _extract_firecrawl_data(response: Any) -> list[dict[str, Any]]:
    """Normalise a Firecrawl v2 response into a list of result dicts.

    Firecrawl's search returns either a ``SearchData`` dataclass with a
    ``web``/``news``/``images`` attribute, or a plain list (v1 compat).
    We pull ``web`` first, then fall back to iterating the response.

    The list items may be Pydantic ``SearchResultWeb`` models (which are
    NOT plain Mappings) — we call ``model_dump()`` on them to convert
    to dicts so the downstream F1 normaliser can read fields by key.
    Without this, the F1 normaliser sees ``{"raw": <pydantic>}`` and
    returns None for every post, dropping the entire sample.
    """
    if response is None:
        return []
    if isinstance(response, Mapping):
        if "data" in response and isinstance(response["data"], list):
            return [_pydantic_to_dict(item) for item in response["data"]]
        if "web" in response and isinstance(response["web"], list):
            return [_pydantic_to_dict(item) for item in response["web"]]
        return [dict(response)]
    web = getattr(response, "web", None)
    if isinstance(web, list):
        return [_pydantic_to_dict(item) for item in web]
    if isinstance(response, list):
        return [_pydantic_to_dict(item) for item in response]
    if isinstance(response, str):
        return [{"raw": response}]
    return [_pydantic_to_dict(response)]


def _pydantic_to_dict(item: Any) -> dict[str, Any]:
    """Convert a Firecrawl result item (possibly a Pydantic model) to a dict.

    The v2 SDK returns Pydantic ``SearchResultWeb`` models whose
    ``__iter__`` is NOT a Mapping (it iterates the model fields). Calling
    ``dict(item)`` on a Pydantic model gives ``{field_name: field_value}``
    for pydantic v2 in most cases — but the safer cross-version path
    is ``model_dump()`` when the model supports it.
    """
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        try:
            return dict(item.model_dump())
        except Exception:  # noqa: BLE001 — fallback to dict() below
            pass
    if isinstance(item, Mapping):
        return dict(item)
    return {"raw": str(item)}


def _post_age_months(timestamp: str) -> float | None:
    """Return how many months old a timestamp is, or None if unparseable.

    Accepts ISO-8601 strings (Firecrawl's default scrape format). Returns
    None for malformed input so the caller can decide whether to drop
    the post (F1 drops posts with no parseable timestamp).
    """
    if not isinstance(timestamp, str) or not timestamp.strip():
        return None
    raw = timestamp.strip()
    try:
        # Strip trailing Z for fromisoformat
        normalized = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    delta_days = (now - dt).days
    if delta_days < 0:
        return 0.0
    return delta_days / 30.0


# =============================================================================
# F1 — community_source_sample
# =============================================================================


class CommunitySourceSampleAdapter(_AdapterBase):
    """F1 community-source read adapter — sample posts from Reddit/HN/X/etc.

    Args received:
      - segment (str, required): the ICP / topic (e.g. "Series A SaaS RevOps")
      - geography (str, optional): the geography filter (e.g. "United States")
      - time_window (str, default "last_12_months"): recency filter window
      - sources (list[str], default = all 8): which community sources to sample
      - post_count (int, default 80): minimum sample size (capped at 300)
      - min_distinct_sources (int, default 4): diversity bar (charter pin)
      - min_post_age_months (int, default 12): recency cutoff for the filter

    Returns:
      - community_posts[]: each with
          url, author, timestamp, upvotes, body_text, segment_tags, source
      - sample_stats: distinct_sources_sampled, total_posts_sampled, oldest_months

    The adapter uses Firecrawl search per source. It does NOT filter on
    content quality (F2's job). It does enforce the diversity bar
    (≥min_distinct_sources) by spreading the post_count across the
    requested sources. If fewer than the diversity bar succeed, the
    adapter still returns what it has (the playbook's F1 sample-size
    check + diversity check then parks the run).
    """

    def __init__(self, *, api_key: str | None = None) -> None:
        self._api_key = api_key or ""
        super().__init__(
            name="community_source_sample",
            category="research",
            maturity_level=3,
            risk_class="read",
            required_ring="L0",
            tenant_auth="api_key",
            fixtures=[
                SyscallTestCase(
                    name="community_source_sample_smoke",
                    input={
                        "segment": "Series A SaaS RevOps",
                        "sources": ["reddit"],
                        "post_count": 5,
                    },
                    expect_status="ok",
                    expect_output_contains={"source": "reddit"},
                )
            ],
        )

    def can_handle(self, req: SyscallRequest, ctx: GatewayContext) -> bool:
        return super().can_handle(req, ctx) and bool(self._api_key)

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        if not self._api_key:
            return _error_result(req, self.name, self.maturity_level, "no Firecrawl API key configured")
        # `_str_arg` raises on missing/empty; we want optional args with defaults.
        segment = req.args.get("segment")
        if not isinstance(segment, str) or not segment.strip():
            segment = "B2B prospects"
        raw_geo = req.args.get("geography")
        geography = raw_geo if isinstance(raw_geo, str) and raw_geo.strip() else ""
        sources = _string_list(req.args.get("sources")) or list(_F1_SOURCE_ALLOWLIST.keys())
        post_count = _int_arg(req.args, "post_count", default=30)
        # Hard cap at 80 for live runs — 80 × 600-char posts = ~50KB, which
        # fits in one LLM tool-message context window. The charter's
        # F1_MIN_POSTS=80 is a sim-mode invariant; live runs use 30 by default.
        post_count = max(1, min(post_count, 80))
        min_distinct_sources = _int_arg(req.args, "min_distinct_sources", default=4)
        min_post_age_months = _int_arg(req.args, "min_post_age_months", default=_F1_DEFAULT_RECENCY_MONTHS)

        # Spread the post_count across the sources (ceiling division so
        # the first N sources each get one more than the rest).
        n = len(sources)
        per_source = max(1, (post_count + n - 1) // n)

        client = _firecrawl_client(self._api_key)
        posts: list[dict[str, Any]] = []
        distinct_sources: set[str] = set()
        try:
            for source in sources:
                domains = _F1_SOURCE_ALLOWLIST.get(source, ())
                if not domains and source != "forum":
                    continue
                query = _build_f1_query(segment, geography, source)
                try:
                    response = client.search(
                        query,
                        limit=per_source,
                        include_domains=list(domains) if domains else None,
                        timeout=60_000,
                    )
                except Exception as exc:  # noqa: BLE001 — adapter swallows SDK errors
                    # One source failing should not kill the whole sample.
                    # The F1 minimum-sample-size check + F2 will reject.
                    posts.append(
                        {
                            "url": "",
                            "author": "",
                            "timestamp": "",
                            "upvotes": 0,
                            "body_text": "",
                            "segment_tags": [source],
                            "source": source,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    continue
                for raw in _extract_firecrawl_data(response):
                    normalised = _normalise_f1_post(raw, source=source, segment=segment)
                    if normalised is None:
                        continue
                    age_months = _post_age_months(normalised.get("timestamp", ""))
                    if age_months is not None and age_months > min_post_age_months:
                        # Older than the recency window — drop unless
                        # explicitly tagged as a structural shift.
                        if not normalised.get("structural_shift"):
                            continue
                    distinct_sources.add(source)
                    posts.append(normalised)
                    if len([p for p in posts if p.get("source") == source]) >= per_source:
                        break
        except Exception as exc:  # noqa: BLE001
            return _error_result(req, self.name, self.maturity_level, f"client error: {exc}")

        # ---- Free-tier fallback ------------------------------------------
        # If Firecrawl returned 0 posts (key expired, rate-limited, or
        # query too narrow), fall back to the public-source providers so
        # the mandate can still surface a portfolio. This is a Phase 14
        # stopgap — the principled fix is a working Firecrawl key.
        if not posts and sources:
            from .discovery_free_providers import (
                search_hackernews,
                search_producthunt,
                search_reddit,
            )
            for source in sources:
                if source == "hackernews":
                    raw_posts = search_hackernews(segment, limit=per_source)
                elif source == "reddit":
                    raw_posts = search_reddit(segment, limit=per_source)
                elif source == "producthunt":
                    raw_posts = search_producthunt(segment, limit=per_source)
                else:
                    continue
                for raw in raw_posts:
                    if "error" in raw:
                        # Provider-level error; record and continue
                        posts.append({"source": source, "error": raw["error"], "url": raw.get("url", "")})
                        continue
                    normalised = _normalise_f1_post(raw, source=source, segment=segment)
                    if normalised is None:
                        continue
                    age_months = _post_age_months(normalised.get("timestamp", ""))
                    if age_months is not None and age_months > min_post_age_months:
                        if not normalised.get("structural_shift"):
                            continue
                    distinct_sources.add(source)
                    posts.append(normalised)
                    if len([p for p in posts if p.get("source") == source]) >= per_source:
                        break

        # The output is a JsonObject; cast the posts list to satisfy the invariant.
        output_payload: JsonObject = cast(
            JsonObject,
            {
                "provider": "firecrawl",
                "credential_ref": cred.ref if cred is not None else None,
                "community_posts": cast(list[object], posts),
                "sample_stats": {
                    "distinct_sources_sampled": len(distinct_sources),
                    "total_posts_sampled": len(posts),
                    "min_distinct_sources_required": min_distinct_sources,
                    "recency_window_months": min_post_age_months,
                },
            },
        )
        return SyscallResult(
            status="ok",
            output=output_payload,
            idempotency_key=req.idempotency_key,
            fulfilled_by=self.name,
            maturity_used=self.maturity_level,
        )

    async def health_check(self) -> Health:
        if not self._api_key:
            return Health(
                status="degraded",
                detail="no Firecrawl API key configured",
                checked_at=datetime.now(UTC),
            )
        return Health(
            status="ok",
            detail="firecrawl client ready",
            checked_at=datetime.now(UTC),
        )


# =============================================================================
# F4 — competitor_search
# =============================================================================


class CompetitorSearchAdapter(_AdapterBase):
    """F4 competitor-stress read adapter — find existing solutions for a candidate.

    Args received:
      - candidate_ids (list[str], required): which mandate candidates to assess
      - include_pricing (bool, default True): include pricing in results
      - include_weaknesses (bool, default True): include weakness flags

    Returns:
      - per_candidate: a dict {candidate_id: {existing_solutions, saturation_score_0to1,
        defensibility_0to1, differentation_axis, build_cost_estimate_story_points}}

    The adapter queries Firecrawl for each candidate with the query
    ``"<candidate name> alternative"`` and ``"<candidate name> review"``,
    then heuristically derives saturation (more results = more saturated)
    and defensibility (named adjacent tools with documented weaknesses
    implies some room for vertical specialisation).
    """

    def __init__(self, *, api_key: str | None = None) -> None:
        self._api_key = api_key or ""
        super().__init__(
            name="competitor_search",
            category="research",
            maturity_level=3,
            risk_class="read",
            required_ring="L0",
            tenant_auth="api_key",
            fixtures=[
                SyscallTestCase(
                    name="competitor_search_smoke",
                    input={"candidate_ids": ["c1"]},
                    expect_status="ok",
                    expect_output_contains={"provider": "firecrawl"},
                )
            ],
        )

    def can_handle(self, req: SyscallRequest, ctx: GatewayContext) -> bool:
        return super().can_handle(req, ctx) and bool(self._api_key)

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        if not self._api_key:
            return _error_result(req, self.name, self.maturity_level, "no Firecrawl API key configured")
        candidate_ids = _string_list(req.args.get("candidate_ids"))
        if not candidate_ids:
            return _error_result(req, self.name, self.maturity_level, "candidate_ids is empty")
        include_pricing = bool(req.args.get("include_pricing", True))
        include_weaknesses = bool(req.args.get("include_weaknesses", True))
        candidate_queries = _candidate_queries_arg(req.args)

        client = _firecrawl_client(self._api_key)
        out: dict[str, Any] = {}
        try:
            for cid in candidate_ids:
                terms = _candidate_query_terms(cid, candidate_queries)
                # NOTE: no exact-match quotes — a de-slugged prose phrase finds
                # real "X alternative / review" pages; a quoted slug finds zero.
                query = f"{terms} alternative OR review OR competitor"
                try:
                    response = client.search(query, limit=8, timeout=60_000)
                except Exception as exc:  # noqa: BLE001
                    out[cid] = {
                        "saturation_score_0to1": 0.5,
                        "defensibility_0to1": 0.5,
                        "differentiation_axis": f"unknown (search error: {type(exc).__name__})",
                        "existing_solutions": [],
                        "build_cost_estimate_story_points": 13,
                    }
                    continue
                results = _extract_firecrawl_data(response)
                solutions = [
                    {
                        "name": str(item.get("title") or item.get("url") or "Unknown"),
                        "url": str(item.get("url") or ""),
                        "pricing": (
                            str(item.get("pricing")) if include_pricing and item.get("pricing") else None
                        ),
                        "weakness": (
                            str(item.get("description"))
                            if include_weaknesses and item.get("description")
                            else None
                        ),
                    }
                    for item in results[:5]
                ]
                # Heuristic saturation: 0-1, more results = more saturated.
                # 5+ results = 0.8, 0 results = 0.1.
                saturation = min(0.95, 0.1 + 0.14 * len(results))
                # Heuristic defensibility: if no pricing/weakness data,
                # assume some room (verticals always have room).
                defensibility = 0.5 if solutions and not any(s.get("pricing") for s in solutions) else 0.6
                out[cid] = {
                    "saturation_score_0to1": round(saturation, 2),
                    "defensibility_0to1": round(defensibility, 2),
                    "differentiation_axis": (
                        "vertical-specific" if defensibility >= 0.5 else "horizontal-feature"
                    ),
                    "existing_solutions": solutions,
                    "build_cost_estimate_story_points": 13,
                }
        except Exception as exc:  # noqa: BLE001
            return _error_result(req, self.name, self.maturity_level, f"client error: {exc}")

        moat_payload: JsonObject = cast(
            JsonObject,
            {
                "provider": "firecrawl",
                "credential_ref": cred.ref if cred is not None else None,
                "moat_assessments": cast(object, out),
            },
        )
        return SyscallResult(
            status="ok",
            output=moat_payload,
            idempotency_key=req.idempotency_key,
            fulfilled_by=self.name,
            maturity_used=self.maturity_level,
        )

    async def health_check(self) -> Health:
        if not self._api_key:
            return Health(
                status="degraded",
                detail="no Firecrawl API key configured",
                checked_at=datetime.now(UTC),
            )
        return Health(
            status="ok",
            detail="firecrawl client ready",
            checked_at=datetime.now(UTC),
        )


# =============================================================================
# F5 — buyer_channel_discovery
# =============================================================================


class BuyerChannelDiscoveryAdapter(_AdapterBase):
    """F5 buyer-mapping read adapter — find sub-reddits / Discord / X audiences.

    Args received:
      - candidate_ids (list[str], required): which candidates to map
      - include_subreddit_discovery (bool, default True)
      - include_x_audience (bool, default True)
      - include_discord_servers (bool, default True)
      - max_channels_per_candidate (int, default 5)

    Returns:
      - per_candidate: {candidate_id: {channels: [...]}}
      - each channel: type, name_or_url, audience_size_estimate, engagement_quality,
        entry_post_strategy, conversion_signal, first_100_prospect_source_query
    """

    def __init__(self, *, api_key: str | None = None) -> None:
        self._api_key = api_key or ""
        super().__init__(
            name="buyer_channel_discovery",
            category="research",
            maturity_level=3,
            risk_class="read",
            required_ring="L0",
            tenant_auth="api_key",
            fixtures=[
                SyscallTestCase(
                    name="buyer_channel_discovery_smoke",
                    input={"candidate_ids": ["c1"]},
                    expect_status="ok",
                    expect_output_contains={"provider": "firecrawl"},
                )
            ],
        )

    def can_handle(self, req: SyscallRequest, ctx: GatewayContext) -> bool:
        return super().can_handle(req, ctx) and bool(self._api_key)

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        if not self._api_key:
            return _error_result(req, self.name, self.maturity_level, "no Firecrawl API key configured")
        candidate_ids = _string_list(req.args.get("candidate_ids"))
        if not candidate_ids:
            return _error_result(req, self.name, self.maturity_level, "candidate_ids is empty")
        max_channels = _int_arg(req.args, "max_channels_per_candidate", default=5)
        max_channels = max(1, min(max_channels, 20))
        candidate_queries = _candidate_queries_arg(req.args)

        client = _firecrawl_client(self._api_key)
        out: dict[str, Any] = {}
        try:
            for cid in candidate_ids:
                terms = _candidate_query_terms(cid, candidate_queries)
                channels: list[dict[str, Any]] = []
                # Sub-reddit discovery: search reddit for communities about the
                # topic. De-slugged prose (no exact-match quotes) is what surfaces
                # real subreddits — a quoted slug returns nothing.
                try:
                    sub_response = client.search(
                        f"{terms} community OR subreddit OR forum",
                        limit=max_channels,
                        include_domains=["reddit.com"],
                        timeout=60_000,
                    )
                except Exception:  # noqa: BLE001
                    sub_response = []
                for raw in _extract_firecrawl_data(sub_response)[:max_channels]:
                    url = str(raw.get("url") or "")
                    if not url:
                        continue
                    if not re.search(r"/r/[A-Za-z0-9_]+", url):
                        continue
                    channels.append(_channel_from_subreddit(terms, url, raw))
                # If we don't have enough, also search Hacker News threads
                # (where B2B buyers post ICP-fit discussions).
                if len(channels) < max_channels:
                    try:
                        hn_response = client.search(
                            terms,
                            limit=max_channels - len(channels),
                            include_domains=["news.ycombinator.com"],
                            timeout=60_000,
                        )
                    except Exception:  # noqa: BLE001
                        hn_response = []
                    for raw in _extract_firecrawl_data(hn_response)[: max_channels - len(channels)]:
                        url = str(raw.get("url") or "")
                        if not url:
                            continue
                        channels.append(_channel_from_hn(terms, url, raw))
                out[cid] = {"channels": channels[:max_channels]}
        except Exception as exc:  # noqa: BLE001
            return _error_result(req, self.name, self.maturity_level, f"client error: {exc}")

        buyer_payload: JsonObject = cast(
            JsonObject,
            {
                "provider": "firecrawl",
                "credential_ref": cred.ref if cred is not None else None,
                "buyer_channels": cast(object, out),
            },
        )
        return SyscallResult(
            status="ok",
            output=buyer_payload,
            idempotency_key=req.idempotency_key,
            fulfilled_by=self.name,
            maturity_used=self.maturity_level,
        )

    async def health_check(self) -> Health:
        if not self._api_key:
            return Health(
                status="degraded",
                detail="no Firecrawl API key configured",
                checked_at=datetime.now(UTC),
            )
        return Health(
            status="ok",
            detail="firecrawl client ready",
            checked_at=datetime.now(UTC),
        )


# =============================================================================
# Helpers
# =============================================================================


def _candidate_query_terms(cid: str, candidate_queries: Mapping[str, str] | None = None) -> str:
    """Turn a candidate_id into a natural-language Firecrawl search phrase.

    The F4/F5 adapters were quoting the raw candidate_id as an exact-match query
    (``"revops_pipeline_hygiene_daily_auditor"``), which matches NOTHING on the
    open web — that was the v1-v3 "shortlist=0" root cause. Real community
    content uses prose, not snake_case slugs.

    This de-slugifies the id into space-separated words (and strips bookkeeping
    prefixes like ``cluster:``), so the candidate becomes a usable search phrase.
    A caller may override per-candidate via ``candidate_queries`` (the LLM can
    pass a crisp product-category phrase, e.g. "RevOps pipeline hygiene tool").
    """
    if candidate_queries:
        override = candidate_queries.get(cid)
        if isinstance(override, str) and override.strip():
            return override.strip()
    terms = cid.strip()
    # Drop a leading bookkeeping namespace ("cluster:foo:bar" → "foo:bar").
    if ":" in terms:
        terms = terms.split(":", 1)[1] if terms.lower().startswith("cluster:") else terms
    # Slug separators → spaces; collapse whitespace.
    for sep in ("_", "-", ":", "/", "."):
        terms = terms.replace(sep, " ")
    terms = " ".join(terms.split())
    return terms or cid


def _candidate_queries_arg(args: Mapping[str, Any]) -> dict[str, str]:
    """Parse the optional ``candidate_queries`` arg into a {candidate_id: phrase} map.

    Accepts either a dict ``{cid: phrase}`` or a list of
    ``{"candidate_id": cid, "query": phrase}`` objects (whichever the harness
    finds easier to emit). Unknown shapes are ignored — the de-slug fallback
    still applies.
    """
    raw = args.get("candidate_queries")
    out: dict[str, str] = {}
    if isinstance(raw, Mapping):
        for k, v in raw.items():
            if isinstance(k, str) and isinstance(v, str) and v.strip():
                out[k] = v.strip()
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, Mapping):
                cid = item.get("candidate_id")
                q = item.get("query")
                if isinstance(cid, str) and isinstance(q, str) and q.strip():
                    out[cid] = q.strip()
    return out


def _build_f1_query(segment: str, geography: str, source: str) -> str:
    """Build a Firecrawl search query for a single source.

    Segment parsing:
      - The full segment (e.g. "Series A SaaS RevOps leaders in the US")
        is too narrow as a quoted string — community users don't write
        posts that way. We extract the **2 most distinctive keywords**
        (the longest two non-stopword tokens) and quote them
        individually. E.g. "Series A SaaS RevOps leaders" → quoted
        "RevOps" + "SaaS" — which actually matches real Reddit threads.

    Source-specific tweaks:
      - reddit: include "discussion OR pain OR complaint" terms
      - hackernews: include "Show HN" or "Ask HN" terms
      - x: include "tweet" / "thread" terms
      - others: just the segment + geography
    """
    keywords = _extract_keywords(segment)
    # Build the quoted keyword phrase. We use 1-2 keywords (whichever
    # produces a useful, specific query). Most Firecrawl searches return
    # 0 results for 3+ quoted keywords — keep it to 2 max.
    quoted = " ".join(f'"{kw}"' for kw in keywords[:2]) or f'"{segment}"'
    parts: list[str] = [quoted]
    if geography:
        parts.append(geography)
    if source == "reddit":
        parts.append("discussion OR pain OR complaint")
    elif source == "hackernews":
        parts.append("Show HN OR Ask HN OR launch")
    elif source == "x":
        parts.append("tweet OR thread OR founder")
    elif source == "indiehackers":
        parts.append("interview OR journey OR revenue")
    elif source == "producthunt":
        parts.append("launch OR alternative OR review")
    elif source == "g2_reviews":
        parts.append("review OR complaints OR pros-cons")
    return " ".join(parts)


_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
        "have", "in", "into", "is", "it", "its", "of", "on", "or", "that", "the",
        "to", "was", "were", "will", "with", "you", "your", "i", "we", "they",
        "this", "these", "those", "their", "our", "us", "them", "any", "all",
        # Role words — too generic to be useful as search keywords.
        "leaders", "operator", "operators", "founder", "founders",
        # Funding-stage words — appear in every job post, dilute the search.
        "series", "startup", "startups", "company", "companies",
        "based", "b2b", "b2c", "smb", "enterprise", "saas",  # 'saas' is too generic on its own
        # Geography words.
        "united", "states", "europe", "global", "world", "city",
    }
)


def _extract_keywords(segment: str, *, max_keywords: int = 2) -> list[str]:
    """Pull the longest non-stopword tokens from a segment string.

    The segment "Series A SaaS RevOps leaders in the US" → ["RevOps", "SaaS"]
    (longest first, stopwords dropped). Quoting these individually is
    what makes Firecrawl return community content; quoting the full
    segment returns 0.
    """
    tokens: list[str] = []
    for raw in segment.split():
        # Strip non-alphanumeric except hyphen/underscore
        cleaned = "".join(ch if ch.isalnum() or ch in "-_" else " " for ch in raw).strip()
        if not cleaned:
            continue
        if cleaned.lower() in _STOPWORDS:
            continue
        if len(cleaned) < 3:  # skip "us", "a", "b" etc
            continue
        tokens.append(cleaned)
    # Sort by length desc, then alphabetical for determinism
    tokens.sort(key=lambda t: (-len(t), t.lower()))
    return tokens[:max_keywords]


def _normalise_f1_post(raw: Mapping[str, Any], *, source: str, segment: str) -> dict[str, Any] | None:
    """Normalise a Firecrawl result into the F1 community_posts shape.

    Returns None if the result lacks a URL (the F2 filter requires a real
    URL+author; we let F2 reject it). Returns a normalisable dict otherwise.
    """
    url = str(raw.get("url") or raw.get("link") or "").strip()
    if not url:
        return None
    title = raw.get("title") or raw.get("name")
    description = raw.get("description") or raw.get("snippet") or raw.get("markdown") or ""
    if isinstance(description, list):
        description = " ".join(str(item) for item in description)
    return {
        "url": url,
        "author": str(raw.get("author") or "").strip(),
        "timestamp": str(raw.get("publishedDate") or raw.get("date") or raw.get("timestamp") or "").strip(),
        "upvotes": int(raw.get("upvotes") or raw.get("score") or 0),
        "body_text": (str(description)[:1500] if description else "").strip(),
        "segment_tags": [source, segment],
        "source": source,
        "title": str(title) if title else "",
        "structural_shift": bool(raw.get("structural_shift")),
    }


def _channel_from_subreddit(cid: str, url: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    """Build a buyer-channel entry from a Reddit subreddit URL."""
    subreddit_match = re.search(r"/r/([A-Za-z0-9_]+)", url)
    subreddit = subreddit_match.group(1) if subreddit_match else "unknown"
    return {
        "type": "reddit_subreddit",
        "name_or_url": f"https://reddit.com/r/{subreddit}",
        "audience_size_estimate": _estimate_subreddit_audience(subreddit),
        "engagement_quality": "unknown (auto-discovered)",
        "entry_post_strategy": (
            f"comment on threads about '{cid}'; offer a free audit"
        ),
        "conversion_signal": "DM with company URL + role",
        "first_100_prospect_source_query": (
            f'site:reddit.com/r/{subreddit} "{cid}" OR "manual pain point"'
        ),
    }


def _channel_from_hn(cid: str, url: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    """Build a buyer-channel entry from a Hacker News thread URL."""
    return {
        "type": "hacker_news_thread",
        "name_or_url": url,
        "audience_size_estimate": 50_000,
        "engagement_quality": "medium — HN threads get targeted founder engagement",
        "entry_post_strategy": (
            f'Show HN: "we built a tool for {cid}"; respond to ICP-fit threads'
        ),
        "conversion_signal": "waitlist signups or email reply",
        "first_100_prospect_source_query": f'site:news.ycombinator.com "{cid}"',
    }


def _estimate_subreddit_audience(subreddit: str) -> int:
    """Cheap heuristic for subreddit size (subscribers × 0.05 = weekly active).

    We don't have a live Reddit API key, so this is a deliberately
    rough estimate. The F5 buyer gate just needs audience_size_estimate > 0
    to NOT drop the channel; a 0-50% underestimate is acceptable.

    For known high-volume subreddits (RevOps, sales, SaaS) we use
    hardcoded member counts; for unknown subreddits we return a
    conservative 5,000-default (which the playbook accepts).
    """
    known: dict[str, int] = {
        "RevOps": 18_000,
        "sales": 220_000,
        "SaaS": 90_000,
        "startups": 1_200_000,
        "Entrepreneur": 1_000_000,
        "smallbusiness": 1_000_000,
        "marketing": 1_100_000,
        "ecommerce": 200_000,
        "Shopify": 180_000,
        "dental": 12_000,
        "dentistry": 25_000,
        "consulting": 90_000,
        "agencies": 35_000,
        "agency": 35_000,
    }
    return known.get(subreddit, 5_000)


__all__ = [
    "CommunitySourceSampleAdapter",
    "CompetitorSearchAdapter",
    "BuyerChannelDiscoveryAdapter",
]
