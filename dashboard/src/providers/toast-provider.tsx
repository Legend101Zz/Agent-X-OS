"use client";

/**
 * ToastProvider — exposes the `useToasts()` API + renders the stack globally.
 * Mount once in the root layout.
 */
import { createContext, useContext, useMemo } from "react";
import type { ReactNode } from "react";
import { ToastStack, useToasts } from "../components/ui/toast";
import type { ToastApi } from "../components/ui/toast";

interface ToastContextValue {
  api: ToastApi;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const { toasts, api } = useToasts();
  const value = useMemo<ToastContextValue>(() => ({ api }), [api]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastStack toasts={toasts} onDismiss={api.dismiss} />
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const value = useContext(ToastContext);
  if (!value) {
    // Provide a no-op API so client components rendered without the provider
    // (e.g. isolated tests) don't throw.
    return {
      push: () => "",
      dismiss: () => {},
      clear: () => {},
    };
  }
  return value.api;
}