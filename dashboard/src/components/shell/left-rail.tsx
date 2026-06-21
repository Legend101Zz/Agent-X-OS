"use client";

/**
 * LeftRail — the primary entity navigation. Active route highlighted via
 * Next.js's `usePathname()`. "System" group collapses/expands inline.
 */
import { usePathname } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import type { ReactNode } from "react";
import {
  Activity,
  Boxes,
  CircleSlash2,
  Cog,
  FlaskConical,
  Gauge,
  Hammer,
  ScrollText,
  ShieldAlert,
  Wallet,
} from "lucide-react";
import { cx } from "../../lib/cx";

export interface RailLink {
  href: string;
  label: string;
  icon: ReactNode;
  /** Optional count rendered as a small badge. */
  count?: number;
  match?: (pathname: string) => boolean;
}

export interface RailGroup {
  title?: string;
  items: RailLink[];
}

export interface LeftRailProps {
  groups: RailGroup[];
}

const PRIMARY_GROUP: RailGroup = {
  items: [
    { href: "/", label: "Mission Control", icon: <Gauge size={15} /> },
    { href: "/instances", label: "Instances", icon: <Boxes size={15} /> },
    { href: "/blueprints", label: "Blueprints", icon: <Hammer size={15} /> },
    { href: "/runs", label: "Runs", icon: <Activity size={15} /> },
    { href: "/approvals", label: "Approvals", icon: <ShieldAlert size={15} /> },
    { href: "/gym", label: "Gym", icon: <FlaskConical size={15} /> },
    { href: "/foundry", label: "Foundry", icon: <CircleSlash2 size={15} /> },
  ],
};

const SYSTEM_GROUP: RailGroup = {
  title: "System",
  items: [
    { href: "/providers", label: "Providers", icon: <Cog size={15} /> },
    { href: "/kernel", label: "Kernel", icon: <ScrollText size={15} /> },
    { href: "/economy", label: "Economy", icon: <Wallet size={15} /> },
    { href: "/design-system", label: "Design system", icon: <FlaskConical size={15} /> },
    { href: "/docs", label: "Docs", icon: <ScrollText size={15} /> },
  ],
};

export function LeftRail() {
  const pathname = usePathname() ?? "/";
  const [systemOpen, setSystemOpen] = useState(true);

  return (
    <aside className="app-rail" aria-label="Primary navigation">
      <Link href="/" className="app-rail__brand">
        <span className="app-rail__brand-mark mono">Ax</span>
        <span>Agent-X</span>
      </Link>

      <nav className="app-rail__nav">
        {PRIMARY_GROUP.items.map((item) => (
          <RailRow key={item.href} item={item} pathname={pathname} />
        ))}

        <button
          type="button"
          className="app-rail__group-title"
          aria-expanded={systemOpen}
          onClick={() => setSystemOpen((o) => !o)}
          style={{ background: "transparent", border: "none", cursor: "pointer", textAlign: "left" }}
        >
          {systemOpen ? "▾" : "▸"} System
        </button>
        {systemOpen
          ? SYSTEM_GROUP.items.map((item) => (
              <RailRow key={item.href} item={item} pathname={pathname} />
            ))
          : null}
      </nav>
    </aside>
  );
}

function RailRow({ item, pathname }: { item: RailLink; pathname: string }) {
  const active = item.match
    ? item.match(pathname)
    : item.href === "/"
      ? pathname === "/"
      : pathname === item.href || pathname.startsWith(`${item.href}/`);
  return (
    <Link
      href={item.href}
      className={cx("app-rail__item", active && "app-rail__item--active")}
      aria-current={active ? "page" : undefined}
    >
      <span className="app-rail__icon">{item.icon}</span>
      <span>{item.label}</span>
      {typeof item.count === "number" ? (
        <span className="app-rail__count mono">{item.count}</span>
      ) : null}
    </Link>
  );
}