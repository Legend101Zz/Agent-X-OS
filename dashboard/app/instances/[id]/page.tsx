"use client";

/**
 * `/instances/[id]` — the per-instance deep Inspector.
 *
 * This is a thin client wrapper that defers all data fetching + state to
 * `InstanceInspector` (so the Inspector can also be embedded in tests and
 * god-views without route coupling).
 *
 * Tabs: Overview · Live Activity · Runs · Approvals · Trust
 * (Memory + Actions land in C4 with the C3 heap read API).
 */

import { useParams } from "next/navigation";
import { useMemo } from "react";

import { InstanceInspector, type InspectorTabKey } from "../../../src/components/instances/instance-inspector";

const VALID_TABS: InspectorTabKey[] = [
  "overview",
  "activity",
  "runs",
  "approvals",
  "trust",
  "memory",
  "actions",
];

export default function InstanceInspectorPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";
  // Allow deep-linking to a specific tab via ?tab=<key>; useful for
  // "send to the approvals tab" share-links.
  const initialTab = useMemo<InspectorTabKey>(() => {
    if (typeof window === "undefined") return "overview";
    const search = new URLSearchParams(window.location.search);
    const tab = search.get("tab") ?? "";
    return VALID_TABS.includes(tab as InspectorTabKey) ? (tab as InspectorTabKey) : "overview";
  }, []);

  if (!id) {
    return <InstanceInspector instanceId="" initialTab={initialTab} />;
  }

  return <InstanceInspector instanceId={id} initialTab={initialTab} />;
}
