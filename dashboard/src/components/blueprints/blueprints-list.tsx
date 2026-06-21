"use client";

/**
 * BlueprintsList — the entry point to every mandate type in the catalog.
 *
 * Each row is a deep-link to `/blueprints/{ref}` (the BlueprintInspector).
 * Pills carry the most-glanced attributes (status, ring floor, instances
 * count, version); the table itself is the body, the parent AppShell is the
 * chrome. The "Instantiate" CTA opens the per-row instantiate drawer (the
 * card's done-when explicitly requires the AsyncButton, never a silent click).
 *
 * Source: `/mandate-types` (existing kernel endpoint); fallback to the rich
 * 7-organ fixture (lead-finder, creator, invoice desk, whatsapp-locked) so
 * the page is scannable offline.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  CircleSlash2,
  Hammer,
  Layers,
  ShieldCheck,
  Sparkles,
  ZapOff,
} from "lucide-react";

import { AppShell } from "../shell/app-shell";
import {
  AsyncButton,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  StatusPill,
  Table,
  TableSkeleton,
} from "../ui";
import { useToast } from "../../providers/toast-provider";
import { fetchMandateTypes } from "../../lib/api";
import {
  formatRelative,
  shortId,
} from "../../lib/format";
import type { MandateType } from "../../lib/types";

import { InstantiateDrawer } from "./instantiate-drawer";

interface BlueprintsListProps {
  initialMandateTypes?: MandateType[];
}

export function BlueprintsList({ initialMandateTypes }: BlueprintsListProps = {}) {
  const toast = useToast();
  const router = useRouter();
  const [types, setTypes] = useState<MandateType[] | null>(initialMandateTypes ?? null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(!initialMandateTypes);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [drawerFor, setDrawerFor] = useState<MandateType | null>(null);

  const load = useCallback(
    async (mode: "initial" | "refresh" = "initial") => {
      if (mode === "refresh") setRefreshing(true);
      try {
        const result = await fetchMandateTypes();
        setTypes(result.data);
        setError(null);
        if (mode === "refresh" && result.source === "fixture" && result.error) {
          toast.push({
            title: "Showing fixture blueprints",
            message: result.error,
            tone: "hot",
          });
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
        if (mode === "refresh") {
          toast.push({ title: "Refresh failed", message, tone: "hot" });
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [toast],
  );

  useEffect(() => {
    if (initialMandateTypes) return;
    void load("initial");
  }, [initialMandateTypes, load]);

  const counts = useMemo(() => {
    if (!types) return { ready: 0, canary: 0, gap: 0, locked: 0 };
    return types.reduce(
      (acc, t) => {
        acc[t.status] += 1;
        return acc;
      },
      { ready: 0, canary: 0, gap: 0, locked: 0 },
    );
  }, [types]);

  return (
    <AppShell
      title="Blueprints"
      crumbs={[{ label: "Blueprints" }]}
      onRefresh={() => void load("refresh")}
      refreshing={refreshing}
    >
      <div className="blueprints-page">
        <Card>
          <CardHeader
            eyebrow="Mandate types"
            title="Every blueprint in the catalog"
            subtitle="Click a blueprint to inspect its seven organs (charter, faculties, domain pack, verification, settlement, eval gym, execution). Use the Instantiate action to spin up a new instance for your business."
            action={
              <AsyncButton
                variant="secondary"
                size="sm"
                icon={<CircleSlash2 size={14} />}
                onClick={() => void load("refresh")}
                loading={refreshing}
              >
                Refresh
              </AsyncButton>
            }
          />
          <CardBody>
            {error && !loading ? (
              <ErrorState
                title="Couldn't load blueprints"
                detail={error}
                action={
                  <AsyncButton variant="secondary" onClick={() => void load("refresh")}>
                    Retry
                  </AsyncButton>
                }
              />
            ) : loading || !types ? (
              <TableSkeleton columns={6} rows={4} />
            ) : types.length === 0 ? (
              <EmptyState
                title="No blueprints in the catalog yet"
                detail="The Creator mandate (canary rung) will emit candidates here. Until then, this view stays empty."
              />
            ) : (
              <Table
                columns={[
                  {
                    key: "name",
                    header: "Blueprint",
                    render: (row) => (
                      <Link
                        href={`/blueprints/${encodeURIComponent(row.id)}`}
                        className="blueprints-row__name"
                      >
                        <span className="h3">{row.title}</span>
                        <span className="mono dim">{shortId(row.id)}</span>
                      </Link>
                    ),
                  },
                  {
                    key: "type_ref",
                    header: "Type ref",
                    mono: true,
                    render: (row) => (
                      <span className="mono dim" title={row.type_ref}>
                        {row.type_ref}
                      </span>
                    ),
                  },
                  {
                    key: "status",
                    header: "Status",
                    render: (row) => <BlueprintStatusPill status={row.status} />,
                  },
                  {
                    key: "ring",
                    header: "Ring floor",
                    mono: true,
                    render: (row) => (
                      <span className="mono">{row.ring_floor || "—"}</span>
                    ),
                  },
                  {
                    key: "faculties",
                    header: "Faculties",
                    align: "right",
                    render: (row) => (
                      <span className="mono">{row.faculties.length}</span>
                    ),
                  },
                  {
                    key: "instances",
                    header: "Instances",
                    align: "right",
                    render: (row) => (
                      <span className="mono" title={`${row.instances_count ?? 0} running`}>
                        {row.instances_count ?? 0}
                      </span>
                    ),
                  },
                  {
                    key: "version",
                    header: "Released",
                    mono: true,
                    render: (row) => {
                      const live = row.versions.find((v) => v.status === "live") ?? row.versions[0];
                      return (
                        <span className="dim" title={live?.changelog}>
                          {live ? formatRelative(live.released_at) : "—"}
                        </span>
                      );
                    },
                  },
                  {
                    key: "actions",
                    header: "",
                    align: "right",
                    render: (row) => (
                      <span onClick={(event) => event.stopPropagation()}>
                        <AsyncButton
                          variant="primary"
                          size="sm"
                          icon={<Hammer size={13} />}
                          onClick={() => setDrawerFor(row)}
                          loading={false}
                          disabled={row.status === "locked"}
                          disabledReason={
                            row.status === "locked"
                              ? "Locked — Phase-2 scope (e.g. WhatsApp adapter)."
                              : row.status === "gap"
                                ? "Gap — adapter scope not yet shipped (see invariants)."
                                : undefined
                          }
                        >
                          Instantiate
                        </AsyncButton>
                      </span>
                    ),
                  },
                ]}
                rows={types}
                rowKey={(row) => row.id}
                onRowClick={(row) => router.push(`/blueprints/${encodeURIComponent(row.id)}`)}
                density="comfortable"
              />
            )}
          </CardBody>
        </Card>

        <div className="blueprints-summary" data-state={loading ? "loading" : "ready"}>
          <SummaryTile
            label="Ready"
            value={counts.ready}
            icon={<ShieldCheck size={14} />}
            tone="good"
          />
          <SummaryTile
            label="Canary"
            value={counts.canary}
            icon={<Sparkles size={14} />}
            tone="info"
          />
          <SummaryTile
            label="Gap"
            value={counts.gap}
            icon={<AlertTriangle size={14} />}
            tone="warn"
          />
          <SummaryTile
            label="Locked"
            value={counts.locked}
            icon={<ZapOff size={14} />}
            tone="muted"
          />
          <SummaryTile
            label="Catalog size"
            value={types?.length ?? 0}
            icon={<Layers size={14} />}
            tone="default"
          />
        </div>

        <div className="dim" style={{ fontSize: 12 }}>
          Source: <code>/mandate-types</code> · Inspector opens at <code>/blueprints/&lt;id&gt;</code> · Instantiate posts to <code>/commands/instantiate</code> with <code>sender_identity</code> (invariant #8).
        </div>
      </div>

      <InstantiateDrawer
        mandate={drawerFor}
        onClose={() => setDrawerFor(null)}
        onCreated={(instanceId) => {
          setDrawerFor(null);
          toast.push({
            title: "Instance created",
            message: instanceId ?? "Mandate instantiated.",
            tone: "good",
          });
          router.push(`/instances/${encodeURIComponent(instanceId ?? "")}`);
        }}
      />
    </AppShell>
  );
}

interface SummaryTileProps {
  label: string;
  value: number | string;
  icon?: React.ReactNode;
  tone?: "default" | "good" | "warn" | "muted" | "info";
}

function SummaryTile({ label, value, icon, tone = "default" }: SummaryTileProps) {
  return (
    <div className={`blueprints-summary__tile blueprints-summary__tile--${tone}`}>
      <div className="blueprints-summary__label">
        {icon}
        <span>{label}</span>
      </div>
      <div className="blueprints-summary__value mono">{value}</div>
    </div>
  );
}

function BlueprintStatusPill({ status }: { status: MandateType["status"] }) {
  switch (status) {
    case "ready":
      return (
        <StatusPill tone="good" dot>
          ready
        </StatusPill>
      );
    case "canary":
      return (
        <StatusPill tone="info" dot pulse>
          canary
        </StatusPill>
      );
    case "gap":
      return (
        <StatusPill tone="warn" dot>
          gap
        </StatusPill>
      );
    case "locked":
      return (
        <StatusPill tone="muted" dot>
          locked
        </StatusPill>
      );
    default:
      return <StatusPill tone="neutral">{status}</StatusPill>;
  }
}