import { PortalPageClient } from "@/components/portal/portal-page-client";

export default async function PortalPage({
  searchParams,
}: {
  searchParams?: Promise<{ page?: string }>;
}) {
  const params = searchParams ? await searchParams : {};
  return <PortalPageClient initialPageId={params.page} />;
}
