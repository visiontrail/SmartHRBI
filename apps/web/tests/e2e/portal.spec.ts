import { expect, test } from "@playwright/test";

test("portal loads a published workspace and sends a chart-scoped chat message", async ({ page }) => {
  await page.route("**/portal/workspaces", async (route) => {
    await route.fulfill({
      json: {
        count: 1,
        workspaces: [
          {
            workspace_id: "workspace-1",
            name: "People Ops",
            latest_page_id: "page-1",
            latest_version: 1,
            published_at: "2026-04-24T00:00:00+00:00",
          },
        ],
      },
    });
  });
  await page.route("**/portal/pages/page-1/manifest", async (route) => {
    await route.fulfill({
      json: {
        page_id: "page-1",
        workspace_id: "workspace-1",
        version: 1,
        published_at: "2026-04-24T00:00:00+00:00",
        manifest: {
          layout: {
            grid: { columns: 2, rows: [{ id: "row-1", height: 260 }] },
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
          sidebar: [{ id: "overview", label: "Overview", anchorRowId: "row-1", children: [] }],
          charts: [{ chart_id: "chart-1", title: "Headcount", chart_type: "bar" }],
        },
      },
    });
  });
  await page.route("**/portal/pages/page-1/charts/chart-1/data", async (route) => {
    await route.fulfill({
      json: {
        page_id: "page-1",
        chart_id: "chart-1",
        spec: { chartType: "bar", title: "Headcount", echartsOption: { xAxis: {}, yAxis: {}, series: [] } },
        rows: [{ department: "HR", headcount: 4 }],
        data_truncated: false,
      },
    });
  });
  await page.route("**/portal/pages/page-1/chat", async (route) => {
    await route.fulfill({
      contentType: "text/event-stream",
      body: 'event: final\ndata: {"text":"Headcount is 4."}\n\n',
    });
  });

  await page.goto("/portal");
  await page.getByRole("button", { name: /People Ops/i }).click();
  await page.getByRole("button", { name: /Headcount/i }).click();
  await page.getByRole("button", { name: "Open portal chat" }).click();
  await expect(page.getByText(/Asking about: Headcount/)).toBeVisible();
  await page.getByPlaceholder("Ask a question...").fill("What is the headcount?");
  await page.getByRole("button", { name: "Send portal chat message" }).click();
  await expect(page.getByText("AI: Headcount is 4.")).toBeVisible();
});
