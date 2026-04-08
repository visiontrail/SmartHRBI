import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatWorkbench } from "../../components/workbench/chat-workbench";
import { createSSEEventStream } from "../test-helpers/sse";

const fetchMock = vi.fn<typeof fetch>();

describe("Workbench states", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    fetchMock.mockReset();
    window.localStorage.clear();
  });

  it("shows skeleton during stream and empty state for empty spec", async () => {
    let resolveFetch: ((value: Response) => void) | undefined;
    fetchMock.mockReturnValue(
      new Promise<Response>((resolve) => {
        resolveFetch = resolve;
      })
    );

    render(<ChatWorkbench apiBaseUrl="http://localhost:8000" />);
    await userEvent.type(screen.getByLabelText("Chat Input"), "query");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(screen.getByTestId("stream-skeleton")).toBeInTheDocument();

    resolveFetch?.(
      new Response(
        createSSEEventStream([
          {
            id: 1,
            event: "spec",
            data: {
              spec: {
                engine: "recharts",
                chart_type: "empty",
                title: "No chart",
                data: [],
                config: {}
              }
            }
          },
          {
            id: 2,
            event: "final",
            data: { status: "completed", text: "done" }
          }
        ])
      )
    );

    await screen.findByTestId("chart-empty");
  });

  it("shows a clear error state when stream request fails", async () => {
    fetchMock.mockRejectedValue(new Error("network_down"));

    render(<ChatWorkbench apiBaseUrl="http://localhost:8000" />);
    await userEvent.type(screen.getByLabelText("Chat Input"), "query");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    const errorPanel = await screen.findByTestId("chart-error");
    expect(errorPanel).toHaveTextContent("network_down");
  });
});
