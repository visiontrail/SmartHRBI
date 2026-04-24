import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PortalChatWindow } from "../../components/portal/portal-chat-window";

describe("PortalChatWindow", () => {
  it("shows selected chart context, sends messages, and clears chart context", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      text: async () => 'event: final\ndata: {"text":"Snapshot answer"}\n\n',
    } as Response);
    const onClearChart = vi.fn();

    render(
      <PortalChatWindow
        pageId="page-1"
        activeChartId="chart-1"
        activeChartTitle="Headcount"
        onClearChart={onClearChart}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: "Open portal chat" }));
    expect(screen.getByText(/Asking about: Headcount/)).toBeInTheDocument();

    await userEvent.type(screen.getByPlaceholderText("Ask a question..."), "What changed?");
    await userEvent.click(screen.getByRole("button", { name: "Send portal chat message" }));

    await waitFor(() => expect(screen.getByText("AI: Snapshot answer")).toBeInTheDocument());
    await userEvent.click(screen.getByText("clear"));
    expect(onClearChart).toHaveBeenCalled();
  });

  it("collapses and expands", async () => {
    render(
      <PortalChatWindow
        pageId="page-1"
        activeChartId={null}
        onClearChart={() => undefined}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: "Open portal chat" }));
    expect(screen.getByText("AI chat")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Collapse portal chat" }));
    expect(screen.getByRole("button", { name: "Open portal chat" })).toBeInTheDocument();
  });
});
