/**
 * /docs/[slug] — render a single design doc.
 *
 * Slug comes from the route param. The doc registry holds the parsed AST
 * data; the renderer in src/components/docs/doc-viewer turns it into
 * headings, paragraphs, lists, code, and inline concept callouts.
 */
import { notFound } from "next/navigation";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { AppShell } from "../../../src/components/shell/app-shell";
import { AsyncButton } from "../../../src/components/ui";
import {
  DOC_REGISTRY,
  getDoc,
  buildConceptExplainers,
} from "../../../src/lib/docs/registry";
import { DocViewer } from "../../../src/components/docs/doc-viewer";

export function generateStaticParams() {
  return DOC_REGISTRY.map((d) => ({ slug: d.slug }));
}

export function generateMetadata({ params }: { params: { slug: string } }) {
  const doc = getDoc(params.slug);
  if (!doc) return { title: "Doc not found — Agent-X" };
  return {
    title: `${doc.title} — Agent-X Docs`,
    description: doc.summary,
  };
}

export default function DocDetailPage({
  params,
}: {
  params: { slug: string };
}) {
  const doc = getDoc(params.slug);
  if (!doc) {
    notFound();
  }
  const callouts = buildConceptExplainers(doc.slug);
  const crumbs = [{ label: "Docs", href: "/docs" }, { label: doc.title }];
  return (
    <AppShell title={doc.title} crumbs={crumbs}>
      <div style={{ marginBottom: 16 }}>
        <Link href="/docs">
          <AsyncButton
            variant="ghost"
            size="sm"
            icon={<ChevronLeft size={14} />}
          >
            All docs
          </AsyncButton>
        </Link>
      </div>
      <DocViewer doc={doc} explainers={callouts} />
    </AppShell>
  );
}
