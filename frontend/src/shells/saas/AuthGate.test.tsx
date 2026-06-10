import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthGate } from "./AuthGate";
import {
  fetchAuthProviders,
  fetchCurrentUser,
  getStoredAuthSession,
  loginWithEmail,
  registerWithPassword,
} from "../../api/client";
import type { AuthProvider, AuthSession, CurrentUser } from "../../types";

vi.mock("../../api/client", () => ({
  fetchAuthProviders: vi.fn(),
  fetchCurrentUser: vi.fn(),
  getStoredAuthSession: vi.fn(),
  loginWithEmail: vi.fn(),
  registerWithPassword: vi.fn(),
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
  label: "用户名密码",
  type: "password",
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
    vi.clearAllMocks();
    vi.mocked(getStoredAuthSession).mockReturnValue(null);
    vi.mocked(fetchAuthProviders).mockResolvedValue([provider]);
    vi.mocked(fetchCurrentUser).mockRejectedValue(new Error("请先登录后继续"));
    vi.mocked(loginWithEmail).mockResolvedValue(session);
    vi.mocked(registerWithPassword).mockResolvedValue(session);
  });

  it("未登录时显示登录页，登录成功后进入工作台", async () => {
    render(
      <AuthGate surface="desktop">
        <div>Workbench Ready</div>
      </AuthGate>,
    );

    await screen.findByRole("heading", { name: "登录云端工作区" });
    fireEvent.change(screen.getByLabelText("用户名或邮箱"), { target: { value: "phase14@example.com" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "Phase14-passw0rd" } });
    const loginButtons = screen.getAllByRole("button", { name: "登录" });
    fireEvent.click(loginButtons[loginButtons.length - 1]);

    await screen.findByText("Workbench Ready");
    expect(loginWithEmail).toHaveBeenCalledWith({
      identifier: "phase14@example.com",
      password: "Phase14-passw0rd",
    });
  });

  it("支持用户名密码注册", async () => {
    render(
      <AuthGate surface="desktop">
        <div>Workbench Ready</div>
      </AuthGate>,
    );

    await screen.findByRole("heading", { name: "登录云端工作区" });
    fireEvent.click(screen.getByRole("button", { name: "注册" }));
    fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "phase14" } });
    fireEvent.change(screen.getByLabelText("邮箱"), { target: { value: "phase14@example.com" } });
    fireEvent.change(screen.getByLabelText("显示名称"), { target: { value: "Phase14 User" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "Phase14-passw0rd" } });
    const registerButtons = screen.getAllByRole("button", { name: "注册" });
    fireEvent.click(registerButtons[registerButtons.length - 1]);

    await screen.findByText("Workbench Ready");
    expect(registerWithPassword).toHaveBeenCalledWith({
      username: "phase14",
      email: "phase14@example.com",
      password: "Phase14-passw0rd",
      displayName: "Phase14 User",
    });
  });

  it("注册字段不合法时显示具体错误且不提交", async () => {
    render(
      <AuthGate surface="desktop">
        <div>Workbench Ready</div>
      </AuthGate>,
    );

    await screen.findByRole("heading", { name: "登录云端工作区" });
    fireEvent.click(screen.getByRole("button", { name: "注册" }));
    fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "-bad" } });
    fireEvent.change(screen.getByLabelText("邮箱"), { target: { value: "bad-email" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "short" } });
    const registerButtons = screen.getAllByRole("button", { name: "注册" });
    fireEvent.click(registerButtons[registerButtons.length - 1]);

    expect(await screen.findByText("用户名只能包含字母、数字、下划线或连字符，且必须以字母或数字开头")).toBeInTheDocument();
    expect(screen.getByText("请输入有效邮箱")).toBeInTheDocument();
    expect(screen.getByText("密码至少 8 位")).toBeInTheDocument();
    expect(registerWithPassword).not.toHaveBeenCalled();
  });

  it("注册接口错误会显示全局反馈", async () => {
    vi.mocked(registerWithPassword).mockRejectedValueOnce(new Error("用户名已被注册"));
    render(
      <AuthGate surface="desktop">
        <div>Workbench Ready</div>
      </AuthGate>,
    );

    await screen.findByRole("heading", { name: "登录云端工作区" });
    fireEvent.click(screen.getByRole("button", { name: "注册" }));
    fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "phase14" } });
    fireEvent.change(screen.getByLabelText("邮箱"), { target: { value: "phase14@example.com" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "Phase14-passw0rd" } });
    const registerButtons = screen.getAllByRole("button", { name: "注册" });
    fireEvent.click(registerButtons[registerButtons.length - 1]);

    expect(await screen.findByText("用户名已被注册")).toBeInTheDocument();
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
