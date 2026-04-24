import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PublishedPageGrid } from "../../components/portal/published-page-grid";
import { PortalWorkspaceSidebar } from "../../components/portal/portal-workspace-sidebar";

vi.mock("../../components/charts/chart-preview", () => ({
  ChartPreview: () => <div>chart preview</div>,
}));

describe("Published portal components", () => {
  it("renders workspace cards and highlights the active page", async () => {
    const onSelect = vi.fn();
    render(
      <PortalWorkspaceSidebar
        activePageId="page-1"
        onSelect={onSelect}
        workspaces={[
          {
            workspace_id: "workspace-1",
            name: "People Ops",
            latest_page_id: "page-1",
            latest_version: 2,
            published_at: "2026-04-24T00:00:00+00:00",
          },
        ]}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /People Ops/i }));
    expect(onSelect).toHaveBeenCalledWith("page-1");
  });

  it("renders published grid zones and selects a chart", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        chart_id: "chart-1",
        spec: { chartType: "bar", title: "Headcount", echartsOption: {} },
        rows: [{ department: "HR", headcount: 4 }],
        data_truncated: false,
      }),
    } as Response);

    const onSelect = vi.fn();
    render(
      <PublishedPageGrid
        pageId="page-1"
        activeChartId={null}
        onSelectChart={onSelect}
        manifest={{
          layout: {
            grid: { columns: 2, rows: [{ id: "row-1", height: 240 }] },
            zones: [
              {
                id: "zone-1",
                nodeId: "node-1",
                chartId: "chart-1",
                column: 0,
                row: 0,
                colSpan: 1,
                rowSpan: 1,
              },
            ],
          },
          sidebar: [],
          charts: [{ chart_id: "chart-1", title: "Headcount" }],
        }}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /Headcount/i }));
    expect(onSelect).toHaveBeenCalledWith("chart-1", "Headcount");
  });
});
