"""Smoke tests for the Phase-12 mandate-discovery read adapters (F1/F4/F5).

These tests exercise the adapter shape without live API calls — the
Firecrawl client is replaced with a stub via monkeypatch. The tests pin:

  - The output contract per adapter (the shape the playbook's gates consume).
  - The error mode when the API key is missing (the run parks for human).
  - The recency filter on F1 (12-month cutoff drops old posts).
  - The can_handle check requires both the syscall name AND a configured key.

The smoke tests are layer-A unit tests — no Mongo, no LLM, no network.
They run in <1s.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import agentx_syscall.discovery_adapters as discovery_adapters_module
from agentx_contracts import (
    GatewayContext,
    Health,
    SyscallRequest,
)
from agentx_contracts.security import Credential
from agentx_syscall.discovery_adapters import (
    BuyerChannelDiscoveryAdapter,
    CommunitySourceSampleAdapter,
    CompetitorSearchAdapter,
)


def _ctx() -> GatewayContext:
    return GatewayContext(
        instance_id="inst_disco",
        run_id="run_disco",
        tenant_id="tenant_disco",
        ring="L1",
        now=datetime.now(UTC),
        channel_rules=[],
    )


def _cred() -> Credential:
    return Credential(ref="vault:firecrawl/test", kind="api_key")


def _as_dict(v: object) -> dict[str, object]:
    assert isinstance(v, dict), f"expected dict, got {type(v).__name__}: {v!r}"
    return v


def _as_list(v: object) -> list[object]:
    assert isinstance(v, list), f"expected list, got {type(v).__name__}: {v!r}"
    return v


def _as_str(v: object) -> str:
    assert isinstance(v, str), f"expected str, got {type(v).__name__}: {v!r}"
    return v


# =============================================================================
# F1 — community_source_sample
# =============================================================================


def test_f1_community_source_can_handle_requires_api_key() -> None:
    adapter = CommunitySourceSampleAdapter(api_key="")
    req = SyscallRequest(
        name="community_source_sample",
        args={},
        instance_id="inst_disco",
        run_id="run_disco",
        idempotency_key="k1",
        ring="L1",
        risk_class="read",
    )
    assert adapter.can_handle(req, _ctx()) is False


def test_f1_community_source_can_handle_with_api_key() -> None:
    adapter = CommunitySourceSampleAdapter(api_key="fi-123")
    req = SyscallRequest(
        name="community_source_sample",
        args={},
        instance_id="inst_disco",
        run_id="run_disco",
        idempotency_key="k1",
        ring="L1",
        risk_class="read",
    )
    assert adapter.can_handle(req, _ctx()) is True


def test_f1_community_source_recency_filter_drops_old_posts(monkeypatch: Any) -> None:
    """Posts older than 12 months are dropped (the F1 sampling rule)."""
    adapter = CommunitySourceSampleAdapter(api_key="fi-123")
    fake_response = MagicMock()
    fake_response.web = [
        {
            "url": "https://reddit.com/r/RevOps/comments/old/x",
            "title": "old post",
            "description": "old pain about manual lead routing",
            "publishedDate": (datetime.now(UTC) - timedelta(days=400)).isoformat(),
        },
        {
            "url": "https://reddit.com/r/RevOps/comments/new/x",
            "title": "new post",
            "description": "new pain about manual lead routing",
            "publishedDate": datetime.now(UTC).isoformat(),
        },
    ]
    monkeypatch.setattr(
        discovery_adapters_module,
        "_firecrawl_client",
        MagicMock(return_value=MagicMock(search=MagicMock(return_value=fake_response))),
    )
    req = SyscallRequest(
        name="community_source_sample",
        args={
            "segment": "Series A SaaS RevOps",
            "sources": ["reddit"],
            "post_count": 5,
            "min_post_age_months": 12,
        },
        instance_id="inst_disco",
        run_id="run_disco",
        idempotency_key="k1",
        ring="L1",
        risk_class="read",
    )
    import asyncio
    result = asyncio.run(adapter.execute(req, _cred()))
    assert result.status == "ok", result
    output = _as_dict(result.output)
    posts = _as_list(output["community_posts"])
    new_post_urls = [_as_str(_as_dict(p)["url"]) for p in posts]
    assert any("new" in u for u in new_post_urls), f"new post missing: {new_post_urls}"
    assert not any("old" in u for u in new_post_urls), f"old post should be dropped: {new_post_urls}"
    stats = _as_dict(output["sample_stats"])
    assert stats["recency_window_months"] == 12


def test_f1_community_source_diversity_bar_required(monkeypatch: Any) -> None:
    """The adapter reports sample_stats.min_distinct_sources_required (charter pin)."""
    adapter = CommunitySourceSampleAdapter(api_key="fi-123")
    fake_response = MagicMock()
    fake_response.web = []
    monkeypatch.setattr(
        discovery_adapters_module,
        "_firecrawl_client",
        MagicMock(return_value=MagicMock(search=MagicMock(return_value=fake_response))),
    )
    req = SyscallRequest(
        name="community_source_sample",
        args={"segment": "SaaS", "sources": ["reddit", "hackernews"], "post_count": 10, "min_distinct_sources": 4},
        instance_id="inst_disco",
        run_id="run_disco",
        idempotency_key="k1",
        ring="L1",
        risk_class="read",
    )
    import asyncio
    result = asyncio.run(adapter.execute(req, _cred()))
    assert result.status == "ok"
    output = _as_dict(result.output)
    stats = _as_dict(output["sample_stats"])
    assert stats["min_distinct_sources_required"] == 4


def test_f1_community_source_error_mode_without_api_key() -> None:
    """No API key → error result (run parks for human fulfilment)."""
    adapter = CommunitySourceSampleAdapter(api_key="")
    req = SyscallRequest(
        name="community_source_sample",
        args={"segment": "SaaS"},
        instance_id="inst_disco",
        run_id="run_disco",
        idempotency_key="k1",
        ring="L1",
        risk_class="read",
    )
    import asyncio
    result = asyncio.run(adapter.execute(req, _cred()))
    assert result.status == "error"
    assert "no Firecrawl API key" in (result.error or "")


# =============================================================================
# F4 — competitor_search
# =============================================================================


def test_f4_competitor_search_returns_moat_assessments_per_candidate(monkeypatch: Any) -> None:
    adapter = CompetitorSearchAdapter(api_key="fi-123")
    fake_response = MagicMock()
    fake_response.web = [
        {"url": "https://gong.io", "title": "Gong", "description": "revenue intelligence"},
        {"url": "https://outreach.io", "title": "Outreach", "description": "sequencing tool"},
    ]
    monkeypatch.setattr(
        discovery_adapters_module,
        "_firecrawl_client",
        MagicMock(return_value=MagicMock(search=MagicMock(return_value=fake_response))),
    )
    req = SyscallRequest(
        name="competitor_search",
        args={"candidate_ids": ["c_revops_one_person"]},
        instance_id="inst_disco",
        run_id="run_disco",
        idempotency_key="k2",
        ring="L1",
        risk_class="read",
    )
    import asyncio
    result = asyncio.run(adapter.execute(req, _cred()))
    assert result.status == "ok", result
    output = _as_dict(result.output)
    moat_assessments = _as_dict(output["moat_assessments"])
    moat = _as_dict(moat_assessments["c_revops_one_person"])
    assert "saturation_score_0to1" in moat
    assert "defensibility_0to1" in moat
    assert "existing_solutions" in moat
    # 2 results → saturation 0.1 + 0.14*2 = 0.38
    assert 0.35 <= float(_as_str(str(moat["saturation_score_0to1"]))) <= 0.45
    assert len(_as_list(moat["existing_solutions"])) == 2


def test_f4_competitor_search_empty_candidate_ids_errors() -> None:
    adapter = CompetitorSearchAdapter(api_key="fi-123")
    req = SyscallRequest(
        name="competitor_search",
        args={"candidate_ids": []},
        instance_id="inst_disco",
        run_id="run_disco",
        idempotency_key="k2",
        ring="L1",
        risk_class="read",
    )
    import asyncio
    result = asyncio.run(adapter.execute(req, _cred()))
    assert result.status == "error"
    assert "candidate_ids is empty" in (result.error or "")


# =============================================================================
# F5 — buyer_channel_discovery
# =============================================================================


def test_f5_buyer_channel_discovery_returns_subreddit_channels(monkeypatch: Any) -> None:
    """The adapter parses /r/<sub> from URLs and emits a buyer channel per subreddit."""
    adapter = BuyerChannelDiscoveryAdapter(api_key="fi-123")
    reddit_response = MagicMock()
    reddit_response.web = [
        {"url": "https://reddit.com/r/RevOps/comments/abc/x", "title": "thread", "description": "..."},
        {"url": "https://reddit.com/r/sales/comments/def/y", "title": "thread", "description": "..."},
    ]
    hn_response = MagicMock()
    hn_response.web = []  # no HN fallback in this test
    client_mock = MagicMock()
    client_mock.search = MagicMock(side_effect=[reddit_response, hn_response])
    monkeypatch.setattr(
        discovery_adapters_module,
        "_firecrawl_client",
        MagicMock(return_value=client_mock),
    )
    req = SyscallRequest(
        name="buyer_channel_discovery",
        args={"candidate_ids": ["c_revops"], "max_channels_per_candidate": 5},
        instance_id="inst_disco",
        run_id="run_disco",
        idempotency_key="k3",
        ring="L1",
        risk_class="read",
    )
    import asyncio
    result = asyncio.run(adapter.execute(req, _cred()))
    assert result.status == "ok", result
    output = _as_dict(result.output)
    buyer_channels = _as_dict(output["buyer_channels"])
    candidate_block = _as_dict(buyer_channels["c_revops"])
    channels = _as_list(candidate_block["channels"])
    assert len(channels) == 2
    # Each channel has the buyer_source_manifest shape.
    for ch in channels:
        ch_dict = _as_dict(ch)
        assert ch_dict["type"] == "reddit_subreddit"
        assert int(_as_str(str(ch_dict["audience_size_estimate"]))) > 0
        query = _as_str(ch_dict["first_100_prospect_source_query"])
        assert "site:reddit.com" in query
    # Known subreddit heuristic: RevOps is 18_000.
    revops_channel = _as_dict(
        next(c for c in channels if "RevOps" in _as_str(_as_dict(c)["name_or_url"]))
    )
    assert int(_as_str(str(revops_channel["audience_size_estimate"]))) == 18_000  # noqa: E501


def test_f5_buyer_channel_discovery_empty_candidate_ids_errors() -> None:
    adapter = BuyerChannelDiscoveryAdapter(api_key="fi-123")
    req = SyscallRequest(
        name="buyer_channel_discovery",
        args={"candidate_ids": []},
        instance_id="inst_disco",
        run_id="run_disco",
        idempotency_key="k3",
        ring="L1",
        risk_class="read",
    )
    import asyncio
    result = asyncio.run(adapter.execute(req, _cred()))
    assert result.status == "error"
    assert "candidate_ids is empty" in (result.error or "")


def test_f5_buyer_channel_discovery_falls_back_to_hn(monkeypatch: Any) -> None:
    """When Reddit returns no /r/ URLs, the adapter falls back to HN search."""
    adapter = BuyerChannelDiscoveryAdapter(api_key="fi-123")
    # First call (Reddit) returns no /r/ URLs; second call (HN) returns a thread.
    reddit_response = MagicMock()
    reddit_response.web = [{"url": "https://reddit.com/some/other/url", "title": "x"}]
    hn_response = MagicMock()
    hn_response.web = [{"url": "https://news.ycombinator.com/item?id=12345", "title": "x"}]
    client_mock = MagicMock()
    client_mock.search = MagicMock(side_effect=[reddit_response, hn_response])
    monkeypatch.setattr(
        discovery_adapters_module,
        "_firecrawl_client",
        MagicMock(return_value=client_mock),
    )
    req = SyscallRequest(
        name="buyer_channel_discovery",
        args={"candidate_ids": ["c_revops"], "max_channels_per_candidate": 5},
        instance_id="inst_disco",
        run_id="run_disco",
        idempotency_key="k3",
        ring="L1",
        risk_class="read",
    )
    import asyncio
    result = asyncio.run(adapter.execute(req, _cred()))
    assert result.status == "ok", result
    output = _as_dict(result.output)
    buyer_channels = _as_dict(output["buyer_channels"])
    candidate_block = _as_dict(buyer_channels["c_revops"])
    channels = _as_list(candidate_block["channels"])
    assert len(channels) == 1
    first = _as_dict(channels[0])
    assert first["type"] == "hacker_news_thread"
    assert int(_as_str(str(first["audience_size_estimate"]))) == 50_000


# =============================================================================
# Health checks
# =============================================================================


def test_all_three_adapters_report_degraded_health_without_api_key() -> None:
    import asyncio
    for adapter_cls in (CommunitySourceSampleAdapter, CompetitorSearchAdapter, BuyerChannelDiscoveryAdapter):
        adapter = adapter_cls(api_key="")
        health: Health = asyncio.run(adapter.health_check())
        assert health.status == "degraded", f"{adapter_cls.__name__}: {health}"
        assert "no Firecrawl API key" in health.detail


def test_all_three_adapters_report_ok_health_with_api_key() -> None:
    import asyncio
    for adapter_cls in (CommunitySourceSampleAdapter, CompetitorSearchAdapter, BuyerChannelDiscoveryAdapter):
        adapter = adapter_cls(api_key="fi-123")
        health: Health = asyncio.run(adapter.health_check())
        assert health.status == "ok", f"{adapter_cls.__name__}: {health}"


# =============================================================================
# Mandate-discovery charter pins (the F1 charter invariants)
# =============================================================================


def test_f1_charter_pins_default_minimum_80_posts() -> None:
    """The F1 sampling rule: min 80 posts, cap 300, default 4+ sources.

    These are the F1 charter invariants (the user signs up to these).
    """
    from agentx_mandate.library.mandate_discovery_faculties.f1_community_source import (
        F1_HARD_CAP_POSTS,
        F1_MIN_DISTINCT_SOURCES,
        F1_MIN_POSTS,
    )
    assert F1_MIN_POSTS == 80, f"charter pin: F1_MIN_POSTS must be 80; got {F1_MIN_POSTS}"
    assert F1_HARD_CAP_POSTS == 300, f"charter pin: F1_HARD_CAP_POSTS must be 300; got {F1_HARD_CAP_POSTS}"
    assert F1_MIN_DISTINCT_SOURCES == 4, (
        f"charter pin: F1_MIN_DISTINCT_SOURCES must be 4; got {F1_MIN_DISTINCT_SOURCES}"
    )
