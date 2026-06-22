#!/usr/bin/env python3
"""run_deep_research.py — drive one in-OS deep_research call and print the cited pack.

A minimal harness for the ``deep_research`` syscall: it builds the configured
providers (Exa + Brave + Firecrawl, whichever keys are set), runs a bounded
multi-hop research loop for a question, and prints the deduped, cited sources.
No Mongo / no LLM — this exercises the Codex-lane research capability directly.

Usage::

    uv run python scripts/run_deep_research.py --question "what do SMB bookkeepers complain about?"
    uv run python scripts/run_deep_research.py -q "..." --hops 3 --per-hop 8
"""

from __future__ import annotations

import argparse
import asyncio
import json

from agentx_contracts.syscall import SyscallRequest
from agentx_syscall.adapters import build_configured_research_providers
from agentx_syscall.deep_research_adapter import DeepResearchAdapter


async def main() -> int:
    ap = argparse.ArgumentParser(description="Run one in-OS deep_research call.")
    ap.add_argument("-q", "--question", required=True, help="the research question")
    ap.add_argument("--hops", type=int, default=2, help="max hops (1-3)")
    ap.add_argument("--per-hop", type=int, default=6, help="results per hop")
    ap.add_argument("--read-top", type=int, default=3, help="how many top results to read per hop")
    ap.add_argument("--json", action="store_true", help="print the raw research pack as JSON")
    args = ap.parse_args()

    # Providers self-configure from whatever keys are present in .env.
    providers = build_configured_research_providers()
    if not providers:
        print("STOP no research provider configured. Add EXA_API_KEY / BRAVE_API_KEY / FIRECRAWL_API_KEY to .env.")
        return 2
    print(f"PROVIDERS={[p.name for p in providers]}")

    adapter = DeepResearchAdapter(providers=providers)
    req = SyscallRequest(
        name="deep_research",
        args={
            "question": args.question, "max_hops": args.hops,
            "results_per_hop": args.per_hop, "read_top": args.read_top,
        },
        instance_id="cli_deep_research",
        run_id="cli_deep_research_run",
        idempotency_key="cli_deep_research",
        ring="L0",
        risk_class="read",
    )
    result = await adapter.execute(req, None)
    if result.status != "ok":
        print(f"ERROR status={result.status} detail={result.error}")
        return 1

    pack = result.output["research_pack"]
    if args.json:
        print(json.dumps(pack, indent=2, default=str))
        return 0

    print(f"\nQUESTION: {pack['question']}")
    print(f"HOPS_RUN={pack['hops_run']}  SOURCES={pack['source_count']}  "
          f"DOMAINS={len(pack['distinct_domains'])}  COVERAGE={pack['provider_coverage']}")
    print("─" * 78)
    for i, s in enumerate(pack["sources"], start=1):
        print(f"[{i}] (hop {s['hop']} · {s['provider']}) {s['title'] or s['url']}")
        print(f"     {s['url']}")
        if s.get("snippet"):
            print(f"     {s['snippet'][:160]}")
        if s.get("excerpt"):
            print(f"     ↳ {s['excerpt'][:160]}")
    print("─" * 78)
    print("This cited pack is what a mandate's harness synthesizes into a brief (every claim → a source url).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
