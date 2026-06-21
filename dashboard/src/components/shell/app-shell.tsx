"use client";

/**
 * AppShell — wraps every page. Provides left rail + topbar + content slot.
 * Mounts the providers internally so each page is a thin shell of content.
 */
import type { ReactNode } from "react";
import { LeftRail } from "./left-rail";
import { TopBar } from "./top-bar";
import { OperatorProvider } from "../../providers/operator-provider";
import { ToastProvider } from "../../providers/toast-provider";
import { FeatureProvider } from "../../providers/feature-provider";

export interface AppShellProps {
  title: string;
  crumbs?: Array<{ href?: string; label: string }>;
  children: ReactNode;
  onRefresh?: () => void;
  refreshing?: boolean;
}

export function AppShell({ title, crumbs, children, onRefresh, refreshing }: AppShellProps) {
  return (
    <OperatorProvider>
      <ToastProvider>
        <FeatureProvider>
          <div className="app-root">
            <LeftRail />
            <TopBar title={title} crumbs={crumbs} onRefresh={onRefresh} refreshing={refreshing} />
            <main className="app-content">{children}</main>
          </div>
        </FeatureProvider>
      </ToastProvider>
    </OperatorProvider>
  );
}