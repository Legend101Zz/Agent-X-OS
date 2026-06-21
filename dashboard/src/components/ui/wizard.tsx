"use client";

/**
 * Wizard — a generic multi-step stepper rendered inside the existing Modal.
 *
 * Drives the "Create a Mandate" guided flow, but knows nothing about mandates:
 * it takes a list of steps (each with its own render + optional validate) and
 * handles bounds, the Back/Next/Finish controls, and validation gating. The
 * navigation rules live in lib/wizard.ts so they're unit-tested without a DOM.
 *
 * Finish is an AsyncButton: the caller's onFinish does the real work (e.g. the
 * instantiate call) and may be async; the wizard shows the pending state.
 */

import { useState } from "react";
import type { ReactNode } from "react";

import { Modal } from "./drawer";
import { AsyncButton } from "./button";
import {
  canFinish as canFinishAt,
  isFirstStep,
  isLastStep,
  nextStep,
  prevStep,
} from "../../lib/wizard";
import { cx } from "../../lib/cx";

export interface WizardStep {
  id: string;
  title: string;
  /** Step body. */
  render: ReactNode;
  /** Optional gate: return false to block Next/Finish on this step. */
  valid?: boolean;
}

export interface WizardProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  steps: WizardStep[];
  /** Runs on Finish; may be async. Throw to keep the wizard open on error. */
  onFinish: () => void | Promise<void>;
  finishLabel?: string;
  width?: number;
}

export function Wizard({
  open,
  onClose,
  title,
  steps,
  onFinish,
  finishLabel = "Launch",
  width = 640,
}: WizardProps) {
  const total = steps.length;
  const [index, setIndex] = useState(0);
  const [finishing, setFinishing] = useState(false);

  const pos = { index: Math.min(index, Math.max(total - 1, 0)), total };
  const step = steps[pos.index];
  const stepValid = step?.valid ?? true;

  const handleFinish = async () => {
    setFinishing(true);
    try {
      await onFinish();
    } finally {
      setFinishing(false);
    }
  };

  if (!step) return null;

  return (
    <Modal open={open} onClose={onClose} title={title} width={width}>
      <div className="ax-wizard">
        <ol className="ax-wizard__steps" aria-label="Progress">
          {steps.map((s, i) => (
            <li
              key={s.id}
              className={cx(
                "ax-wizard__step",
                i === pos.index && "ax-wizard__step--current",
                i < pos.index && "ax-wizard__step--done",
              )}
              aria-current={i === pos.index ? "step" : undefined}
            >
              <span className="ax-wizard__dot" aria-hidden />
              <span className="ax-wizard__steplabel">{s.title}</span>
            </li>
          ))}
        </ol>

        <div className="ax-wizard__panel">
          <div className="ax-wizard__eyebrow">
            Step {pos.index + 1} of {total}
          </div>
          <h3 className="ax-wizard__title">{step.title}</h3>
          <div className="ax-wizard__body">{step.render}</div>
        </div>

        <div className="ax-wizard__footer">
          <AsyncButton
            variant="ghost"
            onClick={() => setIndex(prevStep(pos).index)}
            disabled={isFirstStep(pos) || finishing}
          >
            ← Back
          </AsyncButton>
          {isLastStep(pos) ? (
            <AsyncButton
              variant="primary"
              loading={finishing}
              loadingText="Launching…"
              disabled={!canFinishAt(pos, stepValid)}
              disabledReason={!stepValid ? "Complete this step first" : undefined}
              onClick={() => void handleFinish()}
            >
              {finishLabel}
            </AsyncButton>
          ) : (
            <AsyncButton
              variant="primary"
              disabled={!stepValid}
              disabledReason={!stepValid ? "Complete this step first" : undefined}
              onClick={() => setIndex(nextStep(pos, stepValid).index)}
            >
              Next →
            </AsyncButton>
          )}
        </div>
      </div>
    </Modal>
  );
}
