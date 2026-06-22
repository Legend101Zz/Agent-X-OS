#!/usr/bin/env python3
"""lead_report.py — render a shareable HTML report for a lead-finder run.

Reads the lead-finder run's committed heap facts (actionable_lead +
qualified_lead_score, with cited website evidence in provenance) and the
draft_email receipt, and emits a self-contained dark-themed HTML lead sheet:
each prospect with its qualification score, the evidence the agent cited, the
reachable contact path, and the personalized outreach draft.

Usage::

    uv run python scripts/lead_report.py --latest
    uv run python scripts/lead_report.py --instance agentx_dogfood_1782140356
    uv run python scripts/lead_report.py --instance <id> --out docs/discovery_reports/leads_foo.html
"""

from __future__ import annotations

import argparse
import asyncio
import html
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import agentx_db.collections as c
from agentx_contracts.config import Settings
from pymongo import AsyncMongoClient

LOG_DIR = Path(os.environ.get("AGENTX_RUN_LOG_DIR", "run_logs"))


def _latest_dogfood_log() -> Path | None:
    files = sorted(LOG_DIR.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files:
        if "dogfood" in p.parent.name or "lead" in p.parent.name:
            return p
    return files[0] if files else None


def _read_log(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not path or not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(__import__("json").loads(line))
            except ValueError:
                pass
    return out


def _esc(s: Any) -> str:
    return html.escape(str(s))


_CSS = """
:root{--bg:#07090e;--panel:#0f131c;--line:#1f2638;--text:#e8eef9;--muted:#8a96ad;
--dim:#5b667a;--g:#22c55e;--a:#f59e0b;--r:#ef4444;--s:#38bdf8;--v:#a78bfa;--good:#0c1d18;--warn:#1d1606;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}
.wrap{max-width:920px;margin:0 auto;padding:40px 24px 80px;}
h1{font-size:26px;margin:0 0 6px;letter-spacing:-.3px}
h2{font-size:18px;margin:38px 0 14px;border-bottom:1px solid var(--line);padding-bottom:8px}
.sub{color:var(--muted);font-size:14px}
code{color:var(--s)}
.pill{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid var(--line)}
.pill.ok{background:var(--good);color:var(--g);border-color:#14532d}
.lead{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px;margin:16px 0}
.lead h3{margin:0;font-size:19px;display:flex;justify-content:space-between;align-items:center;gap:10px}
.score{font-size:13px;font-weight:700;padding:3px 10px;border-radius:8px;background:var(--good);color:var(--g);border:1px solid #14532d;white-space:nowrap}
.score.mid{background:var(--warn);color:var(--a);border-color:#5c4708}
.contact{margin:10px 0;font-size:14px}
.contact b{color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.4px;margin-right:6px}
ul.ev{margin:10px 0 0;padding-left:0;list-style:none}
ul.ev li{padding:7px 12px;margin:6px 0;background:#0b1220;border-left:2px solid var(--s);border-radius:6px;font-size:13px;color:#cdd6e6}
.draft{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:0;overflow:hidden;margin-top:12px}
.draft .hd{background:#0b1220;padding:12px 16px;border-bottom:1px solid var(--line);font-size:13px}
.draft .hd .k{color:var(--dim);display:inline-block;width:64px}
.draft pre{white-space:pre-wrap;padding:18px;margin:0;font:14px/1.65 -apple-system,Menlo,monospace;color:#dde5f2}
.foot{color:var(--dim);font-size:12px;margin-top:40px;border-top:1px solid var(--line);padding-top:16px}
"""


def render(*, icp: str, location: str, run_id: str, state: str,
           leads: list[dict[str, Any]], draft: dict[str, Any]) -> str:
    lead_html = ""
    for ld in leads:
        try:
            score = float(ld.get("score", 0) or 0)
        except (TypeError, ValueError):
            score = 0.0
        cls = "score" if score >= 0.7 else "score mid"
        ev = "".join(f"<li>{_esc(e)}</li>" for e in ld.get("evidence", [])[:7])
        contact = ld.get("contact", "")
        lead_html += f"""
        <div class="lead">
          <h3>{_esc(ld.get('company','(unknown)'))}<span class="{cls}">score {score:.2f}</span></h3>
          {f'<div class="contact"><b>Reach</b>{_esc(contact)}</div>' if contact else ''}
          <ul class="ev">{ev or '<li>(no evidence captured)</li>'}</ul>
        </div>"""

    draft_html = ""
    if draft:
        draft_html = f"""
        <div class="draft">
          <div class="hd"><span class="k">To</span>{_esc(draft.get('to',''))}<br>
          <span class="k">Subject</span>{_esc(draft.get('subject',''))}</div>
          <pre>{_esc(draft.get('body',''))}</pre>
        </div>
        <p class="sub">Drafted by the agent and <b>parked for your approval</b> — nothing was sent. The contact path
        above is a real, reachable channel the agent found (it does not invent personal email addresses).</p>"""

    gen = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lead-finder — {_esc(icp[:50])}</title><style>{_CSS}</style></head>
<body><div class="wrap">
  <span class="pill ok">● {_esc(state)}</span>
  <h1>Lead-Finder Report</h1>
  <p class="sub">ICP: <b>{_esc(icp)}</b>{f' · {_esc(location)}' if location else ''}</p>
  <p class="sub">Run <code>{_esc(run_id)}</code> · {len(leads)} qualified lead(s) · generated {gen}</p>

  <h2>Qualified leads</h2>
  <p class="sub">Each prospect is a real company the agent found and qualified, with the website evidence it cited.
  Verify before outreach — scores and contacts are the agent's findings pending your review.</p>
  {lead_html or '<p class="sub">No leads were committed for this run.</p>'}

  <h2>Drafted outreach</h2>
  {draft_html or '<p class="sub">No draft email captured for this run.</p>'}

  <p class="foot">Generated by Agent-X lead-finder. Leads carry provenance (cited website quotes); the draft is a
  human-approval-gated proposal — Agent-X never sends without your sign-off. Verify a prospect's contact details
  independently before reaching out.</p>
</div></body></html>"""


async def main() -> int:
    ap = argparse.ArgumentParser(description="Render an HTML report for a lead-finder run.")
    ap.add_argument("--instance", help="instance_id")
    ap.add_argument("--latest", action="store_true")
    ap.add_argument("--out", help="output HTML path")
    args = ap.parse_args()

    if args.latest or not args.instance:
        log_path = _latest_dogfood_log()
        instance_id = log_path.parent.name if log_path else ""
    else:
        instance_id = args.instance
        folder = LOG_DIR / re.sub(r"[^A-Za-z0-9_.:-]+", "_", instance_id)
        logs = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True) if folder.exists() else []
        log_path = logs[0] if logs else None

    events = _read_log(log_path) if log_path else []
    for ev in events:
        if ev.get("kind") == "run_opened":
            instance_id = ev.get("detail", {}).get("instance_id", instance_id)
    run_id = next((e.get("detail", {}).get("run_id", "") for e in events if e.get("kind") == "run_opened"), instance_id)
    state = next((e.get("detail", {}).get("state", "settled") for e in reversed(events) if e.get("kind") == "run_closed"), "settled")
    icp, location = "", ""
    for ev in events:
        tgt = ev.get("detail", {}).get("target")
        if isinstance(tgt, dict) and tgt.get("icp"):
            icp = str(tgt.get("icp", ""))
            location = str(tgt.get("location", ""))
            break

    settings = Settings()
    client: AsyncMongoClient[dict[str, object]] = AsyncMongoClient(settings.mongodb_uri.get_secret_value())
    try:
        db = client[settings.mongodb_db_name]
        rows = [f async for f in db[c.HEAP_FACT].find({"instance_id": instance_id})]
        draft: dict[str, Any] = {}
        async for r in db[c.SYSCALL_RECEIPT].find({"run_id": {"$regex": re.escape(instance_id)}}):
            nm = r.get("syscall") or r.get("fulfilled_by")
            if nm and "draft" in str(nm):
                out = r.get("output") or (r.get("result") or {}).get("output") or {}
                if isinstance(out, dict) and out.get("body"):
                    draft = {"to": out.get("to", ""), "subject": out.get("subject", ""), "body": out.get("body", "")}
    finally:
        await client.close()

    def _company_like(v: str) -> bool:
        # A real company name, not an internal lead id ("firecrawl_1") or a
        # placeholder ("company") or a bare number.
        v = v.strip()
        if not v or v.lower() == "company" or re.fullmatch(r"[a-z]+_\d+", v) or v.replace(".", "").isdigit():
            return False
        return True

    # Group facts by lead (subject is the stable key, but the company NAME may
    # live in either the subject or the actionable_lead object — pick whichever
    # is company-like).
    leads_by_company: dict[str, dict[str, Any]] = {}
    for r in rows:
        subj = str(r.get("subject", ""))
        if not subj:
            continue
        bucket = leads_by_company.setdefault(subj, {"company": subj, "score": None, "evidence": [], "contact": ""})
        pred = r.get("predicate")
        if pred == "qualified_lead_score":
            bucket["score"] = r.get("object")
        if pred == "actionable_lead":
            obj = str(r.get("object", ""))
            # Prefer a company-like name: subject first, else the object.
            bucket["company"] = subj if _company_like(subj) else (obj if _company_like(obj) else subj)
        prov = r.get("provenance") or {}
        ev = prov.get("evidence") if isinstance(prov, dict) else None
        if isinstance(ev, list):
            for e in ev:
                es = str(e)
                if es not in bucket["evidence"]:
                    bucket["evidence"].append(es)
                    m = re.search(r"contact[^:]*:\s*(https?://\S+|[\w./-]+form\S*)", es, re.I)
                    if m and not bucket["contact"]:
                        bucket["contact"] = m.group(0)
    leads = sorted(leads_by_company.values(), key=lambda d: float(d.get("score") or 0), reverse=True)
    # If a lead has no explicit contact line, fall back to the draft 'to'.
    for ld in leads:
        if not ld["contact"] and draft.get("to") and ld["company"].split()[0].lower() in str(draft.get("to","")).lower():
            ld["contact"] = draft["to"]

    html_out = render(icp=icp or "(icp not recorded)", location=location, run_id=run_id,
                      state=state, leads=leads, draft=draft)
    safe = re.sub(r"[^A-Za-z0-9]+", "_", (icp or instance_id))[:40].strip("_").lower()
    out_path = Path(args.out) if args.out else Path("docs/discovery_reports") / f"leads_{safe}.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_out, encoding="utf-8")
    print(f"Wrote {out_path}  ({len(leads)} lead(s), draft={'yes' if draft else 'no'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
