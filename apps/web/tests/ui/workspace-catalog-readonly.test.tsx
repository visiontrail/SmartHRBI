import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WorkspaceCatalogReadonly } from "../../components/workspace/workspace-catalog-readonly";

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("WorkspaceCatalogReadonly", () => {
  it("renders readonly table catalog entries for a workspace", async () => {
    renderWithProviders(<WorkspaceCatalogReadonly workspaceId="ws-1" />);

    expect(await screen.findByText("Employees Roster")).toBeInTheDocument();
    expect(screen.getByText(/project_progress/)).toBeInTheDocument();
    expect(screen.getAllByText("Active")).toHaveLength(2);
  });

  it("renders empty state when workspace has no catalog entries", async () => {
    renderWithProviders(<WorkspaceCatalogReadonly workspaceId="ws-empty" />);

    expect(await screen.findByText("No catalog entries yet. Complete setup to add one.")).toBeInTheDocument();
  });
});
