"""Per-run structured log sink — durable, crash-safe visibility into a single run.

The kernel builds a ``Trace`` (``agentx_contracts.verification.Trace``) as a run
executes, but until now that trace was **never persisted**: it lived only on the
in-memory ``RunResult``, which the caller discards on a crash. So when a run
escalates or crashes you could not see *what the harness actually did* — which
faculty ran, what the F1 syscall returned, which gate dropped the run.

``RunLog`` closes that gap. It writes one JSONL file per run, incrementally and
flushed after every event, so even a hard crash leaves a complete record on
disk. One file = one ``MandateRun`` (one stack frame); files are grouped by
instance so ``view_run.py`` can list "every run of this instance".

Design rules:
  - **Never break a run because of logging.** Every write is wrapped; an IO
    error degrades to a no-op, it does not raise into the run loop.
  - **Append-only + flush.** Each event is a single JSON line, flushed
    immediately. A reader can ``tail -f`` a live run.
  - **No new dependency / no Mongo / no schema migration.** This is a sidecar
    file sink, so it touches neither the journal (source of truth) nor the
    UI-backend contract. The journal stays the durable source of truth for
    *facts*; this is the durable record of *reasoning*.

Layout::

    <base_dir>/<instance_id>/<run_id>.jsonl

The first line is a ``run_opened`` header; the last is a ``run_closed`` terminal
event carrying the final state. Everything in between mirrors the ``Trace`` plus
richer detail the trace omits (syscall output summaries, harness action bodies).
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Default location for run logs. Overridable via the AGENTX_RUN_LOG_DIR env var
# so a deployment can point it at a mounted volume. Relative to the process CWD
# by default (the repo root when run via scripts/run_mandate_discovery.py).
_DEFAULT_DIR_ENV = "AGENTX_RUN_LOG_DIR"
_DEFAULT_DIR = "run_logs"

_SAFE = re.compile(r"[^A-Za-z0-9_.:-]+")


def default_run_log_dir() -> str:
    """The configured run-log root (env override → repo-relative default)."""
    return os.environ.get(_DEFAULT_DIR_ENV, _DEFAULT_DIR)


def _safe(component: str) -> str:
    """Make a path component filesystem-safe (run_ids contain ':' on every OS but Windows)."""
    cleaned = _SAFE.sub("_", component.strip()) or "unknown"
    return cleaned[:200]


def _summarize(value: Any, *, depth: int = 0) -> Any:
    """Shrink a JSON-ish value so the log stays readable: clip strings, cap lists.

    Logs are for humans skimming "what happened", not a byte-for-byte replica of
    every syscall payload (the journal/receipts already hold those). We keep the
    shape but clip long strings to 500 chars and lists to the first 8 items.
    """
    if isinstance(value, str):
        # Long enough to keep a harness's finish/claim/think narrative intact
        # (that prose is the "deep research" signal), short enough that a raw F1
        # post can't flood the log. Syscall payloads are already summarized to
        # counts before reaching here.
        return value if len(value) <= 4000 else value[:4000] + f"…(+{len(value) - 4000} chars)"
    if isinstance(value, dict):
        if depth >= 4:
            return {"…": f"{len(value)} keys"}
        return {str(k): _summarize(v, depth=depth + 1) for k, v in list(value.items())[:40]}
    if isinstance(value, (list, tuple)):
        if depth >= 4:
            return f"[{len(value)} items]"
        head = [_summarize(v, depth=depth + 1) for v in list(value)[:8]]
        if len(value) > 8:
            head.append(f"…(+{len(value) - 8} more)")
        return head
    return value


class RunLog:
    """A single run's append-only JSONL log. Construct one per run; ``close()`` at the end."""

    def __init__(self, *, run_id: str, instance_id: str, type_ref: str, base_dir: str | None = None) -> None:
        self.run_id = run_id
        self.instance_id = instance_id
        self.type_ref = type_ref
        self._seq = 0
        self._enabled = True
        root = Path(base_dir or default_run_log_dir())
        self.path = root / _safe(instance_id) / f"{_safe(run_id)}.jsonl"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Truncate any prior file for this exact run_id (a re-run is a fresh record).
            self._fh = self.path.open("w", encoding="utf-8")
        except OSError:
            self._enabled = False
            self._fh = None
        self.event(
            "run_opened",
            f"run {run_id} opened",
            {"run_id": run_id, "instance_id": instance_id, "type_ref": type_ref},
        )

    def event(self, kind: str, summary: str, detail: dict[str, Any] | None = None) -> None:
        """Append one event. Never raises — logging must not break the run."""
        if not self._enabled or self._fh is None:
            return
        self._seq += 1
        record = {
            "seq": self._seq,
            "ts": datetime.now(UTC).isoformat(),
            "kind": kind,
            "summary": summary,
            "detail": _summarize(detail or {}),
        }
        try:
            self._fh.write(json.dumps(record, default=str) + "\n")
            self._fh.flush()
        except (OSError, TypeError, ValueError):
            # A bad payload or a closed file should not kill the run.
            self._enabled = False

    def terminal(self, state: str, detail: dict[str, Any] | None = None) -> None:
        """Write the closing event carrying the run's final state, then close the file."""
        self.event("run_closed", f"run ended: state={state}", {"state": state, **(detail or {})})
        self.close()

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None


class _NullRunLog(RunLog):
    """A RunLog that writes nowhere — used when logging is disabled, so callers need no None checks."""

    def __init__(self) -> None:  # noqa: D107 — intentionally bypasses file setup
        self.run_id = ""
        self.instance_id = ""
        self.type_ref = ""
        self._seq = 0
        self._enabled = False
        self._fh = None
        self.path = Path(os.devnull)

    def event(self, kind: str, summary: str, detail: dict[str, Any] | None = None) -> None:
        return

    def terminal(self, state: str, detail: dict[str, Any] | None = None) -> None:
        return

    def close(self) -> None:
        return


NULL_RUN_LOG: RunLog = _NullRunLog()
