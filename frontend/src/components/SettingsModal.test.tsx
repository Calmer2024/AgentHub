import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SettingsModal } from "./SettingsModal";

vi.mock("../api/client", () => ({
  fetchSettings: vi.fn().mockResolvedValue({
    anthropicApiKey: null,
    deepseekApiKey: "sk-****",
    geminiApiKey: null,
  }),
  updateSettings: vi.fn().mockResolvedValue({
    anthropicApiKey: "sk-****",
    deepseekApiKey: "sk-****",
    geminiApiKey: "sk-****",
  }),
}));

describe("SettingsModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("open=false 时不渲染", () => {
    const { container } = render(
      <SettingsModal open={false} onClose={vi.fn()} onSaved={vi.fn()} />
    );
    expect(container.innerHTML).toBe("");
  });

  it("open=true 时渲染模态框标题", () => {
    render(
      <SettingsModal open={true} onClose={vi.fn()} onSaved={vi.fn()} />
    );
    expect(screen.getByText("API Key 设置")).toBeInTheDocument();
  });

  it("加载完成后渲染三个厂商输入框", async () => {
    render(
      <SettingsModal open={true} onClose={vi.fn()} onSaved={vi.fn()} />
    );
    expect(await screen.findByText("Anthropic API Key")).toBeInTheDocument();
    expect(screen.getByText("DeepSeek API Key")).toBeInTheDocument();
    expect(screen.getByText("Gemini API Key")).toBeInTheDocument();
  });

  it("全部输入框为空时保存按钮禁用", async () => {
    render(
      <SettingsModal open={true} onClose={vi.fn()} onSaved={vi.fn()} />
    );
    await screen.findByText("Anthropic API Key");
    const saveBtn = screen.getByText("保存");
    expect(saveBtn).toBeDisabled();
  });

  it("点击取消调用 onClose", async () => {
    const onClose = vi.fn();
    render(
      <SettingsModal open={true} onClose={onClose} onSaved={vi.fn()} />
    );
    await screen.findByText("取消");
    await userEvent.click(screen.getByText("取消"));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
