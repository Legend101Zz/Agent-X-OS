#!/usr/bin/env python3
"""view_run.py — read the detailed log of a single mandate-instance run.

The kernel writes one JSONL file per run (see
``packages/kernel/src/agentx_kernel/run_log.py``) capturing every harness
action (Think / Call / Claim / Escalate / Finish), every syscall result with an
output summary, every gate/park/escalate decision, and the terminal state. This
script renders that file as a readable, colourised timeline so you can see
*exactly what the harness did* — which is the thing that was previously
invisible when a run escalated or crashed.

Usage::

    # List recent runs across all instances (most recent first)
    uv run python scripts/view_run.py
    uv run python scripts/view_run.py --list

    # Show the most recent run, full timeline
    uv run python scripts/view_run.py --latest

    # Show a specific run by run_id (or any unique substring of it)
    uv run python scripts/view_run.py agentx_discovery_1782102614_default

    # List runs for one instance
    uv run python scripts/view_run.py --instance agentx_discovery_1782102614_default

    # Dump the raw JSONL (no formatting)
    uv run python scripts/view_run.py <run_id> --raw

The log directory is ``AGENTX_RUN_LOG_DIR`` (env) or ``./run_logs`` by default.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

LOG_DIR = Path(os.environ.get("AGENTX_RUN_LOG_DIR", "run_logs"))

# ANSI colours — disabled automatically when stdout is not a TTY.
_TTY = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


def dim(t: str) -> str:
    return _c("2", t)


def bold(t: str) -> str:
    return _c("1", t)


# kind → (symbol, colour code)
_KIND_STYLE: dict[str, tuple[str, str]] = {
    "run_opened": ("▶", "36"),
    "thought": ("·", "37"),
    "syscall_attempt": ("→", "33"),
    "syscall_result": ("←", "32"),
    "parked": ("⏸", "35"),
    "resumed": ("▶", "36"),
    "verify": ("✓", "32"),
    "decision": ("◆", "34"),
    "error": ("✗", "31"),
    "run_closed": ("■", "36"),
}


def _iter_run_files() -> list[Path]:
    if not LOG_DIR.exists():
        return []
    return sorted(LOG_DIR.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)


def _read_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"kind": "error", "summary": f"(unparseable log line) {line[:200]}", "detail": {}})
    return events


def _run_meta(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract header + terminal metadata from a run's events."""
    meta: dict[str, Any] = {"run_id": "", "instance_id": "", "type_ref": "", "state": "running", "events": len(events)}
    for ev in events:
        if ev.get("kind") == "run_opened":
            d = ev.get("detail", {})
            meta["run_id"] = d.get("run_id", meta["run_id"])
            meta["instance_id"] = d.get("instance_id", "")
            meta["type_ref"] = d.get("type_ref", "")
            meta["opened_at"] = ev.get("ts", "")
        if ev.get("kind") == "run_closed":
            meta["state"] = ev.get("detail", {}).get("state", "?")
            meta["closed_at"] = ev.get("ts", "")
    return meta


def _find_run(token: str) -> Path | None:
    """Find a run file by run_id, filename stem, or unique substring."""
    files = _iter_run_files()
    # Exact filename stem first
    for p in files:
        if p.stem == token:
            return p
    # Match the run_id stored in the header, or substring of file path
    matches: list[Path] = []
    for p in files:
        meta = _run_meta(_read_events(p))
        if token == meta.get("run_id") or token in p.stem or token in str(meta.get("run_id", "")):
            matches.append(p)
    if matches:
        return matches[0]
    return None


def _fmt_ts(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts).strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return ts[:8] if ts else "--:--:--"


def _fmt_detail(detail: dict[str, Any], indent: str) -> list[str]:
    lines: list[str] = []
    for key, value in detail.items():
        if key == "step":
            continue
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value, default=str, ensure_ascii=False)
            if len(rendered) > 140:
                rendered = rendered[:140] + " …"
        else:
            rendered = str(value)
        lines.append(dim(f"{indent}{key}: ") + rendered)
    return lines


def show_run(path: Path, *, raw: bool = False) -> None:
    if raw:
        sys.stdout.write(path.read_text(encoding="utf-8"))
        return
    events = _read_events(path)
    meta = _run_meta(events)
    state = meta.get("state", "?")
    state_colour = "32" if state == "settled" else "31" if state == "crashed" else "35" if state == "parked" else "37"
    print()
    print(bold(f"  Run: {meta.get('run_id') or path.stem}"))
    print(f"  instance: {meta.get('instance_id', '')}")
    print(f"  type:     {meta.get('type_ref', '')}")
    print(f"  state:    {_c(state_colour, bold(str(state)))}    events: {meta['events']}    file: {path}")
    print(dim("  " + "─" * 72))
    for ev in events:
        kind = ev.get("kind", "?")
        symbol, colour = _KIND_STYLE.get(kind, ("•", "37"))
        ts = _fmt_ts(ev.get("ts", ""))
        summary = ev.get("summary", "")
        print(f"  {dim(ts)} {_c(colour, symbol)} {_c(colour, kind):<24} {summary}")
        detail = ev.get("detail", {})
        if isinstance(detail, dict) and detail:
            for line in _fmt_detail(detail, "          "):
                print(line)
    print()


def list_runs(instance: str | None = None, limit: int = 30) -> None:
    files = _iter_run_files()
    if instance:
        files = [p for p in files if p.parent.name == instance or instance in p.parent.name]
    if not files:
        where = f" for instance {instance!r}" if instance else ""
        print(f"No runs found{where} under {LOG_DIR}/ (set AGENTX_RUN_LOG_DIR if logs live elsewhere).")
        return
    print()
    print(bold(f"  {'STATE':<9} {'EVENTS':>6}  {'WHEN':<20} RUN"))
    print(dim("  " + "─" * 78))
    for p in files[:limit]:
        meta = _run_meta(_read_events(p))
        state = meta.get("state", "?")
        colour = "32" if state == "settled" else "31" if state == "crashed" else "35" if state == "parked" else "37"
        when = _fmt_full(meta.get("closed_at") or meta.get("opened_at", ""))
        print(f"  {_c(colour, f'{state:<9}')} {meta['events']:>6}  {when:<20} {meta.get('run_id') or p.stem}")
    print()
    print(dim(f"  {min(len(files), limit)} of {len(files)} run(s). View one: scripts/view_run.py <run_id>"))
    print()


def _fmt_full(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return ts[:19] if ts else "—"


def main() -> int:
    parser = argparse.ArgumentParser(description="View the detailed log of a mandate-instance run.")
    parser.add_argument("run", nargs="?", help="run_id (or unique substring) to display")
    parser.add_argument("--latest", action="store_true", help="show the most recent run")
    parser.add_argument("--list", action="store_true", help="list recent runs")
    parser.add_argument("--instance", help="list runs for one instance_id")
    parser.add_argument("--raw", action="store_true", help="dump raw JSONL")
    parser.add_argument("--limit", type=int, default=30, help="max runs to list")
    args = parser.parse_args()

    if args.instance and not args.run and not args.latest:
        list_runs(instance=args.instance, limit=args.limit)
        return 0
    if args.latest:
        files = _iter_run_files()
        if not files:
            print(f"No runs found under {LOG_DIR}/")
            return 1
        show_run(files[0], raw=args.raw)
        return 0
    if args.run:
        path = _find_run(args.run)
        if path is None:
            print(f"No run matching {args.run!r} under {LOG_DIR}/")
            return 1
        show_run(path, raw=args.raw)
        return 0
    # Default: list
    list_runs(limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
