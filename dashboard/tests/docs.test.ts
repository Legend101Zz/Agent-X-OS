import assert from "node:assert/strict";
import test from "node:test";

import {
  parseMarkdown,
  extractHeadings,
  extractSections,
} from "../src/lib/docs/markdown";
import {
  DOC_REGISTRY,
  getDoc,
  listDocs,
  buildConceptExplainers,
} from "../src/lib/docs/registry";

// ─────────────────────────────────────────────────────────────────────────────
// parseMarkdown
// ─────────────────────────────────────────────────────────────────────────────

test("parseMarkdown returns an empty array for empty input", () => {
  assert.deepEqual(parseMarkdown(""), []);
  assert.deepEqual(parseMarkdown("   \n\n  \n"), []);
});

test("parseMarkdown treats a top-level H1 as a heading node", () => {
  const ast = parseMarkdown("# Hello\n\nBody.");
  assert.equal(ast[0]?.kind, "heading");
  assert.equal(ast[0]?.level, 1);
  assert.equal(ast[0]?.text, "Hello");
  assert.equal(ast[1]?.kind, "paragraph");
  assert.equal(ast[1]?.text, "Body.");
});

test("parseMarkdown recognises H1–H4 with stable id slugs", () => {
  const md = `# A\n\n## B C\n\n### D-E\n\n#### F G H\n`;
  const ast = parseMarkdown(md);
  const headings = ast.filter((n) => n.kind === "heading");
  assert.deepEqual(
    headings.map((h) => ({ level: h.level, text: h.text, id: h.id })),
    [
      { level: 1, text: "A", id: "a" },
      { level: 2, text: "B C", id: "b-c" },
      { level: 3, text: "D-E", id: "d-e" },
      { level: 4, text: "F G H", id: "f-g-h" },
    ],
  );
});

test("parseMarkdown assigns unique ids to duplicate heading text", () => {
  const md = `## Foo\n\nbody\n\n## Foo\n\nmore\n`;
  const ast = parseMarkdown(md);
  const headings = ast.filter((n) => n.kind === "heading") as Array<{
    id: string;
    text: string;
  }>;
  assert.equal(headings.length, 2);
  assert.equal(headings[0]?.id, "foo");
  assert.equal(headings[1]?.id, "foo-1");
});

test("parseMarkdown recognises fenced code blocks with language and mono class", () => {
  const md = "```ts\nconst x: number = 1;\n```\n";
  const ast = parseMarkdown(md);
  assert.equal(ast[0]?.kind, "code");
  assert.equal(ast[0]?.lang, "ts");
  assert.match(ast[0]?.text ?? "", /const x: number = 1;/);
  assert.equal((ast[0] as { mono: boolean }).mono, true);
});

test("parseMarkdown recognises fenced text blocks (no language)", () => {
  const md = "```\nplain text fence\n```\n";
  const ast = parseMarkdown(md);
  assert.equal(ast[0]?.kind, "code");
  assert.equal((ast[0] as { lang?: string | null }).lang, null);
  assert.match(ast[0]?.text ?? "", /plain text fence/);
});

test("parseMarkdown recognises blockquotes starting with >", () => {
  const md = "> A note.\n> Still a note.\n";
  const ast = parseMarkdown(md);
  assert.equal(ast[0]?.kind, "blockquote");
  assert.match(ast[0]?.text ?? "", /A note\.\s*Still a note\./);
});

test("parseMarkdown recognises unordered lists with - markers", () => {
  const md = "- one\n- two\n- three\n";
  const ast = parseMarkdown(md);
  assert.equal(ast[0]?.kind, "list");
  assert.equal((ast[0] as { ordered: boolean }).ordered, false);
  assert.deepEqual((ast[0] as { items: string[] }).items, ["one", "two", "three"]);
});

test("parseMarkdown recognises ordered lists with N. markers", () => {
  const md = "1. alpha\n2. beta\n3. gamma\n";
  const ast = parseMarkdown(md);
  assert.equal(ast[0]?.kind, "list");
  assert.equal((ast[0] as { ordered: boolean }).ordered, true);
  assert.deepEqual((ast[0] as { items: string[] }).items, ["alpha", "beta", "gamma"]);
});

test("parseMarkdown recognises a horizontal rule", () => {
  const md = "above\n\n---\n\nbelow\n";
  const ast = parseMarkdown(md);
  assert.equal(ast[1]?.kind, "hr");
});

test("parseMarkdown handles a representative doc-shaped fixture", () => {
  const md = `# Title\n\nIntro.\n\n## Section A\n\n\`\`\`python\nprint(1)\n\`\`\`\n\n## Section B\n\n- x\n- y\n`;
  const ast = parseMarkdown(md);
  const kinds = ast.map((n) => n.kind);
  assert.deepEqual(kinds, ["heading", "paragraph", "heading", "code", "heading", "list"]);
});

// ─────────────────────────────────────────────────────────────────────────────
// extractHeadings / extractSections
// ─────────────────────────────────────────────────────────────────────────────

test("extractHeadings returns the flat heading list", () => {
  const md = `# A\n\n## B\n\n### C\n`;
  const ast = parseMarkdown(md);
  const heads = extractHeadings(ast);
  assert.deepEqual(
    heads.map((h) => h.text),
    ["A", "B", "C"],
  );
});

test("extractSections returns H2-level groupings under each H1", () => {
  const md = `# A\n\npara\n\n## A.1\n\n## A.2\n\n# B\n\n## B.1\n`;
  const ast = parseMarkdown(md);
  const sections = extractSections(ast);
  assert.equal(sections.length, 2);
  assert.equal(sections[0]?.title, "A");
  assert.deepEqual(
    sections[0]?.subsections.map((s) => s.title),
    ["A.1", "A.2"],
  );
  assert.equal(sections[1]?.title, "B");
  assert.deepEqual(
    sections[1]?.subsections.map((s) => s.title),
    ["B.1"],
  );
});

// ─────────────────────────────────────────────────────────────────────────────
// DOC_REGISTRY
// ─────────────────────────────────────────────────────────────────────────────

test("DOC_REGISTRY contains the four shipped design docs", () => {
  const slugs = listDocs().map((d) => d.slug).sort();
  assert.deepEqual(slugs, ["architecture", "blueprint", "mandate", "readme"]);
});

test("each registry doc has slug, title, source path, and parsed content", () => {
  for (const doc of listDocs()) {
    assert.ok(doc.slug.length > 0, "slug");
    assert.ok(doc.title.length > 0, "title");
    assert.ok(doc.sourcePath.endsWith(".md"), "sourcePath ends .md");
    assert.ok(doc.headings.length > 0, "has headings");
    assert.ok(doc.sections.length > 0, "has sections");
    assert.ok(doc.raw.length > 0, "has raw markdown");
  }
});

test("getDoc returns the BLUEPRINT doc for slug 'blueprint'", () => {
  const doc = getDoc("blueprint");
  assert.equal(doc?.title, "Agent-X — The Finalized Blueprint");
  assert.ok((doc?.headings.length ?? 0) > 5);
});

test("getDoc returns null for an unknown slug", () => {
  assert.equal(getDoc("nope"), null);
});

// ─────────────────────────────────────────────────────────────────────────────
// buildConceptExplainers
// ─────────────────────────────────────────────────────────────────────────────

test("buildConceptExplainers returns at least one explainer for BLUEPRINT", () => {
  const explainers = buildConceptExplainers("blueprint");
  assert.ok(explainers.length > 0);
  for (const ex of explainers) {
    assert.ok(ex.term.length > 0);
    assert.ok(ex.definition.length > 0);
    assert.ok(ex.anchorId.length > 0, "anchorId present");
  }
});

test("concept explainer anchor ids resolve to headings in the parent doc", () => {
  const explainers = buildConceptExplainers("blueprint");
  const doc = getDoc("blueprint");
  assert.ok(doc, "blueprint exists");
  const headingIds = new Set(doc!.headings.map((h) => h.id));
  for (const ex of explainers) {
    assert.ok(
      headingIds.has(ex.anchorId),
      `anchorId ${ex.anchorId} should resolve to a heading in BLUEPRINT`,
    );
  }
});
