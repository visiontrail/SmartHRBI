import type { ReactNode } from "react";

type PanelProps = {
  title: string;
  description: string;
  children?: ReactNode;
  testId?: string;
};

function BasePanel({ title, description, children, testId }: PanelProps) {
  return (
    <section className="genui-panel genui-panel--state" data-testid={testId}>
      <h3>{title}</h3>
      <p>{description}</p>
      {children}
    </section>
  );
}

export function SkeletonPanel() {
  return (
    <section className="genui-panel genui-panel--skeleton" data-testid="stream-skeleton">
      <div className="skeleton-line" />
      <div className="skeleton-line" />
      <div className="skeleton-line skeleton-line--short" />
    </section>
  );
}

export function EmptyPanel({ title = "No Data" }: { title?: string }) {
  return (
    <BasePanel
      title={title}
      description="当前查询暂无可视化数据，请调整筛选条件或重新提问。"
      testId="chart-empty"
    />
  );
}

export function ErrorPanel({
  title = "Render Failed",
  description = "组件规范不合法或渲染过程失败。"
}: {
  title?: string;
  description?: string;
}) {
  return <BasePanel title={title} description={description} testId="chart-error" />;
}
