import { PortalPageClient } from "@/components/portal/portal-page-client";

export default async function PortalPageById({ params }: { params: Promise<{ pageId: string }> }) {
  const { pageId } = await params;
  return <PortalPageClient initialPageId={pageId} />;
}
