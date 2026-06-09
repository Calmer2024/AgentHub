import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthGate } from "./AuthGate";
import {
  fetchAuthProviders,
  fetchCurrentUser,
  getStoredAuthSession,
  loginWithEmail,
} from "../../api/client";
import type { AuthProvider, AuthSession, CurrentUser } from "../../types";

vi.mock("../../api/client", () => ({
  fetchAuthProviders: vi.fn(),
  fetchCurrentUser: vi.fn(),
  getStoredAuthSession: vi.fn(),
  loginWithEmail: vi.fn(),
}));

const user: CurrentUser = {
  id: "u1",
  email: "phase14@example.com",
  displayName: "Phase14 User",
  createdAt: "2026-06-09T12:00:00",
  status: "active",
  teams: [],
  defaultSpace: { kind: "personal", id: "u1", name: "个人空间" },
};

const provider: AuthProvider = {
  id: "local_email",
  label: "邮箱登录",
  type: "email",
  enabled: true,
  devOnly: false,
};

const session: AuthSession = {
  accessToken: "access-token",
  refreshToken: "refresh-token",
  tokenType: "bearer",
  expiresAt: "2026-06-09T12:00:00",
  user,
};

describe("AuthGate", () => {
  beforeEach(() => {
    vi.mocked(getStoredAuthSession).mockReturnValue(null);
    vi.mocked(fetchAuthProviders).mockResolvedValue([provider]);
    vi.mocked(fetchCurrentUser).mockRejectedValue(new Error("请先登录后继续"));
    vi.mocked(loginWithEmail).mockResolvedValue(session);
  });

  it("未登录时显示登录页，登录成功后进入工作台", async () => {
    render(
      <AuthGate surface="desktop">
        <div>Workbench Ready</div>
      </AuthGate>,
    );

    await screen.findByRole("heading", { name: "登录云端工作区" });
    fireEvent.change(screen.getByLabelText("邮箱"), { target: { value: "phase14@example.com" } });
    fireEvent.change(screen.getByLabelText("显示名称"), { target: { value: "Phase14 User" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    await screen.findByText("Workbench Ready");
    expect(loginWithEmail).toHaveBeenCalledWith({
      email: "phase14@example.com",
      displayName: "Phase14 User",
    });
  });

  it("已有 session 时恢复当前用户并渲染子界面", async () => {
    vi.mocked(getStoredAuthSession).mockReturnValue(session);
    vi.mocked(fetchCurrentUser).mockResolvedValue(user);

    render(
      <AuthGate surface="mobile">
        <div>Mobile Ready</div>
      </AuthGate>,
    );

    await waitFor(() => expect(screen.getByText("Mobile Ready")).toBeInTheDocument());
  });
});
