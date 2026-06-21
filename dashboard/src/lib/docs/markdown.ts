/**
 * docs/markdown.ts — minimal, deterministic Markdown → AST parser.
 *
 * Scope is deliberately narrow: just enough to render the four Agent-X design
 * docs (BLUEPRINT, MANDATE, README, ARCHITECTURE) in the dashboard. We do NOT
 * pull in a markdown library — these docs are authored in a stable shape (H1
 * title, H2/H3/H4 sections, fenced code blocks with optional language,
 * paragraphs, ordered/unordered lists, blockquotes, horizontal rules) and a
 * hand-rolled parser keeps the bundle small, the test surface tight, and the
 * rendering predictable.
 *
 * AST node kinds: heading | paragraph | code | blockquote | list | hr
 *
 * Each node has a `kind` discriminator; readers should narrow with that.
 */

export type DocNode =
  | { kind: "heading"; level: 1 | 2 | 3 | 4; text: string; id: string }
  | { kind: "paragraph"; text: string }
  | { kind: "code"; lang: string | null; text: string; mono: true }
  | { kind: "blockquote"; text: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "hr" };

export interface DocHeading {
  level: 1 | 2 | 3 | 4;
  text: string;
  id: string;
}

export interface DocSubsection {
  /** Heading level of this subsection (always 2 in the current extractor). */
  level: 2 | 3;
  /** Heading text, the way the reader sees it. */
  title: string;
  /** Stable anchor id slugified from the heading text. */
  id: string;
}

export interface DocSection {
  title: string;
  titleId: string;
  /** Top-level (H2) subsections under this H1. */
  subsections: DocSubsection[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Slug helper — produces URL-safe ids and stays deterministic for duplicates.
// ─────────────────────────────────────────────────────────────────────────────

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/`/g, "")
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

// ─────────────────────────────────────────────────────────────────────────────
// Parser
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Parse a markdown string into a flat list of DocNodes. Whitespace and blank
 * lines are normalised; the parser never throws on malformed input — it
 * returns whatever it can.
 */
export function parseMarkdown(input: string): DocNode[] {
  if (!input) return [];
  const lines = input.replace(/\r\n?/g, "\n").split("\n");
  const out: DocNode[] = [];
  let i = 0;
  let paraBuf: string[] = [];
  let quoteBuf: string[] = [];

  const flushPara = () => {
    if (paraBuf.length === 0) return;
    const text = paraBuf.join(" ").replace(/\s+/g, " ").trim();
    if (text) out.push({ kind: "paragraph", text });
    paraBuf = [];
  };

  const flushQuote = () => {
    if (quoteBuf.length === 0) return;
    const text = quoteBuf.join("\n").trim();
    if (text) out.push({ kind: "blockquote", text });
    quoteBuf = [];
  };

  while (i < lines.length) {
    const raw = lines[i] ?? "";
    const line = raw.replace(/\s+$/, "");

    // Blank line — flush current buffer.
    if (line.trim() === "") {
      flushPara();
      flushQuote();
      i++;
      continue;
    }

    // Horizontal rule.
    if (/^---+\s*$/.test(line) || /^\*\*\*+\s*$/.test(line)) {
      flushPara();
      flushQuote();
      out.push({ kind: "hr" });
      i++;
      continue;
    }

    // Heading.
    const h = /^(#{1,4})\s+(.+?)\s*#*\s*$/.exec(line);
    if (h) {
      flushPara();
      flushQuote();
      const level = h[1]!.length as 1 | 2 | 3 | 4;
      const text = stripInline(h[2] ?? "").trim();
      out.push({ kind: "heading", level, text, id: "__pending__" });
      i++;
      continue;
    }

    // Fenced code block.
    const fence = /^```([A-Za-z0-9_+-]*)\s*$/.exec(line);
    if (fence) {
      flushPara();
      flushQuote();
      const lang = fence[1] || null;
      const buf: string[] = [];
      i++;
      while (i < lines.length) {
        const close = /^```\s*$/.exec(lines[i] ?? "");
        if (close) {
          i++;
          break;
        }
        buf.push(lines[i] ?? "");
        i++;
      }
      out.push({ kind: "code", lang, text: buf.join("\n"), mono: true });
      continue;
    }

    // Blockquote (one or more consecutive `> ` lines).
    if (/^>\s?/.test(line)) {
      flushPara();
      quoteBuf.push(line.replace(/^>\s?/, ""));
      i++;
      continue;
    }

    // Unordered list.
    if (/^[-*]\s+/.test(line)) {
      flushPara();
      flushQuote();
      const items: string[] = [];
      while (i < lines.length) {
        const cur = (lines[i] ?? "").replace(/\s+$/, "");
        const m = /^[-*]\s+(.+)$/.exec(cur);
        if (!m) break;
        items.push(stripInline(m[1] ?? "").trim());
        i++;
      }
      out.push({ kind: "list", ordered: false, items });
      continue;
    }

    // Ordered list.
    if (/^\d+\.\s+/.test(line)) {
      flushPara();
      flushQuote();
      const items: string[] = [];
      while (i < lines.length) {
        const cur = (lines[i] ?? "").replace(/\s+$/, "");
        const m = /^\d+\.\s+(.+)$/.exec(cur);
        if (!m) break;
        items.push(stripInline(m[1] ?? "").trim());
        i++;
      }
      out.push({ kind: "list", ordered: true, items });
      continue;
    }

    // Default — paragraph text.
    flushQuote();
    paraBuf.push(stripInline(line).trim());
    i++;
  }

  flushPara();
  flushQuote();

  // Second pass: assign deterministic ids to headings, de-duping collisions.
  const seen = new Map<string, number>();
  return out.map((node) => {
    if (node.kind !== "heading") return node;
    const base = slugify(node.text) || "section";
    const count = seen.get(base) ?? 0;
    seen.set(base, count + 1);
    const id = count === 0 ? base : `${base}-${count}`;
    return { ...node, id };
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Inline stripping — keep prose readable but drop link targets / emphasis
// markers. (We never emit inline links in the docs viewer; we surface whole
// docs as static markdown for now.)
// ─────────────────────────────────────────────────────────────────────────────

function stripInline(text: string): string {
  return text
    // `[label](url)` → `label`
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    // `code` → `code` (kept literal — the renderer styles them).
    .replace(/`([^`]+)`/g, "$1")
    // **bold** / *italic* → plain
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    // leading/trailing whitespace per line
    .replace(/\s+/g, " ");
}

// ─────────────────────────────────────────────────────────────────────────────
// extractHeadings / extractSections
// ─────────────────────────────────────────────────────────────────────────────

export function extractHeadings(ast: DocNode[]): DocHeading[] {
  const out: DocHeading[] = [];
  for (const node of ast) {
    if (node.kind === "heading") {
      out.push({ level: node.level, text: node.text, id: node.id });
    }
  }
  return out;
}

/**
 * Group the flat AST into H1 sections, each with its H2-level subsections.
 * Subsections are H2 only — H3/H4 headings appear in `extractHeadings` and
 * are rendered inline within their parent H2 in the UI.
 */
export function extractSections(ast: DocNode[]): DocSection[] {
  const sections: DocSection[] = [];
  let current: DocSection | null = null;

  for (const node of ast) {
    if (node.kind !== "heading") continue;
    if (node.level === 1) {
      current = { title: node.text, titleId: node.id, subsections: [] };
      sections.push(current);
    } else if (node.level === 2 && current) {
      current.subsections.push({
        level: 2,
        title: node.text,
        id: node.id,
      });
    }
  }
  return sections;
}
