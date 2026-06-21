"use client";

/**
 * C12 — Providers / Connectors view (BLUEPRINT §5 row "Providers").
 *
 * Consumes the C11-extended `GET /capabilities` payload (provider reachability,
 * transport configured, model routing) and renders three sections:
 *
 *   1. Research providers    — Exa + Firecrawl, with reachability + credential
 *                              pills per row.
 *   2. Outbound email        — the configured transport (SMTP / Resend / none),
 *                              its non-secret details (host, port, from), and
 *                              the live-send gate (`RUN_LIVE_EMAIL`).
 *   3. Model routing         — the faculty model (Minimax OpenAI-compat) and
 *                              the judge model (OpenRouter) with the slugs +
 *                              base URL the kernel actually uses.
 *
 * Every command button uses `AsyncButton` (spinner + toast). The view handles
 * loading / empty / error gracefully and degrades to fixtures when the API is
 * unreachable (the existing `fetchJson` contract). No faked success states.
 *
 * Graceful disable: when `feature_flags.capability_health !== "live"`, the
 * view shows a "wip" banner and disables refresh/controls. The data still
 * loads — it just gets surfaced with explicit "fixture / wip" pills so the
 * operator can see what would render once the backend is wired.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Check,
  CircleSlash2,
  Cog,
  Cpu,
  Globe,
  KeyRound,
  Mail,
  RefreshCcw,
  ShieldCheck,
  Sparkles,
  Wand2,
  X,
} from "lucide-react";

import {
  AsyncButton,
  Card,
  CardBody,
  CardHeader,
  Cluster,
  EmptyState,
  ErrorState,
  Row,
  Stack,
  StatusPill,
  Table,
  TableSkeleton,
} from "../ui";
import { JsonViewer } from "../ui/json";
import { useToast } from "../../providers/toast-provider";
import { useFeature } from "../../providers/feature-provider";
import { useOperator } from "../../providers/operator-provider";
import { fetchCapabilitiesForProviders } from "../../lib/api";
import {
  formatRelative,
  formatTime,
  healthTone,
} from "../../lib/format";
import type {
  CapabilitiesWithHealth,
  ModelRoutingStatus,
  ProviderReachability,
  TransportStatus,
} from "../../lib/types";

const POLL_INTERVAL_MS = 15_000;

const EMPTY_PROVIDERS_DATA: CapabilitiesWithHealth = {
  capabilities: [],
  providers: [],
  transport: { configured: false, name: null, live_gated: false, details: {} },
  model_routing: {
    faculty_model: { configured: false },
    judge_model: { configured: false },
    checked_at: new Date(0).toISOString(),
  },
};

function reachabilityPillTone(
  row: ProviderReachability,
): "good" | "warn" | "hot" | "muted" {
  if (!row.configured) return "muted";
  if (row.reachable) return "good";
  return "hot";
}

function reachabilityLabel(row: ProviderReachability): string {
  if (!row.configured) return "credential missing";
  if (row.reachable) return "reachable";
  if (row.error) return "unreachable";
  return "configured · probe failed";
}

function transportTone(transport: TransportStatus): "good" | "warn" | "hot" | "muted" {
  if (!transport.configured) return "muted";
  if (transport.live_gated) return "good";
  return "warn";
}

function transportLabel(transport: TransportStatus): string {
  if (!transport.configured) return "no transport configured";
  if (transport.live_gated) return "live · sends enabled";
  return "configured · RUN_LIVE_EMAIL=0";
}

function modelConfiguredTone(configured: boolean): "good" | "hot" {
  return configured ? "good" : "hot";
}

function describeModelId(id: string | undefined): string {
  if (!id) return "—";
  // Strip the leading "provider/" if present so the operator sees the bare slug.
  const idx = id.indexOf("/");
  return idx >= 0 && idx < id.length - 1 ? id.slice(idx + 1) : id;
}

export function ProvidersView() {
  const toast = useToast();
  const { baseUrl, token } = useOperator();
  const { status: capHealthStatus } = useFeature("capability_health");
  const capHealthLive = capHealthStatus === "live";

  const [data, setData] = useState<CapabilitiesWithHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<"api" | "fixture" | null>(null);

  const load = useCallback(
    async (mode: "initial" | "refresh" = "initial") => {
      if (mode === "refresh") setRefreshing(true);
      try {
        const result = await fetchCapabilitiesForProviders({
          baseUrl,
          token,
        });
        setData(result.data);
        setError(result.error ?? null);
        setSource(result.source);
        if (mode === "refresh" && result.source === "fixture" && result.error) {
          toast.push({
            title: "Showing fixture provider data",
            message: result.error,
            tone: "hot",
          });
        } else if (mode === "refresh" && result.source === "api") {
          toast.push({
            title: "Providers refreshed",
            tone: "good",
          });
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
        if (mode === "refresh") {
          toast.push({ title: "Refresh failed", message, tone: "hot" });
        }
      } finally {
        if (mode === "initial") setLoading(false);
        setRefreshing(false);
      }
    },
    [baseUrl, token, toast],
  );

  useEffect(() => {
    void load("initial");
  }, [load]);

  // Light polling — the diagnostics don't move often but the operator wants
  // them fresh after a config change. 15s is a sensible default; the Refresh
  // button gives an immediate path.
  useEffect(() => {
    if (!capHealthLive) return;
    const id = setInterval(() => void load("refresh"), POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [capHealthLive, load]);

  const summary = useMemo(() => summariseProviders(data ?? EMPTY_PROVIDERS_DATA), [data]);

  return (
    <Stack gap={5}>
      <Card>
        <CardHeader
          eyebrow="Providers / connectors"
          title="Adapters, transports, and model routing"
          subtitle={
            "Every external system the kernel depends on — research providers, outbound email, and the LLM routing the kernel + judge use. " +
            "Health and credential pills are sourced from the C11 /capabilities extension; the page degrades to fixtures when the API is unreachable."
          }
          action={
            <Cluster gap={2} align="center">
              <StatusPill
                tone={
                  source === "fixture"
                    ? "warn"
                    : source === "api"
                      ? "good"
                      : "muted"
                }
                dot
              >
                {source === "fixture" ? "fixture" : source === "api" ? "api" : "—"}
              </StatusPill>
              <StatusPill tone={capHealthLive ? "good" : "warn"} dot>
                {capHealthLive ? "capability_health: live" : "capability_health: wip"}
              </StatusPill>
              <AsyncButton
                variant="secondary"
                size="sm"
                icon={<RefreshCcw size={14} />}
                onClick={() => void load("refresh")}
                loading={refreshing}
              >
                Refresh
              </AsyncButton>
            </Cluster>
          }
        />
        <CardBody>
          <SummaryStrip summary={summary} checkedAt={data?.model_routing.checked_at} />
        </CardBody>
      </Card>

      {!capHealthLive ? (
        <Card tone="muted">
          <CardBody>
            <Stack gap={2}>
              <Cluster gap={2} align="center">
                <Wand2 size={14} />
                <strong>Capability health detail is in wip</strong>
              </Cluster>
              <span className="dim">
                The backend extension that powers the providers/transport/model_routing sections
                (C11) is not yet live. The data below is sourced from fixtures; once C11 lands the
                view reads from <code className="mono">GET /capabilities</code> and refreshes
                automatically.
              </span>
            </Stack>
          </CardBody>
        </Card>
      ) : null}

      <Row gap={5} align="stretch" wrap>
        <ResearchProvidersCard
          rows={data?.providers ?? []}
          loading={loading && !data}
          error={error}
          onRetry={() => void load("refresh")}
        />
        <EmailTransportCard
          transport={data?.transport ?? EMPTY_PROVIDERS_DATA.transport}
          loading={loading && !data}
          error={error}
        />
      </Row>

      <ModelRoutingCard
        routing={data?.model_routing ?? EMPTY_PROVIDERS_DATA.model_routing}
        loading={loading && !data}
        error={error}
      />

      {error && !loading ? (
        <ErrorState
          title="Couldn't load provider details"
          detail={error}
          action={
            <AsyncButton variant="secondary" onClick={() => void load("refresh")}>
              Retry
            </AsyncButton>
          }
        />
      ) : null}
    </Stack>
  );
}

// =============================================================================
// Sub-components
// =============================================================================

interface ProvidersSummary {
  researchConfigured: number;
  researchReachable: number;
  transportConfigured: boolean;
  transportLive: boolean;
  facultyModelConfigured: boolean;
  judgeModelConfigured: boolean;
}

function summariseProviders(data: CapabilitiesWithHealth): ProvidersSummary {
  const research = data.providers.filter((row) => row.kind === "research");
  return {
    researchConfigured: research.filter((row) => row.configured).length,
    researchReachable: research.filter((row) => row.reachable).length,
    transportConfigured: data.transport.configured,
    transportLive: data.transport.configured && data.transport.live_gated,
    facultyModelConfigured: data.model_routing.faculty_model.configured === true,
    judgeModelConfigured: data.model_routing.judge_model.configured === true,
  };
}

function SummaryStrip({
  summary,
  checkedAt,
}: {
  summary: ProvidersSummary;
  checkedAt?: string;
}) {
  const tone: "good" | "warn" | "hot" =
    summary.researchReachable === summary.researchConfigured &&
    summary.transportConfigured &&
    summary.facultyModelConfigured &&
    summary.judgeModelConfigured
      ? "good"
      : summary.transportLive === false && summary.transportConfigured
        ? "warn"
        : summary.researchConfigured === 0 && !summary.transportConfigured
          ? "hot"
          : "warn";
  return (
    <Cluster gap={3} align="center">
      <StatusPill tone={tone} dot>
        {tone === "good"
          ? "all green"
          : tone === "warn"
            ? "partial"
            : "not wired"}
      </StatusPill>
      <span className="dim">
        Research {summary.researchReachable}/{summary.researchConfigured} reachable ·{" "}
        {summary.transportConfigured
          ? summary.transportLive
            ? "transport live"
            : "transport staged"
          : "no transport"}{" "}
        · faculty {summary.facultyModelConfigured ? "ok" : "missing"} · judge{" "}
        {summary.judgeModelConfigured ? "ok" : "missing"}
      </span>
      {checkedAt ? (
        <span className="dim mono" title={checkedAt}>
          checked {formatRelative(checkedAt)} · {formatTime(checkedAt)}
        </span>
      ) : null}
    </Cluster>
  );
}

function ResearchProvidersCard({
  rows,
  loading,
  error,
  onRetry,
}: {
  rows: ProviderReachability[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  return (
    <Card block className="providers-card">
      <CardHeader
        eyebrow="Research adapters"
        title="Exa · Firecrawl"
        subtitle="The research providers the kernel uses for lead-finder and other batch lookups. Each row shows whether the credential is present and whether the provider's own health probe reports it usable right now."
        action={
          <StatusPill tone="info" dot>
            {rows.length} configured
          </StatusPill>
        }
      />
      <CardBody>
        {loading ? (
          <TableSkeleton columns={3} rows={3} />
        ) : error && rows.length === 0 ? (
          <ErrorState
            title="Couldn't reach research providers"
            detail={error}
            action={
              <AsyncButton variant="secondary" onClick={onRetry}>
                Retry
              </AsyncButton>
            }
          />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={<Globe size={20} />}
            title="No research providers reported"
            detail="The /capabilities extension returned an empty providers array. Once C11 is live, this will list Exa + Firecrawl explicitly."
          />
        ) : (
          <Table
            columns={[
              {
                key: "name",
                header: "Provider",
                render: (row) => (
                  <Cluster gap={2} align="center">
                    <strong>{row.name}</strong>
                    <span className="dim mono">{row.kind}</span>
                  </Cluster>
                ),
              },
              {
                key: "credential",
                header: "Credential",
                render: (row) => (
                  <StatusPill tone={row.configured ? "good" : "hot"}>
                    <Cluster gap={1} align="center">
                      <KeyRound size={11} /> {row.configured ? "present" : "missing"}
                    </Cluster>
                  </StatusPill>
                ),
              },
              {
                key: "health",
                header: "Health",
                render: (row) => {
                  const tone = reachabilityPillTone(row);
                  return (
                    <Cluster gap={1} align="center">
                      <StatusPill tone={tone} dot>
                        {reachabilityLabel(row)}
                      </StatusPill>
                      {row.error ? (
                        <span className="dim mono" title={row.error}>
                          <AlertCircle size={11} /> {row.error}
                        </span>
                      ) : null}
                    </Cluster>
                  );
                },
              },
            ]}
            rows={rows}
            rowKey={(row) => row.name}
            density="compact"
          />
        )}
      </CardBody>
    </Card>
  );
}

function EmailTransportCard({
  transport,
  loading,
  error,
}: {
  transport: TransportStatus;
  loading: boolean;
  error: string | null;
}) {
  return (
    <Card block className="providers-card">
      <CardHeader
        eyebrow="Outbound email"
        title="Transport + live-send gate"
        subtitle="Which email transport the kernel registers (SMTP / Resend / none) and whether RUN_LIVE_EMAIL is on. Credentials never cross this seam — only the non-secret host / port / from shape."
        action={
          <StatusPill tone={transportTone(transport)} dot>
            {transportLabel(transport)}
          </StatusPill>
        }
      />
      <CardBody>
        {loading ? (
          <TableSkeleton columns={2} rows={4} />
        ) : error && !transport.configured ? (
          <ErrorState
            title="Couldn't read transport status"
            detail={error}
          />
        ) : !transport.configured ? (
          <EmptyState
            icon={<Mail size={20} />}
            title="No outbound transport configured"
            detail="The kernel will fall back to the human-task queue (invariant #5) until a transport is wired. Set SMTP_HOST + SMTP_USERNAME + SMTP_PASSWORD in .env to enable live send."
            action={
              <Cluster gap={2} align="center">
                <StatusPill tone="hot" dot>
                  stage-only
                </StatusPill>
                <span className="dim mono">RUN_LIVE_EMAIL={transport.live_gated ? "1" : "0"}</span>
              </Cluster>
            }
          />
        ) : (
          <Stack gap={3}>
            <Cluster gap={3} align="center">
              <StatusPill tone="accent">
                <Cog size={11} /> {transport.name ?? "transport"}
              </StatusPill>
              <StatusPill tone={transport.live_gated ? "good" : "warn"} dot>
                {transport.live_gated ? (
                  <Cluster gap={1} align="center">
                    <ShieldCheck size={11} /> live gate open
                  </Cluster>
                ) : (
                  <Cluster gap={1} align="center">
                    <X size={11} /> live gate closed
                  </Cluster>
                )}
              </StatusPill>
              <span className="dim mono">RUN_LIVE_EMAIL={transport.live_gated ? "1" : "0"}</span>
            </Cluster>

            <div className="providers-transport-grid">
              <TransportDetail label="Host" value={transport.details.host} mono />
              <TransportDetail label="Port" value={String(transport.details.port ?? "")} mono />
              <TransportDetail label="Username" value={transport.details.username} mono />
              <TransportDetail label="From address" value={transport.details.default_from} mono />
              <TransportDetail label="From name" value={transport.details.from_name} />
            </div>
          </Stack>
        )}
      </CardBody>
    </Card>
  );
}

function TransportDetail({
  label,
  value,
  mono,
}: {
  label: string;
  value: string | undefined;
  mono?: boolean;
}) {
  return (
    <div className="providers-transport-detail">
      <div className="providers-transport-detail__label dim">{label}</div>
      <div className={`providers-transport-detail__value${mono ? " mono" : ""}`}>
        {value && value.length > 0 ? value : "—"}
      </div>
    </div>
  );
}

function ModelRoutingCard({
  routing,
  loading,
  error,
}: {
  routing: ModelRoutingStatus;
  loading: boolean;
  error: string | null;
}) {
  return (
    <Card>
      <CardHeader
        eyebrow="Model routing"
        title="Faculty model · Judge model"
        subtitle="Which model the kernel uses to drive faculties (Hermes → Minimax OpenAI-compat) and which model the promptfoo judge uses for grading. Confirms the slugs match .env without grepping."
        action={
          <Cluster gap={2} align="center">
            <StatusPill
              tone={
                routing.faculty_model.configured && routing.judge_model.configured
                  ? "good"
                  : "warn"
              }
              dot
            >
              {routing.faculty_model.configured && routing.judge_model.configured
                ? "routing ok"
                : "partial"}
            </StatusPill>
            <span className="dim mono" title={routing.checked_at}>
              {routing.checked_at
                ? `checked ${formatRelative(routing.checked_at)}`
                : "—"}
            </span>
          </Cluster>
        }
      />
      <CardBody>
        {loading ? (
          <TableSkeleton columns={3} rows={2} />
        ) : error && !routing.faculty_model.configured && !routing.judge_model.configured ? (
          <ErrorState
            title="Couldn't read model routing"
            detail={error}
          />
        ) : (
          <div className="providers-routing-grid">
            <ModelRoutingEntry
              title="Faculty model"
              icon={<Sparkles size={14} />}
              configured={routing.faculty_model.configured}
              provider={routing.faculty_model.provider}
              modelId={routing.faculty_model.model_id}
              baseUrl={routing.faculty_model.base_url}
            />
            <ModelRoutingEntry
              title="Judge model"
              icon={<Cpu size={14} />}
              configured={routing.judge_model.configured}
              provider={routing.judge_model.via}
              modelId={routing.judge_model.model_id}
              baseUrl={routing.judge_model.base_url}
            />
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function ModelRoutingEntry({
  title,
  icon,
  configured,
  provider,
  modelId,
  baseUrl,
}: {
  title: string;
  icon: React.ReactNode;
  configured: boolean;
  provider?: string;
  modelId?: string;
  baseUrl?: string;
}) {
  return (
    <div className="providers-routing-entry" data-configured={configured}>
      <Cluster gap={2} align="center">
        {icon}
        <strong>{title}</strong>
        <StatusPill tone={modelConfiguredTone(configured)} dot>
          {configured ? (
            <Cluster gap={1} align="center">
              <Check size={11} /> configured
            </Cluster>
          ) : (
            <Cluster gap={1} align="center">
              <CircleSlash2 size={11} /> missing
            </Cluster>
          )}
        </StatusPill>
      </Cluster>
      <div className="providers-routing-entry__details">
        <div>
          <span className="dim">via</span>{" "}
          <span className="mono">{provider ?? "—"}</span>
        </div>
        <div>
          <span className="dim">model</span>{" "}
          <span className="mono" title={modelId}>
            {describeModelId(modelId)}
          </span>
        </div>
        {baseUrl ? (
          <div>
            <span className="dim">base url</span>{" "}
            <span className="mono">{baseUrl}</span>
          </div>
        ) : null}
      </div>
      {!configured ? (
        <div className="dim">
          The relevant API key or model id is not set; the kernel will fall back to the manual queue
          for any faculty that needs this model.
        </div>
      ) : null}
    </div>
  );
}

// re-export the JSON viewer so pages that embed the view inline can also
// expose the raw payload (helps when an operator wants to copy/paste a
// transport shape into a debug log).
export { JsonViewer };
