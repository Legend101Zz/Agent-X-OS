"use client";

/**
 * Primitives demo page — the C1 done-when assertion: "a demo page shows every
 * primitive incl. an AsyncButton that spins+toasts".
 * Mounted at /design-system so the founder can QA the design system in the
 * running app, and so other coder cards can refer to it as the canonical example.
 */
import { useState } from "react";
import { Sparkles, Loader2 } from "lucide-react";
import { AppShell } from "../../src/components/shell/app-shell";
import {
  AsyncButton,
  Badge,
  Button,
  Card,
  CardBody,
  CardFooter,
  CardHeader,
  Cluster,
  CodeBlock,
  Drawer,
  EmptyState,
  ErrorState,
  JsonViewer,
  Modal,
  RingPill,
  Row,
  Section,
  Skeleton,
  Sparkline,
  Stack,
  StatTile,
  StatusPill,
  Table,
  TableSkeleton,
  Tabs,
  TabPanel,
  Timeline,
} from "../../src/components/ui";
import { useToast } from "../../src/providers/toast-provider";
import { formatCurrency, formatRelative, journalKindTone } from "../../src/lib/format";

const TIMELINE_SAMPLE = [
  { id: "1", kind: "think", title: "Reasoning step", detail: "Decided to draft outreach email", tone: "info" as const, ts: "12:01:04" },
  { id: "2", kind: "claim", title: "Claimed fact", detail: "lead_score: 0.82", tone: "info" as const, ts: "12:01:06" },
  { id: "3", kind: "call", title: "Tool call: send_email (draft)", detail: "idempotency_key: 0xabc", tone: "info" as const, ts: "12:01:08" },
  { id: "4", kind: "park", title: "Parked awaiting L1 approval", detail: "Required ring L1", tone: "warn" as const, ts: "12:01:09" },
  { id: "5", kind: "settled", title: "Settled after approval", detail: "Trust delta +0.5", tone: "good" as const, ts: "12:04:30" },
];

const SAMPLE_JSON = {
  instance: { id: "inst_acme", name: "Acme — outreach", ring: "L2", trust_score: 0.78 },
  run: { id: "run_001", state: "settled", syscall: "send_email", args: { to: "founder@acme.io" } },
  evidence: ["exa:company.acme.io", "firecrawl:about-page"],
};

export default function ComponentsDemoPage() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [tab, setTab] = useState("buttons");

  function fakeWork(title: string, tone: "good" | "hot" | "info" = "good") {
    setBusy(true);
    setTimeout(() => {
      setBusy(false);
      toast.push({ title, message: "completed", tone });
    }, 900);
  }

  return (
    <AppShell title="Design system" crumbs={[{ label: "Design system" }]}>
      <Stack gap={5}>
        <Section title="Design system demo" eyebrow="C1 done-when">
          <Card>
            <CardHeader
              eyebrow="Foundation"
              title="Every primitive the new dashboard builds on"
              subtitle="Each section below renders a category of primitives. If you see them styled correctly, the design system is live."
            />
            <CardBody>
              <Tabs
                active={tab}
                onChange={setTab}
                items={[
                  { key: "buttons", label: "Buttons" },
                  { key: "status", label: "Status" },
                  { key: "data", label: "Data" },
                  { key: "feedback", label: "Feedback" },
                  { key: "overlays", label: "Overlays" },
                ]}
              />
              <TabPanel activeKey={tab} tabKey="buttons">
                <Stack gap={3}>
                  <Cluster gap={2}>
                    <AsyncButton onClick={() => fakeWork("Primary click")} loading={busy} icon={<Sparkles size={14} />}>
                      Run command
                    </AsyncButton>
                    <AsyncButton variant="secondary" loading={busy} loadingText="Sending…">
                      Secondary
                    </AsyncButton>
                    <AsyncButton variant="danger" disabledReason="Destructive action — confirm first">
                      Delete
                    </AsyncButton>
                    <AsyncButton variant="success">Approve</AsyncButton>
                    <Button variant="ghost">Ghost</Button>
                  </Cluster>
                  <div className="dim" style={{ fontSize: 12 }}>
                    AsyncButton owns: spinner, disabled, success/failure toasts. Disabled controls surface a tooltip explaining why (graceful disable).
                  </div>
                </Stack>
              </TabPanel>
              <TabPanel activeKey={tab} tabKey="status">
                <Cluster gap={3}>
                  <StatusPill tone="good" dot pulse>LIVE</StatusPill>
                  <StatusPill tone="warn" dot>PARKED</StatusPill>
                  <StatusPill tone="hot" dot>CRASHED</StatusPill>
                  <StatusPill tone="info" dot>RUNNING</StatusPill>
                  <StatusPill tone="muted">DRAFT</StatusPill>
                  <RingPill ring="L0" />
                  <RingPill ring="L1" />
                  <RingPill ring="L2" />
                  <RingPill ring="L3" />
                  <RingPill ring="L4" />
                  <Badge tone="good">12 settles</Badge>
                  <Badge tone="warn">3 awaiting</Badge>
                </Cluster>
              </TabPanel>
              <TabPanel activeKey={tab} tabKey="data">
                <Stack gap={3}>
                  <div className="mc-stats">
                    <StatTile label="Active runs" value="3" tone="warn" icon={<Loader2 size={14} />} hint="2 awaiting approval" />
                    <StatTile label="Pending approvals" value="2" tone="hot" hint="L0/L1 inbox" />
                    <StatTile label="Monthly net" value={formatCurrency(4820, { sign: true })} tone="good" />
                    <StatTile label="Settles today" value="14" tone="good" />
                  </div>
                  <Table
                    density="compact"
                    rowKey={(row) => row.id}
                    columns={[
                      { key: "id", header: "ID", mono: true, render: (row) => row.id },
                      { key: "kind", header: "Kind", render: (row) => <StatusPill tone={journalKindTone(row.kind)}>{row.kind}</StatusPill> },
                      { key: "ts", header: "When", render: (row) => <span className="mono dim">{formatRelative(row.ts)}</span> },
                    ]}
                    rows={[
                      { id: "evt_1", kind: "settled", ts: new Date().toISOString() },
                      { id: "evt_2", kind: "parked", ts: new Date().toISOString() },
                    ]}
                  />
                  <TableSkeleton columns={4} rows={3} />
                  <JsonViewer value={SAMPLE_JSON} title="Sample claim payload" />
                  <Sparkline values={[1, 2, 1, 3, 4, 3, 5, 6, 5, 8]} tone="accent" />
                  <Timeline entries={TIMELINE_SAMPLE} />
                </Stack>
              </TabPanel>
              <TabPanel activeKey={tab} tabKey="feedback">
                <Cluster gap={3}>
                  <EmptyState title="Empty" detail="Nothing to show yet." />
                  <ErrorState
                    title="Couldn't fetch"
                    detail="The API is offline. Retry?"
                    action={<AsyncButton onClick={() => fakeWork("Retried")}>Retry</AsyncButton>}
                  />
                  <Stack gap={1}>
                    <Skeleton width={120} />
                    <Skeleton width={200} />
                    <Skeleton block height={60} />
                  </Stack>
                </Cluster>
              </TabPanel>
              <TabPanel activeKey={tab} tabKey="overlays">
                <Cluster gap={2}>
                  <Button onClick={() => setDrawerOpen(true)}>Open drawer</Button>
                  <Button onClick={() => setModalOpen(true)}>Open modal</Button>
                </Cluster>
                <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)} title="Drawer example">
                  <Stack gap={3}>
                    <p className="muted">A right-anchored detail pane. Used by the Inspector for actions like editing an approval.</p>
                    <CodeBlock>{`POST /commands/edit\n{ "instance_id": "...", "run_id": "...", "actor": "operator" }`}</CodeBlock>
                  </Stack>
                </Drawer>
                <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Confirm">
                  <p className="muted">This is the modal variant. Used for one-shot confirmations.</p>
                </Modal>
              </TabPanel>
            </CardBody>
            <CardFooter>
              <Button variant="ghost" onClick={() => toast.clear()}>Clear toasts</Button>
              <Button variant="primary" onClick={() => fakeWork("Test toast")}>Trigger toast</Button>
            </CardFooter>
          </Card>
        </Section>

        <Section title="Color tokens" eyebrow="Theme" density="compact">
          <Cluster gap={2}>
            {[
              { name: "background-base", cls: "ax-swatch ax-swatch--base" },
              { name: "background-raised", cls: "ax-swatch ax-swatch--raised" },
              { name: "background-overlay", cls: "ax-swatch ax-swatch--overlay" },
              { name: "accent", cls: "ax-swatch ax-swatch--accent" },
              { name: "success", cls: "ax-swatch ax-swatch--good" },
              { name: "warning", cls: "ax-swatch ax-swatch--warn" },
              { name: "destructive", cls: "ax-swatch ax-swatch--hot" },
              { name: "info", cls: "ax-swatch ax-swatch--info" },
            ].map((swatch) => (
              <Stack key={swatch.name} gap={1} align="center">
                <span className={swatch.cls} />
                <span className="mono dim" style={{ fontSize: 10 }}>{swatch.name}</span>
              </Stack>
            ))}
          </Cluster>
        </Section>
      </Stack>
    </AppShell>
  );
}