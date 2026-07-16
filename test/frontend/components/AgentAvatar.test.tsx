import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgentAvatar } from "../../../frontend/src/components/AgentAvatar";

describe("AgentAvatar", () => {
  it("将内置 CLI Logo 放入统一的圆形裁剪容器", () => {
    render(<AgentAvatar agent={{ name: "Codex", cliTool: "codex", status: "ready", avatar: "" }} />);

    const avatar = screen.getByLabelText("Codex");
    expect(avatar).toHaveClass("rounded-full", "overflow-hidden");
    expect(avatar.querySelector("img")).toHaveAttribute("src", "/brands/openai.svg");
  });

  it("根据角色名称加载对应的内置头像文件", () => {
    render(<AgentAvatar agent={{ name: "前端工程师", cliTool: "codex", status: "ready", avatar: "preset:blue" }} />);

    const avatar = screen.getByLabelText("前端工程师");
    expect(avatar).toHaveClass("agenthub-role-avatar", "rounded-full");
    expect(avatar.querySelector("img")?.getAttribute("src")).toContain(encodeURIComponent("前端工程师.png"));
  });

  it("兼容 UX/UI 模板名称与 UI-UX 图标文件名", () => {
    render(<AgentAvatar agent={{ name: "UX/UI设计师", cliTool: "codex", status: "ready", avatar: "preset:violet" }} />);

    expect(screen.getByLabelText("UX/UI设计师").querySelector("img")?.getAttribute("src"))
      .toContain(encodeURIComponent("UI-UX工程师.png"));
  });

  it("兼容项目经理名称与产品经理头像资源", () => {
    render(<AgentAvatar agent={{ name: "项目经理", cliTool: "codex", status: "ready", avatar: "" }} />);

    expect(screen.getByLabelText("项目经理").querySelector("img")?.getAttribute("src"))
      .toContain(encodeURIComponent("产品经理.png"));
  });

  it("将调度器映射到项目 Leader 头像", () => {
    render(<AgentAvatar agent={{ name: "项目Leader", cliTool: "codex", status: "ready", avatar: "" }} />);

    expect(screen.getByLabelText("项目Leader").querySelector("img")?.getAttribute("src"))
      .toContain(encodeURIComponent("项目Leader.png"));
  });

  it("恢复 OpenCode 官方头像并使用统一的 CLI 底板", () => {
    render(<AgentAvatar agent={{ name: "OpenCode", cliTool: "opencode", status: "ready", avatar: "" }} />);

    const avatar = screen.getByLabelText("OpenCode");
    expect(avatar).toHaveClass("agenthub-cli-avatar");
    expect(avatar).not.toHaveClass("agenthub-cli-avatar-opencode");
    expect(avatar.querySelector("img")).toHaveAttribute("src", "/brands/opencode-light.svg");
  });
});
