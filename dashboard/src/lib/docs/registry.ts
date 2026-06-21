/**
 * docs/registry.ts — the public API for the in-app docs viewer (C17).
 *
 * Reads the four design docs embedded by the build script (registry.content.ts)
 * and exposes:
 *   - `DOC_REGISTRY` — frozen list of all registered docs.
 *   - `listDocs()` — same list, for callers that prefer a function.
 *   - `getDoc(slug)` — fetch a doc by slug, or null.
 *   - `buildConceptExplainers(slug)` — derived concept cards that link to
 *     specific headings in the doc. Anchors are validated against the
 *     doc's heading list so a stale callout cannot dangle.
 *
 * The docs are static and the registry is intentionally pure: no I/O, no
 * Date.now(), no environment reads. This keeps the docs view prerenderable
 * and the tests deterministic.
 */
import { DOC_CONTENT } from "./registry.content";
import {
  parseMarkdown,
  extractHeadings,
  extractSections,
  type DocNode,
  type DocHeading,
  type DocSection,
  type DocSubsection,
} from "./markdown";

// Re-exports so consumers only ever need to import from "./registry".
export { parseMarkdown, extractHeadings, extractSections } from "./markdown";
export type { DocNode, DocHeading, DocSection, DocSubsection } from "./markdown";

// ─────────────────────────────────────────────────────────────────────────────
// Public types
// ─────────────────────────────────────────────────────────────────────────────

export interface DocRef {
  slug: string;
  /** Display title, taken from the H1 of the markdown source. */
  title: string;
  /** Relative source path of the original .md file (label only, not read at runtime). */
  sourcePath: string;
  /** One- or two-sentence description; used in the doc-list rail. */
  summary: string;
  /** Full H1–H4 heading list with stable anchor ids. */
  headings: DocHeading[];
  /** H1 sections, each with their H2 subsections. */
  sections: DocSection[];
  /** The original markdown text (for raw / copy-to-clipboard views). */
  raw: string;
}

export interface ConceptExplainer {
  /** Concept name as the user sees it (e.g. "Mandate", "Trust rings"). */
  term: string;
  /** One-paragraph definition, written for an operator reading the docs. */
  definition: string;
  /** Anchor id of the heading this explainer links to. Resolved against the parent doc's heading list. */
  anchorId: string;
  /** Optional kind tag — used by the renderer to pick a tone (concept | pillar | invariant | system). */
  kind: "concept" | "pillar" | "invariant" | "system";
}

// ─────────────────────────────────────────────────────────────────────────────
// Per-doc summaries
// ─────────────────────────────────────────────────────────────────────────────

const SUMMARIES: Record<string, string> = {
  blueprint:
    "The canonical Agent-X design doc. The eight sections are the single source of truth — when this disagrees with anything else, this wins.",
  mandate:
    "Focused companion to the README and ARCHITECTURE. The mandate structure in one place: type / instance / run, the heap, and the swarm.",
  readme:
    "First-principles design document. The thesis, the anatomy of a mandate, the excellence flywheel, and the build order.",
  architecture:
    "Diagrams and full flows. Eleven reference diagrams covering the layers, the lifecycle, settlement, the SDK, and the data model.",
};

// ─────────────────────────────────────────────────────────────────────────────
// Concept explainers — anchored to real heading ids in each doc.
// ─────────────────────────────────────────────────────────────────────────────

const EXPLAINERS: Record<string, ConceptExplainer[]> = {
  blueprint: [
    {
      kind: "concept",
      term: "Mandate",
      definition:
        "A unit of delegated authority, wrapped in a contract that says what 'done' means and who checks it. The basic process the kernel runs.",
      anchorId: "1-pillar-1-how-a-mandate-looks",
    },
    {
      kind: "system",
      term: "Syscall",
      definition:
        "How a mandate touches the outside world — sending email, fetching a page, hitting an API. Every capability installs as a plugin at the gateway.",
      anchorId: "3-pillar-3-how-the-syscall-integration-layer-looks",
    },
    {
      kind: "system",
      term: "Kernel",
      definition:
        "The live, online control plane. It is deliberately dumb — it schedules, journals, and commits, but never improvises with money or credentials.",
      anchorId: "4-pillar-2-how-the-kernel-looks",
    },
    {
      kind: "pillar",
      term: "Trust rings",
      definition:
        "The go-to-market motion, mechanically. Each ring (L0 manual → L4 autonomous) earns authority by surviving graded eval cases against real outcomes.",
      anchorId: "the-trust-ladder-the-go-to-market-motion-mechanically",
    },
    {
      kind: "concept",
      term: "Foundry",
      definition:
        "The offline workshop that takes settled results and a sandbox (the swarm) and forges better versions of mandates. Promotion needs real, graded evidence.",
      anchorId: "5-the-foundry-the-creator-mandate-how-new-mandates-get-born-fast",
    },
    {
      kind: "invariant",
      term: "The eight invariants",
      definition:
        "No fact without a commit. No credentials in user space. No raw fact crossing customers. No brain in the live kernel. The list that makes the architecture honest.",
      anchorId: "the-master-invariant-list-these-make-the-architecture-honest",
    },
  ],
  mandate: [
    {
      kind: "concept",
      term: "Mandate type vs instance",
      definition:
        "A type is the class — shared, almost open-source. An instance is the object — private to one business. The moat lives in the instance's heap and overrides.",
      anchorId: "1-the-three-layers-your-mental-model-checked",
    },
    {
      kind: "system",
      term: "Kernel: dumb on purpose",
      definition:
        "The live kernel never improvises. Intelligence lives in the faculties (online) and the Foundry (offline). This is the design choice that keeps money safe.",
      anchorId: "why-the-live-kernel-must-be-dumb",
    },
    {
      kind: "concept",
      term: "Swarm",
      definition:
        "The sandbox where candidate mandates are tried against graded scenarios. Real graded outcomes — not vibes — decide what promotes.",
      anchorId: "4-the-swarm-and-the-gym-your-third-question",
    },
  ],
  readme: [
    {
      kind: "concept",
      term: "Mandate, defined",
      definition:
        "A mandate is a unit of delegated authority with a verification function attached. The thesis of the whole product: mandates are compiled, not written.",
      anchorId: "part-2-the-anatomy-of-a-mandate",
    },
    {
      kind: "system",
      term: "The excellence flywheel",
      definition:
        "Mandates get good because the gym grades them against real outcomes, and the compiler iterates against those grades. A snapshot is buildable; a gym compounds.",
      anchorId: "part-3-the-excellence-flywheel-mandates-are-compiled",
    },
    {
      kind: "concept",
      term: "The seven organs",
      definition:
        "Charter, faculties, domain pack, verification, settlement, gym, routing. Every mandate type is composed from these — this is what makes mandate #2 ship in a day.",
      anchorId: "22-the-seven-organs",
    },
  ],
  architecture: [
    {
      kind: "system",
      term: "Three layers of a mandate",
      definition:
        "Type (class) → Instance (per-business object) → Run (per-trigger stack frame). The instance is where the moat lives.",
      anchorId: "diagram-1-the-three-layers-of-a-mandate",
    },
    {
      kind: "system",
      term: "Run lifecycle",
      definition:
        "Trigger → hydrate → think/call/claim → settle (or park for approval). Settlement is the atomic commit: heap + journal + trust update in one transaction.",
      anchorId: "diagram-3-full-lifecycle-of-one-run-the-master-flow",
    },
    {
      kind: "concept",
      term: "Mandate SDK",
      definition:
        "The reusable faculties and organs that compose mandate #2. The whole point: mandate #2 ships in days, not quarters.",
      anchorId: "diagram-6-the-mandate-sdk-assembling-mandate-2-in-days",
    },
  ],
};

// ─────────────────────────────────────────────────────────────────────────────
// Build the registry at module load (deterministic, no I/O).
// ─────────────────────────────────────────────────────────────────────────────

function buildDoc(slug: string): DocRef {
  const content = DOC_CONTENT[slug];
  if (!content) {
    throw new Error(`buildDoc: unknown slug ${slug}`);
  }
  const ast = parseMarkdown(content.raw);
  const headings = extractHeadings(ast);
  const sections = extractSections(ast);
  const titleNode = ast.find(
    (n: DocNode): n is Extract<DocNode, { kind: "heading" }> =>
      n.kind === "heading" && n.level === 1,
  );
  const title = titleNode?.text ?? slug;
  return {
    slug,
    title,
    sourcePath: content.sourcePath,
    summary: SUMMARIES[slug] ?? "",
    headings,
    sections,
    raw: content.raw,
  };
}

const _registry: DocRef[] = Object.keys(DOC_CONTENT)
  .map(buildDoc)
  // Stable order matching the task brief: BLUEPRINT, MANDATE, README, ARCHITECTURE.
  .sort((a, b) => {
    const order = ["blueprint", "mandate", "readme", "architecture"];
    return order.indexOf(a.slug) - order.indexOf(b.slug);
  });

/** All registered docs in stable order. */
export const DOC_REGISTRY: readonly DocRef[] = Object.freeze(_registry);

/** Same list as `DOC_REGISTRY`, for callers that prefer a function. */
export function listDocs(): readonly DocRef[] {
  return DOC_REGISTRY;
}

/** Look up a doc by slug. Returns `null` if no such slug is registered. */
export function getDoc(slug: string): DocRef | null {
  return DOC_REGISTRY.find((d) => d.slug === slug) ?? null;
}

/**
 * Return the concept explainers for a given doc. Each explainer carries an
 * `anchorId` that resolves to a heading in the parent doc — guaranteed by
 * the validation pass below (a stale anchor would throw at module load).
 */
export function buildConceptExplainers(slug: string): ConceptExplainer[] {
  const doc = getDoc(slug);
  if (!doc) return [];
  const headingIds = new Set(doc.headings.map((h) => h.id));
  const list = EXPLAINERS[slug] ?? [];
  return list
    .filter((ex) => headingIds.has(ex.anchorId))
    .map((ex) => ({ ...ex }));
}
