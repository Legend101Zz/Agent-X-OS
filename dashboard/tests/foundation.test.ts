import assert from "node:assert/strict";
import test from "node:test";

import { cx } from "../src/lib/cx";
import {
  formatCurrency,
  formatRelative,
  formatTime,
  ringTone,
  runStateLabel,
  runStateTone,
  shortId,
  journalKindTone,
  healthTone,
} from "../src/lib/format";

test("cx joins strings and skips falsy values", () => {
  // cx() separates class names with spaces, like the popular cn() libs.
  assert.equal(cx("a", "b"), "a b");
  assert.equal(cx("a", false, null, undefined, "b"), "a b");
  assert.equal(cx("a", true && "b"), "a b");
  assert.equal(cx("a", "b", false), "a b");
});

test("cx evaluates conditional objects", () => {
  assert.equal(cx("a", { b: true, c: false }), "a b");
  assert.equal(cx({ a: true, b: false }), "a");
});

test("formatCurrency handles null, sign, decimals", () => {
  assert.equal(formatCurrency(null), "—");
  assert.equal(formatCurrency(0), "$0.00");
  assert.equal(formatCurrency(1234.5), "$1,234.50");
  assert.equal(formatCurrency(-42, { sign: true }), "−$42.00");
  assert.equal(formatCurrency(42, { sign: true }), "+$42.00");
});

test("formatRelative returns humanised times", () => {
  const fiveMinAgo = new Date(Date.now() - 5 * 60_000).toISOString();
  assert.match(formatRelative(fiveMinAgo), /5m ago/);
  assert.equal(formatRelative(null), "—");
});

test("formatTime returns HH:MM:SS-ish string", () => {
  const t = "2026-06-21T08:09:05.000Z";
  const out = formatTime(t);
  assert.match(out, /\d{1,2}:\d{2}:\d{2}/);
});

test("ringTone maps L0-L4 correctly", () => {
  assert.equal(ringTone("L0"), "l0");
  assert.equal(ringTone("L4"), "l4");
  assert.equal(ringTone("L99"), "neutral");
  assert.equal(ringTone(null), "neutral");
});

test("runStateLabel and runStateTone", () => {
  assert.equal(runStateLabel("waiting_approval"), "Waiting Approval");
  assert.equal(runStateTone("complete"), "good");
  assert.equal(runStateTone("failed"), "hot");
});

test("shortId strips well-known prefixes", () => {
  assert.equal(shortId("inst_acme1234"), "acme12…");
  assert.equal(shortId("abcdef"), "abcdef");
  assert.equal(shortId(null), "—");
});

test("journalKindTone picks by event kind suffix", () => {
  assert.equal(journalKindTone("run_settled"), "good");
  assert.equal(journalKindTone("run_parked"), "warn");
  assert.equal(journalKindTone("run_failed"), "hot");
  assert.equal(journalKindTone("claim"), "info");
});

test("healthTone maps known states", () => {
  assert.equal(healthTone("ok"), "good");
  assert.equal(healthTone("degraded"), "warn");
  assert.equal(healthTone("down"), "hot");
  assert.equal(healthTone(undefined), "neutral");
});