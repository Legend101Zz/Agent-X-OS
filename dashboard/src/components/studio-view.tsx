"use client";

import {
  Activity,
  ArrowLeft,
  ArrowRight,
  Boxes,
  CheckCircle2,
  ExternalLink,
  KeyRound,
  Loader2,
  Mail,
  Plus,
  Radar,
  RadioTower,
  Rocket,
  Send,
  ShieldCheck,
  Sparkles,
  Target,
  TriangleAlert,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  approveRun,
  deriveSendPosture,
  fetchApprovals,
  fetchInstanceRaw,
  fetchRunRaw,
  fetchRuns,
  instantiate,
  mapScoredLeads,
  triggerRun,
} from "@/lib/api";
import type { JournalStreamEvent } from "@/lib/events";
import type { ApprovalCard, DashboardData, ScoredLead, SendPosture } from "@/lib/types";
import { classNames, stagger, type ToastInput } from "./shared";

type Stage = "pick" | "find" | "leads" | "draft" | "send";

const STAGES: Array<{ id: Stage; label: string }> = [
  { id: "pick", label: "Pick" },
  { id: "find", label: "Find" },
  { id: "leads", label: "Leads" },
  { id: "draft", label: "Draft" },
  { id: "send", label: "Send" },
];

const TERMINAL_RUN_STATES = new Set(["complete", "parked", "waiting_approval", "failed"]);

interface StudioViewProps {
  data: DashboardData;
  apiBaseUrl: string;
  operatorToken: string;
  events: JournalStreamEvent[];
  onRefresh: () => void | Promise<void>;
  pushToast: (input: ToastInput) => void;
  onOpenBusinessFile: (instanceId: string) => void;
}

interface Receipt {
  tone: "good" | "warn";
  title: string;
  detail: string;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function mandateRef(title: string, stage: string): string {
  return `${title.toLowerCase().replace(/\s+/g, "_")}@${stage}`;
}

function draftArgs(card: ApprovalCard): { to: string; subject: string; body: string; syscall: string; idem: string } {
  const drafted = card.drafted_effect;
  const has = (key: string) => drafted && typeof drafted === "object" && key in drafted;
  const syscall = has("syscall") ? String((drafted as Record<string, unknown>).syscall) : "send_email";
  const idem = has("idempotency_key") ? String((drafted as Record<string, unknown>).idempotency_key) : "—";
  const args = has("args") ? ((drafted as Record<string, unknown>).args as Record<string, unknown>) : {};
  return {
    to: String(args.to ?? "—"),
    subject: String(args.subject ?? "—"),
    body: String(args.body ?? ""),
    syscall,
    idem,
  };
}

export function StudioView({
  data,
  apiBaseUrl,
  operatorToken,
  events,
  onRefresh,
  pushToast,
  onOpenBusinessFile,
}: StudioViewProps) {
  const [stage, setStage] = useState<Stage>("pick");
  const [instanceId, setInstanceId] = useState("");
  const [businessLabel, setBusinessLabel] = useState("");
  const [runId, setRunId] = useState("");
  const [runState, setRunState] = useState("");
  const [finding, setFinding] = useState(false);
  const [leads, setLeads] = useState<ScoredLead[]>([]);
  const [draftCard, setDraftCard] = useState<ApprovalCard | null>(null);
  const [sending, setSending] = useState(false);
  const [receipt, setReceipt] = useState<Receipt | null>(null);

  // PICK — create-new form state
  const firstMandate = data.mandateTypes[0];
  const [businessName, setBusinessName] = useState("Acme Dental Co");
  const [typeRef, setTypeRef] = useState(
    firstMandate ? mandateRef(firstMandate.title, firstMandate.stage) : "lead-finder@0.1.0",
  );
  const [ring, setRing] = useState("L1");
  const [icp, setIcp] = useState("");
  const [creating, setCreating] = useState(false);

  const sendPosture = useMemo<SendPosture>(() => deriveSendPosture(data.capabilities), [data.capabilities]);
  const hasToken = Boolean(operatorToken);

  const armBusiness = useCallback((id: string, label: string) => {
    setInstanceId(id);
    setBusinessLabel(label);
    setRunId("");
    setRunState("");
    setLeads([]);
    setDraftCard(null);
    setReceipt(null);
    setFinding(false);
    setStage("find");
  }, []);

  const loadReview = useCallback(
    async (resolvedRunId: string) => {
      const runRaw = await fetchRunRaw(resolvedRunId, { baseUrl: apiBaseUrl });
      let scored = mapScoredLeads(runRaw.data);
      if (scored.length === 0 && instanceId) {
        const instRaw = await fetchInstanceRaw(instanceId, { baseUrl: apiBaseUrl });
        scored = mapScoredLeads(instRaw.data);
      }
      setLeads(scored);
      const approvals = await fetchApprovals({ instance_id: instanceId }, { baseUrl: apiBaseUrl });
      const card = approvals.data.find((item) => item.run_id === resolvedRunId) ?? approvals.data[0] ?? null;
      setDraftCard(card);
      setStage("leads");
    },
    [apiBaseUrl, instanceId],
  );

  // Poll for the worker-created run while "finding", until it reaches a terminal/parked state.
  useEffect(() => {
    if (!finding || !instanceId) return;
    let cancelled = false;
    const tick = async () => {
      const runs = await fetchRuns({ instance_id: instanceId }, { baseUrl: apiBaseUrl });
      if (cancelled) return;
      const newest = runs.data[0];
      if (!newest) return;
      setRunId(newest.id);
      setRunState(newest.state);
      if (TERMINAL_RUN_STATES.has(newest.state)) {
        setFinding(false);
        await loadReview(newest.id);
      }
    };
    void tick();
    const timer = window.setInterval(() => void tick(), 1300);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [finding, instanceId, apiBaseUrl, loadReview]);

  const handleCreate = useCallback(async () => {
    if (!hasToken) {
      pushToast({ title: "instantiate", message: "Set the operator token to enable writes.", tone: "hot" });
      return;
    }
    setCreating(true);
    const target: Record<string, unknown> = {};
    if (icp.trim()) target.icp = icp.trim();
    const result = await instantiate(
      {
        type_ref: typeRef,
        customer_id: businessName.trim(),
        business_name: businessName.trim(),
        ring,
        target_override: Object.keys(target).length > 0 ? target : undefined,
        actor: "dashboard/operator",
      },
      { baseUrl: apiBaseUrl, token: operatorToken },
    );
    setCreating(false);
    if (!result.supported || !result.instanceId) {
      pushToast({ title: "instantiate", message: result.message ?? "failed", tone: "hot" });
      return;
    }
    pushToast({ title: "instantiate", message: `created ${result.instanceId}`, tone: "good" });
    await onRefresh();
    armBusiness(result.instanceId, businessName.trim());
  }, [apiBaseUrl, armBusiness, businessName, hasToken, icp, onRefresh, operatorToken, pushToast, ring, typeRef]);

  const handleFind = useCallback(async () => {
    if (!hasToken || !instanceId) {
      pushToast({ title: "find leads", message: "Set the operator token to enable writes.", tone: "hot" });
      return;
    }
    setReceipt(null);
    setLeads([]);
    setDraftCard(null);
    setRunId("");
    setRunState("");
    const result = await triggerRun(
      { instance_id: instanceId, mode: "sim", actor: "dashboard/operator" },
      { baseUrl: apiBaseUrl, token: operatorToken },
    );
    if (!result.supported) {
      pushToast({ title: "find leads", message: result.message ?? "failed", tone: "hot" });
      return;
    }
    pushToast({ title: "find leads", message: `run queued · ${result.workId ?? "?"}`, tone: "good" });
    setFinding(true);
  }, [apiBaseUrl, hasToken, instanceId, operatorToken, pushToast]);

  const pollSendOutcome = useCallback(
    async (resolvedRunId: string) => {
      const deadline = Date.now() + 12_000;
      while (Date.now() < deadline) {
        const runs = await fetchRuns({ instance_id: instanceId }, { baseUrl: apiBaseUrl });
        const thisRun = runs.data.find((item) => item.id === resolvedRunId);
        if (thisRun && thisRun.state === "complete") {
          const runRaw = await fetchRunRaw(resolvedRunId, { baseUrl: apiBaseUrl });
          let scored = mapScoredLeads(runRaw.data);
          if (scored.length === 0) {
            const instRaw = await fetchInstanceRaw(instanceId, { baseUrl: apiBaseUrl });
            scored = mapScoredLeads(instRaw.data);
          }
          if (scored.length > 0) setLeads(scored);
          return sendPosture === "live"
            ? { tone: "good" as const, title: "Sent", detail: "Run settled — the gated outreach dispatched through the live transport." }
            : {
                tone: "warn" as const,
                title: "Committed · staged",
                detail:
                  "Run settled and the leads are committed with provenance. No live mail transport is configured, so the email send fail-closes to the human tail (invariant #5).",
              };
        }
        await sleep(750);
      }
      return sendPosture === "live"
        ? { tone: "good" as const, title: "Approved", detail: "Approval recorded; the run is resuming — check the Business File." }
        : { tone: "warn" as const, title: "Staged", detail: "Approval recorded; the send fail-closes to the human tail (invariant #5)." };
    },
    [apiBaseUrl, instanceId, sendPosture],
  );

  const handleApproveSend = useCallback(async () => {
    if (!draftCard) return;
    if (!hasToken) {
      pushToast({ title: "approve & send", message: "Set the operator token to enable writes.", tone: "hot" });
      return;
    }
    setStage("send");
    setSending(true);
    setReceipt(null);
    const result = await approveRun(
      { instance_id: instanceId, run_id: draftCard.run_id, actor: "dashboard/operator" },
      { baseUrl: apiBaseUrl, token: operatorToken },
    );
    if (!result.supported) {
      setSending(false);
      pushToast({ title: "approve & send", message: result.message ?? "failed", tone: "hot" });
      setReceipt({ tone: "warn", title: "Rejected", detail: result.message ?? "approve failed" });
      return;
    }
    pushToast({ title: "approve & send", message: `approved · ${result.status ?? "queued"}`, tone: "good" });
    const outcome = await pollSendOutcome(draftCard.run_id);
    setReceipt(outcome);
    setSending(false);
    await onRefresh();
  }, [apiBaseUrl, draftCard, hasToken, instanceId, onRefresh, operatorToken, pollSendOutcome, pushToast]);

  // --- which stages are reachable ---------------------------------------------------------
  const canGo = useCallback(
    (target: Stage): boolean => {
      if (target === "pick") return true;
      if (target === "find") return Boolean(instanceId);
      if (target === "leads") return Boolean(runId) || leads.length > 0;
      if (target === "draft") return Boolean(draftCard);
      if (target === "send") return Boolean(draftCard) || Boolean(receipt);
      return false;
    },
    [draftCard, instanceId, leads.length, receipt, runId],
  );
  const stageIndex = STAGES.findIndex((item) => item.id === stage);

  const liveTrace = events
    .filter((event) => event.instance_id === instanceId)
    .slice(-14)
    .reverse();

  return (
    <div className="studio">
      <DriveTrack stage={stage} stageIndex={stageIndex} canGo={canGo} onGo={setStage} />

      {!hasToken ? (
        <div className="studio-token-warn">
          <TriangleAlert size={15} /> No operator token set — commands are disabled. Add it in the header to drive a run.
        </div>
      ) : null}

      {stage === "pick" ? (
        <section className="studio-card stagger-floor">
          <header className="studio-card-head">
            <p className="eyebrow">stage 1 · ignition</p>
            <h2>Pick a business to drive</h2>
          </header>
          <div className="studio-pick">
            <div className="studio-garage" style={stagger(0)}>
              <p className="eyebrow">your businesses</p>
              {data.instances.length === 0 ? (
                <p className="studio-empty">No businesses yet — spin one up on the right.</p>
              ) : (
                <div className="studio-garage-list">
                  {data.instances.map((inst, index) => (
                    <button
                      key={inst.id}
                      className="studio-garage-card"
                      style={stagger(index)}
                      onClick={() => armBusiness(inst.id, inst.name)}
                      type="button"
                    >
                      <Boxes size={18} />
                      <div>
                        <strong>{inst.name}</strong>
                        <span>
                          {inst.mandate_type} · {inst.ring} · trust {inst.trust_score}
                        </span>
                      </div>
                      <ArrowRight size={16} />
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="studio-ignite" style={stagger(1)}>
              <p className="eyebrow">spin up a new one</p>
              <label className="studio-field">
                Business
                <input value={businessName} onChange={(e) => setBusinessName(e.target.value)} placeholder="Acme Dental Co" />
              </label>
              <label className="studio-field">
                Mandate
                <select value={typeRef} onChange={(e) => setTypeRef(e.target.value)}>
                  {data.mandateTypes.map((mandate) => {
                    const id = mandateRef(mandate.title, mandate.stage);
                    return (
                      <option key={mandate.id} value={id}>
                        {mandate.title} @ {mandate.stage}
                      </option>
                    );
                  })}
                  {data.mandateTypes.length === 0 ? <option value="lead-finder@0.1.0">lead-finder @ 0.1.0</option> : null}
                </select>
              </label>
              <div className="studio-field-row">
                <label className="studio-field">
                  Ring
                  <select value={ring} onChange={(e) => setRing(e.target.value)}>
                    <option value="L0">L0</option>
                    <option value="L1">L1</option>
                    <option value="L2">L2</option>
                  </select>
                </label>
                <label className="studio-field">
                  ICP (optional)
                  <input value={icp} onChange={(e) => setIcp(e.target.value)} placeholder="dental clinics in Pune" />
                </label>
              </div>
              <button
                className={classNames("studio-primary", (!hasToken || creating) && "is-disabled")}
                disabled={!hasToken || creating}
                onClick={() => void handleCreate()}
                type="button"
              >
                {creating ? <Loader2 className="spin" size={16} /> : <Plus size={16} />}
                {creating ? "Spinning up…" : "Create & arm"}
              </button>
              <p className="studio-ignition-readout">
                <span>&gt;</span> {businessName || "(unnamed)"} · {typeRef} · {ring}
              </p>
            </div>
          </div>
        </section>
      ) : null}

      {stage === "find" ? (
        <section className="studio-card stagger-floor">
          <header className="studio-card-head">
            <p className="eyebrow">stage 2 · the run</p>
            <h2>Find leads</h2>
            <p className="studio-armed">
              <Rocket size={14} /> armed: <strong>{businessLabel || instanceId}</strong>
            </p>
          </header>
          <div className="studio-find">
            <button
              className={classNames("studio-primary", (!hasToken || finding) && "is-disabled")}
              disabled={!hasToken || finding}
              onClick={() => void handleFind()}
              type="button"
            >
              {finding ? <Loader2 className="spin" size={16} /> : <Radar size={16} />}
              {finding ? "Running…" : "Find leads"}
            </button>
            <div className="studio-run-state">
              <span className={classNames("studio-pulse", finding && "is-live")} />
              <span className="studio-mono">{runState || (finding ? "dispatching…" : "idle")}</span>
              {runId ? <span className="studio-mono studio-dim">run {runId}</span> : null}
            </div>
          </div>
          <div className="studio-scope" aria-label="live run trace">
            <div className="studio-scope-head">
              <Activity size={14} /> live trace <span className="studio-dim">/events (SSE)</span>
            </div>
            {liveTrace.length === 0 ? (
              <p className="studio-empty">{finding ? "waiting for the worker to pick up the run…" : "press Find leads to stream the run"}</p>
            ) : (
              <ol className="studio-trace">
                {liveTrace.map((event, index) => (
                  <li key={`${event.event_id}:${index}`} style={stagger(index)}>
                    <RadioTower size={12} />
                    <span className="studio-trace-kind">{event.kind}</span>
                    <span className="studio-dim">{event.run_id ?? "—"}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>
          {runId && !finding ? (
            <button className="studio-next" onClick={() => setStage("leads")} type="button">
              Review leads <ArrowRight size={16} />
            </button>
          ) : null}
        </section>
      ) : null}

      {stage === "leads" ? (
        <section className="studio-card stagger-floor">
          <header className="studio-card-head">
            <p className="eyebrow">stage 3 · qualified leads</p>
            <h2>Scored leads &amp; cited evidence</h2>
          </header>
          {leads.length === 0 ? (
            <p className="studio-empty">
              No settled leads yet — the run parked on the outreach draft before committing facts. Leads finalize when you
              approve &amp; send. Review the draft next.
            </p>
          ) : (
            <div className="studio-leads">
              {leads.map((lead, index) => (
                <article key={`${lead.lead}:${index}`} className="studio-lead" style={stagger(index)}>
                  <div className="studio-lead-top">
                    <div>
                      <Target size={16} />
                      <strong>{lead.lead}</strong>
                    </div>
                    <ScoreDial score={lead.score} />
                  </div>
                  <p className="studio-lead-pred">{lead.predicate}</p>
                  {lead.note ? <p className="studio-lead-note">{lead.note}</p> : null}
                  <div className="studio-evidence">
                    <span className="studio-dim">
                      <KeyRound size={12} /> evidence
                    </span>
                    {lead.evidence.length === 0 ? (
                      <span className="studio-dim">no citations</span>
                    ) : (
                      lead.evidence.map((cite) => (
                        <span key={cite} className="studio-cite">
                          {cite}
                        </span>
                      ))
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
          <div className="studio-nav-row">
            <button className="studio-back" onClick={() => setStage("find")} type="button">
              <ArrowLeft size={15} /> Back to run
            </button>
            {draftCard ? (
              <button className="studio-next" onClick={() => setStage("draft")} type="button">
                Review outreach <ArrowRight size={16} />
              </button>
            ) : (
              <button className="studio-next" onClick={() => onOpenBusinessFile(instanceId)} type="button">
                Open Business File <ExternalLink size={15} />
              </button>
            )}
          </div>
        </section>
      ) : null}

      {stage === "draft" && draftCard ? (
        <DraftStage
          card={draftCard}
          posture={sendPosture}
          hasToken={hasToken}
          onBack={() => setStage("leads")}
          onApproveSend={() => void handleApproveSend()}
        />
      ) : null}

      {stage === "send" ? (
        <section className="studio-card stagger-floor">
          <header className="studio-card-head">
            <p className="eyebrow">stage 5 · the gated trigger</p>
            <h2>Approve &amp; send</h2>
          </header>
          {sending ? (
            <div className="studio-sending">
              <Loader2 className="spin" size={18} /> resuming the run &amp; executing send_email…
            </div>
          ) : receipt ? (
            <div className={classNames("studio-receipt", `is-${receipt.tone}`)}>
              <div className="studio-receipt-stamp alive-strip">
                {receipt.tone === "good" ? <CheckCircle2 size={22} /> : <TriangleAlert size={22} />}
                <strong>{receipt.title}</strong>
              </div>
              <p className="studio-mono">{receipt.detail}</p>
              {leads.length > 0 ? (
                <p className="studio-dim">{leads.length} lead(s) settled with provenance into the heap.</p>
              ) : null}
              <button className="studio-primary" onClick={() => onOpenBusinessFile(instanceId)} type="button">
                Open Business File <ExternalLink size={15} />
              </button>
            </div>
          ) : (
            <p className="studio-empty">Awaiting approval.</p>
          )}
        </section>
      ) : null}

      <footer className="studio-foot">
        <button className="studio-back" onClick={() => setStage("pick")} type="button">
          <Boxes size={14} /> Back to garage
        </button>
        <span className="studio-dim">
          <Sparkles size={13} /> send posture: <strong className={sendPosture === "live" ? "tone-good" : "tone-warn"}>{sendPosture}</strong>
        </span>
      </footer>
    </div>
  );
}

function DriveTrack({
  stage,
  stageIndex,
  canGo,
  onGo,
}: {
  stage: Stage;
  stageIndex: number;
  canGo: (s: Stage) => boolean;
  onGo: (s: Stage) => void;
}) {
  return (
    <nav className="studio-track" aria-label="Drive steps">
      {STAGES.map((item, index) => {
        const state = index < stageIndex ? "done" : index === stageIndex ? "active" : "future";
        const reachable = canGo(item.id);
        return (
          <button
            key={item.id}
            className={classNames("studio-node", `is-${state}`, reachable && "is-reachable")}
            disabled={!reachable}
            onClick={() => reachable && onGo(item.id)}
            type="button"
          >
            <span className="studio-node-dot">{index < stageIndex ? <Check14 /> : index + 1}</span>
            <span className="studio-node-label">{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

function Check14() {
  return <CheckCircle2 size={14} />;
}

function ScoreDial({ score }: { score: number }) {
  const pct = Math.round(Math.min(Math.max(score, 0), 1) * 100);
  return (
    <div className="studio-dial" aria-label={`score ${pct}%`}>
      <strong>{pct}</strong>
      <div className="progress-rail">
        <span style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function DraftStage({
  card,
  posture,
  hasToken,
  onBack,
  onApproveSend,
}: {
  card: ApprovalCard;
  posture: SendPosture;
  hasToken: boolean;
  onBack: () => void;
  onApproveSend: () => void;
}) {
  const { to, subject, body, syscall, idem } = draftArgs(card);
  return (
    <section className="studio-card stagger-floor">
      <header className="studio-card-head">
        <p className="eyebrow">stage 4 · the outreach</p>
        <h2>Review the drafted outreach</h2>
      </header>
      <div className="studio-compose" style={stagger(0)}>
        <div className="studio-compose-line">
          <span className="studio-dim">to</span>
          <span className="studio-mono">{to}</span>
        </div>
        <div className="studio-compose-line">
          <span className="studio-dim">subject</span>
          <span className="studio-mono">{subject}</span>
        </div>
        <div className="studio-compose-body studio-mono">
          {body || "(no body)"}
          <span className="studio-cursor" aria-hidden />
        </div>
      </div>

      <div className="studio-gated" style={stagger(1)}>
        <span className="studio-chip">
          <ShieldCheck size={13} /> requires {card.required_ring ?? "L?"}
        </span>
        <span className="studio-chip">
          <Mail size={13} /> {syscall}
        </span>
        <span className="studio-chip studio-dim">idem {idem}</span>
      </div>

      <div className={classNames("studio-posture", posture === "live" ? "is-live" : "is-staged")} style={stagger(2)}>
        {posture === "live" ? (
          <>
            <Send size={15} /> <strong>LIVE</strong> — a <code>send_email</code> transport is registered; a gated send goes out
            for real on approval.
          </>
        ) : (
          <>
            <TriangleAlert size={15} /> <strong>STAGED</strong> — no <code>send_email</code> transport is configured. Approving
            commits the gated outreach; the actual send fail-closes to the human tail (invariant #5).
          </>
        )}
      </div>

      <div className="studio-nav-row">
        <button className="studio-back" onClick={onBack} type="button">
          <ArrowLeft size={15} /> Back to leads
        </button>
        <button
          className={classNames("studio-primary studio-send", !hasToken && "is-disabled")}
          disabled={!hasToken}
          onClick={onApproveSend}
          type="button"
        >
          <Send size={16} /> Approve &amp; send
        </button>
      </div>
    </section>
  );
}
