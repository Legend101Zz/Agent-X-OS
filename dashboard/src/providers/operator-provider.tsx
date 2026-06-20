"use client";

/**
 * Operator settings — base URL + bearer token + actor. Stored in localStorage
 * so the page survives reloads and the operator doesn't re-enter them. Read
 * from `useOperator()` anywhere.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

const STORAGE_KEY = "agentx.operator.v1";

export interface OperatorSettings {
  baseUrl: string;
  token: string;
  actor: string;
}

const DEFAULTS: OperatorSettings = {
  baseUrl: "",
  token: "",
  actor: "operator",
};

export interface OperatorContextValue extends OperatorSettings {
  setSettings: (next: Partial<OperatorSettings>) => void;
  /** True when the operator has both a base URL and a token. */
  isLive: boolean;
  /** True when the operator has explicitly enabled live (non-fixture) writes. */
  writesEnabled: boolean;
}

const OperatorContext = createContext<OperatorContextValue | null>(null);

export function OperatorProvider({ children }: { children: ReactNode }) {
  const [settings, setSettingsState] = useState<OperatorSettings>(DEFAULTS);

  // Hydrate from localStorage after mount (so SSR doesn't get a stale value).
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as Partial<OperatorSettings>;
      setSettingsState((current) => ({ ...current, ...parsed }));
    } catch {
      // ignore
    }
  }, []);

  const setSettings = useCallback((next: Partial<OperatorSettings>) => {
    setSettingsState((current) => {
      const merged = { ...current, ...next };
      if (typeof window !== "undefined") {
        try {
          window.localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
        } catch {
          // localStorage unavailable; in-memory only
        }
      }
      return merged;
    });
  }, []);

  const value = useMemo<OperatorContextValue>(() => {
    const isLive = Boolean(settings.baseUrl && settings.token);
    return {
      ...settings,
      setSettings,
      isLive,
      writesEnabled: isLive,
    };
  }, [settings, setSettings]);

  return <OperatorContext.Provider value={value}>{children}</OperatorContext.Provider>;
}

export function useOperator(): OperatorContextValue {
  const value = useContext(OperatorContext);
  if (!value) {
    // Safe fallback so server components / tests can import without a provider.
    return {
      ...DEFAULTS,
      setSettings: () => {},
      isLive: false,
      writesEnabled: false,
    };
  }
  return value;
}