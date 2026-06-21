/**
 * /docs — landing page for the C17 docs view.
 *
 * Shows the doc-list card grid (one card per registered design doc) plus a
 * quick-look at the BLUEPRINT concept explainers. The /docs/[slug] route
 * renders the full doc.
 */
import Link from "next/link";
import { BookOpen, ArrowRight } from "lucide-react";
import { AppShell } from "../../src/components/shell/app-shell";
import {
  Card,
  CardHeader,
  CardBody,
  Stack,
  Cluster,
  AsyncButton,
  StatusPill,
} from "../../src/components/ui";
import {
  DOC_REGISTRY,
  buildConceptExplainers,
  getDoc,
} from "../../src/lib/docs/registry";
import { ConceptCallouts } from "../../src/components/docs/doc-viewer";

export default function DocsPage() {
  const blueprint = getDoc("blueprint");
  const featuredExplainers = blueprint
    ? buildConceptExplainers(blueprint.slug)
    : [];
  return (
    <AppShell title="Docs" crumbs={[{ label: "Docs" }]}>
      <Stack gap={5}>
        <Card>
          <CardHeader
            eyebrow="C17"
            title="Design docs"
            subtitle="The four canonical Agent-X design documents, rendered in-app. Pick a doc to read, or jump straight into the BLUEPRINT."
            action={<StatusPill tone="info" dot>STATIC</StatusPill>}
          />
          <CardBody>
            <Cluster gap={2}>
              {DOC_REGISTRY.map((doc) => (
                <Link key={doc.slug} href={`/docs/${doc.slug}`}>
                  <AsyncButton
                    variant="secondary"
                    icon={<BookOpen size={14} />}
                  >
                    {doc.title}
                  </AsyncButton>
                </Link>
              ))}
            </Cluster>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            eyebrow="Library"
            title={`${DOC_REGISTRY.length} docs · ${DOC_REGISTRY.reduce((n, d) => n + d.headings.length, 0)} headings`}
            subtitle="Each card links to the full doc. Source path is the .md file the doc is rendered from — the text itself is embedded in the bundle so the page prerenders."
          />
          <CardBody>
            <div className="ax-doc-list">
              {DOC_REGISTRY.map((doc) => (
                <a key={doc.slug} className="ax-doc-card" href={`/docs/${doc.slug}`}>
                  <span className="ax-doc-card__eyebrow">design doc</span>
                  <span className="ax-doc-card__title">{doc.title}</span>
                  <span className="ax-doc-card__summary">{doc.summary}</span>
                  <span className="ax-doc-card__meta">
                    {doc.sourcePath} · {doc.headings.length} headings
                  </span>
                </a>
              ))}
            </div>
          </CardBody>
        </Card>

        {blueprint && featuredExplainers.length > 0 ? (
          <Card>
            <CardHeader
              eyebrow="Concept explainers"
              title="The spine of the Blueprint"
              subtitle="Six concepts that the rest of the docs keep coming back to. Each card jumps to the section in the BLUEPRINT where the idea is defined."
              action={
                <Link href={`/docs/blueprint`}>
                  <AsyncButton
                    variant="ghost"
                    icon={<ArrowRight size={14} />}
                  >
                    Read the Blueprint
                  </AsyncButton>
                </Link>
              }
            />
            <CardBody>
              <ConceptCallouts explainers={featuredExplainers} />
            </CardBody>
          </Card>
        ) : null}
      </Stack>
    </AppShell>
  );
}
