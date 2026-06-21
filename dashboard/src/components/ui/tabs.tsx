"use client";

/**
 * Tabs — controlled tab strip + panels. Pure controlled component (parent owns
 * the active key). Used by Inspector (C2), Kernel (C14), etc.
 */
import type { ReactNode } from "react";
import { useId } from "react";
import { cx } from "../../lib/cx";

export interface TabItem {
  key: string;
  label: ReactNode;
  /** Optional badge content shown after the label (e.g. counts). */
  badge?: ReactNode;
  /** Disable the tab (rendered but unclickable; useful during feature wiring). */
  disabled?: boolean;
  /** Reason for the disable — surfaced as a tooltip. */
  disabledReason?: string;
}

export interface TabsProps {
  items: TabItem[];
  active: string;
  onChange: (key: string) => void;
  density?: "comfortable" | "compact";
  className?: string;
}

export function Tabs({ items, active, onChange, density = "comfortable", className }: TabsProps) {
  const id = useId();
  return (
    <div className={cx("ax-tabs", className)} data-density={density} role="tablist">
      {items.map((item) => {
        const isActive = item.key === active;
        return (
          <button
            key={item.key}
            role="tab"
            type="button"
            aria-selected={isActive}
            aria-controls={`${id}-panel-${item.key}`}
            disabled={item.disabled}
            title={item.disabled ? item.disabledReason ?? undefined : undefined}
            onClick={() => !item.disabled && onChange(item.key)}
            className={cx(
              "ax-tab",
              isActive && "ax-tab--active",
              item.disabled && "ax-tab--disabled",
            )}
          >
            <span>{item.label}</span>
            {item.badge !== undefined ? <span className="ax-tab__badge">{item.badge}</span> : null}
          </button>
        );
      })}
    </div>
  );
}

export interface TabPanelProps {
  activeKey: string;
  tabKey: string;
  children: ReactNode;
  className?: string;
}

export function TabPanel({ activeKey, tabKey, children, className }: TabPanelProps) {
  if (activeKey !== tabKey) return null;
  return <div className={cx("ax-tab-panel", className)}>{children}</div>;
}