import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceCatalogSetupCard } from "../../components/workspace/workspace-catalog-setup-card";

describe("WorkspaceCatalogSetupCard", () => {
  it("submits display name and purpose without generating a local table name", async () => {
    const onAdd = vi.fn();
    render(<WorkspaceCatalogSetupCard entries={[]} onAdd={onAdd} />);

    await userEvent.type(screen.getByLabelText("Human Label"), "员工主数据");
    await userEvent.type(screen.getByLabelText("Table Purpose"), "存放员工主数据，用于人数、组织、职级等分析。");
    await userEvent.click(screen.getByRole("button", { name: "Add Table" }));

    expect(onAdd).toHaveBeenCalledTimes(1);
    expect(onAdd).toHaveBeenCalledWith(
      expect.objectContaining({
        tableName: "",
        humanLabel: "员工主数据",
        description: "存放员工主数据，用于人数、组织、职级等分析。",
      })
    );
  });
});
