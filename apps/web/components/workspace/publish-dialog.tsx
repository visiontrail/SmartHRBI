"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { UserSearchInput, type UserSearchResult } from "@/components/sharing/user-search-input";
import { useI18n } from "@/lib/i18n/context";

export type VisibilityMode = "private" | "registered" | "allowlist";

export type PublishDialogResult = {
  visibility_mode: VisibilityMode;
  visibility_user_ids: string[];
};

type Props = {
  open: boolean;
  onClose: () => void;
  onPublish: (result: PublishDialogResult) => void;
  isPublishing?: boolean;
};

export function PublishDialog({ open, onClose, onPublish, isPublishing }: Props) {
  const { t } = useI18n();
  const [visibilityMode, setVisibilityMode] = useState<VisibilityMode>("private");
  const [selectedUsers, setSelectedUsers] = useState<UserSearchResult[]>([]);

  function handlePublish() {
    onPublish({
      visibility_mode: visibilityMode,
      visibility_user_ids:
        visibilityMode === "allowlist" ? selectedUsers.map((u) => u.id) : [],
    });
  }

  function addUser(user: UserSearchResult) {
    setSelectedUsers((prev) => {
      if (prev.some((u) => u.id === user.id)) return prev;
      return [...prev, user];
    });
  }

  function removeUser(userId: string) {
    setSelectedUsers((prev) => prev.filter((u) => u.id !== userId));
  }

  if (!open) return null;

  const canPublish =
    visibilityMode !== "allowlist" || selectedUsers.length > 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      role="dialog"
      aria-modal
    >
      <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-lg space-y-4">
        <h2 className="text-lg font-semibold">发布设置</h2>

        {/* Visibility mode */}
        <div className="space-y-2">
          <p className="text-sm font-medium">可见性</p>
          {(["private", "registered", "allowlist"] as VisibilityMode[]).map((mode) => (
            <label key={mode} className="flex items-center gap-2 cursor-pointer text-sm">
              <input
                type="radio"
                name="visibility"
                value={mode}
                checked={visibilityMode === mode}
                onChange={() => {
                  setVisibilityMode(mode);
                  if (mode !== "allowlist") setSelectedUsers([]);
                }}
              />
              {t(`visibility.${mode}`)}
            </label>
          ))}
        </div>

        {/* User search for allowlist */}
        {visibilityMode === "allowlist" && (
          <div className="space-y-2">
            <p className="text-sm font-medium">搜索用户</p>
            <UserSearchInput
              onSelect={addUser}
              excludeIds={selectedUsers.map((u) => u.id)}
              placeholder="输入邮箱或姓名..."
            />
            {selectedUsers.length === 0 && (
              <p className="text-xs text-destructive">请至少选择一位用户</p>
            )}
            {selectedUsers.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {selectedUsers.map((u) => (
                  <span
                    key={u.id}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-warm-sand text-xs"
                  >
                    {u.display_name}
                    <button
                      type="button"
                      onClick={() => removeUser(u.id)}
                      className="text-stone-gray hover:text-error-crimson"
                      aria-label={`移除 ${u.display_name}`}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button onClick={handlePublish} disabled={!canPublish || isPublishing}>
            {isPublishing ? "发布中..." : "确认发布"}
          </Button>
        </div>
      </div>
    </div>
  );
}
