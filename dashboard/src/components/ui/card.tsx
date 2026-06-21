"use client";

/**
 * Card — surface primitive. Every entity tile in the dashboard extends this.
 *
 *   <Card tone="default" padding="md" interactive>
 *     <CardHeader title="..." subtitle="..." action={<AsyncButton/>} />
 *     <CardBody>...</CardBody>
 *     <CardFooter>...</CardFooter>
 *   </Card>
 */
import type { HTMLAttributes, ReactNode } from "react";
import { cx } from "../../lib/cx";

export type CardTone =
  | "default"
  | "raised"
  | "muted"
  | "accent"
  | "danger"
  | "success"
  | "warn"
  | "good"
  | "hot";
export type CardPadding = "none" | "sm" | "md" | "lg";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  tone?: CardTone;
  padding?: CardPadding;
  interactive?: boolean;
  block?: boolean;
}

export function Card({
  tone = "default",
  padding = "md",
  interactive,
  block,
  className,
  children,
  ...rest
}: CardProps) {
  return (
    <div
      {...rest}
      data-tone={tone}
      data-padding={padding}
      className={cx(
        "ax-card",
        `ax-card--${tone}`,
        `ax-card--p-${padding}`,
        interactive && "ax-card--interactive",
        block && "ax-card--block",
        className,
      )}
    >
      {children}
    </div>
  );
}

export interface CardHeaderProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  eyebrow?: ReactNode;
}

export function CardHeader({ title, subtitle, action, eyebrow, className, ...rest }: CardHeaderProps) {
  return (
    <div {...rest} className={cx("ax-card__header", className)}>
      <div className="ax-card__title-block">
        {eyebrow ? <div className="ax-card__eyebrow">{eyebrow}</div> : null}
        <div className="ax-card__title">{title}</div>
        {subtitle ? <div className="ax-card__subtitle">{subtitle}</div> : null}
      </div>
      {action ? <div className="ax-card__action">{action}</div> : null}
    </div>
  );
}

export function CardBody({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div {...rest} className={cx("ax-card__body", className)} />;
}

export function CardFooter({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div {...rest} className={cx("ax-card__footer", className)} />;
}

/** A card-shaped stat tile for the Mission Control home. */
export interface StatTileProps {
  label: string;
  value: ReactNode;
  delta?: ReactNode;
  tone?: "default" | "good" | "warn" | "hot";
  hint?: ReactNode;
  icon?: ReactNode;
  to?: string;
}
export function StatTile({ label, value, delta, tone = "default", hint, icon, to }: StatTileProps) {
  const cardTone: CardTone =
    tone === "good" ? "success" : tone === "hot" ? "danger" : tone === "warn" ? "warn" : "default";
  const inner = (
    <Card tone={cardTone} padding="md" interactive={Boolean(to)} block>
      <div className="ax-stat">
        <div className="ax-stat__row">
          <div className="ax-stat__label">{label}</div>
          {icon ? <div className="ax-stat__icon">{icon}</div> : null}
        </div>
        <div className="ax-stat__value">{value}</div>
        {delta ? <div className="ax-stat__delta">{delta}</div> : null}
        {hint ? <div className="ax-stat__hint">{hint}</div> : null}
      </div>
    </Card>
  );
  if (to) {
    return (
      <a href={to} className="ax-stat-link">
        {inner}
      </a>
    );
  }
  return inner;
}