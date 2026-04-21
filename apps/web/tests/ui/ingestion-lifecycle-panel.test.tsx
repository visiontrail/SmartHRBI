import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { IngestionLifecyclePanel } from "../../components/chat/ingestion-lifecycle-panel";

const ingestionApiMocks = vi.hoisted(() => ({
  createIngestionUpload: vi.fn(),
  createIngestionPlan: vi.fn(),
  confirmIngestionSetup: vi.fn(),
  approveIngestionProposal: vi.fn(),
  executeIngestionProposal: vi.fn(),
}));

const {
  createIngestionUpload,
  createIngestionPlan,
  confirmIngestionSetup,
  approveIngestionProposal,
  executeIngestionProposal,
} = ingestionApiMocks;

vi.mock("../../lib/ingestion/api", () => {
  class MockIngestionApiError extends Error {
    code?: string;
    status: number;

    constructor(message: string, code?: string, status = 400) {
      super(message);
      this.code = code;
      this.status = status;
      this.name = "IngestionApiError";
    }
  }

  return {
    ...ingestionApiMocks,
    IngestionApiError: MockIngestionApiError,
  };
});

function sampleUploadResult() {
  return {
    uploadId: "upload-1",
    jobId: "job-1",
    workspaceId: "ws-1",
    status: "uploaded" as const,
    fileSummary: {
      fileName: "roster.xlsx",
      sizeBytes: 1024,
      fileHash: "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
      storagePath: "/tmp/roster.xlsx",
    },
    sheetSummary: {},
    columnSummary: {},
    samplePreview: [],
  };
}

function sampleProposalPlan() {
  return {
    status: "awaiting_user_approval" as const,
    workspaceId: "ws-1",
    jobId: "job-1",
    proposalId: "proposal-1",
    proposal: {
      businessType: "roster" as const,
      confidence: 0.9,
      recommendedAction: "update_existing" as const,
      candidateActions: ["update_existing", "time_partitioned_new_table", "new_table", "cancel"] as const,
      targetTable: "employee_roster",
      timeGrain: "none" as const,
      matchColumns: ["employee_id"],
      columnMapping: { "Employee ID": "employee_id" },
      diffPreview: {
        predictedInsertCount: 2,
        predictedUpdateCount: 1,
        predictedConflictCount: 0,
      },
      risks: ["Potential duplicate employee_id rows"],
      explanation: "matched",
      sqlDraft: "MERGE INTO employee_roster ...",
      requiresCatalogSetup: false,
      createdAt: "2026-04-17T00:00:00Z",
    },
    humanApproval: {
      required: true,
      mechanism: "frontend_approval_card",
      stage: "proposal_approval" as const,
      question: "是否将数据合并到现有花名册表？",
      options: ["update_existing", "time_partitioned_new_table", "new_table", "cancel"],
      recommendedOption: "update_existing",
    },
    route: { route: "write_ingestion", reason: "has_files" },
    toolTrace: [],
  };
}

describe("IngestionLifecyclePanel", () => {
  beforeEach(() => {
    createIngestionUpload.mockReset();
    createIngestionPlan.mockReset();
    confirmIngestionSetup.mockReset();
    approveIngestionProposal.mockReset();
    executeIngestionProposal.mockReset();
  });

  it("renders setup card when planning requires catalog setup", async () => {
    createIngestionUpload.mockResolvedValue(sampleUploadResult());
    createIngestionPlan.mockResolvedValue({
      status: "awaiting_catalog_setup",
      workspaceId: "ws-1",
      jobId: "job-1",
      agentGuess: { businessType: "roster", confidence: 0.8 },
      setupQuestions: [
        { questionId: "business_type", title: "Type", options: ["roster", "other"] },
        { questionId: "write_mode", title: "Mode", options: ["update_existing"] },
      ],
      suggestedCatalogSeed: {
        businessType: "roster",
        tableName: "employee_roster",
        humanLabel: "Employee Roster",
        writeMode: "update_existing",
        timeGrain: "none",
        primaryKeys: ["employee_id"],
        matchColumns: ["employee_id"],
        isActiveTarget: true,
        description: "seed",
      },
      humanApproval: {
        required: true,
        mechanism: "catalog_setup_card",
        stage: "catalog_setup" as const,
        question: "先确认目录设置再继续？",
        options: ["confirm_catalog_setup", "cancel"],
        recommendedOption: "confirm_catalog_setup",
      },
      route: { route: "write_ingestion", reason: "has_file" },
      toolTrace: [],
    });
    confirmIngestionSetup.mockResolvedValue(sampleProposalPlan());

    render(<IngestionLifecyclePanel workspaceId="ws-1" workspaceTitle="Ops Workspace" />);

    const file = new File(["demo"], "roster.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    await userEvent.upload(screen.getByTestId("ingestion-upload-input"), file);
    await userEvent.click(screen.getByRole("button", { name: "Upload & Plan" }));

    expect(await screen.findByTestId("ingestion-setup-flow")).toBeInTheDocument();
    expect(screen.getByText("Catalog setup is required before planning can continue.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Apply Setup" }));
    expect(await screen.findByTestId("ingestion-proposal-card")).toBeInTheDocument();
    expect(confirmIngestionSetup).toHaveBeenCalledTimes(1);
  });

  it("completes proposal approval and execution receipt flow", async () => {
    createIngestionUpload.mockResolvedValue(sampleUploadResult());
    createIngestionPlan.mockResolvedValue(sampleProposalPlan());
    approveIngestionProposal.mockResolvedValue({
      status: "approved",
      workspaceId: "ws-1",
      jobId: "job-1",
      proposalId: "proposal-1",
      approvedAction: "update_existing",
      targetTable: "employee_roster",
      timeGrain: "none",
      dryRunSummary: {
        approvedAction: "update_existing",
        targetTable: "employee_roster",
        timeGrain: "none",
        predictedInsertCount: 2,
        predictedUpdateCount: 1,
        predictedConflictCount: 0,
        predictedAffectedRows: 3,
        schemaWarnings: [],
        risks: [],
      },
    });
    executeIngestionProposal.mockResolvedValue({
      status: "succeeded",
      workspaceId: "ws-1",
      jobId: "job-1",
      proposalId: "proposal-1",
      executionId: "exec-1",
      receipt: {
        success: true,
        workspaceId: "ws-1",
        jobId: "job-1",
        targetTable: "employee_roster",
        executionMode: "update_existing",
        insertedRows: 2,
        updatedRows: 1,
        affectedRows: 3,
        rowsAfter: 10,
        duckdbPath: "/tmp/ws-1.duckdb",
        finishedAt: "2026-04-17T00:00:00Z",
      },
    });

    render(<IngestionLifecyclePanel workspaceId="ws-1" workspaceTitle="Ops Workspace" />);

    const file = new File(["demo"], "roster.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    await userEvent.upload(screen.getByTestId("ingestion-upload-input"), file);
    await userEvent.click(screen.getByRole("button", { name: "Upload & Plan" }));

    expect(await screen.findByTestId("ingestion-proposal-card")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "更新现有表" }));

    expect(await screen.findByTestId("ingestion-approved-card")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Execute Write" }));

    expect(await screen.findByTestId("ingestion-receipt-card")).toBeInTheDocument();
    expect(screen.getByText(/Target: employee_roster/)).toBeInTheDocument();

    await waitFor(() => {
      expect(approveIngestionProposal).toHaveBeenCalledTimes(1);
      expect(executeIngestionProposal).toHaveBeenCalledTimes(1);
    });
  });

  it("shows interpretable error state when upload fails", async () => {
    createIngestionUpload.mockRejectedValue(new Error("upload_failed_500"));

    render(<IngestionLifecyclePanel workspaceId="ws-1" workspaceTitle="Ops Workspace" />);

    const file = new File(["demo"], "roster.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    await userEvent.upload(screen.getByTestId("ingestion-upload-input"), file);
    await userEvent.click(screen.getByRole("button", { name: "Upload & Plan" }));

    expect(await screen.findByTestId("ingestion-error-card")).toHaveTextContent("upload_failed_500");
    expect(screen.getByText(/Ingestion failed at upload_or_plan/)).toBeInTheDocument();
  });
});
