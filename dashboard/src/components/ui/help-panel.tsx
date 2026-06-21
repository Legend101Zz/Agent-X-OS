"use client";

/**
 * HelpPanel — a collapsible "How this page works" strip.
 *
 * Sits under a page title and orients a first-time operator. It defaults open
 * the first time and remembers your choice per-page in localStorage (logic in
 * lib/help-panel.ts). Quiet by design: a hairline card with a mono eyebrow,
 * never a loud callout.
 */

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ChevronDown, HelpCircle } from "lucide-react";

import { readHelpPanelOpen, writeHelpPanelOpen } from "../../lib/help-panel";
import { cx } from "../../lib/cx";

export interface HelpPanelProps {
  /** Stable id used for the localStorage open/closed memory (e.g. "blueprints"). */
  id: string;
  /** Heading; defaults to "How this page works". */
  title?: string;
  /** Explanatory body — plain sentences, optionally with <InfoTip>s inside. */
  children: ReactNode;
}

export function HelpPanel({ id, title = "How this page works", children }: HelpPanelProps) {
  // Start open for SSR/first paint, then reconcile with the saved choice.
  const [open, setOpen] = useState(true);

  useEffect(() => {
    const storage = typeof window === "undefined" ? undefined : window.localStorage;
    setOpen(readHelpPanelOpen(id, storage));
  }, [id]);

  const toggle = () => {
    setOpen((prev) => {
      const next = !prev;
      const storage = typeof window === "undefined" ? undefined : window.localStorage;
      writeHelpPanelOpen(id, next, storage);
      return next;
    });
  };

  return (
    <section className={cx("ax-help", open && "ax-help--open")}>
      <button
        type="button"
        className="ax-help__head"
        aria-expanded={open}
        onClick={toggle}
      >
        <HelpCircle size={14} aria-hidden className="ax-help__icon" />
        <span className="ax-help__title">{title}</span>
        <ChevronDown size={15} aria-hidden className="ax-help__chevron" />
      </button>
      {open ? <div className="ax-help__body">{children}</div> : null}
    </section>
  );
}
