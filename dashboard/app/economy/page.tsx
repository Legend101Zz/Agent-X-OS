"use client";

/**
 * C16 — Economy / P&L view.
 * Reads the C15 endpoints only: /economy/units for fleet/business-unit totals and
 * /economy?instance_id=... for per-instance settlement ledgers.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { CircleDollarSign, ReceiptText, RefreshCw, TrendingUp, Wallet } from "lucide-react";
import Link from "next/link";
import { AppShell } from "../../src/components/shell/app-shell";
import {
  AsyncButton,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  HelpPanel,
  InfoTip,
  Section,
  Stack,
  StatTile,
  StatusPill,
  Table,
  TableSkeleton,
} from "../../src/components/ui";
import { fetchEconomy, fetchEconomyUnits, fetchInstances } from "../../src/lib/api";
import { formatCurrency, formatDateTime, formatInt, shortId } from "../../src/lib/format";
import type { EconomyUnitsSnapshot, InstancePnL, InstanceSummary } from "../../src/lib/types";

type InstancePnLRow = InstancePnL & {
  name: string;
  business: string;
};

const emptyUnits: EconomyUnitsSnapshot = {
  units: [],
  totals: { billing_total: 0, settled_count: 0, currency: "INR" },
};

export default function EconomyPage() {
  const [units, setUnits] = useState<EconomyUnitsSnapshot>(emptyUnits);
  const [instances, setInstances] = useState<InstanceSummary[]>([]);
  const [instancePnl, setInstancePnl] = useState<InstancePnL[]>([]);
  const [selectedInstanceId, setSelectedInstanceId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (mode: "initial" | "refresh" = "initial") => {
    if (mode === "refresh") setRefreshing(true);
    try {
      const [unitResult, instanceResult] = await Promise.all([
        fetchEconomyUnits(),
        fetchInstances(),
      ]);
      const instanceIds = unitResult.data.units.flatMap((unit) => unit.instance_ids);
      const pnlResults = await Promise.all(
        instanceIds.map((instanceId) => fetchEconomy({ instance_id: instanceId })),
      );
      const livePnl = pnlResults
        .map((result) => result.data)
        .filter((row) => !row.missing);

      setUnits(unitResult.data);
      setInstances(instanceResult.data);
      setInstancePnl(livePnl);
      setSelectedInstanceId((current) => {
        if (current && livePnl.some((row) => row.instance_id === current)) return current;
        return livePnl[0]?.instance_id ?? "";
      });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load("initial");
  }, [load]);

  const rows = useMemo<InstancePnLRow[]>(() => {
    return instancePnl.map((row) => {
      const instance = instances.find((item) => item.id === row.instance_id);
      return {
        ...row,
        name: instance?.name ?? row.instance_id,
        business: instance?.business ?? instance?.mandate_type ?? "business unit",
      };
    });
  }, [instancePnl, instances]);

  const selected = rows.find((row) => row.instance_id === selectedInstanceId) ?? rows[0];
  const currency = units.totals.currency || selected?.currency || "INR";

  return (
    <AppShell
      title="Economy"
      crumbs={[{ label: "System" }, { label: "Economy" }]}
      onRefresh={() => load("refresh")}
      refreshing={refreshing}
    >
      <Stack gap={5}>
        <HelpPanel id="economy">
          <p>
            Profit and loss per instance and business unit, built from settled runs{" "}
            <InfoTip term="settlement" />. Revenue, cost, and margin roll up here so you can see which
            mandates pay for themselves.
          </p>
        </HelpPanel>
        {error ? (
          <Card tone="danger">
            <CardHeader
              title="Could not load Economy/P&L"
              subtitle={error}
              action={
                <AsyncButton onClick={() => load("refresh")} loading={refreshing}>
                  Retry
                </AsyncButton>
              }
            />
          </Card>
        ) : null}

        <Section
          title="P&L snapshot"
          eyebrow="C15 endpoints"
          subtitle="Read-only rollups from settlement billing lines and resume trust projections."
          action={
            <AsyncButton variant="secondary" onClick={() => load("refresh")} loading={refreshing}>
              <RefreshCw size={14} /> Refresh
            </AsyncButton>
          }
        >
          <div className="mc-stats">
            <StatTile
              label="Net billing"
              value={loading ? "—" : formatCurrency(units.totals.billing_total, { currency, sign: true })}
              tone={units.totals.billing_total >= 0 ? "good" : "hot"}
              icon={<CircleDollarSign size={14} />}
              hint="GET /economy/units"
            />
            <StatTile
              label="Settled runs"
              value={loading ? "—" : formatInt(units.totals.settled_count)}
              tone="good"
              icon={<ReceiptText size={14} />}
              hint="RunSettled billing lines"
            />
            <StatTile
              label="Business units"
              value={loading ? "—" : formatInt(units.units.length)}
              icon={<Wallet size={14} />}
              hint="customer_id rollups"
            />
            <StatTile
              label="Instances with P&L"
              value={loading ? "—" : formatInt(rows.length)}
              icon={<TrendingUp size={14} />}
              hint="GET /economy?instance_id=..."
            />
          </div>
        </Section>

        <Section title="Business-unit P&L" subtitle="Grouped by MandateInstance.customer_id.">
          {loading ? (
            <TableSkeleton columns={6} rows={4} />
          ) : units.units.length === 0 ? (
            <EmptyState
              title="No settled business units yet"
              detail="The Economy view will populate after the first RunSettled billing line projects."
              icon={<Wallet size={20} />}
            />
          ) : (
            <Table
              density="compact"
              rowKey={(row) => row.customer_id}
              rows={units.units}
              columns={[
                { key: "unit", header: "Business unit", render: (row) => <strong>{row.customer_id}</strong> },
                { key: "net", header: "Net", align: "right", render: (row) => formatCurrency(row.billing_total, { currency: row.currency, sign: true }) },
                { key: "settles", header: "Settles", align: "right", render: (row) => formatInt(row.settled_count) },
                { key: "trust", header: "Trust", align: "right", render: (row) => formatInt(row.trust_score) },
                { key: "instances", header: "Instances", align: "right", render: (row) => formatInt(row.instance_count) },
                { key: "ids", header: "IDs", render: (row) => <span className="mono">{row.instance_ids.map((id) => shortId(id)).join(", ")}</span> },
              ]}
            />
          )}
        </Section>

        <Section title="Per-instance P&L" subtitle="Every row is fetched from /economy?instance_id=...">
          {loading ? (
            <TableSkeleton columns={7} rows={5} />
          ) : rows.length === 0 ? (
            <EmptyState
              title="No instance P&L yet"
              detail="No instance has a settlement-backed billing line."
              icon={<CircleDollarSign size={20} />}
            />
          ) : (
            <Table
              density="compact"
              rowKey={(row) => row.instance_id}
              rows={rows}
              onRowClick={(row) => setSelectedInstanceId(row.instance_id)}
              columns={[
                {
                  key: "instance",
                  header: "Instance",
                  render: (row) => (
                    <Stack gap={1}>
                      <Link className="mono" href={`/instances/${row.instance_id}`}>{shortId(row.instance_id)}</Link>
                      <span>{row.name}</span>
                    </Stack>
                  ),
                },
                { key: "unit", header: "Business", render: (row) => <span className="muted">{row.business}</span> },
                { key: "net", header: "Net", align: "right", render: (row) => formatCurrency(row.billing_total, { currency: row.currency, sign: true }) },
                { key: "settles", header: "Settles", align: "right", render: (row) => formatInt(row.settled_count) },
                { key: "trust", header: "Trust", align: "right", render: (row) => formatInt(row.trust_score) },
                { key: "currency", header: "Currency", render: (row) => <StatusPill tone="info">{row.currency}</StatusPill> },
                { key: "ledger", header: "Ledger", align: "right", render: (row) => `${row.settlements.length} lines` },
              ]}
            />
          )}
        </Section>

        <Section
          title="Settlement ledger"
          subtitle={selected ? `Newest settlement lines for ${selected.name}` : "Select an instance row to inspect its billing ledger."}
        >
          {!selected ? (
            <EmptyState title="No settlement selected" detail="Pick a per-instance row above." />
          ) : selected.settlements.length === 0 ? (
            <EmptyState title="No settlement lines" detail="This instance has no projected billing lines yet." />
          ) : (
            <Card>
              <CardHeader
                title={selected.name}
                subtitle={<span className="mono">{selected.instance_id}</span>}
                action={<StatusPill tone="good">{formatCurrency(selected.billing_total, { currency: selected.currency, sign: true })}</StatusPill>}
              />
              <CardBody>
                <Table
                  density="compact"
                  rowKey={(row) => row.run_id}
                  rows={selected.settlements}
                  columns={[
                    { key: "run", header: "Run", render: (row) => <Link href={`/runs/${row.run_id}`} className="mono">{shortId(row.run_id)}</Link> },
                    { key: "amount", header: "Amount", align: "right", render: (row) => formatCurrency(row.amount, { currency: selected.currency, sign: true }) },
                    { key: "ts", header: "Projected", render: (row) => formatDateTime(row.ts) },
                  ]}
                />
              </CardBody>
            </Card>
          )}
        </Section>
      </Stack>
    </AppShell>
  );
}
