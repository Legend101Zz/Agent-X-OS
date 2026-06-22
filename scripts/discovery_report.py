#!/usr/bin/env python3
"""discovery_report.py — render a shareable HTML report for a mandate-discovery run.

Reads the 5 committed heap facts (from MongoDB) plus the per-run JSONL log (the
harness narrative + F1 sample stats + timeline) and emits a self-contained,
dark-themed HTML page you can send to a partner or open in a browser.

Usage::

    uv run python scripts/discovery_report.py --latest
    uv run python scripts/discovery_report.py --instance agentx_discovery_1782137194_default
    uv run python scripts/discovery_report.py --instance <id> --out docs/discovery_reports/foo.html

Output defaults to ``docs/discovery_reports/<instance_id>.html``.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import agentx_db.collections as c
from agentx_contracts.config import Settings
from pymongo import AsyncMongoClient

LOG_DIR = Path(os.environ.get("AGENTX_RUN_LOG_DIR", "run_logs"))


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #
def _latest_run_log() -> Path | None:
    files = sorted(LOG_DIR.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _run_log_for_instance(instance_id: str) -> Path | None:
    folder = LOG_DIR / re.sub(r"[^A-Za-z0-9_.:-]+", "_", instance_id)
    if folder.exists():
        files = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            return files[0]
    return None


def _read_log(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def _log_field(events: list[dict[str, Any]], kind: str, key: str, default: str = "") -> str:
    for ev in events:
        if ev.get("kind") == kind:
            val = ev.get("detail", {}).get(key)
            if val:
                return str(val)
    return default


def _finish_summary(events: list[dict[str, Any]]) -> str:
    for ev in events:
        if ev.get("kind") == "decision" and "finish" in ev.get("summary", ""):
            return str(ev.get("detail", {}).get("summary", ""))
    return ""


def _f1_stats(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Pull the best F1 sample stats (most posts) seen across the run."""
    best: dict[str, Any] = {}
    best_posts = -1
    for ev in events:
        if ev.get("kind") == "syscall_result" and ev.get("detail", {}).get("syscall") == "community_source_sample":
            out = ev.get("detail", {}).get("output", {})
            posts = out.get("community_posts", 0)
            if isinstance(posts, int) and posts > best_posts:
                best_posts = posts
                best = out
    return best


# --------------------------------------------------------------------------- #
# Manifest parsing
# --------------------------------------------------------------------------- #
async def _load_buyer_channels(db: Any, run_id: str, instance_id: str) -> dict[str, list[dict[str, Any]]]:
    """Pull the F5 buyer_channel_discovery output (the real subreddits + prospect queries).

    The manifest fact is the agent's prose summary; the authoritative channel list
    (with first_100_prospect_source_query — the actual "go find prospects" query)
    lives in the syscall receipt. Deduped by channel URL per candidate.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    query = {"$or": [{"run_id": run_id}, {"run_id": {"$regex": re.escape(instance_id)}}]}
    async for r in db[c.SYSCALL_RECEIPT].find(query):
        name = r.get("syscall") or r.get("fulfilled_by") or r.get("name")
        if not name or "buyer_channel" not in str(name):
            continue
        payload = r.get("output") or (r.get("result") or {}).get("output") or {}
        channels_map = payload.get("buyer_channels") if isinstance(payload, dict) else None
        if not isinstance(channels_map, dict):
            continue
        for cand, blob in channels_map.items():
            chans = blob.get("channels") if isinstance(blob, dict) else None
            if not isinstance(chans, list):
                continue
            seen: set[str] = {ch.get("name_or_url", "") for ch in out.get(cand, []) if isinstance(ch, dict)}
            bucket = out.setdefault(cand, [])
            for ch in chans:
                if isinstance(ch, dict) and ch.get("name_or_url") not in seen:
                    bucket.append(ch)
                    seen.add(ch.get("name_or_url", ""))
    return out


def _parse_manifest(manifest: str) -> list[dict[str, str]]:
    """Parse 'shortlist=N: name1 (channels: ...) | name2 (...)' into structured items."""
    items: list[dict[str, str]] = []
    # Strip a leading "shortlist=N:" prefix.
    body = re.sub(r"^\s*shortlist\s*=\s*\d+\s*:", "", manifest).strip()
    # Two observed LLM formats: pipe-separated with "(channels: …)", or a plain
    # comma-separated list of names. Pick the delimiter that yields >1 chunk.
    chunks = [c.strip() for c in body.split("|") if c.strip()]
    if len(chunks) <= 1 and "(channels" not in body:
        chunks = [c.strip() for c in body.split(",") if c.strip()]
    for chunk in chunks:
        m = re.match(r"^(.*?)\s*\(channels:\s*(.*?)\)\s*$", chunk)
        if m:
            items.append({"name": m.group(1).strip(), "channels": m.group(2).strip()})
        else:
            items.append({"name": chunk, "channels": ""})
    return items


# --------------------------------------------------------------------------- #
# HTML rendering
# --------------------------------------------------------------------------- #
def _esc(s: Any) -> str:
    return html.escape(str(s))


_CSS = """
:root{--bg:#07090e;--panel:#0f131c;--line:#1f2638;--text:#e8eef9;--muted:#8a96ad;
--dim:#5b667a;--g:#22c55e;--a:#f59e0b;--r:#ef4444;--s:#38bdf8;--v:#a78bfa;--good:#0c1d18;--warn:#1d1606;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}
.wrap{max-width:960px;margin:0 auto;padding:40px 24px 80px;}
h1{font-size:26px;margin:0 0 6px;letter-spacing:-.3px}
h2{font-size:18px;margin:38px 0 14px;border-bottom:1px solid var(--line);padding-bottom:8px}
a{color:var(--s)}
.sub{color:var(--muted);font-size:14px}
.pill{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid var(--line)}
.pill.ok{background:var(--good);color:var(--g);border-color:#14532d}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0}
.card{flex:1;min-width:120px;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px}
.card .n{font-size:30px;font-weight:700}
.card .l{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.5px;margin-top:4px}
.rec{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px;margin:16px 0}
.rec.top{border-color:#14532d;box-shadow:0 0 0 1px #14532d33}
.rec h3{margin:0 0 4px;font-size:18px}
.rec .rank{color:var(--a);font-weight:700;font-size:13px;letter-spacing:.5px}
.rec .row{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}
.tag{background:#0b1220;border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:13px;color:var(--text)}
.tag b{color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.4px;display:block}
.warnbox{background:var(--warn);border:1px solid #5c4708;border-radius:8px;padding:4px 10px;color:var(--a);font-size:12px;margin-top:10px;display:inline-block}
pre.narr{white-space:pre-wrap;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px;font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;color:#cdd6e6;overflow:auto}
table{width:100%;border-collapse:collapse;margin-top:10px;font-size:14px}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.4px}
.foot{color:var(--dim);font-size:12px;margin-top:40px;border-top:1px solid var(--line);padding-top:16px}
.tl{font:12px/1.5 ui-monospace,Menlo,monospace;color:var(--muted)}
.tl .k{display:inline-block;width:130px;color:var(--dim)}
details{margin-top:10px}summary{cursor:pointer;color:var(--s)}
"""


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _channels_for(name: str, channels_by_candidate: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    target = _norm(name)
    for cand, chans in channels_by_candidate.items():
        if _norm(cand) == target:
            return chans
    return []


def render(*, segment: str, run_id: str, state: str, facts: dict[str, str],
           manifest_items: list[dict[str, str]], narrative: str,
           f1: dict[str, Any], timeline: list[dict[str, Any]],
           channels_by_candidate: dict[str, list[dict[str, Any]]]) -> str:
    counts = {
        "pain clusters": facts.get("pain_cluster_count", "?"),
        "candidates": facts.get("mandate_candidate_count", "?"),
        "passed moat": facts.get("moat_pass_count", "?"),
        "shortlist": facts.get("mandate_portfolio", facts.get("shortlist", "?")),
    }
    card_html = "".join(
        f'<div class="card"><div class="n">{_esc(v)}</div><div class="l">{_esc(k)}</div></div>'
        for k, v in counts.items()
    )

    rec_html = ""
    for i, it in enumerate(manifest_items, start=1):
        name = it["name"]
        weak = "weak" in it["channels"].lower() or "weak" in name.lower()
        title = name.split("(")[0].strip()
        top = " top" if i == 1 and not weak else ""
        warn = '<div class="warnbox">⚠ LLM flagged this as a weaker fit — verify the ICP</div>' if weak else ""
        f5 = _channels_for(title, channels_by_candidate)
        if f5:
            chan_rows = "".join(
                f'<div class="tag"><b>{_esc(ch.get("name_or_url","").split("/")[-1] or "channel")}</b>'
                f'~{_esc(ch.get("audience_size_estimate","?"))} members · '
                f'<a href="https://www.google.com/search?q={_esc(ch.get("first_100_prospect_source_query",""))}" '
                f'target="_blank">find prospects ↗</a></div>'
                for ch in f5[:5]
            )
        else:
            chan_rows = f'<div class="tag"><b>Where to find first prospects</b>{_esc(it["channels"]) or "see narrative"}</div>'
        rec_html += f"""
        <div class="rec{top}">
          <div class="rank">CANDIDATE #{i}</div>
          <h3>{_esc(title.replace('_',' ').title())}</h3>
          <div class="sub"><code>{_esc(title)}</code></div>
          <div class="row">{chan_rows}</div>
          {warn}
        </div>"""

    stats = ""
    if f1:
        ss = f1.get("sample_stats", {})
        srcs = ", ".join(f1.get("distinct_sources", []))
        stats = (f'<p class="sub">Evidence base: <b>{_esc(ss.get("total_posts_sampled","?"))}</b> community posts '
                 f'across <b>{_esc(ss.get("distinct_sources_sampled","?"))}</b> sources ({_esc(srcs)}), last 12 months.</p>')

    tl_html = ""
    for ev in timeline:
        k = ev.get("kind", "")
        if k in ("run_opened", "run_closed"):
            continue
        s = _esc(ev.get("summary", ""))[:160]
        tl_html += f'<div class="tl"><span class="k">{_esc(k)}</span> {s}</div>'

    gen = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mandate Discovery — {_esc(segment[:60])}</title><style>{_CSS}</style></head>
<body><div class="wrap">
  <span class="pill ok">● {_esc(state)}</span>
  <h1>Mandate Discovery Report</h1>
  <p class="sub">Target segment: <b>{_esc(segment)}</b></p>
  <p class="sub">Run <code>{_esc(run_id)}</code> · generated {gen}</p>
  {stats}

  <div class="cards">{card_html}</div>

  <h2>Recommended next mandates</h2>
  <p class="sub">Each is a recurring business process an Agent-X mandate could own, with the community
  channels where the first prospects already gather. These are leads to reach out to and validate — not
  yet named contacts (that is the lead-finder mandate's job, which this run is designed to spawn per pick).</p>
  {rec_html}

  <h2>What the agent found (its own words)</h2>
  <pre class="narr">{_esc(narrative) or '(narrative not captured for this run)'}</pre>

  <h2>How to reach the prospects</h2>
  <table><tr><th>Mandate</th><th>Channel</th><th>Audience</th><th>Prospect-finding search</th></tr>
  {''.join(
      ''.join(
        f'<tr><td>{_esc(it["name"].split("(")[0].strip())}</td>'
        f'<td>{_esc(ch.get("name_or_url",""))}</td>'
        f'<td>{_esc(ch.get("audience_size_estimate","?"))}</td>'
        f'<td><a href="https://www.google.com/search?q={_esc(ch.get("first_100_prospect_source_query",""))}" target="_blank"><code>{_esc(ch.get("first_100_prospect_source_query",""))}</code></a></td></tr>'
        for ch in (_channels_for(it["name"].split("(")[0].strip(), channels_by_candidate)[:4] or [{}])
      )
      for it in manifest_items
  )}
  </table>
  <p class="sub" style="margin-top:12px">Each search query finds 100 prospects already discussing this pain. To turn a
  channel into actual named contacts (company, role, buying-signal citation), run the <code>lead-finder</code>
  mandate against it — mandate-discovery is designed to spawn lead-finder per approved pick.</p>

  <details><summary>Harness timeline ({len(timeline)} events)</summary>
    <div style="margin-top:10px">{tl_html}</div>
  </details>

  <p class="foot">Generated by Agent-X mandate-discovery (read-only: no outreach, no posting). Counts and
  audience sizes are the agent's heuristic estimates pending human review; facts are committed in
  <i>probation</i> status. Methodology: F1 community sampling (Firecrawl) → F2 pain clustering →
  F3 mandate shaping → F4 competitor/moat → F5 buyer-channel mapping → ranked shortlist.</p>
</div></body></html>"""


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
async def main() -> int:
    ap = argparse.ArgumentParser(description="Render an HTML report for a mandate-discovery run.")
    ap.add_argument("--instance", help="instance_id to report on")
    ap.add_argument("--latest", action="store_true", help="use the most recent run log")
    ap.add_argument("--out", help="output HTML path")
    args = ap.parse_args()

    if args.latest or not args.instance:
        log_path = _latest_run_log()
        if log_path is None:
            print(f"No run logs under {LOG_DIR}/")
            return 1
        instance_id = log_path.parent.name
    else:
        instance_id = args.instance
        log_path = _run_log_for_instance(instance_id)

    events = _read_log(log_path) if log_path else []
    # Resolve the true instance_id from the log header (folder name is path-safe-encoded).
    instance_id = _log_field(events, "run_opened", "instance_id", instance_id)
    run_id = _log_field(events, "run_opened", "run_id", instance_id)
    state = next((e.get("detail", {}).get("state", "?") for e in reversed(events) if e.get("kind") == "run_closed"), "?")

    # Segment from the "run invoked" thought's target.
    segment = ""
    for ev in events:
        tgt = ev.get("detail", {}).get("target")
        if isinstance(tgt, dict) and tgt.get("segment"):
            segment = str(tgt["segment"])
            break

    settings = Settings()
    client: AsyncMongoClient[dict[str, object]] = AsyncMongoClient(settings.mongodb_uri.get_secret_value())
    try:
        db = client[settings.mongodb_db_name]
        rows = [f async for f in db[c.HEAP_FACT].find({"instance_id": instance_id})]
        channels_by_candidate = await _load_buyer_channels(db, run_id, instance_id)
    finally:
        await client.close()

    facts = {str(r.get("predicate")): str(r.get("object")) for r in rows}
    manifest = facts.get("buyer_source_manifest", "")
    manifest_items = _parse_manifest(manifest) if manifest else []
    narrative = _finish_summary(events)
    f1 = _f1_stats(events)

    if not facts:
        print(f"WARNING: no heap facts for instance {instance_id!r} — report will be sparse.")

    html_out = render(
        segment=segment or "(segment not recorded)",
        run_id=run_id, state=state, facts=facts, manifest_items=manifest_items,
        narrative=narrative, f1=f1, timeline=events,
        channels_by_candidate=channels_by_candidate,
    )
    out_path = Path(args.out) if args.out else Path("docs/discovery_reports") / f"{instance_id}.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_out, encoding="utf-8")
    print(f"Wrote {out_path}  ({len(manifest_items)} mandate(s), state={state})")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
