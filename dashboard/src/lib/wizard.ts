/**
 * Wizard navigation — the pure step logic behind the <Wizard> primitive.
 *
 * Kept separate from the component so the navigation rules (bounds, when you
 * may advance, when you may finish) are unit-testable without a DOM, matching
 * the rest of the dashboard's "logic in lib, thin JSX" convention.
 */

export interface WizardPosition {
  /** Zero-based index of the current step. */
  index: number;
  /** Total number of steps (must be >= 1). */
  total: number;
}

/** Clamp an index into the valid range for `total` steps. */
export function clampStepIndex(index: number, total: number): number {
  if (total <= 0) return 0;
  if (index < 0) return 0;
  if (index > total - 1) return total - 1;
  return index;
}

/** True when the current step is the last one. */
export function isLastStep(pos: WizardPosition): boolean {
  return pos.index >= pos.total - 1;
}

/** True when the current step is the first one. */
export function isFirstStep(pos: WizardPosition): boolean {
  return pos.index <= 0;
}

/**
 * Advance one step. `canAdvance` gates forward motion (e.g. step validation);
 * when false, or when already on the last step, the position is unchanged.
 */
export function nextStep(pos: WizardPosition, canAdvance = true): WizardPosition {
  if (!canAdvance || isLastStep(pos)) return pos;
  return { ...pos, index: clampStepIndex(pos.index + 1, pos.total) };
}

/** Go back one step. No-op on the first step. */
export function prevStep(pos: WizardPosition): WizardPosition {
  if (isFirstStep(pos)) return pos;
  return { ...pos, index: clampStepIndex(pos.index - 1, pos.total) };
}

/**
 * Whether the Finish action should be live: only on the last step, and only
 * when that step's validation passes.
 */
export function canFinish(pos: WizardPosition, lastStepValid = true): boolean {
  return isLastStep(pos) && lastStepValid;
}
