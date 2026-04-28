import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

const mockRegister = vi.fn().mockResolvedValue({
  access_token: "token123",
  expires_at: Date.now() / 1000 + 3600,
  user: { id: "u1", email: "new@example.com", display_name: "New User", job_id: 1 },
});

vi.mock("@/lib/auth/auth-client", () => ({
  apiRegister: mockRegister,
  AuthError: class AuthError extends Error {
    code: string;
    status: number;
    constructor(code: string, message: string, status: number) {
      super(message);
      this.code = code;
      this.status = status;
    }
  },
}));

vi.mock("@/lib/auth/session", () => ({
  setInMemoryToken: vi.fn(),
}));

// Mock fetch for /jobs endpoint
global.fetch = vi.fn().mockResolvedValue({
  json: () => Promise.resolve({
    jobs: [
      { id: 1, code: "developer", label_zh: "开发者", label_en: "Developer", sort_order: 1 },
    ],
  }),
} as Response);

import RegisterPage from "../../app/(auth)/register/page";

describe("RegisterPage", () => {
  it("renders registration fields", () => {
    render(<RegisterPage />);
    expect(screen.getByLabelText(/邮箱/)).toBeInTheDocument();
    expect(screen.getByLabelText(/姓名/)).toBeInTheDocument();
    expect(screen.getByLabelText(/密码/)).toBeInTheDocument();
  });

  it("shows error when password is too short", async () => {
    render(<RegisterPage />);

    fireEvent.change(screen.getByLabelText(/邮箱/), { target: { value: "a@b.com" } });
    fireEvent.change(screen.getByLabelText(/姓名/), { target: { value: "Alice" } });
    fireEvent.change(screen.getByLabelText(/密码/), { target: { value: "short" } });
    fireEvent.submit(document.querySelector("form")!);

    await waitFor(() => {
      expect(screen.getByText(/密码至少 8 位/)).toBeInTheDocument();
    });
  });
});
