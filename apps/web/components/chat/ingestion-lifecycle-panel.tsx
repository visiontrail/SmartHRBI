"use client";

import { ChangeEvent, useMemo, useState } from "react";
import { Loader2, Upload, AlertTriangle, CheckCircle2, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type {
  IngestionApprovalResult,
  IngestionCatalogSetupSeed,
  IngestionExecuteResult,
  IngestionLifecyclePhase,
  IngestionPlanAwaitingApproval,
  IngestionPlanAwaitingSetup,
  IngestionProposalAction,
  IngestionTimeGrain,
  IngestionUploadResult,
} from "@/types/ingestion";
import {
  approveIngestionProposal,
  confirmIngestionSetup,
  createIngestionPlan,
  createIngestionUpload,
  executeIngestionProposal,
  IngestionApiError,
} from "@/lib/ingestion/api";
import { IngestionSetupCard } from "@/components/workspace/ingestion-setup-card";

type IngestionLifecyclePanelProps = {
  workspaceId: string;
  workspaceTitle?: string | null;
};

type IngestionErrorState = {
  stage: string;
  message: string;
  code?: string;
};

type ProposalActionButton = {
  label: string;
  approvedAction: IngestionProposalAction;
  timeGrain?: IngestionTimeGrain;
};

const PROPOSAL_ACTION_BUTTONS: ProposalActionButton[] = [
  { label: "更新现有表", approvedAction: "update_existing" },
  { label: "按月新建", approvedAction: "time_partitioned_new_table", timeGrain: "month" },
  { label: "按季度新建", approvedAction: "time_partitioned_new_table", timeGrain: "quarter" },
  { label: "按年新建", approvedAction: "time_partitioned_new_table", timeGrain: "year" },
  { label: "创建独立新表", approvedAction: "new_table" },
  { label: "取消", approvedAction: "cancel" },
];

export function IngestionLifecyclePanel({ workspaceId, workspaceTitle }: IngestionLifecyclePanelProps) {
  const [phase, setPhase] = useState<IngestionLifecyclePhase>("idle");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadResult, setUploadResult] = useState<IngestionUploadResult | null>(null);
  const [setupPayload, setSetupPayload] = useState<IngestionPlanAwaitingSetup | null>(null);
  const [approvalPayload, setApprovalPayload] = useState<IngestionPlanAwaitingApproval | null>(null);
  const [approvedResult, setApprovedResult] = useState<IngestionApprovalResult | null>(null);
  const [executeResult, setExecuteResult] = useState<IngestionExecuteResult | null>(null);
  const [errorState, setErrorState] = useState<IngestionErrorState | null>(null);

  const isBusy =
    phase === "uploading" || phase === "planning" || phase === "approving" || phase === "executing";

  const phaseLabel = useMemo(() => {
    switch (phase) {
      case "uploading":
        return "Uploading";
      case "planning":
        return "Planning";
      case "awaiting_catalog_setup":
        return "Setup Required";
      case "awaiting_user_approval":
        return "Awaiting Approval";
      case "approving":
        return "Approving";
      case "approved":
        return "Approved";
      case "executing":
        return "Executing";
      case "succeeded":
        return "Succeeded";
      case "cancelled":
        return "Cancelled";
      case "failed":
        return "Failed";
      default:
        return "Ready";
    }
  }, [phase]);

  async function handleUploadAndPlan() {
    if (!selectedFile) {
      setErrorState({ stage: "upload", message: "Please choose one .xlsx file first." });
      setPhase("failed");
      return;
    }

    clearLifecycleError();
    setApprovalPayload(null);
    setSetupPayload(null);
    setApprovedResult(null);
    setExecuteResult(null);

    try {
      setPhase("uploading");
      const upload = await createIngestionUpload({ workspaceId, file: selectedFile });
      setUploadResult(upload);

      setPhase("planning");
      const plan = await createIngestionPlan({
        workspaceId,
        jobId: upload.jobId,
        message: `ingest ${selectedFile.name}`,
      });
      applyPlanPayload(plan);
    } catch (error) {
      handleFailure("upload_or_plan", error);
    }
  }

  async function handleSetupConfirm(seed: IngestionCatalogSetupSeed) {
    if (!uploadResult) {
      handleFailure("setup", new Error("Upload context is missing. Please upload again."));
      return;
    }

    clearLifecycleError();
    try {
      setPhase("planning");
      const plan = await confirmIngestionSetup({
        workspaceId,
        jobId: uploadResult.jobId,
        setup: seed,
      });
      applyPlanPayload(plan);
    } catch (error) {
      handleFailure("setup", error);
    }
  }

  async function handleProposalAction(button: ProposalActionButton) {
    if (!uploadResult || !approvalPayload) {
      handleFailure("approval", new Error("Proposal context is missing. Please re-run planning."));
      return;
    }

    clearLifecycleError();
    try {
      setPhase("approving");
      const approved = await approveIngestionProposal({
        workspaceId,
        jobId: uploadResult.jobId,
        proposalId: approvalPayload.proposalId,
        approvedAction: button.approvedAction,
        userOverrides: button.timeGrain
          ? {
              timeGrain: button.timeGrain,
            }
          : undefined,
      });
      setApprovedResult(approved);
      if (approved.status === "cancelled") {
        setPhase("cancelled");
        return;
      }
      setPhase("approved");
    } catch (error) {
      handleFailure("approval", error);
    }
  }

  async function handleExecute() {
    if (!uploadResult || !approvalPayload) {
      handleFailure("execute", new Error("Execution context is missing. Please approve proposal again."));
      return;
    }

    clearLifecycleError();
    try {
      setPhase("executing");
      const execution = await executeIngestionProposal({
        workspaceId,
        jobId: uploadResult.jobId,
        proposalId: approvalPayload.proposalId,
      });
      setExecuteResult(execution);
      setPhase("succeeded");
    } catch (error) {
      handleFailure("execute", error);
    }
  }

  function applyPlanPayload(plan: IngestionPlanAwaitingSetup | IngestionPlanAwaitingApproval) {
    if (plan.status === "awaiting_catalog_setup") {
      setSetupPayload(plan);
      setApprovalPayload(null);
      setPhase("awaiting_catalog_setup");
      return;
    }

    setSetupPayload(null);
    setApprovalPayload(plan);
    setPhase("awaiting_user_approval");
  }

  function clearLifecycleError() {
    if (errorState) {
      setErrorState(null);
    }
    if (phase === "failed") {
      setPhase("idle");
    }
  }

  function handleFailure(stage: string, error: unknown) {
    if (error instanceof IngestionApiError) {
      setErrorState({ stage, code: error.code, message: error.message });
    } else if (error instanceof Error) {
      setErrorState({ stage, message: error.message });
    } else {
      setErrorState({ stage, message: "Unexpected ingestion error" });
    }
    setPhase("failed");
  }

  function resetLifecycle() {
    setPhase("idle");
    setSelectedFile(null);
    setUploadResult(null);
    setSetupPayload(null);
    setApprovalPayload(null);
    setApprovedResult(null);
    setExecuteResult(null);
    setErrorState(null);
  }

  const candidateActions = approvalPayload?.proposal.candidateActions ?? [];

  return (
    <div className="border-b border-border-cream bg-parchment/60 px-4 py-3" data-testid="ingestion-lifecycle-panel">
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base">Agentic Ingestion</CardTitle>
              <CardDescription>
                Workspace-bound upload lifecycle: upload, setup, proposal approval, and execution receipt.
              </CardDescription>
            </div>
            <Badge variant={phase === "failed" ? "secondary" : "outline"}>{phaseLabel}</Badge>
          </div>
          <p className="text-label text-stone-gray">
            Bound workspace: <strong>{workspaceTitle ?? workspaceId}</strong>
          </p>
        </CardHeader>

        <CardContent className="space-y-4">
          <div className="flex flex-col gap-2 md:flex-row md:items-center">
            <label className="text-label text-stone-gray" htmlFor="ingestion-upload-input">
              Upload `.xlsx`
            </label>
            <input
              id="ingestion-upload-input"
              data-testid="ingestion-upload-input"
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                setSelectedFile(event.target.files?.[0] ?? null);
                if (phase === "failed") {
                  setPhase("idle");
                  setErrorState(null);
                }
              }}
              disabled={isBusy}
              className="text-body-sm"
            />
            <Button onClick={handleUploadAndPlan} disabled={!selectedFile || isBusy} size="sm" type="button">
              {isBusy ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Upload className="mr-1 h-4 w-4" />}
              {isBusy ? "Processing..." : "Upload & Plan"}
            </Button>
            {(phase === "succeeded" || phase === "cancelled" || phase === "failed") && (
              <Button variant="ghost" size="sm" onClick={resetLifecycle} type="button" disabled={isBusy}>
                Start New Upload
              </Button>
            )}
          </div>

          {selectedFile ? (
            <p className="text-caption text-stone-gray" data-testid="ingestion-selected-file">
              Selected file: {selectedFile.name}
            </p>
          ) : null}

          {uploadResult ? (
            <div className="rounded-comfortable border border-border-cream bg-ivory/70 px-3 py-2">
              <p className="text-body-sm text-near-black">
                Job: <strong>{uploadResult.jobId}</strong>
              </p>
              <p className="text-caption text-stone-gray">
                File hash: {uploadResult.fileSummary.fileHash.slice(0, 12)}... · {uploadResult.fileSummary.sizeBytes} bytes
              </p>
            </div>
          ) : null}

          {setupPayload ? (
            <div className="space-y-2" data-testid="ingestion-setup-flow">
              <div className="rounded-comfortable border border-border-cream bg-amber-50 px-3 py-2 text-body-sm text-near-black">
                Catalog setup is required before planning can continue.
              </div>
              <IngestionSetupCard
                initialSeed={setupPayload.suggestedCatalogSeed}
                setupQuestions={setupPayload.setupQuestions}
                isSubmitting={phase === "planning"}
                onConfirm={handleSetupConfirm}
                onCancel={() => {
                  setPhase("cancelled");
                  setSetupPayload(null);
                }}
              />
            </div>
          ) : null}

          {approvalPayload ? (
            <div className="space-y-3" data-testid="ingestion-proposal-card">
              <div className="rounded-comfortable border border-border-cream bg-ivory/70 px-3 py-3">
                <p className="text-body-sm font-medium text-near-black">
                  Recommended action: {approvalPayload.proposal.recommendedAction}
                </p>
                <p className="text-caption text-stone-gray">
                  Target table: {approvalPayload.proposal.targetTable ?? "(not set)"} · Business type: {approvalPayload.proposal.businessType}
                </p>
                <p className="text-caption text-stone-gray">
                  Inserts {approvalPayload.proposal.diffPreview.predictedInsertCount}, Updates {approvalPayload.proposal.diffPreview.predictedUpdateCount}, Conflicts {approvalPayload.proposal.diffPreview.predictedConflictCount}
                </p>
                {approvalPayload.proposal.risks.length > 0 ? (
                  <ul className="list-disc space-y-1 pl-5 pt-1 text-caption text-stone-gray">
                    {approvalPayload.proposal.risks.map((risk) => (
                      <li key={risk}>{risk}</li>
                    ))}
                  </ul>
                ) : null}
              </div>

              <div className="flex flex-wrap gap-2">
                {PROPOSAL_ACTION_BUTTONS.map((button) => {
                  const isSupported =
                    button.approvedAction === "cancel" || candidateActions.includes(button.approvedAction);
                  return (
                    <Button
                      key={`${button.approvedAction}-${button.timeGrain ?? "none"}`}
                      size="sm"
                      variant={button.approvedAction === "cancel" ? "secondary" : "default"}
                      disabled={!isSupported || isBusy}
                      onClick={() => handleProposalAction(button)}
                      type="button"
                    >
                      {button.label}
                    </Button>
                  );
                })}
              </div>
            </div>
          ) : null}

          {approvedResult?.status === "approved" ? (
            <div className="rounded-comfortable border border-border-cream bg-green-50 px-3 py-3" data-testid="ingestion-approved-card">
              <p className="flex items-center gap-2 text-body-sm font-medium text-near-black">
                <CheckCircle2 className="h-4 w-4 text-green-700" />
                Proposal approved: {approvedResult.approvedAction}
              </p>
              <p className="text-caption text-stone-gray">
                Dry-run affected rows: {approvedResult.dryRunSummary.predictedAffectedRows} · target: {approvedResult.targetTable}
              </p>
              <div className="pt-2">
                <Button size="sm" onClick={handleExecute} type="button" disabled={isBusy}>
                  {phase === "executing" ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
                  Execute Write
                </Button>
              </div>
            </div>
          ) : null}

          {executeResult ? (
            <div className="rounded-comfortable border border-border-cream bg-emerald-50 px-3 py-3" data-testid="ingestion-receipt-card">
              <p className="flex items-center gap-2 text-body-sm font-medium text-near-black">
                <CheckCircle2 className="h-4 w-4 text-emerald-700" />
                Execution receipt generated
              </p>
              <p className="text-caption text-stone-gray">
                Target: {executeResult.receipt.targetTable} · Inserted {executeResult.receipt.insertedRows} · Updated {executeResult.receipt.updatedRows}
              </p>
              <p className="text-caption text-stone-gray">
                Affected rows: {executeResult.receipt.affectedRows} · Rows after: {executeResult.receipt.rowsAfter}
              </p>
            </div>
          ) : null}

          {phase === "cancelled" ? (
            <div className="rounded-comfortable border border-border-cream bg-stone-100 px-3 py-3 text-body-sm text-near-black" data-testid="ingestion-cancelled-card">
              <p className="flex items-center gap-2">
                <XCircle className="h-4 w-4 text-stone-700" />
                Ingestion proposal was cancelled.
              </p>
            </div>
          ) : null}

          {errorState ? (
            <div className="rounded-comfortable border border-red-200 bg-red-50 px-3 py-3" role="alert" data-testid="ingestion-error-card">
              <p className="flex items-center gap-2 text-body-sm font-medium text-red-700">
                <AlertTriangle className="h-4 w-4" />
                Ingestion failed at {errorState.stage}
              </p>
              <p className="text-caption text-red-700">
                {errorState.code ? `[${errorState.code}] ` : ""}
                {errorState.message}
              </p>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
