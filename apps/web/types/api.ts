export type ApiResponse<T> = {
  success: boolean;
  data: T;
  error?: string;
};

export type PaginatedResponse<T> = {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
};

export type CreateSessionRequest = {
  title?: string;
};

export type CreateSessionResponse = {
  id: string;
  title: string;
  createdAt: string;
};

export type FetchSessionsResponse = {
  sessions: import("./chat").ChatSession[];
};

export type FetchMessagesRequest = {
  sessionId: string;
};

export type FetchMessagesResponse = {
  messages: import("./chat").ChatMessage[];
};

export type SendChatRequest = {
  sessionId: string;
  content: string;
};

export type SendChatResponse = import("./chat").SendMessageResponse;

export type FetchWorkspacesResponse = {
  workspaces: import("./workspace").Workspace[];
};

export type CreateWorkspaceRequest = {
  title?: string;
  description?: string;
};

export type CreateWorkspaceResponse = import("./workspace").Workspace;

export type SaveWorkspaceRequest = {
  workspaceId: string;
  snapshot: import("./workspace").WorkspaceSnapshot;
};

export type SaveWorkspaceResponse = {
  success: boolean;
  updatedAt: string;
};

export type FetchWorkspaceSnapshotRequest = {
  workspaceId: string;
};

export type FetchWorkspaceSnapshotResponse = import("./workspace").WorkspaceSnapshot;

export type AddChartToWorkspaceRequest = {
  workspaceId: string;
  assetId: string;
  position?: { x: number; y: number };
};

export type AddChartToWorkspaceResponse = {
  nodeId: string;
};
