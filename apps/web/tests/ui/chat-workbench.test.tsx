import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatWorkbench } from "../../components/workbench/chat-workbench";
import { SESSION_STORAGE_KEY } from "../../lib/chat/session-storage";
import { createSSEEventStream } from "../test-helpers/sse";

const fetchMock = vi.fn<typeof fetch>();
const AUTH_EXPIRES_AT = 4102444800;

function createLoginResponse(accessToken = "token-123") {
  return new Response(
    JSON.stringify({
      access_token: accessToken,
      token_type: "bearer",
      expires_at: AUTH_EXPIRES_AT
    }),
    { status: 200, headers: { "Content-Type": "application/json" } }
  );
}

describe("Chat workbench streaming UI", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    window.localStorage.clear();
    fetchMock.mockReset();
  });

  it("consumes streaming events and renders chat + chart incrementally", async () => {
    fetchMock
      .mockResolvedValueOnce(createLoginResponse())
      .mockResolvedValueOnce(
        new Response(
          createSSEEventStream([
            {
              id: 1,
              event: "reasoning",
              data: { text: "Intent analyzed. Selected tool: query_metrics." }
            },
            {
              id: 2,
              event: "tool",
              data: { tool_name: "query_metrics", status: "success", attempts: 1 }
            },
            {
              id: 3,
              event: "spec",
              data: {
                spec: {
                  engine: "recharts",
                  chart_type: "bar",
                  title: "Attrition Rate",
                  data: [{ department: "RD", metric_value: 0.12 }],
                  config: { xKey: "department", yKey: "metric_value" }
                }
              }
            },
            {
              id: 4,
              event: "final",
              data: { status: "completed", text: "Query completed for metric attrition_rate." }
            }
          ])
        )
      );

    render(<ChatWorkbench apiBaseUrl="http://localhost:8000" />);
    await userEvent.type(screen.getByLabelText("Chat Input"), "show attrition by department");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText("Intent analyzed. Selected tool: query_metrics.");
    await screen.findByText("Query completed for metric attrition_rate.");
    expect(screen.getByText("Attrition Rate")).toBeInTheDocument();
    expect(screen.getByTestId("tool-status")).toHaveTextContent("query_metrics");
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/chat/stream",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer token-123"
        })
      })
    );
  }, 10000);

  it("saves current view and exposes share link", async () => {
    fetchMock
      .mockResolvedValueOnce(createLoginResponse())
      .mockResolvedValueOnce(
        new Response(
          createSSEEventStream([
            {
              id: 1,
              event: "spec",
              data: {
                spec: {
                  engine: "recharts",
                  chart_type: "bar",
                  title: "Headcount",
                  data: [{ department: "HR", metric_value: 10 }],
                  config: { xKey: "department", yKey: "metric_value" }
                }
              }
            },
            { id: 2, event: "final", data: { status: "completed", text: "done" } }
          ])
        )
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            view_id: "view-1",
            share_url: "/share/view-1",
            share_path: "/share/view-1",
            version: 1
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );

    render(<ChatWorkbench apiBaseUrl="http://localhost:8000" />);
    await userEvent.type(screen.getByLabelText("Chat Input"), "show headcount");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText("Headcount");
    await userEvent.click(screen.getByRole("button", { name: "Save & Share" }));

    await screen.findByText("Share Link:");
    expect(screen.getByRole("link", { name: "/share/view-1" })).toHaveAttribute("href", "/share/view-1");
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://localhost:8000/views",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer token-123"
        })
      })
    );
  });

  it("rehydrates the last session from local storage", async () => {
    window.localStorage.setItem(
      SESSION_STORAGE_KEY,
      JSON.stringify({
        conversationId: "conv-1",
        userId: "u-1",
        projectId: "p-1",
        role: "hr",
        department: "HR",
        clearance: 1,
        datasetTable: "employees_wide",
        composer: "restored question",
        messages: [{ id: "m-1", role: "assistant", text: "restored message" }],
        activeSpec: {
          engine: "recharts",
          chart_type: "single_value",
          title: "Restored KPI",
          data: [{ metric_value: 42 }],
          config: { yKey: "metric_value" }
        },
        lastToolEvent: { tool_name: "query_metrics", status: "success" }
      })
    );

    fetchMock
      .mockResolvedValueOnce(createLoginResponse())
      .mockResolvedValueOnce(
        new Response(createSSEEventStream([{ id: 1, event: "final", data: { status: "completed", text: "done" } }]))
      );

    render(<ChatWorkbench apiBaseUrl="http://localhost:8000" />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("restored question")).toBeInTheDocument();
      expect(screen.getByText("restored message")).toBeInTheDocument();
      expect(screen.getByText("Restored KPI")).toBeInTheDocument();
      expect(screen.getByTestId("tool-status")).toHaveTextContent("query_metrics");
    });
  });

  it("uploads excel files and switches the active dataset table", async () => {
    fetchMock
      .mockResolvedValueOnce(createLoginResponse())
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            batch_id: "batch-1",
            dataset_table: "dataset_batch_1",
            file_count: 1,
            diagnostics: {
              result_row_count: 12,
              result_column_count: 4
            }
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            batch_id: "batch-1",
            summary: {
              row_count: 12,
              column_count: 4
            },
            blocking_issues: [],
            can_publish_to_semantic_layer: true
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );

    render(<ChatWorkbench apiBaseUrl="http://localhost:8000" />);

    const uploadInput = screen.getByLabelText("Excel Upload");
    const file = new File(["sheet"], "employees.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    });

    await userEvent.upload(uploadInput, file);
    await userEvent.click(screen.getByRole("button", { name: "Upload Excel" }));

    await waitFor(() => {
      expect(screen.getByDisplayValue("dataset_batch_1")).toBeInTheDocument();
    });
    expect(screen.getByTestId("upload-summary")).toHaveTextContent("Semantic layer ready");
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/datasets/upload",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer token-123"
        }),
        body: expect.any(FormData)
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://localhost:8000/datasets/batch-1/quality-report",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer token-123"
        })
      })
    );
  });
});
