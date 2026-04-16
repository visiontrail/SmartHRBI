import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { IngestionSetupCard } from "../../components/workspace/ingestion-setup-card";

const DEFAULT_SEED = {
  businessType: "roster" as const,
  tableName: "employee_roster",
  humanLabel: "Employee Roster",
  writeMode: "update_existing" as const,
  timeGrain: "none" as const,
  primaryKeys: ["employee_id"],
  matchColumns: ["employee_id"],
  isActiveTarget: true,
  description: "seed",
};

describe("IngestionSetupCard", () => {
  it("submits normalized setup seed", async () => {
    const onConfirm = vi.fn();
    render(<IngestionSetupCard initialSeed={DEFAULT_SEED} onConfirm={onConfirm} />);

    await userEvent.clear(screen.getByLabelText("Table Name"));
    await userEvent.type(screen.getByLabelText("Table Name"), "  Employee_Roster_2026  ");
    await userEvent.click(screen.getByRole("button", { name: "Apply Setup" }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({
        tableName: "employee_roster_2026",
        primaryKeys: ["employee_id"],
        matchColumns: ["employee_id"],
      })
    );
  });

  it("shows validation error when no key columns are configured", async () => {
    const onConfirm = vi.fn();
    render(
      <IngestionSetupCard
        initialSeed={{
          ...DEFAULT_SEED,
          primaryKeys: [],
          matchColumns: [],
        }}
        onConfirm={onConfirm}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: "Apply Setup" }));

    expect(onConfirm).not.toHaveBeenCalled();
    expect(
      screen.getByText("At least one primary key or match column is required.")
    ).toBeInTheDocument();
  });
});
