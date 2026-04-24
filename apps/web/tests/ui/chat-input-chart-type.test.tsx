import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatInput } from "../../components/chat/chat-input";
import { useChatStore } from "../../stores/chat-store";
import { useUIStore } from "../../stores/ui-store";

const mutate = vi.fn();

vi.mock("../../hooks/use-chat", () => ({
  useSendMessage: () => ({ mutate }),
}));

describe("ChatInput chart type picker", () => {
  beforeEach(() => {
    mutate.mockReset();
    useChatStore.setState({
      composerText: "",
      pendingIngestionBySession: {},
    });
    useUIStore.setState({
      isSending: false,
    });
  });

  it("opens chart type suggestions on # and sends the selected chart_type", async () => {
    const user = userEvent.setup();
    render(React.createElement(ChatInput, { sessionId: "session-1" }));

    const input = screen.getByLabelText("Chat Input");
    await user.type(input, "#");

    expect(screen.getByRole("listbox", { name: "Chart type picker" })).toBeInTheDocument();
    expect(screen.getByText("Bar")).toBeInTheDocument();
    expect(screen.getByText("chart_type: bar")).toBeInTheDocument();

    await user.keyboard("{ArrowDown}{Enter}");
    expect(input).toHaveValue("#stacked_bar ");
    expect(screen.getByText("Selected chart_type: stacked_bar. Press Enter to send.")).toBeInTheDocument();

    await user.type(input, "show headcount by department");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        sessionId: "session-1",
        content: "#stacked_bar show headcount by department",
        preferredChartType: "stacked_bar",
      })
    );
  });
});
