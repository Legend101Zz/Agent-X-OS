"use client";

/**
 * InspectorHeader — the persistent header on `/instances/{id}`.
 *
 * Per BLUEPRINT §6 / the C2 spec it surfaces, in this order:
 *   name · customer/business · type_ref · ring + trust · channel binding ·
 *   live run state · P&L summary
 *
 * The header is the "what is this thing right now" surface. Tabs underneath
 * dive into the why and how (Overview, Live Activity, Runs, Approvals, Trust).
 */

import { useState } from "react";
import { Check, CircleSlash2, Mail, Pause, Play, ShieldCheck } from "lucide-react";

import {
  AsyncButton,
  Card,
  CardBody,
  RingPill,
  Row,
  Stack,
  StatusPill,
} from "../ui";
import {
  formatCurrency,
  formatRelative,
  runStateLabel,
  runStateTone,
  shortId,
} from "../../lib/format";
import { useOperator } from "../../providers/operator-provider";
import { useToast } from "../../providers/toast-provider";
import type { InstanceSummary, RunSummary } from "../../lib/types";
import { setRingCommand } from "../../lib/api";

interface InspectorHeaderProps {
  instance: InstanceSummary;
  /** The "currently-featured" run (most interesting: active > parked > recent). */
  featuredRun: RunSummary | null;
  /** Optional live-update pulse to draw the eye when something just changed. */
  livePulseKey?: string;
  /** When the parent refetches, surface a brief non-blocking pulse. */
  isRefreshing?: boolean;
  onAfterCommand?: () => void;
}

const CHANNEL_ICON: Record<string, React.ReactNode> = {
  email: <Mail size={14} />,
  manual: <CircleSlash2 size={14} />,
  kernel: <CircleSlash2 size={14} />,
};

export function InspectorHeader({
  instance,
  featuredRun,
  livePulseKey,
  isRefreshing,
  onAfterCommand,
}: InspectorHeaderProps) {
  const { token, actor, isLive } = useOperator();
  const toast = useToast();
  const [ringState, setRingState] = useState<"idle" | "submitting" | "ok" | "error">("idle");
  const [ringMessage, setRingMessage] = useState<string | null>(null);

  async function handleSetRing(nextRing: string) {
    if (!token) {
      toast.push({
        title: "Set operator token first",
        message: "Open Connect in the top bar to wire the bearer token.",
        tone: "warn",
      });
      return;
    }
    setRingState("submitting");
    setRingMessage(null);
    const result = await setRingCommand({
      instance_id: instance.id,
      ring: nextRing,
      actor: actor || "operator",
    });
    if (result.supported) {
      setRingState("ok");
      setRingMessage(`ring → ${nextRing}`);
      toast.push({
        title: "Ring updated",
        message: `${instance.name} → ${nextRing}`,
        tone: "good",
      });
      onAfterCommand?.();
    } else {
      setRingState("error");
      setRingMessage(result.message ?? "ring update failed");
      toast.push({
        title: "Ring update failed",
        message: result.message ?? "Unknown error",
        tone: "hot",
      });
    }
  }

  // The "channel binding" for now is the most-recent thread's channel.
  // A real ChannelBinding object will arrive via the kernel contract soon;
  // we surface what the existing data has.
  const channelBinding = pickChannelBinding(instance);

  return (
    <Card
      tone="raised"
      padding="md"
      className={`inspector-header${livePulseKey ? " ax-live-pulse" : ""}`}
    >
      <CardBody>
        <Stack gap={4}>
          <Row gap={4} wrap align="start" justify="between">
            <Stack gap={1}>
              <div className="inspector-header__crumbs">
                <span className="dim mono">inst</span>
                <span className="dim mono">/</span>
                <span className="mono">{shortId(instance.id, 16)}</span>
              </div>
              <div className="inspector-header__name">
                <h1 className="h1">{instance.name}</h1>
                <span className="inspector-header__customer dim">
                  {instance.business}
                </span>
              </div>
              <div className="inspector-header__type">
                <span className="ax-tab-panel__eyebrow">type_ref</span>
                <code className="mono">{instance.mandate_type ?? "—"}</code>
              </div>
            </Stack>

            <Stack gap={2} className="inspector-header__pills">
              <Row gap={2} wrap>
                <RingPill ring={instance.ring} />
                <StatusPill tone="info" dot title="Trust score">
                  <ShieldCheck size={11} /> trust {instance.trust_score.toFixed(2)}
                </StatusPill>
                {featuredRun ? (
                  <StatusPill
                    tone={runStateTone(featuredRun.state)}
                    dot={featuredRun.state === "active"}
                    pulse={featuredRun.state === "active"}
                    title={`Run ${featuredRun.id} · ${featuredRun.syscall}`}
                  >
                    {featuredRun.state === "active" ? (
                      <Play size={11} />
                    ) : featuredRun.state === "parked" || featuredRun.state === "waiting_approval" ? (
                      <Pause size={11} />
                    ) : null}
                    {runStateLabel(featuredRun.state)} · {featuredRun.title}
                  </StatusPill>
                ) : (
                  <StatusPill tone="muted">no live run</StatusPill>
                )}
              </Row>
              {channelBinding ? (
                <div className="inspector-header__channel">
                  <span className="ax-tab-panel__eyebrow">channel binding</span>
                  <StatusPill tone="accent">
                    {CHANNEL_ICON[channelBinding.channel] ?? <CircleSlash2 size={11} />}
                    {channelBinding.label}
                  </StatusPill>
                </div>
              ) : null}
            </Stack>
          </Row>

          <div className="inspector-header__pnl" data-testid="pnl-summary">
            <PnLStat
              label="Revenue (period)"
              value={formatCurrency(instance.pnl.revenue)}
            />
            <PnLStat
              label="Cost (period)"
              value={formatCurrency(instance.pnl.cost)}
            />
            <PnLStat
              label="Margin"
              value={formatCurrency(instance.pnl.margin)}
              emphasis
            />
            <PnLStat
              label="Facts on file"
              value={String(instance.facts.length)}
            />
            <PnLStat
              label="Updated"
              value={formatRelative(instance.facts[0]?.committed_at ?? null)}
            />
          </div>

          <div className="inspector-header__ring-row">
            <span className="ax-tab-panel__eyebrow">set ring</span>
            <Row gap={2} wrap>
              {["L0", "L1", "L2"].map((ring) => (
                <AsyncButton
                  key={ring}
                  variant={ring === instance.ring ? "primary" : "secondary"}
                  size="sm"
                  icon={
                    ring === instance.ring ? (
                      <Check size={12} />
                    ) : (
                      <ShieldCheck size={12} />
                    )
                  }
                  onClick={() => void handleSetRing(ring)}
                  loading={ringState === "submitting"}
                  disabled={!isLive || ring === instance.ring || isRefreshing}
                  disabledReason={
                    !isLive
                      ? "Set the API base URL + operator token to change ring."
                      : ring === instance.ring
                        ? "Current ring."
                        : undefined
                  }
                >
                  {ring}
                </AsyncButton>
              ))}
              {ringMessage ? (
                <span
                  className={`inspector-header__ring-msg tone-${ringState}`}
                  role="status"
                >
                  {ringMessage}
                </span>
              ) : null}
            </Row>
          </div>
        </Stack>
      </CardBody>
    </Card>
  );
}

interface PnLStatProps {
  label: string;
  value: string;
  emphasis?: boolean;
}

function PnLStat({ label, value, emphasis }: PnLStatProps) {
  return (
    <div
      className={`inspector-header__pnl-stat${emphasis ? " inspector-header__pnl-stat--emphasis" : ""}`}
    >
      <div className="ax-tab-panel__eyebrow">{label}</div>
      <div className="inspector-header__pnl-value mono">{value}</div>
    </div>
  );
}

interface ChannelBindingLite {
  channel: string;
  label: string;
}

/**
 * Best-effort ChannelBinding inference. The kernel contract is still being
 * finalised; until it lands we surface the most-recent thread channel + a
 * stable label like "email · 2 threads" so the slot isn't blank.
 */
function pickChannelBinding(instance: InstanceSummary): ChannelBindingLite | null {
  const channels = new Map<string, number>();
  for (const thread of instance.threads ?? []) {
    if (!thread.channel) continue;
    channels.set(thread.channel, (channels.get(thread.channel) ?? 0) + 1);
  }
  if (channels.size === 0) return null;
  // Prefer email, then manual, then anything else.
  const order = ["email", "manual", "kernel", "sms", "voice"];
  const sorted = [...channels.entries()].sort(
    (a, b) =>
      (order.indexOf(a[0]) === -1 ? 999 : order.indexOf(a[0])) -
      (order.indexOf(b[0]) === -1 ? 999 : order.indexOf(b[0])) ||
      b[1] - a[1],
  );
  const [channel, count] = sorted[0];
  return {
    channel,
    label: `${channel}${count > 1 ? ` · ${count} threads` : ""}`,
  };
}
