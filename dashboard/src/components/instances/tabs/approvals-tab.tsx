"use client";

/**
 * Approvals tab — this instance's parked cards (inline approve / reject).
 *
 * C7 ships the full approve/reject/edit + diff surface; this tab is the
 * instance-scoped view of the same data so the founder can clear the
 * approval gate from the Inspector without leaving the mandate context.
 *
 * Approve / reject are wired through the existing `approveCommand` /
 * `rejectCommand` helpers (already in the dashboard's API client); we
 * reuse them here so the path matches the C1 approval inbox.
 */

import { useCallback, useEffect, useState } from "react";
import { Check, Inbox, ShieldAlert, X } from "lucide-react";

import {
  AsyncButton,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  Row,
  Skeleton,
  Stack,
  StatusPill,
  Timeline,
} from "../../ui";
import {
  approveCommand,
  fetchApprovals,
  rejectCommand,
} from "../../../lib/api";
import { useOperator } from "../../../providers/operator-provider";
import { useToast } from "../../../providers/toast-provider";
import { formatRelative, runStateTone } from "../../../lib/format";
import type { ApprovalCard } from "../../../lib/types";
import type { TimelineEntry } from "../../ui/timeline";

interface ApprovalsTabProps {
  instanceId: string;
  initialApprovals?: ApprovalCard[];
  loading?: boolean;
  onAfterCommand?: () => void;
}

export function ApprovalsTab({
  instanceId,
  initialApprovals,
  loading,
  onAfterCommand,
}: ApprovalsTabProps) {
  const { token, actor, isLive } = useOperator();
  const toast = useToast();
  const [approvals, setApprovals] = useState<ApprovalCard[] | null>(initialApprovals ?? null);
  const [error, setError] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await fetchApprovals({ instance_id: instanceId });
      setApprovals(result.data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [instanceId]);

  useEffect(() => {
    if (initialApprovals) return;
    void load();
  }, [initialApprovals, load]);

  const list = approvals ?? [];

  async function handleApprove(card: ApprovalCard) {
    if (!token) {
      toast.push({
        title: "Set operator token",
        message: "Approve is a write — wire the bearer token in Connect.",
        tone: "warn",
      });
      return;
    }
    setBusyKey(`${card.run_id}:approve`);
    const result = await approveCommand({
      instance_id: card.instance_id,
      run_id: card.run_id,
      actor: actor || "operator",
    });
    setBusyKey(null);
    if (result.supported) {
      toast.push({
        title: "Approved",
        message: `run ${card.run_id} resumed`,
        tone: "good",
      });
      onAfterCommand?.();
      void load();
    } else {
      toast.push({
        title: "Approve failed",
        message: result.message ?? "Unknown error",
        tone: "hot",
      });
    }
  }

  async function handleReject(card: ApprovalCard) {
    if (!token) {
      toast.push({
        title: "Set operator token",
        message: "Reject is a write — wire the bearer token in Connect.",
        tone: "warn",
      });
      return;
    }
    setBusyKey(`${card.run_id}:reject`);
    const result = await rejectCommand({
      instance_id: card.instance_id,
      run_id: card.run_id,
      actor: actor || "operator",
    });
    setBusyKey(null);
    if (result.supported) {
      toast.push({
        title: "Rejected",
        message: `run ${card.run_id} closed`,
        tone: "good",
      });
      onAfterCommand?.();
      void load();
    } else {
      toast.push({
        title: "Reject failed",
        message: result.message ?? "Unknown error",
        tone: "hot",
      });
    }
  }

  return (
    <Card>
      <CardHeader
        eyebrow="Approvals"
        title={
          list.length === 0
            ? "Nothing parked here"
            : `${list.length} parked card${list.length === 1 ? "" : "s"}`
        }
        subtitle={
          list.length === 0
            ? "When this instance's runs reach the L0/L1 gate, they queue here for your sign-off."
            : "Approve to resume into the gated send; reject to close."
        }
        action={
          <StatusPill tone={list.length > 0 ? "warn" : "muted"} dot={list.length > 0}>
            <ShieldAlert size={11} /> gate
          </StatusPill>
        }
      />
      <CardBody>
        {error ? (
          <ErrorState
            title="Couldn't load approvals"
            detail={error}
            action={
              <button
                type="button"
                className="ax-btn ax-btn--secondary"
                onClick={() => void load()}
              >
                Retry
              </button>
            }
          />
        ) : loading || approvals === null ? (
          <Stack gap={2}>
            <Skeleton width="80%" />
            <Skeleton width="60%" />
            <Skeleton width="70%" />
          </Stack>
        ) : list.length === 0 ? (
          <EmptyState
            icon={<Inbox size={20} />}
            title="No parked approvals"
            detail="The L0/L1 gate is clear for this instance."
          />
        ) : (
          <Stack gap={3}>
            {list.map((card) => {
              const drafted = (card.drafted_effect ?? {}) as Record<string, unknown>;
              const syscall = typeof drafted.syscall === "string" ? drafted.syscall : "—";
              const args = (drafted.args ?? {}) as Record<string, unknown>;
              const busy = busyKey === `${card.run_id}:approve` || busyKey === `${card.run_id}:reject`;
              return (
                <Card key={`${card.run_id}-${card.seq}`} tone="raised" padding="sm">
                  <CardBody>
                    <Stack gap={3}>
                      <Row gap={3} wrap justify="between" align="start">
                        <Stack gap={1}>
                          <div className="inspector-approval__reason">{card.reason || "Awaiting your decision"}</div>
                          <Row gap={2} wrap>
                            <StatusPill tone="muted" size="sm" title={`run ${card.run_id}`}>
                              run {card.run_id}
                            </StatusPill>
                            <StatusPill tone="info" size="sm">
                              syscall · {syscall}
                            </StatusPill>
                            {card.required_ring ? (
                              <StatusPill tone="warn" size="sm">
                                required · {card.required_ring}
                              </StatusPill>
                            ) : null}
                            <span className="dim mono" style={{ fontSize: 12 }}>
                              {formatRelative(card.timeline?.[0]?.ts)}
                            </span>
                          </Row>
                        </Stack>
                        <Row gap={2} wrap>
                          <AsyncButton
                            variant="success"
                            size="sm"
                            icon={<Check size={12} />}
                            onClick={() => void handleApprove(card)}
                            loading={busyKey === `${card.run_id}:approve`}
                            disabled={!isLive || busy}
                            disabledReason={
                              !isLive
                                ? "Set the API base URL + operator token to approve."
                                : undefined
                            }
                          >
                            Approve
                          </AsyncButton>
                          <AsyncButton
                            variant="danger"
                            size="sm"
                            icon={<X size={12} />}
                            onClick={() => void handleReject(card)}
                            loading={busyKey === `${card.run_id}:reject`}
                            disabled={!isLive || busy}
                            disabledReason={
                              !isLive
                                ? "Set the API base URL + operator token to reject."
                                : undefined
                            }
                          >
                            Reject
                          </AsyncButton>
                        </Row>
                      </Row>
                      {Object.keys(args).length > 0 ? (
                        <details className="inspector-approval__args">
                          <summary className="dim">drafted args ({Object.keys(args).length})</summary>
                          <pre className="mono">{JSON.stringify(args, null, 2)}</pre>
                        </details>
                      ) : null}
                      {card.timeline && card.timeline.length > 0 ? (
                        <Timeline
                          entries={card.timeline.map(
                            (entry): TimelineEntry => ({
                              id: `${card.run_id}-${entry.ts}-${entry.kind}`,
                              title: entry.summary,
                              detail: typeof entry.event === "object" && entry.event !== null
                                ? JSON.stringify(entry.event)
                                : "",
                              tone: runStateTone(String(entry.kind)) as TimelineEntry["tone"],
                              ts: entry.ts,
                            }),
                          )}
                        />
                      ) : null}
                    </Stack>
                  </CardBody>
                </Card>
              );
            })}
          </Stack>
        )}
      </CardBody>
    </Card>
  );
}
