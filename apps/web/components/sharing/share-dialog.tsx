"use client";

import { useState, useEffect } from "react";
import { useI18n } from "@/lib/i18n/context";
import { UserSearchInput, type UserSearchResult } from "./user-search-input";
import { MembersList } from "./members-list";
import { InviteLinkSection } from "./invite-link-section";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
  listMembers,
  addMember,
  updateMemberRole,
  removeMember,
  listInvites,
  createInvite,
  revokeInvite,
  type WorkspaceMember,
  type WorkspaceInvite,
} from "@/lib/workspace/collaboration";

type Props = {
  open: boolean;
  workspaceId: string;
  workspaceName: string;
  currentUserId?: string;
  onClose: () => void;
};

export function ShareDialog({ open, workspaceId, workspaceName, currentUserId, onClose }: Props) {
  const { t } = useI18n();
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [invites, setInvites] = useState<WorkspaceInvite[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    Promise.all([listMembers(workspaceId), listInvites(workspaceId)])
      .then(([m, i]) => {
        setMembers(m);
        setInvites(i);
      })
      .catch(() => toast.error("加载协作信息失败"))
      .finally(() => setLoading(false));
  }, [open, workspaceId]);

  async function handleInviteUser(user: UserSearchResult) {
    try {
      await addMember(workspaceId, user.id, "editor");
      toast.success(`已邀请${user.display_name}为编辑者`);
      const updated = await listMembers(workspaceId);
      setMembers(updated);
    } catch {
      toast.error("邀请失败");
    }
  }

  async function handleRoleChange(userId: string, role: string) {
    await updateMemberRole(workspaceId, userId, role);
    setMembers((prev) => prev.map((m) => m.user_id === userId ? { ...m, role } : m));
  }

  async function handleRemoveMember(userId: string) {
    await removeMember(workspaceId, userId);
    setMembers((prev) => prev.filter((m) => m.user_id !== userId));
  }

  async function handleCreateInvite(role: string) {
    const invite = await createInvite(workspaceId, { role });
    setInvites((prev) => [invite, ...prev]);
    return invite;
  }

  async function handleRevokeInvite(inviteId: string) {
    await revokeInvite(workspaceId, inviteId);
    setInvites((prev) => prev.map((i) => i.id === inviteId ? { ...i, revoked_at: new Date().toISOString() } : i));
  }

  if (!open) return null;

  const existingMemberIds = members.map((m) => m.user_id);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-lg space-y-4 max-h-[80vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">共享 · {workspaceName}</h2>
          <Button variant="ghost" size="sm" onClick={onClose}>✕</Button>
        </div>

        {/* Search to invite */}
        <div className="space-y-2">
          <p className="text-sm font-medium">{t("collab.invite")}</p>
          <UserSearchInput
            onSelect={handleInviteUser}
            excludeIds={existingMemberIds}
            placeholder="搜索用户邀请..."
          />
        </div>

        {/* Members list */}
        <div className="space-y-2">
          <p className="text-sm font-medium">{t("collab.collaborators")}</p>
          {loading ? (
            <p className="text-xs text-muted-foreground">加载中...</p>
          ) : (
            <MembersList
              members={members}
              currentUserId={currentUserId}
              onRoleChange={handleRoleChange}
              onRemove={handleRemoveMember}
            />
          )}
        </div>

        {/* Invite link */}
        <InviteLinkSection
          invites={invites}
          onGenerate={handleCreateInvite}
          onRevoke={handleRevokeInvite}
        />
      </div>
    </div>
  );
}
