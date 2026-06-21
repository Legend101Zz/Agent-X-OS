import { GymDetail } from "../../../src/components/gym/gym-detail";

export const dynamic = "force-dynamic";

interface GymDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function GymDetailPage({ params }: GymDetailPageProps) {
  const { id } = await params;
  return <GymDetail caseId={decodeURIComponent(id)} />;
}