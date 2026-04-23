import { create } from "zustand";

export type ActivePanel = "chat" | "workspace" | "both" | "catalog";

type UIState = {
  activePanel: ActivePanel;
  chatSidebarOpen: boolean;
  workspaceSidebarOpen: boolean;
  isSending: boolean;
  isSaving: boolean;

  setActivePanel: (panel: ActivePanel) => void;
  setChatSidebarOpen: (open: boolean) => void;
  setWorkspaceSidebarOpen: (open: boolean) => void;
  toggleChatSidebar: () => void;
  toggleWorkspaceSidebar: () => void;
  setIsSending: (value: boolean) => void;
  setIsSaving: (value: boolean) => void;
};

export const useUIStore = create<UIState>((set) => ({
  activePanel: "both",
  chatSidebarOpen: true,
  workspaceSidebarOpen: false,
  isSending: false,
  isSaving: false,

  setActivePanel: (panel) => set({ activePanel: panel }),
  setChatSidebarOpen: (open) => set({ chatSidebarOpen: open }),
  setWorkspaceSidebarOpen: (open) => set({ workspaceSidebarOpen: open }),
  toggleChatSidebar: () => set((s) => ({ chatSidebarOpen: !s.chatSidebarOpen })),
  toggleWorkspaceSidebar: () => set((s) => ({ workspaceSidebarOpen: !s.workspaceSidebarOpen })),
  setIsSending: (value) => set({ isSending: value }),
  setIsSaving: (value) => set({ isSaving: value }),
}));
