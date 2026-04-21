import { expect, test } from "@playwright/test";

type SSEEvent = {
  id: number;
  event: string;
  data: Record<string, unknown>;
};

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "*"
};

const jsonHeaders = {
  ...corsHeaders,
  "Content-Type": "application/json"
};

test("covers upload -> query -> save -> share rehydration flow", async ({ page }) => {
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    const method = request.method();
    const url = new URL(request.url());

    if (method === "OPTIONS") {
      await route.fulfill({ status: 204, headers: corsHeaders, body: "" });
      return;
    }

    if (url.pathname === "/auth/login" && method === "POST") {
      await route.fulfill({
        status: 200,
        headers: jsonHeaders,
        body: JSON.stringify({
          access_token: "e2e-token",
          token_type: "bearer",
          expires_at: 4102444800
        })
      });
      return;
    }

    if (url.pathname === "/chat/stream" && method === "POST") {
      await route.fulfill({
        status: 200,
        headers: {
          ...corsHeaders,
          "Content-Type": "text/event-stream"
        },
        body: buildSSEPayload([
          {
            id: 1,
            event: "reasoning",
            data: {
              text: "Intent analyzed. Selected tool: query_metrics.",
              tool_name: "query_metrics"
            }
          },
          {
            id: 2,
            event: "tool",
            data: {
              tool_name: "query_metrics",
              status: "success",
              attempts: 1
            }
          },
          {
            id: 3,
            event: "spec",
            data: {
              spec: {
                engine: "recharts",
                chart_type: "bar",
                title: "Headcount by Department",
                data: [
                  { department: "HR", metric_value: 24 },
                  { department: "PM", metric_value: 18 }
                ],
                config: { xKey: "department", yKey: "metric_value" }
              }
            }
          },
          {
            id: 4,
            event: "final",
            data: {
              status: "completed",
              text: "Query completed for metric headcount_total, rows=2."
            }
          }
        ])
      });
      return;
    }

    if (url.pathname === "/views" && method === "POST") {
      await route.fulfill({
        status: 200,
        headers: jsonHeaders,
        body: JSON.stringify({
          view_id: "view-e2e",
          share_url: "/share/view-e2e",
          share_path: "/share/view-e2e",
          version: 1
        })
      });
      return;
    }

    if (url.pathname === "/share/view-e2e" && method === "GET") {
      await route.fulfill({
        status: 200,
        headers: jsonHeaders,
        body: JSON.stringify({
          view_id: "view-e2e",
          title: "Shared Snapshot",
          current_version: 1,
          owner_user_id: "demo-user",
          updated_at: "2026-04-08T12:00:00Z",
          ai_state: {
            active_spec: {
              engine: "recharts",
              chart_type: "bar",
              title: "Headcount by Department",
              data: [
                { department: "HR", metric_value: 24 },
                { department: "PM", metric_value: 18 }
              ],
              config: { xKey: "department", yKey: "metric_value" }
            },
            messages: [
              { id: "m-1", role: "assistant", text: "headcount trend looks stable" }
            ]
          }
        })
      });
      return;
    }

    await route.fulfill({
      status: 404,
      headers: jsonHeaders,
      body: JSON.stringify({ code: "NOT_FOUND" })
    });
  });

  await page.goto("/");

  const datasetTable = "employee_roster";

  await page.getByLabel("Dataset Table").fill(datasetTable);

  await page.getByLabel("Chat Input").fill("show headcount by department");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByRole("heading", { name: "Headcount by Department" })).toBeVisible();
  await expect(page.getByText("Query completed for metric headcount_total, rows=2.")).toBeVisible();
  await expect(page.getByTestId("tool-status")).toContainText("query_metrics");

  await page.getByRole("button", { name: "Save & Share" }).click();

  const link = page.getByRole("link", { name: "/share/view-e2e" });
  await expect(link).toBeVisible();
  const sharePath = await link.getAttribute("href");
  expect(sharePath).toBe("/share/view-e2e");
  await page.goto(String(sharePath));

  await expect(page).toHaveURL(/\/share\/view-e2e$/);
  await expect(page.getByRole("heading", { name: "Shared Snapshot" })).toBeVisible();
  await expect(page.getByText("headcount trend looks stable")).toBeVisible();
});

function buildSSEPayload(events: SSEEvent[]): string {
  return events
    .map((event) => {
      const data = JSON.stringify(event.data);
      return `id: ${event.id}\nevent: ${event.event}\ndata: ${data}\n\n`;
    })
    .join("");
}
