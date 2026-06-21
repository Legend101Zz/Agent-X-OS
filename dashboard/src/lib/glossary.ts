/**
 * Glossary — the single source of plain-language copy for the guidance layer.
 *
 * Every ⓘ tooltip and "How this page works" panel reads its words from here so
 * the vocabulary stays consistent across the app and is edited in one place.
 * Copy is written from the operator's side of the screen: what a thing IS and
 * what you DO with it, in plain terms — not how the backend is built.
 *
 * Grounded in BLUEPRINT.md (the 7 organs, the 8 invariants, the ring/trust
 * ladder) and MANDATE.md. `href` points at the in-app /docs route that explains
 * the concept in more depth, when one exists.
 */

export interface GlossaryTerm {
  /** Stable id used by <InfoTip term="…" /> and the help panels. */
  id: string;
  /** Human label shown as the tooltip heading. */
  label: string;
  /** One or two plain sentences. No jargon that isn't itself a term. */
  short: string;
  /** Optional deep-dive link into the in-app docs. */
  href?: string;
}

export const GLOSSARY: Record<string, GlossaryTerm> = {
  blueprint: {
    id: "blueprint",
    label: "Blueprint",
    short:
      "A reusable mandate type — the recipe an agent follows (its charter, faculties, and rules). You instantiate a blueprint to get a running instance.",
    href: "/docs/blueprint",
  },
  instance: {
    id: "instance",
    label: "Instance",
    short:
      "One running agent created from a blueprint, bound to a specific customer. It has its own memory, runs, trust, and P&L.",
    href: "/docs/blueprint",
  },
  mandate: {
    id: "mandate",
    label: "Mandate",
    short:
      "The job you delegate to an agent — defined by a blueprint, carried out by its instances.",
    href: "/docs/mandate",
  },
  ring: {
    id: "ring",
    label: "Ring (L0–L4)",
    short:
      "How much autonomy an instance has. L0 needs you to approve every effect; each ring up earns more independence as trust grows. L4 acts on its own.",
    href: "/docs/blueprint",
  },
  trust: {
    id: "trust",
    label: "Trust",
    short:
      "An instance's earned track record. Verified good outcomes add trust and can raise its ring; failures take it away.",
    href: "/docs/blueprint",
  },
  run_state: {
    id: "run_state",
    label: "Run state",
    short:
      "Where a run is: running (working), parked (waiting on your approval), settled (finished and billed), or crashed (failed).",
  },
  charter: {
    id: "charter",
    label: "Charter",
    short:
      "The instance's mission in one place — what it's trying to achieve and the boundaries it must stay within.",
    href: "/docs/mandate",
  },
  target: {
    id: "target",
    label: "Target",
    short: "Who or what this instance is working on — e.g. the customer or segment it pursues.",
  },
  faculty: {
    id: "faculty",
    label: "Faculty",
    short:
      "A reusable skill a blueprint plugs in — research, judgment, memory-craft, or escalation. Faculties are the bricks; blueprints combine them.",
    href: "/docs/blueprint",
  },
  fact: {
    id: "fact",
    label: "Fact",
    short:
      "Something an instance has learned and committed to its memory (heap), written as subject · predicate · object with evidence attached.",
  },
  provenance: {
    id: "provenance",
    label: "Provenance",
    short:
      "The receipt behind a fact: which run produced it and what evidence backs it. No fact is stored without one.",
  },
  fact_status: {
    id: "fact_status",
    label: "Fact status",
    short:
      "Probation means newly claimed and not yet trusted; verified means it passed checks and can be relied on.",
  },
  approval: {
    id: "approval",
    label: "Approval gate",
    short:
      "When an instance wants to take a risky action it parks the run here for your sign-off. You can approve, reject, or edit before it proceeds.",
    href: "/docs/blueprint",
  },
  sender_identity: {
    id: "sender_identity",
    label: "Sender identity",
    short:
      "The business identity an instance acts as — its from-name and channel. The business is always the sender of record, never Agent-X.",
    href: "/docs/mandate",
  },
  settlement: {
    id: "settlement",
    label: "Settlement",
    short:
      "Closing out a run: verifying what it did, recording the outcome, and billing. Money moves only here, never mid-run.",
  },
  syscall: {
    id: "syscall",
    label: "Syscall",
    short:
      "An effect an instance asks the kernel to perform (send an email, look something up). Intent is recorded; how it's fulfilled can change.",
  },
  eval_case: {
    id: "eval_case",
    label: "Eval case",
    short:
      "A graded test of a blueprint's behaviour. Real cases come from live runs; synthetic ones from the swarm wind-tunnel.",
  },
  origin: {
    id: "origin",
    label: "Origin (real / synthetic)",
    short:
      "Where a case came from. Synthetic (swarm) cases can train but can never promote a customer-facing version — only real cases can.",
  },
  promotion: {
    id: "promotion",
    label: "Promotion",
    short:
      "Graduating a blueprint version to customer-facing after it clears the eval gate on real cases.",
  },
  swarm: {
    id: "swarm",
    label: "Swarm (Foundry)",
    short:
      "A safe wind-tunnel that runs a blueprint against synthetic scenarios and a judge, so you can see how it behaves before it touches a customer.",
  },
  scheduler_work: {
    id: "scheduler_work",
    label: "Scheduled work",
    short:
      "Jobs the kernel has queued to run later — triggers, retries, and approvals waiting their turn.",
  },
  capability: {
    id: "capability",
    label: "Capability",
    short:
      "Something the platform can actually do right now — an adapter, a data provider, or an email transport — with its live health.",
  },
  core_gap: {
    id: "core_gap",
    label: "Core gap",
    short:
      "A known missing piece the kernel has flagged — a capability or fix the system needs but doesn't have yet.",
  },
  journal: {
    id: "journal",
    label: "Journal",
    short:
      "The append-only log of everything that happened — every think, call, claim, park, and settle, in order.",
  },
};

/** Look up a term by id. Returns undefined for unknown ids (callers degrade gracefully). */
export function getTerm(id: string): GlossaryTerm | undefined {
  return GLOSSARY[id];
}

/** All term ids, sorted — handy for the design-system demo and integrity tests. */
export function glossaryTermIds(): string[] {
  return Object.keys(GLOSSARY).sort();
}
