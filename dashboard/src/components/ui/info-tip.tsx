"use client";

/**
 * InfoTip — the ⓘ affordance that explains a term or field inline.
 *
 * Two ways to use it:
 *   <InfoTip term="ring" />                     // pulls copy from the glossary
 *   <InfoTip label="Pass rate" content="…" />   // ad-hoc copy
 *
 * Signature treatment: the popover reads like a terminal annotation — a mono
 * eyebrow (the term id, comment-style) over plain-language copy, with a hairline
 * accent rail. Calm, analytical, native to the deep-teal/cream theme.
 *
 * Accessible: a real button, reachable by keyboard, opens on hover OR focus,
 * closes on blur/Escape, and links the popover via aria-describedby.
 */

import { useId, useState } from "react";
import type { ReactNode } from "react";
import { Info } from "lucide-react";

import { getTerm } from "../../lib/glossary";
import { cx } from "../../lib/cx";

export interface InfoTipProps {
  /** Glossary term id. When set, label/content/href default from the glossary. */
  term?: string;
  /** Heading shown in the popover. Falls back to the glossary label. */
  label?: ReactNode;
  /** Body copy. Falls back to the glossary short definition. */
  content?: ReactNode;
  /** Optional deep-dive link. Falls back to the glossary href. */
  href?: string;
  /** Comment-style eyebrow; defaults to the term id. */
  eyebrow?: string;
  className?: string;
}

export function InfoTip({ term, label, content, href, eyebrow, className }: InfoTipProps) {
  const [open, setOpen] = useState(false);
  const popoverId = useId();

  const entry = term ? getTerm(term) : undefined;
  const resolvedLabel = label ?? entry?.label ?? "Info";
  const resolvedContent = content ?? entry?.short;
  const resolvedHref = href ?? entry?.href;
  const resolvedEyebrow = eyebrow ?? entry?.id ?? term;

  // Nothing to say -> render nothing rather than an empty bubble.
  if (!resolvedContent) return null;

  return (
    <span
      className={cx("ax-infotip", className)}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className="ax-infotip__trigger"
        aria-label={typeof resolvedLabel === "string" ? `About ${resolvedLabel}` : "More information"}
        aria-expanded={open}
        aria-describedby={open ? popoverId : undefined}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={(e) => {
          e.preventDefault();
          setOpen((v) => !v);
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
        }}
      >
        <Info size={13} aria-hidden />
      </button>
      {open ? (
        <span id={popoverId} role="tooltip" className="ax-infotip__pop">
          {resolvedEyebrow ? <span className="ax-infotip__eyebrow">// {resolvedEyebrow}</span> : null}
          <span className="ax-infotip__title">{resolvedLabel}</span>
          <span className="ax-infotip__body">{resolvedContent}</span>
          {resolvedHref ? (
            <a className="ax-infotip__link" href={resolvedHref}>
              Learn more →
            </a>
          ) : null}
        </span>
      ) : null}
    </span>
  );
}
