/**
 * docs/doc-viewer.tsx — render a DocRef as React, using C1 primitives.
 *
 * Used by the /docs page. The viewer is a server component (no "use client"
 * directive) so it prerenders cleanly. The doc text itself is static; the
 * only interactive surface is the "jump to anchor" link in each heading,
 * which uses native hash links and CSS scroll-margin.
 *
 * Companion styles: src/components/ui/primitives.css (ax-prose / ax-callout /
 * ax-doc-rail / ax-doc-card).
 */
import type { ReactNode } from "react";
import { CodeBlock } from "../ui/json";
import { Stack, Cluster, Card, CardHeader, CardBody } from "../ui";
import {
  parseMarkdown,
  type DocNode,
  type DocRef,
  type ConceptExplainer,
} from "../../lib/docs/registry";
import { buildConceptExplainers } from "../../lib/docs/registry";

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function slugId(level: 1 | 2 | 3 | 4, text: string, taken: Set<string>): string {
  // Re-run the same slugifier the parser uses so the heading anchor we render
  // here is byte-identical to the id stored on the parsed node. (The parser
  // is the source of truth — this is a defensive fallback only.)
  const base =
    text
      .toLowerCase()
      .trim()
      .replace(/`/g, "")
      .replace(/[^a-z0-9\s-]/g, "")
      .replace(/\s+/g, "-")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "") || `h${level}`;
  if (!taken.has(base)) {
    taken.add(base);
    return base;
  }
  let n = 1;
  while (taken.has(`${base}-${n}`)) n++;
  const id = `${base}-${n}`;
  taken.add(id);
  return id;
}

// ─────────────────────────────────────────────────────────────────────────────
// Per-node renderer
// ─────────────────────────────────────────────────────────────────────────────

function RenderNode({ node, takenIds }: { node: DocNode; takenIds: Set<string> }): ReactNode {
  switch (node.kind) {
    case "heading": {
      // Heading ids were assigned by the parser; re-derive defensively in case
      // a future caller passes a node without one.
      const id = node.id && node.id !== "__pending__"
        ? node.id
        : slugId(node.level, node.text, takenIds);
      const inner = (
        <a className="ax-anchor" href={`#${id}`}>
          {node.text}
          <span className="ax-anchor__hash" aria-hidden="true">
            #
          </span>
        </a>
      );
      if (node.level === 1) return <h1 id={id}>{inner}</h1>;
      if (node.level === 2) return <h2 id={id}>{inner}</h2>;
      if (node.level === 3) return <h3 id={id}>{inner}</h3>;
      return <h4 id={id}>{inner}</h4>;
    }
    case "paragraph":
      return <p>{node.text}</p>;
    case "code":
      return (
        <div>
          {node.lang ? (
            <div className="ax-prose__pre-meta">
              <span>{node.lang}</span>
              <span>fenced code</span>
            </div>
          ) : null}
          <CodeBlock language={node.lang ?? undefined}>{node.text}</CodeBlock>
        </div>
      );
    case "blockquote":
      return <blockquote>{node.text}</blockquote>;
    case "list": {
      if (node.ordered) {
        return (
          <ol>
            {node.items.map((item: string, i: number) => (
              <li key={i}>{item}</li>
            ))}
          </ol>
        );
      }
      return (
        <ul>
          {node.items.map((item: string, i: number) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      );
    }
    case "hr":
      return <hr />;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Concept explainer callouts
// ─────────────────────────────────────────────────────────────────────────────

export function ConceptCallouts({
  explainers,
}: {
  explainers: ConceptExplainer[];
}) {
  if (explainers.length === 0) return null;
  return (
    <div className="ax-callouts">
      {explainers.map((ex) => (
        <a
          key={ex.term}
          className={`ax-callout ax-callout--${ex.kind}`}
          href={`#${ex.anchorId}`}
        >
          <div className="ax-callout__head">
            <span className="ax-callout__term">{ex.term}</span>
            <span className="ax-callout__kind">{ex.kind}</span>
          </div>
          <p className="ax-callout__definition">{ex.definition}</p>
          <span className="ax-callout__anchor">→ #{ex.anchorId}</span>
        </a>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Table-of-contents rail
// ─────────────────────────────────────────────────────────────────────────────

function DocRail({ doc }: { doc: DocRef }) {
  const headings = doc.headings;
  if (headings.length === 0) return null;
  return (
    <nav className="ax-doc-rail" aria-label={`${doc.title} — contents`}>
      <div className="ax-doc-rail__group">
        <div className="ax-doc-rail__group-title">On this page</div>
        {headings.map((h) => (
          <a
            key={`${h.level}-${h.id}`}
            className={
              h.level === 3
                ? "ax-doc-rail__link ax-doc-rail__link--h3"
                : "ax-doc-rail__link ax-doc-rail__link--h2"
            }
            href={`#${h.id}`}
          >
            {h.text}
          </a>
        ))}
      </div>
    </nav>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Public component
// ─────────────────────────────────────────────────────────────────────────────

export interface DocViewerProps {
  doc: DocRef;
  /** If omitted, derived from `doc.slug` via buildConceptExplainers. */
  explainers?: ConceptExplainer[];
  /** Show the callouts block. Defaults to true. */
  showCallouts?: boolean;
}

/**
 * Render a doc. The structure is:
 *   ┌──────────────┬───────────────────────────────────────────┐
 *   │  rail (TOC)  │  prose body (H1, H2, H3, paragraphs, etc) │
 *   │              │  concept explainer callouts               │
 *   └──────────────┴───────────────────────────────────────────┘
 *
 * In a narrow viewport the rail collapses (its CSS uses min-width/max-width
 * and the parent Card lays it out beside the prose; below the threshold the
 * layout reflows naturally).
 */
export function DocViewer({ doc, explainers, showCallouts = true }: DocViewerProps) {
  const ast = parseMarkdown(doc.raw);
  const takenIds = new Set<string>();
  const callouts = explainers ?? buildConceptExplainers(doc.slug);
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 260px", gap: 24 }}>
      <div className="ax-prose">
        {ast.map((node, i) => (
          <RenderNode key={i} node={node} takenIds={takenIds} />
        ))}
        {showCallouts && callouts.length > 0 ? (
          <section
            id={`${doc.slug}-concepts`}
            aria-label="Concept explainers"
            style={{ marginTop: 32 }}
          >
            <h2>Concept explainers</h2>
            <p className="muted" style={{ fontSize: 12 }}>
              Inline cards that summarise the spine of {doc.title}. Each one jumps
              to the section it came from.
            </p>
            <ConceptCallouts explainers={callouts} />
          </section>
        ) : null}
      </div>
      <DocRail doc={doc} />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Doc list (the picker on the /docs landing)
// ─────────────────────────────────────────────────────────────────────────────

export interface DocListProps {
  docs: DocRef[];
  /** If set, the cards are anchors; otherwise each card is a link to /docs/[slug]. */
  basePath?: string;
}

export function DocList({ docs, basePath = "/docs" }: DocListProps) {
  return (
    <div className="ax-doc-list">
      {docs.map((doc) => (
        <a
          key={doc.slug}
          className="ax-doc-card"
          href={`${basePath}/${doc.slug}`}
        >
          <span className="ax-doc-card__eyebrow">design doc</span>
          <span className="ax-doc-card__title">{doc.title}</span>
          <span className="ax-doc-card__summary">{doc.summary}</span>
          <span className="ax-doc-card__meta">
            {doc.sourcePath} · {doc.headings.length} headings
          </span>
        </a>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Convenience wrapper used by the single-doc view at /docs/[slug]
// ─────────────────────────────────────────────────────────────────────────────

export interface DocPageProps {
  doc: DocRef;
}

export function DocPage({ doc }: DocPageProps) {
  const callouts = buildConceptExplainers(doc.slug);
  return (
    <Stack gap={5}>
      <Card>
        <CardHeader
          eyebrow={`design doc · ${doc.sourcePath}`}
          title={doc.title}
          subtitle={doc.summary}
        />
        <CardBody>
          <Cluster gap={2}>
            <span className="ax-data-pair__label mono dim" style={{ fontSize: 11 }}>
              {doc.sections.length} sections · {doc.headings.length} headings
            </span>
          </Cluster>
        </CardBody>
      </Card>
      <DocViewer doc={doc} explainers={callouts} />
    </Stack>
  );
}
