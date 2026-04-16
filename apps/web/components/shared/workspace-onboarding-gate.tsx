"use client";

import { useMemo, useState } from "react";
import { Building2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type WorkspaceOnboardingGateProps = {
  onCreate: (name: string) => void;
  isSubmitting: boolean;
};

const DEFAULT_WORKSPACE_NAME = "My Workspace";

export function WorkspaceOnboardingGate({ onCreate, isSubmitting }: WorkspaceOnboardingGateProps) {
  const [workspaceName, setWorkspaceName] = useState("");

  const normalizedName = useMemo(() => workspaceName.trim(), [workspaceName]);

  const handleCreate = () => {
    onCreate(normalizedName || DEFAULT_WORKSPACE_NAME);
  };

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-parchment px-6">
      <section className="w-full max-w-xl rounded-2xl border border-border-cream bg-ivory p-8 shadow-ring-warm">
        <div className="mb-6 flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-warm-sand text-terracotta">
            <Building2 className="h-5 w-5" />
          </span>
          <div>
            <h1 className="font-serif text-heading text-near-black">Create Your First Workspace</h1>
            <p className="text-body-sm text-olive-gray">
              A workspace is required before chatting and running analysis.
            </p>
          </div>
        </div>

        <div className="space-y-3">
          <label htmlFor="workspace-name" className="text-label text-stone-gray">
            Workspace Name
          </label>
          <Input
            id="workspace-name"
            value={workspaceName}
            onChange={(event) => setWorkspaceName(event.target.value)}
            placeholder={DEFAULT_WORKSPACE_NAME}
            autoFocus
          />
          <p className="text-caption text-stone-gray">
            You can rename this workspace later from the canvas toolbar.
          </p>
        </div>

        <div className="mt-6 flex items-center justify-end">
          <Button onClick={handleCreate} disabled={isSubmitting}>
            Create Workspace
          </Button>
        </div>
      </section>
    </div>
  );
}
