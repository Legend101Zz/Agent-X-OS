"use client";

/**
 * Generic stub for views that will be built by their dedicated cards (C2..C17).
 * Renders the AppShell + an EmptyState pointing at the responsible card.
 */
import Link from "next/link";
import { Construction } from "lucide-react";
import { AppShell } from "../../src/components/shell/app-shell";
import { Card, CardHeader, EmptyState, Stack, StatusPill, AsyncButton } from "../../src/components/ui";

export interface StubProps {
  title: string;
  cardId?: string;
  cardTitle?: string;
  owner?: string;
  blockedFeatures?: Array<{ key: string; label: string }>;
  description?: string;
}

export default function StubPage(props: StubProps) {
  return (
    <AppShell title={props.title} crumbs={[{ label: props.title }]}>
      <Stack gap={5}>
        <Card tone="muted">
          <CardHeader
            eyebrow="Under construction"
            title={props.title}
            subtitle={props.description ?? "This view ships with its dedicated Kanban card."}
            action={
              props.cardId ? (
                <StatusPill tone="info" dot>
                  {props.cardId}
                </StatusPill>
              ) : null
            }
          />
          {props.blockedFeatures?.length ? (
            <div>
              <div className="dim" style={{ fontSize: 12, marginBottom: 8 }}>GRACEFUL DISABLE — these surfaces wait for backend wiring:</div>
              <Stack gap={1}>
                {props.blockedFeatures.map((feat) => (
                  <div key={feat.key} className="ax-data-pair">
                    <span className="ax-data-pair__label">{feat.label}</span>
                    <span className="ax-data-pair__value">
                      <StatusPill tone="warn">wip</StatusPill>
                    </span>
                  </div>
                ))}
              </Stack>
            </div>
          ) : null}
        </Card>
        <EmptyState
          icon={<Construction size={20} />}
          title={`${props.title} — under construction`}
          detail={
            props.cardTitle ??
            "Once the responsible Kanban card lands, this view will render against the live API."
          }
          action={
            <Link href="/">
              <AsyncButton variant="secondary">Back to Mission Control</AsyncButton>
            </Link>
          }
        />
      </Stack>
    </AppShell>
  );
}