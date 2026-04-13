import type { ReactNode } from "react";

type PanelProps = {
  title: string;
  description: string;
  children?: ReactNode;
  testId?: string;
};

function BasePanel({ title, description, children, testId }: PanelProps) {
  return (
    <section
      className="rounded-comfortable border border-border-cream bg-ivory p-4"
      data-testid={testId}
    >
      <h3 className="text-body font-medium text-near-black mb-1">{title}</h3>
      <p className="text-caption text-olive-gray">{description}</p>
      {children}
    </section>
  );
}

export function SkeletonPanel() {
  return (
    <section
      className="rounded-comfortable border border-border-cream bg-ivory p-4 space-y-3"
      data-testid="stream-skeleton"
    >
      <div className="h-4 w-3/4 bg-warm-sand rounded animate-pulse" />
      <div className="h-4 w-full bg-warm-sand rounded animate-pulse" />
      <div className="h-4 w-1/2 bg-warm-sand rounded animate-pulse" />
    </section>
  );
}

export function EmptyPanel({ title = "No Data" }: { title?: string }) {
  return (
    <BasePanel
      title={title}
      description="No visualization data available for this query. Try adjusting your question."
      testId="chart-empty"
    />
  );
}

export function ErrorPanel({
  title = "Render Failed",
  description = "The chart specification is invalid or rendering failed.",
}: {
  title?: string;
  description?: string;
}) {
  return <BasePanel title={title} description={description} testId="chart-error" />;
}
