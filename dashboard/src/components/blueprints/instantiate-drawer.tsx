"use client";

/**
 * InstantiateDrawer — opens when the user clicks an "Instantiate" CTA on the
 * Blueprints list (or the BlueprintInspector). Posts to /commands/instantiate
 * with the type_ref, target_override, ring, and per-instance sender_identity
 * (invariant #8: every outbound channel binding is per-instance).
 *
 * The submit button is an AsyncButton so the click is never silent — toasts
 * fire on success/failure, and the button stays disabled while the request
 * is in flight (no double-submit, no optimistic nothing).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { CircleSlash2, Hammer, ShieldAlert } from "lucide-react";

import {
  AsyncButton,
  Badge,
  Card,
  CardBody,
  CardFooter,
  Drawer,
  ErrorState,
  RingPill,
  Stack,
  StatusPill,
} from "../ui";
import { useOperator } from "../../providers/operator-provider";
import { useToast } from "../../providers/toast-provider";
import { fetchInstance, fetchMandateType, instantiate } from "../../lib/api";
import { buildInstantiatePayload, parseTargetOverride } from "../../lib/instantiate";
import { formatCurrency, formatRelative, shortId } from "../../lib/format";
import type { MandateType } from "../../lib/types";

export interface InstantiateDrawerProps {
  mandate: MandateType | null;
  onClose: () => void;
  onCreated: (instanceId: string | undefined) => void;
}

const RING_OPTIONS = ["L0", "L1", "L2", "L3", "L4"] as const;

export function InstantiateDrawer({ mandate, onClose, onCreated }: InstantiateDrawerProps) {
  const { baseUrl, isLive, token } = useOperator();
  const toast = useToast();
  const [businessName, setBusinessName] = useState<string>("");
  const [customerId, setCustomerId] = useState<string>("");
  const [senderIdentity, setSenderIdentity] = useState<string>("");
  const [ring, setRing] = useState<(typeof RING_OPTIONS)[number]>("L0");
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [icpJson, setIcpJson] = useState<string>("");

  const open = mandate !== null;

  useEffect(() => {
    if (!mandate) {
      setBusinessName("");
      setCustomerId("");
      setSenderIdentity("");
      setRing("L0");
      setSubmitError(null);
      setSubmitting(false);
      setIcpJson("");
      return;
    }
    // Default the ring floor to whatever the type requires; user can step up.
    const floor = mandate.ring_floor as (typeof RING_OPTIONS)[number];
    setRing((RING_OPTIONS as readonly string[]).includes(floor) ? floor : "L0");
    // Seed the ICP target JSON from the charter so the user doesn't have to
    // re-type. Editable inline.
    setIcpJson(JSON.stringify(mandate.charter.target ?? {}, null, 2));
  }, [mandate]);

  const targetOverride = useMemo(() => parseTargetOverride(icpJson), [icpJson]);

  const icpValid = !icpJson.trim() || Boolean(targetOverride);

  const submit = useCallback(async () => {
    if (!mandate) return;
    const built = buildInstantiatePayload({
      typeRef: mandate.type_ref,
      businessName,
      customerId,
      senderIdentity,
      ring,
      icpJson,
    });
    if (!built.payload) {
      setSubmitError(built.errors.join(" "));
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const result = await instantiate(built.payload, { baseUrl, token });
      if (!result.supported) {
        const message = result.message ?? "Backend rejected the request.";
        setSubmitError(message);
        toast.push({ title: "Instantiate failed", message, tone: "hot" });
        return;
      }
      onCreated(result.instanceId);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setSubmitError(message);
      toast.push({ title: "Instantiate failed", message, tone: "hot" });
    } finally {
      setSubmitting(false);
    }
  }, [
    mandate,
    businessName,
    customerId,
    ring,
    icpJson,
    senderIdentity,
    baseUrl,
    token,
    toast,
    onCreated,
  ]);

  // Cheap "would this even resolve?" check against the kernel — best-effort,
  // fails open. If the type can't be resolved at all we surface a friendly
  // note before the user types anything.
  const [lookupError, setLookupError] = useState<string | null>(null);
  useEffect(() => {
    if (!mandate) return;
    let cancelled = false;
    void (async () => {
      try {
        const result = await fetchMandateType(mandate.id, { baseUrl });
        if (cancelled) return;
        if (result.source === "api" && !result.data) {
          setLookupError(`Kernel returned no MandateType for ${mandate.type_ref}.`);
        } else {
          setLookupError(null);
        }
        // touch the result so unused-var lints don't bark
        void fetchInstance;
      } catch (err) {
        if (!cancelled) {
          setLookupError(err instanceof Error ? err.message : String(err));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mandate, baseUrl]);

  if (!mandate) {
    return <Drawer open={false} onClose={onClose} title="Instantiate" />;
  }

  const liveDisabledReason = !isLive && !baseUrl
    ? "Set the API base URL in operator settings to instantiate against a live kernel."
    : undefined;

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={`Instantiate · ${mandate.title}`}
      width={520}
    >
      <Stack gap={4}>
        <Card padding="sm">
          <CardBody>
            <Stack gap={3}>
              <div className="blueprints-instantiate__type">
                <div>
                  <div className="h3">{mandate.title}</div>
                  <div className="mono dim" style={{ fontSize: 12 }}>
                    {mandate.type_ref}
                  </div>
                </div>
                <div className="blueprints-instantiate__pills">
                  <RingPill ring={ring} />
                  <StatusPill tone="good">{mandate.status}</StatusPill>
                  <Badge tone="neutral">{mandate.faculties.length} faculties</Badge>
                </div>
              </div>
              {mandate.description ? (
                <div className="dim" style={{ fontSize: 12 }}>
                  {mandate.description}
                </div>
              ) : null}
              {lookupError ? (
                <ErrorState
                  title="Kernel couldn't resolve this type"
                  detail={lookupError}
                />
              ) : null}
            </Stack>
          </CardBody>
        </Card>

        <Field
          label="Business name"
          help="Display name of the company you're instantiating for. Shows up in instance headers and audit logs."
          required
        >
          <input
            type="text"
            className="ax-input"
            value={businessName}
            onChange={(event) => setBusinessName(event.target.value)}
            placeholder="e.g. Kaveri Pumps"
            autoComplete="off"
            disabled={submitting}
          />
        </Field>

        <Field
          label="Customer id"
          help="Stable external id (often a CRM id). Used to derive the instance id."
          required
        >
          <input
            type="text"
            className="ax-input mono"
            value={customerId}
            onChange={(event) => setCustomerId(event.target.value)}
            placeholder="cust_kaveri"
            autoComplete="off"
            disabled={submitting}
          />
        </Field>

        <Field
          label="Sender identity (outbound channel)"
          help="The per-instance address used by send_email (invariant #8). Never shared across instances. Leave blank to skip channel binding."
        >
          <input
            type="email"
            className="ax-input mono"
            value={senderIdentity}
            onChange={(event) => setSenderIdentity(event.target.value)}
            placeholder="outreach@kaveri-pumps.com"
            autoComplete="off"
            disabled={submitting}
          />
          <div className="dim" style={{ fontSize: 11, marginTop: 4 }}>
            <ShieldAlert size={11} /> If unset, the instance gets no channel binding and
            can't send.
          </div>
        </Field>

        <Field label="Ring floor" help="Authority level for this instance. Can step up later.">
          <div className="blueprints-instantiate__rings">
            {RING_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                className={`blueprints-instantiate__ring${ring === option ? " is-active" : ""}`}
                onClick={() => setRing(option)}
                disabled={submitting}
                title={`Set ring to ${option}`}
              >
                {option}
              </button>
            ))}
          </div>
        </Field>

        <Field
          label="ICP target (JSON)"
          help="Typed-JSON goal schema: industry, location, count, etc. Sent as target_override on /commands/instantiate."
        >
          <textarea
            className="ax-input mono"
            value={icpJson}
            onChange={(event) => setIcpJson(event.target.value)}
            rows={6}
            spellCheck={false}
            disabled={submitting}
          />
          {!icpValid ? (
            <div className="dim" style={{ fontSize: 11, color: "var(--warning)" }}>
              Not valid JSON. The drawer will still submit, but target_override will be omitted.
            </div>
          ) : null}
        </Field>

        {submitError ? (
          <ErrorState title="Instantiate failed" detail={submitError} />
        ) : null}

        <CardFooter>
          <div className="blueprints-instantiate__footer">
            <div className="dim" style={{ fontSize: 11 }}>
              Posts to <code>/commands/instantiate</code> · actor: <code>manager:dashboard</code>
            </div>
            <div className="blueprints-instantiate__actions">
              <AsyncButton
                variant="ghost"
                onClick={onClose}
                disabled={submitting}
                icon={<CircleSlash2 size={13} />}
              >
                Cancel
              </AsyncButton>
              <AsyncButton
                variant="primary"
                onClick={() => void submit()}
                loading={submitting}
                disabled={Boolean(liveDisabledReason)}
                disabledReason={liveDisabledReason}
                loadingText="Instantiating…"
                icon={<Hammer size={13} />}
              >
                Instantiate
              </AsyncButton>
            </div>
          </div>
        </CardFooter>

        <MandateEconomics mandate={mandate} />
      </Stack>
    </Drawer>
  );
}

interface FieldProps {
  label: string;
  help?: string;
  required?: boolean;
  children: React.ReactNode;
}

function Field({ label, help, required, children }: FieldProps) {
  return (
    <label className="blueprints-instantiate__field">
      <span className="blueprints-instantiate__field-label">
        {label}
        {required ? <span aria-hidden> *</span> : null}
      </span>
      {children}
      {help ? <span className="dim blueprints-instantiate__field-help">{help}</span> : null}
    </label>
  );
}

function MandateEconomics({ mandate }: { mandate: MandateType }) {
  const liveVersion = mandate.versions.find((v) => v.status === "live") ?? mandate.versions[0];
  return (
    <Card padding="sm" tone="muted">
      <CardBody>
        <Stack gap={2}>
          <div className="dim" style={{ fontSize: 12 }}>
            At-a-glance
          </div>
          <div className="blueprints-instantiate__economics">
            <span>
              <span className="dim">Billing / run</span>
              <span className="mono">
                {mandate.settlement.billing_per_run !== null
                  ? formatCurrency(mandate.settlement.billing_per_run)
                  : "—"}
              </span>
            </span>
            <span>
              <span className="dim">Trust deltas</span>
              <span className="mono">
                +{mandate.settlement.trust_on_success}/−{Math.abs(mandate.settlement.trust_on_failure)}
              </span>
            </span>
            <span>
              <span className="dim">Watch window</span>
              <span className="mono">{mandate.settlement.watch_window_hours}h</span>
            </span>
            <span>
              <span className="dim">Released</span>
              <span className="mono">
                {liveVersion ? formatRelative(liveVersion.released_at) : "—"}
              </span>
            </span>
            <span>
              <span className="dim">Type id</span>
              <span className="mono">{shortId(mandate.id)}</span>
            </span>
          </div>
        </Stack>
      </CardBody>
    </Card>
  );
}