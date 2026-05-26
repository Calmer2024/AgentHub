import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AgentSelector } from "./AgentSelector";
import type { Agent } from "../types";

const mockAgent: Agent = {
  name: "claude",
  displayName: "Claude 4 Opus",
  provider: "anthropic",
  isAvailable: true,
  capability: {
    supportsStreaming: true,
    supportsFileInput: false,
    supportsToolCall: false,
    maxContextTokens: 200000,
    tags: ["code", "writing"],
  },
};

const unavailableAgent: Agent = {
  ...mockAgent,
  name: "deepseek",
  displayName: "DeepSeek V3",
  isAvailable: false,
  unavailableReason: "API Key 未配置",
};

describe("AgentSelector", () => {
  describe("加载状态", () => {
    it("显示加载指示器", () => {
      render(
        <AgentSelector
          agents={[]}
          selectedName="claude"
          isLoading={true}
          error={null}
          onSelect={vi.fn()}
          onRetry={vi.fn()}
          onOpenSettings={vi.fn()}
        />
      );
      expect(screen.getByText("加载可用 Agent...")).toBeInTheDocument();
    });
  });

  describe("空状态", () => {
    it("无可用 Agent 时显示提示", () => {
      render(
        <AgentSelector
          agents={[]}
          selectedName="claude"
          isLoading={false}
          error={null}
          onSelect={vi.fn()}
          onRetry={vi.fn()}
          onOpenSettings={vi.fn()}
        />
      );
      expect(screen.getByText("暂无可用的 Agent")).toBeInTheDocument();
    });
  });

  describe("正常状态", () => {
    it("渲染 agent 列表", () => {
      render(
        <AgentSelector
          agents={[mockAgent]}
          selectedName="claude"
          isLoading={false}
          error={null}
          onSelect={vi.fn()}
          onRetry={vi.fn()}
          onOpenSettings={vi.fn()}
        />
      );
      expect(screen.getByText("Claude 4 Opus")).toBeInTheDocument();
    });

    it("当前选中 agent 为默认值", () => {
      render(
        <AgentSelector
          agents={[mockAgent, unavailableAgent]}
          selectedName="claude"
          isLoading={false}
          error={null}
          onSelect={vi.fn()}
          onRetry={vi.fn()}
          onOpenSettings={vi.fn()}
        />
      );
      const select = screen.getByRole("combobox") as HTMLSelectElement;
      expect(select.value).toBe("claude");
    });

    it("不可用 agent 显示不可用提示", () => {
      render(
        <AgentSelector
          agents={[mockAgent, unavailableAgent]}
          selectedName="claude"
          isLoading={false}
          error={null}
          onSelect={vi.fn()}
          onRetry={vi.fn()}
          onOpenSettings={vi.fn()}
        />
      );
      expect(screen.getByText(/不可用的 Agent/i)).toBeInTheDocument();
    });
  });

  describe("错误状态", () => {
    it("显示错误信息和重试按钮", async () => {
      const onRetry = vi.fn();
      render(
        <AgentSelector
          agents={[]}
          selectedName="claude"
          isLoading={false}
          error="无法加载 Agent 列表"
          onSelect={vi.fn()}
          onRetry={onRetry}
          onOpenSettings={vi.fn()}
        />
      );
      expect(screen.getByText("无法加载 Agent 列表")).toBeInTheDocument();
      await userEvent.click(screen.getByText("重试"));
      expect(onRetry).toHaveBeenCalledOnce();
    });
  });

  describe("交互", () => {
    it("选择 agent 时触发 onSelect", async () => {
      const secondAgent: Agent = {
        name: "gpt4",
        displayName: "GPT-4",
        provider: "openai",
        isAvailable: true,
        capability: {
          supportsStreaming: true,
          supportsFileInput: true,
          supportsToolCall: true,
          maxContextTokens: 128000,
          tags: ["code"],
        },
      };
      const onSelect = vi.fn();
      render(
        <AgentSelector
          agents={[mockAgent, secondAgent]}
          selectedName="claude"
          isLoading={false}
          error={null}
          onSelect={onSelect}
          onRetry={vi.fn()}
          onOpenSettings={vi.fn()}
        />
      );
      await userEvent.selectOptions(screen.getByRole("combobox"), "gpt4");
      expect(onSelect).toHaveBeenCalledWith("gpt4");
    });
  });
});
