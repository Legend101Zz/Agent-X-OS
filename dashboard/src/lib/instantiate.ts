/**
 * Instantiate form logic — the single, shared way to turn create-a-mandate form
 * state into an InstantiatePayload.
 *
 * Both the existing InstantiateDrawer and the guided CreateMandateWizard build
 * their payload here, so there is exactly one place that decides required fields,
 * trims input, and parses the ICP target JSON. The network call itself remains
 * `instantiate()` in lib/api. Pure and unit-tested (no DOM).
 */

import type { InstantiatePayload } from "./types";

export interface InstantiateFormState {
  /** Fully-qualified type_ref of the blueprint being instantiated. */
  typeRef: string;
  businessName: string;
  customerId: string;
  senderIdentity: string;
  ring: string;
  /** Raw JSON text for target_override; empty means "no override". */
  icpJson: string;
  /** Defaults to "manager:dashboard" (matches the drawer). */
  actor?: string;
}

export interface BuiltInstantiate {
  /** Ready-to-send payload, or null when there are blocking errors. */
  payload: InstantiatePayload | null;
  /** Blocking validation errors (empty means good to submit). */
  errors: string[];
  /** True when ICP text was provided but isn't valid JSON (non-blocking; omitted). */
  targetWarning: boolean;
}

/** Parse the ICP target JSON. Returns undefined for empty/invalid/non-object input. */
export function parseTargetOverride(icpJson: string): Record<string, unknown> | undefined {
  if (!icpJson.trim()) return undefined;
  try {
    const parsed: unknown = JSON.parse(icpJson);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : undefined;
  } catch {
    return undefined;
  }
}

/**
 * Assemble + validate the instantiate payload from form state. Error wording
 * matches the drawer's existing behaviour exactly so nothing user-visible
 * changes when the drawer adopts this helper.
 */
export function buildInstantiatePayload(form: InstantiateFormState): BuiltInstantiate {
  const errors: string[] = [];
  const businessName = form.businessName.trim();
  const customerId = form.customerId.trim();

  if (!businessName || !customerId) {
    errors.push("Business name and customer id are required.");
  }

  const target = parseTargetOverride(form.icpJson);
  const targetWarning = Boolean(form.icpJson.trim()) && target === undefined;

  if (errors.length > 0) {
    return { payload: null, errors, targetWarning };
  }

  const payload: InstantiatePayload = {
    type_ref: form.typeRef,
    customer_id: customerId,
    business_name: businessName,
    ring: form.ring,
    target_override: target,
    sender_identity: form.senderIdentity.trim() || undefined,
    actor: form.actor ?? "manager:dashboard",
  };
  return { payload, errors: [], targetWarning };
}
