"use client";

/**
 * BlueprintInspector — the deep Inspector for a single mandate type.
 *
 * Routes: /blueprints/{ref} where {ref} is the mandate id (e.g. "lead-finder")
 * OR the fully-qualified type_ref (e.g. "lead-finder@0.3.1"). The list endpoint
 * already carries every row, so we resolve locally for cheap correctness.
 *
 * The seven organs (BLUEPRINT §1) drive the tab structure:
 *   1. Charter · 2. Faculties · 3. Domain pack · 4. Verification ·
 *   5. Settlement · 6. Eval gym · 7. Execution · 8. Versions
 * Plus a "Faculty library" tab cross-cutting the faculties used by every
 * mandate type — so the operator can see what other types reuse the same brick.
 *
 * The "Instantiate" CTA at the top right opens the InstantiateDrawer (the same
 * drawer the list page uses), so behaviour is identical. The button itself is
 * the AsyncButton (no silent clicks — spec §9).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Hammer,
  Layers,
  ScrollText,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { AppShell } from "../shell/app-shell";
import {
  AsyncButton,
  Badge,
  Card,
  CardBody,
  CardFooter,
  CardHeader,
  EmptyState,
  ErrorState,
  JsonViewer,
  RingPill,
  Stack,
  StatusPill,
  Table,
  TableSkeleton,
  Tabs,
  TabPanel,
} from "../ui";
import { useToast } from "../../providers/toast-provider";
import { fetchMandateType, fetchMandateTypes } from "../../lib/api";
import {
  formatCurrency,
  formatRelative,
  shortId,
} from "../../lib/format";
import type {
  FacultyBindingView,
  FacultyLibraryEntry,
  MandateType,
  MandateTypeVersion,
  VerificationOrgan,
} from "../../lib/types";

import { InstantiateDrawer } from "./instantiate-drawer";

interface BlueprintInspectorProps {
  /** Either the bare id (e.g. "lead-finder") or the full type_ref (e.g. "lead-finder@0.3.1"). */
  ref: string;
}

type TabKey =
  | "charter"
  | "faculties"
  | "domain"
  | "verification"
  | "settlement"
  | "gym"
  | "execution"
  | "versions"
  | "library";

const TAB_LABELS: Record<TabKey, string> = {
  charter: "Charter",
  faculties: "Faculties",
  domain: "Domain pack",
  verification: "Verification",
  settlement: "Settlement",
  gym: "Eval gym",
  execution: "Execution",
  versions: "Versions",
  library: "Faculty library",
};

export function BlueprintInspector({ ref }: BlueprintInspectorProps) {
  const toast = useToast();
  const [type, setType] = useState<MandateType | null>(null);
  const [facultyLibrary, setFacultyLibrary] = useState<FacultyLibraryEntry[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<TabKey>("charter");
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);

  const load = useCallback(
    async (mode: "initial" | "refresh" = "initial") => {
      if (mode === "refresh") setRefreshing(true);
      try {
        const [single, library] = await Promise.all([
          fetchMandateType(ref),
          fetchMandateTypes(),
        ]);
        setType(single.data);
        setFacultyLibrary(buildFacultyLibrary(library.data));
        setError(null);
        if (mode === "refresh" && library.source === "fixture" && library.error) {
          toast.push({
            title: "Showing fixture blueprints",
            message: library.error,
            tone: "hot",
          });
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [ref, toast],
  );

  useEffect(() => {
    void load("initial");
  }, [load]);

  const tabs = useMemo(() => {
    if (!type) return [];
    return [
      { key: "charter" as const, label: TAB_LABELS.charter },
      {
        key: "faculties" as const,
        label: TAB_LABELS.faculties,
        badge: type.faculties.length,
      },
      { key: "domain" as const, label: TAB_LABELS.domain },
      { key: "verification" as const, label: TAB_LABELS.verification },
      { key: "settlement" as const, label: TAB_LABELS.settlement },
      {
        key: "gym" as const,
        label: TAB_LABELS.gym,
        badge: type.gym_ref?.cases_count ?? 0,
      },
      { key: "execution" as const, label: TAB_LABELS.execution },
      {
        key: "versions" as const,
        label: TAB_LABELS.versions,
        badge: type.versions.length,
      },
      { key: "library" as const, label: TAB_LABELS.library, badge: facultyLibrary.length },
    ];
  }, [type, facultyLibrary.length]);

  if (loading) {
    return (
      <AppShell
        title="Blueprints"
        crumbs={[{ label: "Blueprints", href: "/blueprints" }, { label: ref }]}
      >
        <Card>
          <CardHeader eyebrow={`Loading ${ref}`} title="Resolving mandate type…" />
          <CardBody>
            <TableSkeleton columns={5} rows={4} />
          </CardBody>
        </Card>
      </AppShell>
    );
  }

  if (error && !type) {
    return (
      <AppShell
        title="Blueprints"
        crumbs={[{ label: "Blueprints", href: "/blueprints" }, { label: ref }]}
        onRefresh={() => void load("refresh")}
        refreshing={refreshing}
      >
        <ErrorState
          title="Couldn't load blueprint"
          detail={error}
          action={
            <AsyncButton variant="secondary" onClick={() => void load("refresh")}>
              Retry
            </AsyncButton>
          }
        />
      </AppShell>
    );
  }

  if (!type) {
    return (
      <AppShell
        title="Blueprints"
        crumbs={[{ label: "Blueprints", href: "/blueprints" }, { label: ref }]}
      >
        <EmptyState
          title={`No blueprint matches "${ref}"`}
          detail="The catalog doesn't carry this id or type_ref. Head back to /blueprints to pick a different one."
          action={
            <Link href="/blueprints" className="ax-input ax-button ax-button--ghost">
              ← Back to Blueprints
            </Link>
          }
        />
      </AppShell>
    );
  }

  const liveVersion = type.versions.find((v) => v.status === "live") ?? type.versions[0];
  const canInstantiate = type.status !== "locked" && type.status !== "gap";
  const instantiateDisabledReason =
    type.status === "locked"
      ? "Locked — Phase-2 scope (e.g. WhatsApp adapter)."
      : type.status === "gap"
        ? "Gap — adapter scope not yet shipped (see invariants)."
        : undefined;

  return (
    <AppShell
      title="Blueprints"
      crumbs={[
        { label: "Blueprints", href: "/blueprints" },
        { label: type.title },
      ]}
      onRefresh={() => void load("refresh")}
      refreshing={refreshing}
    >
      <div className="blueprint-inspector">
        <div className="blueprint-inspector__back">
          <Link href="/blueprints" className="blueprint-inspector__back-link">
            <ArrowLeft size={14} /> All blueprints
          </Link>
        </div>

        <Card>
          <CardHeader
            eyebrow={`Mandate type · ${type.type_ref}`}
            title={type.title}
            subtitle={type.description}
            action={
              <span className="blueprint-inspector__cta">
                <AsyncButton
                  variant="primary"
                  size="md"
                  icon={<Hammer size={14} />}
                  onClick={() => setDrawerOpen(true)}
                  loading={false}
                  disabled={!canInstantiate}
                  disabledReason={instantiateDisabledReason}
                  loadingText="Opening…"
                >
                  Instantiate
                </AsyncButton>
              </span>
            }
          />
          <CardBody>
            <div className="blueprint-inspector__meta">
              <MetaCell label="Type ref" mono value={type.type_ref} />
              <MetaCell
                label="Ring floor"
                value={<RingPill ring={type.ring_floor} />}
              />
              <MetaCell
                label="Status"
                value={<StatusPill tone={statusTone(type.status)}>{type.status}</StatusPill>}
              />
              <MetaCell
                label="Live version"
                mono
                value={liveVersion?.version ?? "—"}
                hint={liveVersion ? `Released ${formatRelative(liveVersion.released_at)}` : undefined}
              />
              <MetaCell label="Instances" mono value={type.instances_count ?? 0} />
              <MetaCell label="Type id" mono value={shortId(type.id)} />
            </div>
            <div className="blueprint-inspector__economics">
              <span className="dim">Unit economics:</span>{" "}
              <span>{type.unit_economics}</span>
            </div>
          </CardBody>
        </Card>

        <Card padding="none">
          <div className="blueprint-inspector__tabs">
            <Tabs items={tabs} active={activeTab} onChange={(k) => setActiveTab(k as TabKey)} />
          </div>
          <CardBody>
            <TabPanel activeKey={activeTab} tabKey="charter">
              <CharterPanel mandate={type} />
            </TabPanel>
            <TabPanel activeKey={activeTab} tabKey="faculties">
              <FacultiesPanel mandate={type} />
            </TabPanel>
            <TabPanel activeKey={activeTab} tabKey="domain">
              <DomainPanel mandate={type} />
            </TabPanel>
            <TabPanel activeKey={activeTab} tabKey="verification">
              <VerificationPanel mandate={type} />
            </TabPanel>
            <TabPanel activeKey={activeTab} tabKey="settlement">
              <SettlementPanel mandate={type} />
            </TabPanel>
            <TabPanel activeKey={activeTab} tabKey="gym">
              <GymPanel mandate={type} />
            </TabPanel>
            <TabPanel activeKey={activeTab} tabKey="execution">
              <ExecutionPanel mandate={type} />
            </TabPanel>
            <TabPanel activeKey={activeTab} tabKey="versions">
              <VersionsPanel versions={type.versions} />
            </TabPanel>
            <TabPanel activeKey={activeTab} tabKey="library">
              <LibraryPanel library={facultyLibrary} />
            </TabPanel>
          </CardBody>
        </Card>
      </div>

      <InstantiateDrawer
        mandate={drawerOpen ? type : null}
        onClose={() => setDrawerOpen(false)}
        onCreated={(instanceId) => {
          setDrawerOpen(false);
          toast.push({
            title: "Instance created",
            message: instanceId ?? "Mandate instantiated.",
            tone: "good",
          });
        }}
      />
    </AppShell>
  );
}

// ----------------------------------------------------------------------------
// Reusable building blocks
// ----------------------------------------------------------------------------

interface MetaCellProps {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
  hint?: string;
}

function MetaCell({ label, value, mono, hint }: MetaCellProps) {
  return (
    <div className="blueprint-inspector__meta-cell">
      <div className="blueprint-inspector__meta-label">{label}</div>
      <div className={mono ? "blueprint-inspector__meta-value mono" : "blueprint-inspector__meta-value"}>
        {value}
      </div>
      {hint ? <div className="blueprint-inspector__meta-hint">{hint}</div> : null}
    </div>
  );
}

function CharterPanel({ mandate }: { mandate: MandateType }) {
  return (
    <div className="organ-panel">
      <section className="organ-panel__section">
        <h3 className="organ-panel__heading">
          <ScrollText size={16} /> Goal
        </h3>
        <p>{mandate.charter.goal}</p>
      </section>

      <div className="organ-panel__grid">
        <ConditionList title="Preconditions" items={mandate.charter.preconditions} />
        <ConditionList title="Path conditions" items={mandate.charter.pathconditions} />
        <ConditionList title="Postconditions" items={mandate.charter.postconditions} />
        <ConditionList title="Constraints" items={mandate.charter.constraints} />
      </div>

      <section className="organ-panel__section">
        <h3 className="organ-panel__heading">
          <Sparkles size={16} /> Target (typed JSON)
        </h3>
        <JsonViewer value={mandate.charter.target} />
      </section>
    </div>
  );
}

function ConditionList({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="organ-panel__list">
      <h4 className="organ-panel__list-heading">{title}</h4>
      {items.length === 0 ? (
        <div className="dim">— none —</div>
      ) : (
        <ul className="organ-panel__list-items">
          {items.map((item, idx) => (
            <li key={`${title}-${idx}`}>{item}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function FacultiesPanel({ mandate }: { mandate: MandateType }) {
  return (
    <Table
      columns={[
        {
          key: "name",
          header: "Faculty",
          render: (row: FacultyBindingView) => (
            <span className="mono">{row.faculty_name}</span>
          ),
        },
        {
          key: "version",
          header: "Version",
          mono: true,
          render: (row) => <span className="mono dim">{row.faculty_version}</span>,
        },
        {
          key: "harness",
          header: "Harness",
          render: (row) => <Badge tone="neutral">{row.harness}</Badge>,
        },
        {
          key: "model",
          header: "Model",
          mono: true,
          render: (row) => <span className="mono">{row.model || "—"}</span>,
        },
        {
          key: "budget",
          header: "Budget / call",
          align: "right",
          mono: true,
          render: (row) => (
            <span className="mono">
              {row.budget !== null ? `$${row.budget.toFixed(3)}` : "—"}
            </span>
          ),
        },
        {
          key: "description",
          header: "What it does",
          render: (row) => <span className="dim">{row.description ?? "—"}</span>,
        },
      ]}
      rows={mandate.faculties}
      rowKey={(row) => `${row.faculty_name}@${row.faculty_version}`}
      density="comfortable"
    />
  );
}

function DomainPanel({ mandate }: { mandate: MandateType }) {
  return (
    <div className="organ-panel">
      <dl className="blueprint-inspector__kv">
        <div>
          <dt>Name</dt>
          <dd className="mono">{mandate.domain_pack.name}</dd>
        </div>
        <div>
          <dt>Version</dt>
          <dd className="mono">{mandate.domain_pack.version}</dd>
        </div>
        <div>
          <dt>Vertical</dt>
          <dd>{mandate.domain_pack.vertical ?? "—"}</dd>
        </div>
      </dl>
      <p className="dim">
        Domain packs are vertical playbooks + cross-customer priors (e.g. "clinics book 2× if
        slot offered"). Sharing one across instances is by design; customers never see each
        other's fact lines (invariant #3).
      </p>
    </div>
  );
}

const RUNG_LABEL: Record<VerificationRungKey, string> = {
  rules: "Rules",
  judge: "Judge",
  human: "Human",
  reality: "Reality",
};

type VerificationRungKey = "rules" | "judge" | "human" | "reality";

function VerificationPanel({ mandate }: { mandate: MandateType }) {
  const verification: VerificationOrgan = mandate.verification;
  return (
    <div className="organ-panel">
      <section className="organ-panel__section">
        <h3 className="organ-panel__heading">
          <ShieldCheck size={16} /> Ladder
        </h3>
        <div className="organ-panel__ladder">
          {verification.ladder.map((rung) => (
            <div
              key={rung.rung}
              className={`organ-panel__rung organ-panel__rung--${
                rung.present ? "present" : "absent"
              }`}
              title={rung.present ? `${rung.rung} rung is live` : `${rung.rung} rung not wired`}
            >
              <span className="organ-panel__rung-dot" />
              <span className="organ-panel__rung-label">{RUNG_LABEL[rung.rung] ?? rung.rung}</span>
              <StatusPill tone={rung.present ? "good" : "muted"} size="sm">
                {rung.present ? "live" : "absent"}
              </StatusPill>
            </div>
          ))}
        </div>
      </section>

      <div className="organ-panel__grid">
        <ConditionList title="Rules" items={verification.rules} />
        <ConditionList title="Rubrics" items={verification.rubrics} />
      </div>
    </div>
  );
}

function SettlementPanel({ mandate }: { mandate: MandateType }) {
  return (
    <div className="organ-panel">
      <dl className="blueprint-inspector__kv">
        <div>
          <dt>Fact-commit confidence</dt>
          <dd className="mono">{(mandate.settlement.fact_commit_confidence * 100).toFixed(0)}%</dd>
        </div>
        <div>
          <dt>Trust on success</dt>
          <dd className="mono">+{mandate.settlement.trust_on_success}</dd>
        </div>
        <div>
          <dt>Trust on failure</dt>
          <dd className="mono">−{Math.abs(mandate.settlement.trust_on_failure)}</dd>
        </div>
        <div>
          <dt>Watch window</dt>
          <dd className="mono">{mandate.settlement.watch_window_hours}h</dd>
        </div>
        <div>
          <dt>Billing / run</dt>
          <dd className="mono">
            {mandate.settlement.billing_per_run !== null
              ? formatCurrency(mandate.settlement.billing_per_run)
              : "—"}
          </dd>
        </div>
      </dl>

      <section className="organ-panel__section">
        <h3 className="organ-panel__heading">Spawn rules</h3>
        {mandate.settlement.spawn_rules.length === 0 ? (
          <div className="dim">— none —</div>
        ) : (
          <ul className="organ-panel__list-items">
            {mandate.settlement.spawn_rules.map((rule, idx) => (
              <li key={`spawn-${idx}`}>
                When <span className="mono">{rule.on_condition}</span> → spawn{" "}
                <span className="mono">{rule.child_type_ref}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function GymPanel({ mandate }: { mandate: MandateType }) {
  if (!mandate.gym_ref) {
    return (
      <EmptyState
        title="No eval gym bound"
        detail="This mandate type hasn't been wired to an eval gym yet — scorecards and PromotionGate evidence live there."
      />
    );
  }
  return (
    <div className="organ-panel">
      <dl className="blueprint-inspector__kv">
        <div>
          <dt>Name</dt>
          <dd className="mono">{mandate.gym_ref.name}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>
            <StatusPill
              tone={
                mandate.gym_ref.status === "active"
                  ? "good"
                  : mandate.gym_ref.status === "blocked"
                    ? "hot"
                    : "muted"
              }
            >
              {mandate.gym_ref.status}
            </StatusPill>
          </dd>
        </div>
        <div>
          <dt>Cases</dt>
          <dd className="mono">{mandate.gym_ref.cases_count}</dd>
        </div>
      </dl>
      <p className="dim">
        The eval gym is where this type's scorecards live. PromotionGate bars synthetic-only
        evidence from promoting any customer-facing version (invariant #7).
      </p>
    </div>
  );
}

function ExecutionPanel({ mandate }: { mandate: MandateType }) {
  if (mandate.execution.routing.length === 0) {
    return <EmptyState title="No execution routing defined" detail="This mandate has no harness×model bindings yet." />;
  }
  return (
    <Table
      columns={[
        {
          key: "faculty",
          header: "Faculty",
          mono: true,
          render: (row) => <span className="mono">{row.faculty_name}</span>,
        },
        {
          key: "harness",
          header: "Harness",
          render: (row) => <Badge tone="neutral">{row.harness}</Badge>,
        },
        {
          key: "model",
          header: "Model",
          mono: true,
          render: (row) => <span className="mono">{row.model || "—"}</span>,
        },
        {
          key: "budget",
          header: "Budget / call",
          align: "right",
          mono: true,
          render: (row) => (
            <span className="mono">
              {row.budget !== null ? `$${row.budget.toFixed(3)}` : "—"}
            </span>
          ),
        },
      ]}
      rows={mandate.execution.routing}
      rowKey={(row, idx) => `${row.faculty_name}-${idx}`}
      density="comfortable"
    />
  );
}

function VersionsPanel({ versions }: { versions: MandateTypeVersion[] }) {
  if (versions.length === 0) {
    return <EmptyState title="No versions yet" detail="This mandate type hasn't shipped a release." />;
  }
  return (
    <Table
      columns={[
        {
          key: "version",
          header: "Version",
          mono: true,
          render: (row) => <span className="mono">{row.version}</span>,
        },
        {
          key: "status",
          header: "Status",
          render: (row) => (
            <StatusPill tone={versionTone(row.status)}>{row.status}</StatusPill>
          ),
        },
        {
          key: "released",
          header: "Released",
          mono: true,
          render: (row) => <span className="dim">{formatRelative(row.released_at)}</span>,
        },
        {
          key: "changelog",
          header: "Changelog",
          render: (row) => <span className="dim">{row.changelog}</span>,
        },
      ]}
      rows={versions}
      rowKey={(row) => row.version}
      density="comfortable"
    />
  );
}

function LibraryPanel({ library }: { library: FacultyLibraryEntry[] }) {
  if (library.length === 0) {
    return <EmptyState title="Faculty library is empty" detail="The catalog has no faculties to cross-reference yet." />;
  }
  return (
    <Table
      columns={[
        {
          key: "name",
          header: "Faculty",
          mono: true,
          render: (row) => <span className="mono">{row.name}</span>,
        },
        {
          key: "category",
          header: "Category",
          render: (row) => <Badge tone="info">{row.category}</Badge>,
        },
        {
          key: "version",
          header: "Version",
          mono: true,
          render: (row) => <span className="mono dim">{row.version}</span>,
        },
        {
          key: "used_by",
          header: "Used by",
          render: (row) => (
            <span className="dim">
              {row.used_by.length === 0 ? "—" : row.used_by.join(", ")}
            </span>
          ),
        },
        {
          key: "description",
          header: "What it does",
          render: (row) => <span className="dim">{row.description}</span>,
        },
      ]}
      rows={library}
      rowKey={(row) => `${row.name}@${row.version}`}
      density="comfortable"
    />
  );
}

// ----------------------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------------------

function buildFacultyLibrary(types: MandateType[]): FacultyLibraryEntry[] {
  const byFaculty = new Map<string, { meta?: FacultyLibraryEntry; usedBy: Set<string> }>();
  for (const type of types) {
    for (const faculty of type.faculties) {
      const key = `${faculty.faculty_name}@${faculty.faculty_version}`;
      const slot = byFaculty.get(key) ?? { usedBy: new Set<string>() };
      slot.usedBy.add(type.id);
      if (!slot.meta) {
        slot.meta = {
          name: faculty.faculty_name,
          version: faculty.faculty_version,
          description: faculty.description ?? "",
          category: classifyFaculty(faculty.faculty_name),
          used_by: [],
        };
      }
      byFaculty.set(key, slot);
    }
  }
  return Array.from(byFaculty.entries())
    .map(([, slot]) => {
      if (!slot.meta) return null;
      return { ...slot.meta, used_by: Array.from(slot.usedBy).sort() };
    })
    .filter((entry): entry is FacultyLibraryEntry => entry !== null)
    .sort((a, b) => a.name.localeCompare(b.name));
}

function classifyFaculty(name: string): FacultyLibraryEntry["category"] {
  if (/research|search|exa/i.test(name)) return "research";
  if (/send|outreach|email|draft/i.test(name)) return "outreach";
  if (/score|judge|analy|evaluat/i.test(name)) return "analysis";
  if (/content|write|copy/i.test(name)) return "content";
  if (/settle|settle_?|commit|spawn/i.test(name)) return "settlement";
  return "ops";
}

function statusTone(status: MandateType["status"]) {
  switch (status) {
    case "ready":
      return "good" as const;
    case "canary":
      return "info" as const;
    case "gap":
      return "warn" as const;
    case "locked":
      return "muted" as const;
    default:
      return "neutral" as const;
  }
}

function versionTone(status: MandateTypeVersion["status"]) {
  switch (status) {
    case "live":
      return "good" as const;
    case "canary":
      return "info" as const;
    case "draft":
      return "neutral" as const;
    case "deprecated":
      return "muted" as const;
    default:
      return "neutral" as const;
  }
}

// re-export icon set so the bundler keeps it
void Layers;