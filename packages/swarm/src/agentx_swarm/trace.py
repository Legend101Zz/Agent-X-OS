"""Trace serialization helpers for a future viewer."""

from __future__ import annotations

from agentx_contracts import JsonObject, Scorecard, Trace


def trace_to_viewer_payload(trace: Trace, *, scorecard: Scorecard | None = None) -> JsonObject:
    """Return JSON-safe trace data shaped for a timeline viewer."""

    payload: JsonObject = {
        "run_id": trace.run_id,
        "events": [
            {
                "seq": event.seq,
                "ts": event.ts.isoformat().replace("+00:00", "Z"),
                "kind": event.kind,
                "summary": event.summary,
                "detail": event.detail,
            }
            for event in trace.events
        ],
    }
    if scorecard is not None:
        payload["scorecard"] = scorecard.model_dump(mode="json")
    return payload
