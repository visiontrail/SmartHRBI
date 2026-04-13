"use client";

import { LayoutDashboard, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCreateWorkspace } from "@/hooks/use-workspace";

export function WorkspaceEmptyState() {
  const createWorkspace = useCreateWorkspace();

  return (
    <div className="flex flex-col items-center justify-center h-full px-8 py-12">
      <div className="w-14 h-14 rounded-maximum bg-warm-sand flex items-center justify-center mb-6">
        <LayoutDashboard className="w-7 h-7 text-terracotta" />
      </div>

      <h2 className="font-serif text-heading text-near-black mb-2 text-center">
        Report Workspace
      </h2>
      <p className="text-body text-olive-gray text-center max-w-md mb-8 leading-relaxed">
        Create a workspace to compose AI-generated charts into a visual report. 
        Drag charts from your conversations and arrange them freely.
      </p>

      <Button
        variant="default"
        onClick={() => createWorkspace.mutate({})}
        disabled={createWorkspace.isPending}
      >
        <Plus className="w-4 h-4" />
        Create Workspace
      </Button>
    </div>
  );
}
