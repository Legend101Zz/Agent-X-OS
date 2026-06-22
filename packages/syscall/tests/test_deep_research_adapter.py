"""Unit tests for the in-OS deep_research multi-hop adapter (no network).

A fake in-memory provider stands in for Exa/Brave/Firecrawl so the tests pin:
  - multi-hop runs the configured number of hops and the 2nd query is refined,
  - sources are deduped by URL across hops,
  - a failing provider is skipped (fallback), the syscall still returns ok,
  - a missing question is a clean error,
  - the generic search-response parser normalizes provider shapes.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from agentx_contracts import GatewayContext, SyscallRequest, SyscallResult
from agentx_syscall.adapters import ResearchPage, ResearchResult, _parse_generic_results
from agentx_syscall.deep_research_adapter import DeepResearchAdapter


def _pack(result: SyscallResult) -> dict[str, Any]:
    """Narrow the research_pack from JsonValue to a dict for assertions."""
    pack = result.output["research_pack"]
    assert isinstance(pack, dict)
    return cast(dict[str, Any], pack)


class FakeProvider:
    """In-memory ResearchProvider: returns canned results per query + pages per url."""

    def __init__(self, *, name: str, results: dict[str, list[ResearchResult]],
                 pages: dict[str, ResearchPage] | None = None, fail: bool = False) -> None:
        self.name = name
        self._results = results
        self._pages = pages or {}
        self._fail = fail
        self.queries: list[str] = []

    async def health_check(self) -> bool:
        return True

    async def search(self, query: str, count: int) -> list[ResearchResult]:
        if self._fail:
            raise RuntimeError("provider down")
        self.queries.append(query)
        items = self._results.get(query, self._results.get("*", []))
        return items[:count]

    async def read_url(self, url: str) -> ResearchPage:
        return self._pages.get(url, ResearchPage(url=url, title=None, markdown="", evidence=[], metadata={}))

    async def search_leads(self, criteria: Mapping[str, Any], count: int) -> list[Any]:
        return []


def _req(args: dict[str, Any]) -> SyscallRequest:
    return SyscallRequest(
        name="deep_research", args=args, instance_id="i", run_id="r",
        idempotency_key="k", ring="L0", risk_class="read",
    )


def _ctx() -> GatewayContext:
    return GatewayContext(
        instance_id="i", run_id="r", tenant_id="t", ring="L0", now=datetime.now(UTC), channel_rules=[],
    )


def _r(url: str, snippet: str = "", provider: str = "fake") -> ResearchResult:
    return ResearchResult(url=url, title=url, snippet=snippet, provider=provider)


def test_multi_hop_dedupes_and_refines_query() -> None:
    hop1 = [_r("https://a.com/1", "invoicing"), _r("https://b.com/2")]
    hop2 = [_r("https://a.com/1"), _r("https://c.com/3")]  # a.com/1 is a duplicate
    pages = {
        "https://a.com/1": ResearchPage(
            url="https://a.com/1", title="Invoicing automation",
            markdown="late payment reconciliation chasing accounts receivable", evidence=[], metadata={},
        )
    }
    fake = FakeProvider(name="fake", results={"q": hop1, "*": hop2}, pages=pages)
    adapter = DeepResearchAdapter(providers=[fake])

    result = asyncio.run(adapter.execute(_req({"question": "q", "max_hops": 2, "read_top": 1}), None))

    assert result.status == "ok"
    pack = _pack(result)
    assert pack["hops_run"] == 2
    urls = [s["url"] for s in pack["sources"]]
    assert urls == ["https://a.com/1", "https://b.com/2", "https://c.com/3"]  # deduped, in order
    assert sorted(pack["distinct_domains"]) == ["a.com", "b.com", "c.com"]
    assert pack["provider_coverage"] == {"fake": 3}
    # Hop 2 query was refined from the read page's keywords (not equal to the raw question).
    assert len(fake.queries) == 2
    assert fake.queries[0] == "q"
    assert fake.queries[1] != "q" and fake.queries[1].startswith("q ")
    # The read excerpt was captured on the read source.
    assert pack["sources"][0]["excerpt"].startswith("late payment")


def test_failing_provider_is_skipped() -> None:
    good = FakeProvider(name="good", results={"*": [_r("https://x.com/1", provider="good")]})
    bad = FakeProvider(name="bad", results={"*": []}, fail=True)
    adapter = DeepResearchAdapter(providers=[bad, good])

    result = asyncio.run(adapter.execute(_req({"question": "q", "max_hops": 1}), None))

    assert result.status == "ok"
    pack = _pack(result)
    assert pack["source_count"] == 1
    assert pack["provider_coverage"] == {"good": 1}


def test_missing_question_errors() -> None:
    adapter = DeepResearchAdapter(providers=[FakeProvider(name="fake", results={})])
    result = asyncio.run(adapter.execute(_req({}), None))
    assert result.status == "error"
    assert "question" in (result.error or "")


def test_no_providers_errors() -> None:
    adapter = DeepResearchAdapter(providers=[])
    result = asyncio.run(adapter.execute(_req({"question": "q"}), None))
    assert result.status == "error"


def test_can_handle_requires_providers() -> None:
    with_provider = DeepResearchAdapter(providers=[FakeProvider(name="f", results={})])
    assert with_provider.can_handle(_req({"question": "q"}), _ctx())
    assert not DeepResearchAdapter(providers=[]).can_handle(_req({"question": "q"}), _ctx())


def test_parse_generic_results_normalizes_shapes() -> None:
    # Firecrawl-ish: list under "web"; Exa-ish: list under "results".
    resp = {"web": [{"url": "https://e.com/x", "title": "X", "description": "snippet here"}]}
    out = _parse_generic_results(resp, provider="firecrawl", count=5)
    assert len(out) == 1
    assert out[0].url == "https://e.com/x" and out[0].snippet == "snippet here" and out[0].provider == "firecrawl"
    # Highlights fall back to snippet when no description.
    resp2 = {"results": [{"url": "https://e.com/y", "highlights": ["a", "b"]}]}
    out2 = _parse_generic_results(resp2, provider="exa", count=5)
    assert out2[0].snippet == "a … b"
    # No url → dropped.
    assert _parse_generic_results({"results": [{"title": "no url"}]}, provider="exa", count=5) == []
