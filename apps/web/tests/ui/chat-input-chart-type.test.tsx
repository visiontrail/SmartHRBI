import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
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

  it("scrolls the chart type list as keyboard selection moves", async () => {
    const user = userEvent.setup();
    const scrollTo = vi.fn();
    const originalScrollTo = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollTo");
    const originalOffsetTop = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "offsetTop");
    const originalOffsetHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "offsetHeight");
    const originalClientHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight");

    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: scrollTo,
    });
    Object.defineProperty(HTMLElement.prototype, "offsetTop", {
      configurable: true,
      get() {
        const options = Array.from(document.querySelectorAll('[role="option"]'));
        return options.indexOf(this) * 40;
      },
    });
    Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
      configurable: true,
      get() {
        return this.getAttribute("role") === "option" ? 40 : 0;
      },
    });
    Object.defineProperty(HTMLElement.prototype, "clientHeight", {
      configurable: true,
      get() {
        return this.id === "chart-type-options" ? 120 : 0;
      },
    });

    try {
      render(React.createElement(ChatInput, { sessionId: "session-1" }));
      const input = screen.getByLabelText("Chat Input");

      await user.type(input, "#");
      scrollTo.mockClear();
      await user.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}");

      await waitFor(() => {
        expect(scrollTo).toHaveBeenCalledWith({ top: 40, behavior: "smooth" });
      });
    } finally {
      if (originalScrollTo) {
        Object.defineProperty(HTMLElement.prototype, "scrollTo", originalScrollTo);
      } else {
        Reflect.deleteProperty(HTMLElement.prototype, "scrollTo");
      }
      if (originalOffsetTop) {
        Object.defineProperty(HTMLElement.prototype, "offsetTop", originalOffsetTop);
      } else {
        Reflect.deleteProperty(HTMLElement.prototype, "offsetTop");
      }
      if (originalOffsetHeight) {
        Object.defineProperty(HTMLElement.prototype, "offsetHeight", originalOffsetHeight);
      } else {
        Reflect.deleteProperty(HTMLElement.prototype, "offsetHeight");
      }
      if (originalClientHeight) {
        Object.defineProperty(HTMLElement.prototype, "clientHeight", originalClientHeight);
      } else {
        Reflect.deleteProperty(HTMLElement.prototype, "clientHeight");
      }
    }
  });
});
