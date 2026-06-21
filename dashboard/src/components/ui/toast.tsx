"use client";

import { useEffect, useRef, useState } from "react";
import { cx } from "../../lib/cx";
import { X } from "lucide-react";

export type ToastTone = "good" | "warn" | "hot" | "info" | "neutral";

export interface ToastItem {
  id: string;
  key: string;
  title: string;
  message?: string;
  tone: ToastTone;
  durationMs: number;
}

export interface ToastInput {
  key?: string;
  title: string;
  message?: string;
  tone?: ToastTone;
  durationMs?: number;
}

export interface ToastApi {
  push: (input: ToastInput) => string;
  dismiss: (id: string) => void;
  clear: () => void;
}

const DEFAULT_LIMIT = 5;
const DEFAULT_DURATION = 5_000;

export function upsertToast(current: ToastItem[], next: ToastItem, limit = DEFAULT_LIMIT): ToastItem[] {
  return [...current.filter((toast) => toast.key !== next.key), next].slice(-limit);
}

/**
 * Imperative toast controller. Use the returned `api` from useToasts() to push
 * notifications from anywhere. Replaces the legacy `useToasts` from
 * components/shared.tsx with the new design-system skin; callers can swap
 * without changing semantics.
 */
export function useToasts(): { toasts: ToastItem[]; api: ToastApi } {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());

  const dismiss = (id: string) => {
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
    setToasts((current) => current.filter((toast) => toast.id !== id));
  };

  useEffect(() => {
    return () => {
      for (const timer of timers.current.values()) clearTimeout(timer);
      timers.current.clear();
    };
  }, []);

  const push: ToastApi["push"] = (input) => {
    const createdAt = Date.now();
    const key = input.key ?? `${input.title}:${input.message ?? ""}`;
    const id = `${key}:${createdAt}`;
    const tone: ToastTone = input.tone ?? "neutral";
    const toast: ToastItem = {
      id,
      key,
      title: input.title,
      message: input.message,
      tone,
      durationMs: input.durationMs ?? DEFAULT_DURATION,
    };
    setToasts((current) => upsertToast(current, toast));
    for (const existing of toasts) {
      if (existing.key === key) dismiss(existing.id);
    }
    const timer = setTimeout(() => dismiss(id), toast.durationMs);
    timers.current.set(id, timer);
    return id;
  };

  const clear = () => {
    for (const timer of timers.current.values()) clearTimeout(timer);
    timers.current.clear();
    setToasts([]);
  };

  return {
    toasts,
    api: { push, dismiss, clear },
  };
}

export function ToastStack({
  toasts,
  onDismiss,
  className,
}: {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
  className?: string;
}) {
  return (
    <div className={cx("ax-toast-stack", className)} aria-live="polite" aria-atomic="true">
      {toasts.map((toast) => (
        <div key={toast.id} className="ax-toast" data-tone={toast.tone} role="status">
          <div>
            <div className="ax-toast__title">{toast.title}</div>
            {toast.message ? <div className="ax-toast__message">{toast.message}</div> : null}
          </div>
          <button
            type="button"
            className="ax-toast__dismiss"
            onClick={() => onDismiss(toast.id)}
            aria-label="Dismiss notification"
          >
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}