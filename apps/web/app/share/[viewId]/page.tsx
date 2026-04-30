import { ShareView } from "@/components/workbench/share-view";
import { API_BASE_URL } from "@/lib/api-base";

const apiBaseUrl = API_BASE_URL;

type SharePageProps = {
  params: Promise<{ viewId: string }>;
};

export default async function SharePage({ params }: SharePageProps) {
  const { viewId } = await params;
  return <ShareView apiBaseUrl={apiBaseUrl} viewId={viewId} />;
}
