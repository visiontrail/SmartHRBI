"use client";

import { LayoutDashboard, Globe, PenLine, LogOut, ChevronUp, Check } from "lucide-react";
import { useI18n } from "@/lib/i18n/context";
import { cn } from "@/lib/utils";
import type { PortalWorkspace } from "@/lib/portal/api";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
} from "@/components/ui/dropdown-menu";
import { useSession } from "@/lib/auth/use-session";
import { apiLogout } from "@/lib/auth/auth-client";
import { clearInMemoryToken } from "@/lib/auth/session";

export function PortalWorkspaceSidebar({
  workspaces,
  activePageId,
  onSelect,
  onOpenDesigner,
}: {
  workspaces: PortalWorkspace[];
  activePageId: string | null;
  onSelect: (pageId: string) => void;
  onOpenDesigner: () => void;
}) {
  const { t, locale, setLocale } = useI18n();
  const { user } = useSession();

  async function handleLogout() {
    await apiLogout().catch(() => {});
    clearInMemoryToken();
    window.location.href = "/login";
  }

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col overflow-hidden border-r border-[#d8d1c1] bg-[#fbfaf5]">
      <div className="flex-1 overflow-auto p-3">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[#2f332f]">
          <LayoutDashboard className="h-4 w-4 text-[#996b35]" />
          {t("portal.publishedWorkspaces")}
        </div>
        {workspaces.length === 0 ? (
          <p className="rounded-md border border-[#d8d1c1] bg-white p-3 text-sm text-[#777166]">
            {t("portal.noPublishedWorkspaces")}
          </p>
        ) : (
          <div className="space-y-2">
            {workspaces.map((workspace) => (
              <button
                key={workspace.latest_page_id}
                onClick={() => onSelect(workspace.latest_page_id)}
                className={cn(
                  "w-full rounded-md border bg-white p-3 text-left shadow-sm transition hover:border-[#ad7d3d]",
                  activePageId === workspace.latest_page_id
                    ? "border-[#ad7d3d] ring-2 ring-[#e8d5b3]"
                    : "border-[#d8d1c1]"
                )}
              >
                <span className="block truncate text-sm font-semibold">{workspace.name}</span>
                <span className="mt-1 block text-xs text-[#777166]">
                  v{workspace.latest_version} · {new Date(workspace.published_at).toLocaleString()}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* User settings footer */}
      <div className="border-t border-[#d8d1c1] px-3 py-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="w-full flex items-center gap-2.5 px-2 py-2 rounded-md hover:bg-[#f3eadb] transition-colors group"
            >
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#996b35] text-white text-sm font-semibold select-none">
                {user?.display_name ? user.display_name.charAt(0).toUpperCase() : "?"}
              </div>
              <div className="flex-1 min-w-0 text-left">
                <p className="text-sm font-medium truncate text-[#2f332f]">
                  {user?.display_name ?? ""}
                </p>
                <p className="text-xs text-[#777166] truncate">{t("appMode.viewer")}</p>
              </div>
              <ChevronUp className="w-4 h-4 text-[#777166] shrink-0 group-data-[state=open]:rotate-180 transition-transform" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="top" align="start" sideOffset={6} className="w-64">
            {/* User email */}
            <div className="px-2 py-1.5 mb-1">
              <p className="text-label text-stone-gray truncate">{user?.email ?? ""}</p>
            </div>
            <DropdownMenuSeparator />

            {/* Language submenu */}
            <DropdownMenuSub>
              <DropdownMenuSubTrigger>
                <Globe className="w-4 h-4" />
                {t("language.label")}
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent className="w-64">
                <DropdownMenuItem onSelect={() => setLocale("en-US")}>
                  {t("language.en")}
                  {locale === "en-US" && <Check className="ml-auto w-4 h-4" />}
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setLocale("zh-CN")}>
                  {t("language.zh")}
                  {locale === "zh-CN" && <Check className="ml-auto w-4 h-4" />}
                </DropdownMenuItem>
              </DropdownMenuSubContent>
            </DropdownMenuSub>

            {/* Switch to Designer */}
            <DropdownMenuItem onSelect={onOpenDesigner}>
              <PenLine className="w-4 h-4" />
              {t("appMode.designer")}
            </DropdownMenuItem>

            <DropdownMenuSeparator />

            {/* Logout */}
            <DropdownMenuItem
              onSelect={handleLogout}
              className="text-error-crimson focus:text-error-crimson focus:bg-error-crimson/10"
            >
              <LogOut className="w-4 h-4" />
              {t("auth.logout")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </aside>
  );
}
