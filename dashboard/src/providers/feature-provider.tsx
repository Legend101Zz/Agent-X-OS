"use client";

/**
 * Feature flags — drives graceful disable. Reads a `FeatureFlags` payload from
 * `/system/info` (or a static fallback for now) and exposes a context. Any
 * control whose feature is "wip" or "stub" renders disabled with a tooltip.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { FeatureFlags } from "../lib/types";
import { useToast } from "./toast-provider";
import { useOperator } from "./operator-provider";

const DEFAULTS: FeatureFlags = {
  heap_read: "wip",
  eval_case_detail: "wip",
  capability_health: "wip",
  scheduler_work_list: "wip",
  economy_pnl: "wip",
};

interface FeatureContextValue {
  flags: FeatureFlags;
  isLive: (key: keyof FeatureFlags) => boolean;
  status: (key: keyof FeatureFlags) => FeatureFlags[keyof FeatureFlags];
}

const FeatureContext = createContext<FeatureContextValue | null>(null);

export function FeatureProvider({ children }: { children: ReactNode }) {
  const { baseUrl, token } = useOperator();
  const [flags, setFlags] = useState<FeatureFlags>(DEFAULTS);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!baseUrl) return;
      try {
        const headers: Record<string, string> = { Accept: "application/json" };
        if (token) headers.Authorization = `Bearer ${token}`;
        const response = await fetch(new URL("/system/info", baseUrl), { headers, cache: "no-store" });
        if (!response.ok) return;
        const body = (await response.json()) as { feature_flags?: Partial<FeatureFlags> };
        if (cancelled || !body.feature_flags) return;
        setFlags((current) => ({ ...current, ...body.feature_flags }));
      } catch {
        // Stay on defaults; graceful disable is still correct.
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [baseUrl, token]);

  const value = useMemo<FeatureContextValue>(
    () => ({
      flags,
      isLive: (key) => flags[key] === "live",
      status: (key) => flags[key],
    }),
    [flags],
  );

  return <FeatureContext.Provider value={value}>{children}</FeatureContext.Provider>;
}

export function useFeatures(): FeatureContextValue {
  const value = useContext(FeatureContext);
  if (!value) {
    return {
      flags: DEFAULTS,
      isLive: () => false,
      status: () => "stub",
    };
  }
  return value;
}

export function useFeature(key: keyof FeatureFlags) {
  const features = useFeatures();
  const status = features.status(key);
  const live = status === "live";
  const reason = live
    ? undefined
    : status === "wip"
      ? "Coming soon — backend wiring in progress."
      : "Not yet wired.";
  return { live, status, reason };
}

/** Run an async command with toast feedback on success/failure. */
export function useCommandRunner() {
  const toast = useToast();
  return useCallback(
    async <T,>(
      op: () => Promise<{ ok: boolean; data?: T; message?: string; title: string }>,
    ) => {
      try {
        const result = await op();
        if (result.ok) {
          toast.push({ title: result.title, message: result.message, tone: "good" });
          return result.data;
        }
        toast.push({ title: result.title, message: result.message, tone: "hot" });
        return undefined;
      } catch (error) {
        toast.push({
          title: resultTitleOf(op) ?? "Command failed",
          message: error instanceof Error ? error.message : String(error),
          tone: "hot",
        });
        return undefined;
      }
    },
    [toast],
  );
}

function resultTitleOf(_op: unknown): string | undefined {
  // The op is opaque; the title is on its returned object. This helper exists
  // only to keep the typed signature clean.
  return undefined;
}