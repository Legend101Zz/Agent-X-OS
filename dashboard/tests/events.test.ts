import assert from "node:assert/strict";
import test from "node:test";

import {
  invalidationsForJournalEvent,
  parseJournalFrame,
} from "../src/lib/events";

test("parseJournalFrame parses a named journal SSE payload", () => {
  const event = parseJournalFrame(JSON.stringify({
    event_id: "evt_7",
    kind: "run_parked",
    seq: 7,
    ts: "2026-06-19T12:00:00Z",
    instance_id: "inst_1",
    run_id: "run_1",
    actor: "kernel",
    reason: "approval required",
  }));

  assert.equal(event.event_id, "evt_7");
  assert.equal(event.kind, "run_parked");
  assert.equal(event.seq, 7);
});

test("run_settled invalidates settlement-backed dashboard slices", () => {
  assert.deepEqual(
    invalidationsForJournalEvent({ event_id: "settled", kind: "run_settled", seq: 8 }),
    ["overview", "instances", "runs", "journal", "evalCases"],
  );
});

test("run_parked invalidates the approval and run surfaces", () => {
  assert.deepEqual(
    invalidationsForJournalEvent({ event_id: "parked", kind: "run_parked", seq: 9 }),
    ["overview", "runs", "journal", "approvals"],
  );
});

test("generic journal events invalidate the overview and ledger", () => {
  assert.deepEqual(
    invalidationsForJournalEvent({ event_id: "manager", kind: "manager_action", seq: 10 }),
    ["overview", "journal"],
  );
});
