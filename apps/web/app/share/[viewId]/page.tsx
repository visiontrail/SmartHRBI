import { ShareView } from "@/components/workbench/share-view";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type SharePageProps = {
  params: Promise<{ viewId: string }>;
};

export default async function SharePage({ params }: SharePageProps) {
  const { viewId } = await params;
  return <ShareView apiBaseUrl={apiBaseUrl} viewId={viewId} />;
}
