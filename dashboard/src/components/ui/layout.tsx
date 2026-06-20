"use client";

/**
 * Layout primitives — Stack, Row, Cluster, Spacer. The composable building
 * blocks of every view. All use `display: flex` with sensible defaults; pass
 * standard flex props via gap / align / justify / wrap.
 */
import type { CSSProperties, HTMLAttributes, ReactNode } from "react";
import { cx } from "../../lib/cx";

type DivProps = HTMLAttributes<HTMLDivElement>;

export type Gap = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12;
export type Align = "start" | "center" | "end" | "stretch" | "baseline";
export type Justify = "start" | "center" | "end" | "between" | "around" | "evenly";

const gapVar: Record<Gap, string> = {
  0: "var(--space-0)",
  1: "var(--space-1)",
  2: "var(--space-2)",
  3: "var(--space-3)",
  4: "var(--space-4)",
  5: "var(--space-5)",
  6: "var(--space-6)",
  8: "var(--space-8)",
  10: "var(--space-10)",
  12: "var(--space-12)",
};

const alignMap: Record<Align, string> = {
  start: "flex-start",
  center: "center",
  end: "flex-end",
  stretch: "stretch",
  baseline: "baseline",
};

const justifyMap: Record<Justify, string> = {
  start: "flex-start",
  center: "center",
  end: "flex-end",
  between: "space-between",
  around: "space-around",
  evenly: "space-evenly",
};

export interface StackProps extends DivProps {
  gap?: Gap;
  align?: Align;
  justify?: Justify;
  wrap?: boolean;
  inline?: boolean;
}

export function Stack({
  gap = 3,
  align,
  justify,
  wrap,
  inline,
  className,
  style,
  ...rest
}: StackProps) {
  const composed: CSSProperties = {
    display: inline ? "inline-flex" : "flex",
    flexDirection: "column",
    gap: gapVar[gap],
    ...(align ? { alignItems: alignMap[align] } : {}),
    ...(justify ? { justifyContent: justifyMap[justify] } : {}),
    ...(wrap ? { flexWrap: "wrap" } : {}),
    ...style,
  };
  return <div {...rest} className={cx("ax-stack", className)} style={composed} />;
}

export interface RowProps extends DivProps {
  gap?: Gap;
  align?: Align;
  justify?: Justify;
  wrap?: boolean;
  inline?: boolean;
}

export function Row({
  gap = 3,
  align = "center",
  justify,
  wrap,
  inline,
  className,
  style,
  ...rest
}: RowProps) {
  const composed: CSSProperties = {
    display: inline ? "inline-flex" : "flex",
    flexDirection: "row",
    gap: gapVar[gap],
    alignItems: alignMap[align],
    ...(justify ? { justifyContent: justifyMap[justify] } : {}),
    ...(wrap ? { flexWrap: "wrap" } : {}),
    ...style,
  };
  return <div {...rest} className={cx("ax-row", className)} style={composed} />;
}

export interface ClusterProps extends DivProps {
  gap?: Gap;
  align?: Align;
}

export function Cluster({ gap = 2, align = "center", className, style, ...rest }: ClusterProps) {
  const composed: CSSProperties = {
    display: "flex",
    flexDirection: "row",
    flexWrap: "wrap",
    gap: gapVar[gap],
    alignItems: alignMap[align],
    ...style,
  };
  return <div {...rest} className={cx("ax-cluster", className)} style={composed} />;
}

export function Spacer() {
  return <div style={{ flex: 1 }} aria-hidden />;
}

export function Divider({ vertical, className }: { vertical?: boolean; className?: string }) {
  return (
    <div
      aria-hidden
      className={cx(vertical ? "ax-divider ax-divider--v" : "ax-divider", className)}
    />
  );
}

export interface SectionProps extends Omit<DivProps, "title"> {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  eyebrow?: ReactNode;
  density?: "comfortable" | "compact";
}

export function Section({
  title,
  subtitle,
  action,
  eyebrow,
  density = "comfortable",
  className,
  children,
  ...rest
}: SectionProps) {
  return (
    <section {...rest} data-density={density} className={cx("ax-section", className)}>
      {(title || subtitle || action || eyebrow) && (
        <header className="ax-section__header">
          <div className="ax-section__titles">
            {eyebrow ? <div className="ax-section__eyebrow">{eyebrow}</div> : null}
            {title ? <h2 className="ax-section__title">{title}</h2> : null}
            {subtitle ? <div className="ax-section__subtitle">{subtitle}</div> : null}
          </div>
          {action ? <div className="ax-section__action">{action}</div> : null}
        </header>
      )}
      <div className="ax-section__body">{children}</div>
    </section>
  );
}