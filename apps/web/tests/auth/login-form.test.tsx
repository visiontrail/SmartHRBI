import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

// Mock auth-client
vi.mock("@/lib/auth/auth-client", () => ({
  apiEmailLogin: vi.fn().mockResolvedValue({
    access_token: "token123",
    expires_at: Date.now() / 1000 + 3600,
    user: { id: "u1", email: "test@example.com", display_name: "Test", job_id: 1 },
  }),
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

import LoginPage from "../../app/(auth)/login/page";

describe("LoginPage", () => {
  it("renders email and password fields", () => {
    render(<LoginPage />);
    expect(screen.getByLabelText(/邮箱/)).toBeInTheDocument();
    expect(screen.getByLabelText(/密码/)).toBeInTheDocument();
  });

  it("submits form with email and password", async () => {
    const { apiEmailLogin } = await import("@/lib/auth/auth-client");
    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText(/邮箱/), {
      target: { value: "test@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/密码/), {
      target: { value: "password123" },
    });
    fireEvent.submit(screen.getByRole("form") ?? document.querySelector("form")!);

    await waitFor(() => {
      expect(apiEmailLogin).toHaveBeenCalledWith({
        email: "test@example.com",
        password: "password123",
      });
    });
  });
});
