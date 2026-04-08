import { ShareView } from "../../../components/workbench/share-view";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type SharePageProps = {
  params: {
    viewId: string;
  };
};

export default function SharePage({ params }: SharePageProps) {
  return <ShareView apiBaseUrl={apiBaseUrl} viewId={params.viewId} />;
}
