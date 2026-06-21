"use client";

/**
 * CreateMandateWizard — the guided path to creating a mandate instance.
 *
 * A friendlier sibling of InstantiateDrawer for first-time operators: it walks
 * through pick-blueprint → identity → charter/target → review, explaining each
 * concept with an InfoTip, then launches the instance. It shares the EXACT
 * submit path with the drawer (buildInstantiatePayload + instantiate), so both
 * produce identical /commands/instantiate calls — only the presentation differs.
 */

import { useEffect, useMemo, useState } from "react";

import { Wizard, InfoTip } from "../ui";
import type { WizardStep } from "../ui";
import { useOperator } from "../../providers/operator-provider";
import { useToast } from "../../providers/toast-provider";
import { instantiate } from "../../lib/api";
import { buildInstantiatePayload } from "../../lib/instantiate";
import type { MandateType } from "../../lib/types";

export interface CreateMandateWizardProps {
  open: boolean;
  mandates: MandateType[];
  onClose: () => void;
  onCreated: (instanceId: string | undefined) => void;
}

const RING_OPTIONS = ["L0", "L1", "L2", "L3", "L4"] as const;

export function CreateMandateWizard({ open, mandates, onClose, onCreated }: CreateMandateWizardProps) {
  const { baseUrl, isLive, token } = useOperator();
  const toast = useToast();

  const [typeRef, setTypeRef] = useState<string>("");
  const [businessName, setBusinessName] = useState<string>("");
  const [customerId, setCustomerId] = useState<string>("");
  const [senderIdentity, setSenderIdentity] = useState<string>("");
  const [ring, setRing] = useState<string>("L0");
  const [icpJson, setIcpJson] = useState<string>("");

  // Reset the form whenever the wizard is (re)opened.
  useEffect(() => {
    if (!open) return;
    setTypeRef("");
    setBusinessName("");
    setCustomerId("");
    setSenderIdentity("");
    setRing("L0");
    setIcpJson("");
  }, [open]);

  const selected = useMemo(
    () => mandates.find((m) => m.type_ref === typeRef) ?? null,
    [mandates, typeRef],
  );

  // When a blueprint is picked, seed the ring floor + ICP target from it.
  const choose = (mandate: MandateType) => {
    setTypeRef(mandate.type_ref);
    const floor = (RING_OPTIONS as readonly string[]).includes(mandate.ring_floor)
      ? mandate.ring_floor
      : "L0";
    setRing(floor);
    setIcpJson(JSON.stringify(mandate.charter?.target ?? {}, null, 2));
  };

  const built = buildInstantiatePayload({
    typeRef,
    businessName,
    customerId,
    senderIdentity,
    ring,
    icpJson,
  });
  const identityValid = businessName.trim().length > 0 && customerId.trim().length > 0;
  const liveDisabledReason = !isLive && !baseUrl
    ? "Set the API base URL in operator settings to launch against a live kernel."
    : undefined;

  const submit = async () => {
    if (!built.payload) {
      toast.push({
        title: "Can't launch yet",
        message: built.errors.join(" ") || "Fill in the required fields.",
        tone: "hot",
      });
      return;
    }
    if (liveDisabledReason) {
      toast.push({ title: "Not connected", message: liveDisabledReason, tone: "hot" });
      return;
    }
    try {
      const result = await instantiate(built.payload, { baseUrl, token });
      if (!result.supported) {
        const message = result.message ?? "Backend rejected the request.";
        toast.push({ title: "Launch failed", message, tone: "hot" });
        throw new Error(message);
      }
      onCreated(result.instanceId);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      toast.push({ title: "Launch failed", message, tone: "hot" });
      throw err; // keep the wizard open on the review step
    }
  };

  const steps: WizardStep[] = [
    {
      id: "blueprint",
      title: "Pick blueprint",
      valid: Boolean(selected),
      render: (
        <div className="ax-wizard__field">
          <p className="dim" style={{ fontSize: 13 }}>
            A blueprint <InfoTip term="blueprint" /> is the reusable mandate type — the recipe an
            agent follows. Choose the one to instantiate for your customer.
          </p>
          <div className="create-wizard__choices">
            {mandates.length === 0 ? (
              <div className="dim">No blueprints in the catalog yet.</div>
            ) : (
              mandates.map((m) => {
                const locked = m.status === "locked" || m.status === "gap";
                return (
                  <button
                    key={m.id}
                    type="button"
                    className={`create-wizard__choice${typeRef === m.type_ref ? " is-active" : ""}`}
                    onClick={() => choose(m)}
                    disabled={locked}
                    title={locked ? `${m.status} — not instantiable yet` : undefined}
                  >
                    <span className="create-wizard__choice-title">{m.title}</span>
                    <span className="mono dim" style={{ fontSize: 11 }}>{m.type_ref}</span>
                  </button>
                );
              })
            )}
          </div>
        </div>
      ),
    },
    {
      id: "identity",
      title: "Identity",
      valid: identityValid,
      render: (
        <div className="ax-wizard__field">
          <Labelled label="Business name" required>
            <input
              className="ax-input"
              value={businessName}
              onChange={(e) => setBusinessName(e.target.value)}
              placeholder="e.g. Kaveri Pumps"
              autoComplete="off"
            />
          </Labelled>
          <Labelled label="Customer id" required>
            <input
              className="ax-input mono"
              value={customerId}
              onChange={(e) => setCustomerId(e.target.value)}
              placeholder="cust_kaveri"
              autoComplete="off"
            />
          </Labelled>
          <Labelled
            label={
              <>
                Sender identity <InfoTip term="sender_identity" />
              </>
            }
          >
            <input
              className="ax-input mono"
              value={senderIdentity}
              onChange={(e) => setSenderIdentity(e.target.value)}
              placeholder="outreach@kaveri-pumps.com"
              autoComplete="off"
            />
            <span className="dim" style={{ fontSize: 11 }}>
              Leave blank to skip channel binding — the instance won&apos;t be able to send.
            </span>
          </Labelled>
        </div>
      ),
    },
    {
      id: "charter",
      title: "Charter & target",
      valid: true,
      render: (
        <div className="ax-wizard__field">
          <Labelled
            label={
              <>
                Ring floor <InfoTip term="ring" />
              </>
            }
          >
            <div className="create-wizard__rings">
              {RING_OPTIONS.map((r) => (
                <button
                  key={r}
                  type="button"
                  className={`create-wizard__ring${ring === r ? " is-active" : ""}`}
                  onClick={() => setRing(r)}
                >
                  {r}
                </button>
              ))}
            </div>
          </Labelled>
          <Labelled
            label={
              <>
                ICP target (JSON) <InfoTip term="target" />
              </>
            }
          >
            <textarea
              className="ax-input mono"
              value={icpJson}
              onChange={(e) => setIcpJson(e.target.value)}
              rows={6}
              spellCheck={false}
            />
            {built.targetWarning ? (
              <span className="dim" style={{ fontSize: 11, color: "var(--warning)" }}>
                Not valid JSON — the target override will be omitted.
              </span>
            ) : null}
          </Labelled>
        </div>
      ),
    },
    {
      id: "review",
      title: "Review & launch",
      valid: Boolean(built.payload) && !liveDisabledReason,
      render: (
        <div className="ax-wizard__field">
          <p className="dim" style={{ fontSize: 13 }}>
            Launching posts to <code>/commands/instantiate</code> as{" "}
            <code>manager:dashboard</code>.
          </p>
          <dl className="create-wizard__review">
            <ReviewRow label="Blueprint" value={selected?.title ?? "—"} mono={false} />
            <ReviewRow label="Type ref" value={typeRef || "—"} />
            <ReviewRow label="Business" value={businessName || "—"} mono={false} />
            <ReviewRow label="Customer" value={customerId || "—"} />
            <ReviewRow label="Ring" value={ring} />
            <ReviewRow label="Sender" value={senderIdentity || "(none)"} />
          </dl>
          {liveDisabledReason ? (
            <span className="dim" style={{ fontSize: 12, color: "var(--warning)" }}>
              {liveDisabledReason}
            </span>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <Wizard
      open={open}
      onClose={onClose}
      title="Create a mandate"
      finishLabel="Launch instance"
      steps={steps}
      onFinish={submit}
    />
  );
}

function Labelled({
  label,
  required,
  children,
}: {
  label: React.ReactNode;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="create-wizard__labelled">
      <span className="create-wizard__label">
        {label}
        {required ? <span aria-hidden> *</span> : null}
      </span>
      {children}
    </label>
  );
}

function ReviewRow({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="create-wizard__review-row">
      <dt className="dim">{label}</dt>
      <dd className={mono ? "mono" : undefined}>{value}</dd>
    </div>
  );
}
