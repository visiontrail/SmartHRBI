import { getAuthorizationHeader } from "@/lib/auth/session";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const DEFAULT_AUTH_CONTEXT = {
  userId: process.env.NEXT_PUBLIC_DEFAULT_USER_ID ?? "demo-user",
  projectId: process.env.NEXT_PUBLIC_DEFAULT_PROJECT_ID ?? "demo-project",
  role: process.env.NEXT_PUBLIC_DEFAULT_ROLE ?? "hr",
  department: null,
  clearance: 1,
};

export type WorkspaceMember = {
  user_id: string;
  role: string;
  display_name: string;
  email: string;
};

export type WorkspaceInvite = {
  id: string;
  workspace_id: string;
  role: string;
  created_by: string;
  expires_at: string;
  revoked_at: string | null;
  used_count: number;
  max_uses: number | null;
  created_at: string;
  invite_url?: string;
};

async function apiHeaders() {
  return getAuthorizationHeader(API_BASE_URL, DEFAULT_AUTH_CONTEXT);
}

export async function listMembers(workspaceId: string): Promise<WorkspaceMember[]> {
  const headers = await apiHeaders();
  const resp = await fetch(`${API_BASE_URL}/workspaces/${encodeURIComponent(workspaceId)}/members`, { headers });
  if (!resp.ok) throw new Error("listMembers failed");
  const data = await resp.json();
  return data.members ?? [];
}

export async function addMember(workspaceId: string, userId: string, role: string): Promise<void> {
  const headers = await apiHeaders();
  const resp = await fetch(`${API_BASE_URL}/workspaces/${encodeURIComponent(workspaceId)}/members`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify({ user_id: userId, role }),
  });
  if (!resp.ok) throw new Error("addMember failed");
}

export async function updateMemberRole(workspaceId: string, userId: string, role: string): Promise<void> {
  const headers = await apiHeaders();
  const resp = await fetch(
    `${API_BASE_URL}/workspaces/${encodeURIComponent(workspaceId)}/members/${encodeURIComponent(userId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify({ role }),
    }
  );
  if (!resp.ok) throw new Error("updateMemberRole failed");
}

export async function removeMember(workspaceId: string, userId: string): Promise<void> {
  const headers = await apiHeaders();
  const resp = await fetch(
    `${API_BASE_URL}/workspaces/${encodeURIComponent(workspaceId)}/members/${encodeURIComponent(userId)}`,
    { method: "DELETE", headers }
  );
  if (!resp.ok) throw new Error("removeMember failed");
}

export async function listInvites(workspaceId: string): Promise<WorkspaceInvite[]> {
  const headers = await apiHeaders();
  const resp = await fetch(`${API_BASE_URL}/workspaces/${encodeURIComponent(workspaceId)}/invites`, { headers });
  if (!resp.ok) throw new Error("listInvites failed");
  const data = await resp.json();
  return data.invites ?? [];
}

export async function createInvite(
  workspaceId: string,
  options: { role?: string; expires_in_days?: number; max_uses?: number }
): Promise<WorkspaceInvite> {
  const headers = await apiHeaders();
  const resp = await fetch(`${API_BASE_URL}/workspaces/${encodeURIComponent(workspaceId)}/invites`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(options),
  });
  if (!resp.ok) throw new Error("createInvite failed");
  return resp.json();
}

export async function revokeInvite(workspaceId: string, inviteId: string): Promise<void> {
  const headers = await apiHeaders();
  const resp = await fetch(
    `${API_BASE_URL}/workspaces/${encodeURIComponent(workspaceId)}/invites/${encodeURIComponent(inviteId)}`,
    { method: "DELETE", headers }
  );
  if (!resp.ok) throw new Error("revokeInvite failed");
}

export async function acceptInvite(token: string): Promise<{ workspace_id: string; role: string; already_member: boolean }> {
  const headers = await apiHeaders();
  const resp = await fetch(`${API_BASE_URL}/invites/${encodeURIComponent(token)}/accept`, {
    method: "POST",
    headers,
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw Object.assign(new Error(data?.detail?.code ?? "invite_failed"), { status: resp.status, code: data?.detail?.code });
  }
  return resp.json();
}
