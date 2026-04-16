import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceOnboardingGate } from "../../components/shared/workspace-onboarding-gate";

describe("WorkspaceOnboardingGate", () => {
  it("uses a default workspace name when input is blank", async () => {
    const onCreate = vi.fn();
    render(React.createElement(WorkspaceOnboardingGate, { onCreate, isSubmitting: false }));

    await userEvent.click(screen.getByRole("button", { name: "Create Workspace" }));

    expect(onCreate).toHaveBeenCalledWith("My Workspace");
  });

  it("submits trimmed workspace name", async () => {
    const onCreate = vi.fn();
    render(React.createElement(WorkspaceOnboardingGate, { onCreate, isSubmitting: false }));

    await userEvent.type(screen.getByLabelText("Workspace Name"), "  Finance Team  ");
    await userEvent.click(screen.getByRole("button", { name: "Create Workspace" }));

    expect(onCreate).toHaveBeenCalledWith("Finance Team");
  });
});
