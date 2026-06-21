import assert from "node:assert/strict";
import test from "node:test";

import {
  factConfidenceTone,
  factStatusLabel,
  factStatusTone,
  filterSyscallEvents,
  formatFactSummary,
  isSyscallKind,
  journalActionTone,
  truncateArgs,
} from "../src/lib/inspector-c4";
import type { JournalEvent } from "../src/lib/types";

const baseEvent = (kind: string, overrides: Partial<JournalEvent> = {}): JournalEvent => ({
  id: `j-${kind}-1`,
  at: "2026-06-21T10:00:00+05:30",
  kind,
  instance_id: "inst-1",
  run_id: "run-1",
  actor: "kernel",
  title: `${kind} title`,
  detail: `${kind} detail`,
  source: "kernel-journal",
  ...overrides,
});

test("isSyscallKind accepts the two kernel syscall kinds only", () => {
  assert.equal(isSyscallKind("syscall_attempted"), true);
  assert.equal(isSyscallKind("syscall_settled"), true);
  assert.equal(isSyscallKind("run_created"), false);
  assert.equal(isSyscallKind("run_hydrated"), false);
  assert.equal(isSyscallKind("run_parked"), false);
  assert.equal(isSyscallKind(""), false);
  assert.equal(isSyscallKind(undefined), false);
});

test("filterSyscallEvents keeps only attempted + settled, in original order", () => {
  const events: JournalEvent[] = [
    baseEvent("run_created", { id: "1" }),
    baseEvent("syscall_attempted", { id: "2" }),
    baseEvent("run_parked", { id: "3" }),
    baseEvent("syscall_settled", { id: "4" }),
    baseEvent("run_settled", { id: "5" }),
    baseEvent("syscall_attempted", { id: "6" }),
  ];
  const filtered = filterSyscallEvents(events);
  assert.deepEqual(
    filtered.map((e: JournalEvent) => e.id),
    ["2", "4", "6"],
  );
  // The original input must NOT be mutated.
  assert.equal(events.length, 6);
});

test("filterSyscallEvents returns [] when no syscall events present", () => {
  const events: JournalEvent[] = [
    baseEvent("run_created", { id: "1" }),
    baseEvent("run_parked", { id: "2" }),
  ];
  assert.deepEqual(filterSyscallEvents(events), []);
});

test("journalActionTone maps settled=good, attempted=info, others=neutral", () => {
  assert.equal(journalActionTone("syscall_settled"), "good");
  assert.equal(journalActionTone("syscall_attempted"), "info");
  assert.equal(journalActionTone("run_created"), "neutral");
  assert.equal(journalActionTone(undefined), "neutral");
});

test("factConfidenceTone maps confidence 0..1 to good / warn / hot", () => {
  assert.equal(factConfidenceTone(0.95), "good");
  assert.equal(factConfidenceTone(0.7), "good");
  assert.equal(factConfidenceTone(0.5), "warn");
  assert.equal(factConfidenceTone(0.3), "warn");
  assert.equal(factConfidenceTone(0.1), "hot");
  assert.equal(factConfidenceTone(0), "hot");
  // Out-of-band: clamp gracefully rather than throw.
  assert.equal(factConfidenceTone(1.2), "good");
  assert.equal(factConfidenceTone(-0.5), "hot");
});

test("factStatusTone + factStatusLabel reflect promotion state", () => {
  assert.equal(factStatusTone("promoted"), "good");
  assert.equal(factStatusTone("probation"), "warn");
  assert.equal(factStatusTone("retired"), "hot");
  assert.equal(factStatusTone("unknown"), "neutral");
  assert.equal(factStatusLabel("promoted"), "Verified");
  assert.equal(factStatusLabel("probation"), "Probation");
  assert.equal(factStatusLabel("retired"), "Retired");
  assert.equal(factStatusLabel("anything-else"), "anything-else");
});

test("formatFactSummary returns subject predicate object", () => {
  assert.equal(
    formatFactSummary({
      subject: "Kaveri Crackers",
      predicate: "is_business_type",
      object: "sparklers-wholesale",
    }),
    "Kaveri Crackers is_business_type sparklers-wholesale",
  );
  // Missing subject should not blow up — degrade to a placeholder.
  assert.equal(
    formatFactSummary({
      subject: "",
      predicate: "is",
      object: "thing",
    }),
    "(unknown) is thing",
  );
});

test("truncateArgs caps a JSON arg payload to a short preview", () => {
  const tiny = truncateArgs({ lead_id: "L1" }, 20);
  assert.match(tiny, /lead_id/);
  assert.ok(tiny.length <= 60, `expected short preview, got ${tiny.length} chars: ${tiny}`);

  const huge = truncateArgs({ payload: "x".repeat(500) }, 40);
  assert.match(huge, /…/);
  assert.ok(huge.length <= 80, `expected truncated preview, got ${huge.length} chars`);
});

test("filterSyscallEvents tolerates bad input shapes (defensive)", () => {
  // Empty array.
  assert.deepEqual(filterSyscallEvents([]), []);
  // Undefined / null / non-array should NOT throw — the tab uses this on
  // freshly-loaded state where the API may not yet have responded.
  assert.deepEqual(filterSyscallEvents(undefined as unknown as JournalEvent[]), []);
  assert.deepEqual(filterSyscallEvents(null as unknown as JournalEvent[]), []);
});
