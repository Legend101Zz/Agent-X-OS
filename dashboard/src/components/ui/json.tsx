"use client";

import { useState } from "react";
import { cx } from "../../lib/cx";

export interface JsonViewerProps {
  /** The value to render — anything JSON-serialisable. */
  value: unknown;
  /** Initial depth shown when collapsed. */
  collapseDepth?: number;
  className?: string;
  /** Title above the JSON. */
  title?: string;
  /** Cap to this many bytes (renders a truncated notice if exceeded). */
  maxBytes?: number;
}

/** A collapsible JSON viewer with monospaced styling. */
export function JsonViewer({
  value,
  collapseDepth = 1,
  className,
  title,
  maxBytes = 256_000,
}: JsonViewerProps) {
  const [collapsed, setCollapsed] = useState(true);
  const serialised = safeStringify(value, 2);
  const truncated = serialised.length > maxBytes;
  const shown = truncated ? `${serialised.slice(0, maxBytes)}\n…(truncated)` : serialised;
  return (
    <div className={cx("ax-json-wrap", className)}>
      {title ? <div className="ax-json__title mono">{title}</div> : null}
      <button
        type="button"
        className="ax-json__toggle"
        onClick={() => setCollapsed((c) => !c)}
        title={collapsed ? `Expand (depth ${collapseDepth} shown)` : "Collapse"}
      >
        {collapsed ? "▸" : "▾"}
      </button>
      <pre className="ax-json">{collapsed ? firstLines(shown, collapseDepth * 12) : shown}</pre>
      {truncated ? (
        <div className="ax-json__hint dim">
          Truncated at {Math.round(maxBytes / 1024)}KB. Click to expand.
        </div>
      ) : null}
    </div>
  );
}

function safeStringify(value: unknown, indent = 2): string {
  try {
    return JSON.stringify(value, null, indent);
  } catch {
    return String(value);
  }
}

function firstLines(text: string, maxLines: number): string {
  const lines = text.split("\n");
  if (lines.length <= maxLines) return text;
  return `${lines.slice(0, maxLines).join("\n")}\n…(${lines.length - maxLines} more lines)`;
}

export function CodeBlock({
  children,
  language,
  className,
}: {
  children: string;
  language?: string;
  className?: string;
}) {
  return (
    <pre className={cx("ax-code", className)}>
      {language ? <code data-lang={language}>{children}</code> : <code>{children}</code>}
    </pre>
  );
}