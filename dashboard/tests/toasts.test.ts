import assert from "node:assert/strict";
import test from "node:test";

import { upsertToast, type ToastItem } from "../src/components/shared";

const first: ToastItem = {
  id: "approve:1",
  key: "approve",
  title: "Approve",
  message: "queued",
  tone: "good",
  createdAt: 1,
  durationMs: 5000,
};

test("upsertToast replaces an existing toast with the same dedupe key", () => {
  const replacement: ToastItem = {
    ...first,
    id: "approve:2",
    message: "settled",
    createdAt: 2,
  };

  assert.deepEqual(upsertToast([first], replacement), [replacement]);
});

test("upsertToast keeps the newest bounded toast history", () => {
  const existing = Array.from({ length: 5 }, (_, index): ToastItem => ({
    ...first,
    id: `command:${index}`,
    key: `command:${index}`,
    createdAt: index,
  }));
  const newest: ToastItem = {
    ...first,
    id: "command:5",
    key: "command:5",
    createdAt: 5,
  };

  assert.deepEqual(
    upsertToast(existing, newest).map((toast) => toast.id),
    ["command:1", "command:2", "command:3", "command:4", "command:5"],
  );
});
