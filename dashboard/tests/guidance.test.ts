import assert from "node:assert/strict";
import test from "node:test";

import { GLOSSARY, getTerm, glossaryTermIds } from "../src/lib/glossary";
import {
  canFinish,
  clampStepIndex,
  isFirstStep,
  isLastStep,
  nextStep,
  prevStep,
} from "../src/lib/wizard";
import {
  helpPanelStorageKey,
  readHelpPanelOpen,
  writeHelpPanelOpen,
} from "../src/lib/help-panel";

// ---------- glossary ----------

test("getTerm resolves known terms and degrades to undefined for unknown ids", () => {
  const ring = getTerm("ring");
  assert.ok(ring);
  assert.equal(ring?.id, "ring");
  assert.match(ring?.label ?? "", /Ring/);
  assert.equal(getTerm("does-not-exist"), undefined);
});

test("every glossary term is internally consistent", () => {
  for (const id of glossaryTermIds()) {
    const term = GLOSSARY[id];
    assert.equal(term.id, id, `term ${id} has mismatched id field`);
    assert.ok(term.label.length > 0, `term ${id} missing label`);
    assert.ok(term.short.length > 0, `term ${id} missing short copy`);
    if (term.href !== undefined) {
      assert.ok(term.href.startsWith("/"), `term ${id} href must be an app path`);
    }
  }
});

test("the core-loop terms a user needs are all present", () => {
  for (const id of ["blueprint", "instance", "ring", "trust", "approval", "sender_identity"]) {
    assert.ok(getTerm(id), `missing core term ${id}`);
  }
});

// ---------- wizard navigation ----------

test("clampStepIndex keeps the index within bounds", () => {
  assert.equal(clampStepIndex(-2, 4), 0);
  assert.equal(clampStepIndex(2, 4), 2);
  assert.equal(clampStepIndex(9, 4), 3);
  assert.equal(clampStepIndex(0, 0), 0);
});

test("first/last step predicates", () => {
  assert.ok(isFirstStep({ index: 0, total: 4 }));
  assert.ok(!isFirstStep({ index: 1, total: 4 }));
  assert.ok(isLastStep({ index: 3, total: 4 }));
  assert.ok(!isLastStep({ index: 2, total: 4 }));
});

test("nextStep advances only when allowed and never past the end", () => {
  const start = { index: 0, total: 3 };
  assert.deepEqual(nextStep(start), { index: 1, total: 3 });
  // blocked by validation
  assert.deepEqual(nextStep(start, false), start);
  // cannot advance past the last step
  assert.deepEqual(nextStep({ index: 2, total: 3 }), { index: 2, total: 3 });
});

test("prevStep retreats but not before the first step", () => {
  assert.deepEqual(prevStep({ index: 2, total: 3 }), { index: 1, total: 3 });
  assert.deepEqual(prevStep({ index: 0, total: 3 }), { index: 0, total: 3 });
});

test("canFinish is true only on a valid last step", () => {
  assert.ok(canFinish({ index: 2, total: 3 }, true));
  assert.ok(!canFinish({ index: 2, total: 3 }, false));
  assert.ok(!canFinish({ index: 1, total: 3 }, true));
});

// ---------- help-panel persistence ----------

function memoryStorage(): Storage {
  const map = new Map<string, string>();
  return {
    getItem: (k) => (map.has(k) ? (map.get(k) as string) : null),
    setItem: (k, v) => void map.set(k, String(v)),
    removeItem: (k) => void map.delete(k),
    clear: () => map.clear(),
    key: (i) => Array.from(map.keys())[i] ?? null,
    get length() {
      return map.size;
    },
  } as Storage;
}

test("helpPanelStorageKey namespaces by id", () => {
  assert.equal(helpPanelStorageKey("blueprints"), "agentx.help.blueprints");
});

test("readHelpPanelOpen defaults to open, then honours the saved choice", () => {
  const store = memoryStorage();
  // first visit -> default open
  assert.equal(readHelpPanelOpen("blueprints", store), true);
  writeHelpPanelOpen("blueprints", false, store);
  assert.equal(readHelpPanelOpen("blueprints", store), false);
  writeHelpPanelOpen("blueprints", true, store);
  assert.equal(readHelpPanelOpen("blueprints", store), true);
});

test("help-panel helpers degrade safely without storage", () => {
  assert.equal(readHelpPanelOpen("x", undefined), true);
  assert.equal(readHelpPanelOpen("x", undefined, false), false);
  assert.doesNotThrow(() => writeHelpPanelOpen("x", true, undefined));
});
