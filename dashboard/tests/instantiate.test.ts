import assert from "node:assert/strict";
import test from "node:test";

import { buildInstantiatePayload, parseTargetOverride } from "../src/lib/instantiate";

const base = {
  typeRef: "lead-finder@0.3.1",
  businessName: "Kaveri Pumps",
  customerId: "cust_kaveri",
  senderIdentity: "outreach@kaveri-pumps.com",
  ring: "L1",
  icpJson: "",
};

test("parseTargetOverride: empty -> undefined, valid object -> parsed, invalid -> undefined", () => {
  assert.equal(parseTargetOverride(""), undefined);
  assert.equal(parseTargetOverride("   "), undefined);
  assert.deepEqual(parseTargetOverride('{"industry":"pumps"}'), { industry: "pumps" });
  assert.equal(parseTargetOverride("{not json"), undefined);
  assert.equal(parseTargetOverride("[1,2]"), undefined); // arrays are not a target object
});

test("buildInstantiatePayload assembles a trimmed, complete payload", () => {
  const { payload, errors, targetWarning } = buildInstantiatePayload({
    ...base,
    businessName: "  Kaveri Pumps  ",
    customerId: "  cust_kaveri  ",
    icpJson: '{"industry":"pumps","count":25}',
  });
  assert.deepEqual(errors, []);
  assert.equal(targetWarning, false);
  assert.deepEqual(payload, {
    type_ref: "lead-finder@0.3.1",
    customer_id: "cust_kaveri",
    business_name: "Kaveri Pumps",
    ring: "L1",
    target_override: { industry: "pumps", count: 25 },
    sender_identity: "outreach@kaveri-pumps.com",
    actor: "manager:dashboard",
  });
});

test("missing business name or customer id blocks with the drawer's exact message", () => {
  const r = buildInstantiatePayload({ ...base, businessName: "  ", customerId: "" });
  assert.equal(r.payload, null);
  assert.deepEqual(r.errors, ["Business name and customer id are required."]);
});

test("blank sender identity becomes undefined, not an empty string", () => {
  const { payload } = buildInstantiatePayload({ ...base, senderIdentity: "   " });
  assert.equal(payload?.sender_identity, undefined);
});

test("invalid ICP JSON warns but does not block; target_override omitted", () => {
  const { payload, errors, targetWarning } = buildInstantiatePayload({
    ...base,
    icpJson: "{broken",
  });
  assert.deepEqual(errors, []);
  assert.equal(targetWarning, true);
  assert.equal(payload?.target_override, undefined);
});

test("actor can be overridden", () => {
  const { payload } = buildInstantiatePayload({ ...base, actor: "manager:wizard" });
  assert.equal(payload?.actor, "manager:wizard");
});
