"use client";

/**
 * AsyncButton — the dashboard's primary action primitive.
 *
 * Solves the existing pain point ("hit a button, nothing happens"). It:
 *   • Spins while pending.
 *   • Disables itself AND children while pending (no double-clicks).
 *   • Fires a toast on success / failure (handled by the parent — AsyncButton
 *     only owns pending/error state; the caller wraps with toast logic).
 *   • Surfaces a "coming soon" tooltip when disabled by graceful-disable.
 *
 * Variants: primary | secondary | ghost | danger | success
 * Sizes:    sm | md | lg
 * Tone via  tone prop, plus `icon`, `trailingIcon`, `loadingText`, `disabledReason`.
 */
import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cx } from "../../lib/cx";

export type AsyncButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "success";
export type AsyncButtonSize = "sm" | "md" | "lg";

export interface AsyncButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type"> {
  variant?: AsyncButtonVariant;
  size?: AsyncButtonSize;
  loading?: boolean;
  loadingText?: ReactNode;
  icon?: ReactNode;
  trailingIcon?: ReactNode;
  disabledReason?: string;
  type?: "button" | "submit" | "reset";
  block?: boolean;
}

export function AsyncButton({
  variant = "primary",
  size = "md",
  loading = false,
  loadingText,
  icon,
  trailingIcon,
  disabledReason,
  className,
  children,
  disabled,
  block,
  type = "button",
  ...rest
}: AsyncButtonProps) {
  const isDisabled = loading || disabled;
  const effectiveReason = loading
    ? "Working…"
    : disabledReason
      ? disabledReason
      : undefined;

  return (
    <button
      {...rest}
      type={type}
      data-variant={variant}
      data-size={size}
      data-loading={loading ? "true" : undefined}
      aria-busy={loading || undefined}
      title={effectiveReason}
      disabled={isDisabled}
      className={cx(
        "ax-btn",
        `ax-btn--${variant}`,
        `ax-btn--${size}`,
        block && "ax-btn--block",
        className,
      )}
    >
      {loading ? (
        <>
          <Loader2 className="ax-btn__spinner" aria-hidden size={14} />
          <span>{loadingText ?? "Working…"}</span>
        </>
      ) : (
        <>
          {icon ? <span className="ax-btn__icon">{icon}</span> : null}
          <span>{children}</span>
          {trailingIcon ? <span className="ax-btn__icon">{trailingIcon}</span> : null}
        </>
      )}
    </button>
  );
}

/**
 * Plain button — for non-async affordances (nav, toggle). Same design tokens.
 */
export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type"> {
  variant?: AsyncButtonVariant;
  size?: AsyncButtonSize;
  icon?: ReactNode;
  trailingIcon?: ReactNode;
  type?: "button" | "submit" | "reset";
  block?: boolean;
  /** Optional loading spinner — same as AsyncButton when true. */
  loading?: boolean;
}

export function Button({
  variant = "secondary",
  size = "md",
  icon,
  trailingIcon,
  className,
  children,
  block,
  loading = false,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      data-variant={variant}
      data-size={size}
      data-loading={loading ? "true" : undefined}
      disabled={rest.disabled || loading}
      className={cx("ax-btn", `ax-btn--${variant}`, `ax-btn--${size}`, block && "ax-btn--block", className)}
    >
      {loading ? <Loader2 className="ax-btn__spinner" aria-hidden size={14} /> : null}
      {icon && !loading ? <span className="ax-btn__icon">{icon}</span> : null}
      <span>{children}</span>
      {trailingIcon ? <span className="ax-btn__icon">{trailingIcon}</span> : null}
    </button>
  );
}