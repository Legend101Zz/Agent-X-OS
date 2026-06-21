import { BlueprintInspector } from "../../../src/components/blueprints/blueprint-inspector";

export const dynamic = "force-dynamic";

interface BlueprintRefPageProps {
  params: Promise<{ ref: string }>;
}

export default async function BlueprintRefPage({ params }: BlueprintRefPageProps) {
  const { ref } = await params;
  return <BlueprintInspector typeRef={ref} />;
}