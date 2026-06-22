"""The ``deep_research`` syscall — a bounded multi-hop web-research fan-out.

This is the Codex-lane actuator behind the in-OS deep-research capability. A
mandate (Claude lane) issues one ``deep_research`` Call with a question; this
adapter runs a bounded loop over the configured providers (Exa + Brave +
Firecrawl) and returns a *cited research pack* — a deduped list of sources with
provenance (url, title, snippet, which hop found it, which provider, a read
excerpt). It does **no LLM work**: synthesis stays in the mandate's harness, so
the two-lane seam (Claude ↔ Codex) is preserved.

The loop (defaults kept small for cost):
  hop 1: search the question across all providers → dedupe by URL.
  read the top results → derive follow-up keywords (reuse the discovery query
  heuristic) → hop 2: search the refined query → dedupe.
Provider failures are swallowed per-call (fallback), never crashing the syscall.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
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

from .adapters import ResearchPage, ResearchProvider, ResearchResult, _AdapterBase, _error_result, _int_arg
from .discovery_adapters import _extract_keywords

# Hard caps so a runaway question can't fan out into a huge bill.
_MAX_HOPS_CAP = 3
_RESULTS_PER_HOP_CAP = 10
_READ_TOP_CAP = 5


def _domain(url: str) -> str:
    raw = url.strip()
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    raw = raw.split("/", 1)[0]
    return raw[4:].lower() if raw.startswith("www.") else raw.lower()


class DeepResearchAdapter(_AdapterBase):
    """Multi-hop, multi-provider web research returning a cited research pack."""

    def __init__(self, *, providers: Sequence[ResearchProvider] | None = None) -> None:
        self._providers = list(providers or [])
        super().__init__(
            name="deep_research",
            category="research",
            maturity_level=3,
            risk_class="read",
            required_ring="L0",
            tenant_auth="api_key",
            fixtures=[
                SyscallTestCase(
                    name="deep_research_smoke",
                    input={"question": "SMB invoicing pain points", "max_hops": 1},
                    expect_status="ok",
                    expect_output_contains={"provider": "deep_research"},
                )
            ],
        )

    def can_handle(self, req: SyscallRequest, ctx: GatewayContext) -> bool:
        return super().can_handle(req, ctx) and bool(self._providers)

    async def execute(self, req: SyscallRequest, cred: Credential | None) -> SyscallResult:
        if not self._providers:
            return _error_result(req, self.name, self.maturity_level, "no research provider configured")
        question_raw = req.args.get("question")
        question = question_raw.strip() if isinstance(question_raw, str) and question_raw.strip() else ""
        if not question:
            return _error_result(req, self.name, self.maturity_level, "deep_research requires a 'question'")
        max_hops = max(1, min(_int_arg(req.args, "max_hops", default=2), _MAX_HOPS_CAP))
        per_hop = max(1, min(_int_arg(req.args, "results_per_hop", default=6), _RESULTS_PER_HOP_CAP))
        read_top = max(0, min(_int_arg(req.args, "read_top", default=3), _READ_TOP_CAP))

        sources: list[dict[str, Any]] = []
        seen: set[str] = set()
        provider_coverage: dict[str, int] = {}
        query = question

        for hop in range(1, max_hops + 1):
            new_records: list[dict[str, Any]] = []
            for result in await self._search_all(query, per_hop):
                if result.url in seen:
                    continue
                seen.add(result.url)
                record: dict[str, Any] = {
                    "url": result.url,
                    "title": result.title,
                    "snippet": result.snippet,
                    "hop": hop,
                    "provider": result.provider,
                    "excerpt": "",
                }
                sources.append(record)
                new_records.append(record)
                provider_coverage[result.provider] = provider_coverage.get(result.provider, 0) + 1

            # Read the top new results: capture an excerpt + mine follow-up terms.
            follow_terms: list[str] = []
            for record in new_records[:read_top]:
                page = await self._read(record["url"])
                if page is not None and page.markdown:
                    record["excerpt"] = page.markdown[:400]
                    text = f"{page.title or ''} {page.markdown[:600]}"
                    follow_terms.extend(_extract_keywords(text, max_keywords=3))

            if hop < max_hops:
                uniq = list(dict.fromkeys(t for t in follow_terms if t))[:4]
                query = f"{question} {' '.join(uniq)}".strip() if uniq else question

        research_pack: JsonObject = cast(
            JsonObject,
            {
                "question": question,
                "hops_run": max_hops,
                "source_count": len(sources),
                "distinct_domains": sorted({_domain(s["url"]) for s in sources if s["url"]}),
                "provider_coverage": provider_coverage,
                "sources": sources,
            },
        )
        return SyscallResult(
            status="ok",
            output={
                "provider": "deep_research",
                "credential_ref": cred.ref if cred is not None else None,
                "research_pack": research_pack,
            },
            idempotency_key=req.idempotency_key,
            fulfilled_by=self.name,
            maturity_used=self.maturity_level,
        )

    async def _search_all(self, query: str, count: int) -> list[ResearchResult]:
        """Fan out the query across every provider; a failing provider is skipped."""
        out: list[ResearchResult] = []
        for provider in self._providers:
            try:
                out.extend(await provider.search(query, count))
            except Exception:  # noqa: BLE001 — provider fallback; never crash the syscall
                continue
        return out

    async def _read(self, url: str) -> ResearchPage | None:
        """Read a URL via the first read-capable provider (Brave returns empty)."""
        for provider in self._providers:
            try:
                page = await provider.read_url(url)
            except Exception:  # noqa: BLE001
                continue
            if page is not None and page.markdown:
                return page
        return None

    async def health_check(self) -> Health:
        if not self._providers:
            return Health(status="degraded", detail="no research provider configured", checked_at=datetime.now(UTC))
        names = ", ".join(p.name for p in self._providers)
        return Health(status="ok", detail=f"deep_research providers: {names}", checked_at=datetime.now(UTC))


__all__ = ["DeepResearchAdapter"]
