import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MessageBubble } from "../../../frontend/src/components/MessageBubble";
import type { AgentConfig, Message } from "../../../frontend/src/types";

const baseMessage: Message = {
  id: "m1",
  sessionId: "s1",
  role: "assistant",
  content: "",
  agentName: "OpenCode",
  createdAt: "2026-06-04T18:23:03.000Z",
};

const handlers = {
  onReply: vi.fn(),
  onRegenerate: vi.fn(),
  onTogglePin: vi.fn(),
  onForward: vi.fn(),
  onMultiSelect: vi.fn(),
  onToggleSelect: vi.fn(),
  onCopy: vi.fn(),
  onJumpToMessage: vi.fn(),
};

describe("MessageBubble", () => {
  it("流式占位消息不显示冗余等待态或空回复", () => {
    render(
      <MessageBubble
        message={baseMessage}
        isStreaming
        {...handlers}
      />,
    );

    expect(screen.queryByLabelText("正在等待 Agent 回复")).not.toBeInTheDocument();
    expect(screen.queryByText("OpenCode 正在组织回复")).not.toBeInTheDocument();
    expect(screen.queryByText("未返回可见回复")).not.toBeInTheDocument();
  });

  it("进程已完成但正文为空时不显示等待回复", () => {
    render(
      <MessageBubble
        message={{
          ...baseMessage,
          metadata: {
            executionTrace: {
              status: "completed",
              agentName: "OpenCode",
              cliTool: "opencode",
              startedAt: "2026-06-04T18:22:49.000Z",
              completedAt: "2026-06-04T18:23:03.000Z",
              processId: "cli_1",
              exitCode: 0,
              items: [{
                id: "trace-1",
                kind: "process",
                text: "OpenCode 已结束",
                source: "system",
                chunkType: "process",
                processId: "cli_1",
                timestamp: "2026-06-04T18:23:03.000Z",
              }],
            },
          },
        }}
        isStreaming={false}
        {...handlers}
      />,
    );

    expect(screen.queryByText("等待回复")).not.toBeInTheDocument();
    expect(screen.getByText("未返回可见回复")).toBeInTheDocument();
    expect(screen.getByText("执行过程")).toBeInTheDocument();
  });

  it("执行流程块展示结构化命令和目标路径", () => {
    render(
      <MessageBubble
        message={{
          ...baseMessage,
          content: "done",
          metadata: {
            executionTrace: {
              status: "completed",
              agentName: "Codex",
              cliTool: "codex",
              startedAt: "2026-06-04T18:22:49.000Z",
              completedAt: "2026-06-04T18:23:03.000Z",
              processId: "cli_1",
              exitCode: 0,
              items: [{
                id: "trace-1",
                kind: "command",
                text: "Codex 执行命令",
                title: "Codex 执行命令",
                command: "npm test",
                target: "frontend",
                action: "run",
                provider: "Codex",
                source: "cli",
                chunkType: "progress",
                processId: "cli_1",
                timestamp: "2026-06-04T18:23:02.000Z",
              }],
            },
          },
        }}
        isStreaming={false}
        {...handlers}
      />,
    );

    expect(screen.queryByText("npm test")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("执行过程"));
    expect(screen.getByText("Codex 执行命令")).toBeInTheDocument();
    expect(screen.getByText("npm test")).toBeInTheDocument();
    expect(screen.getByText("frontend")).toBeInTheDocument();
  });

  it("执行流程摘要区分过程记录和真实步骤", () => {
    render(
      <MessageBubble
        message={{
          ...baseMessage,
          content: "done",
          metadata: {
            executionTrace: {
              status: "completed",
              agentName: "Codex",
              totalItemCount: 512,
              truncated: true,
              items: Array.from({ length: 300 }, (_, index) => ({
                id: `trace-${index}`,
                kind: "progress",
                text: `过程 ${index}`,
                timestamp: "2026-06-04T18:23:02.000Z",
              })),
            },
          },
        }}
        isStreaming={false}
        {...handlers}
      />,
    );

    expect(screen.getByText("已完成，最近 300/共 512 个步骤，0 次工具调用，用时 0 秒")).toBeInTheDocument();
    expect(screen.queryByText(/条过程记录/)).not.toBeInTheDocument();
  });

  it("右键气泡时展示消息操作菜单", () => {
    render(
      <MessageBubble
        message={{
          ...baseMessage,
          content: "```ts\nconst ok = true\n```",
        }}
        isStreaming={false}
        {...handlers}
      />,
    );

    fireEvent.contextMenu(screen.getByRole("button", { name: "复制代码" }).closest(".agenthub-message-bubble")!);
    expect(screen.getByRole("menuitem", { name: "引用回复" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "重新生成" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Pin 消息" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "转发" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "多选" })).toBeInTheDocument();
  });

  it("多选模式显示选择控件", () => {
    render(
      <MessageBubble
        message={{
          ...baseMessage,
          content: "hello",
        }}
        selectionMode
        selected
        isStreaming={false}
        {...handlers}
      />,
    );

    expect(screen.getByLabelText("取消选择消息")).toBeInTheDocument();
  });

  it("显示气泡时间戳和精致 Agent 名称", () => {
    render(
      <MessageBubble
        message={{
          ...baseMessage,
          content: "hello",
          agentName: "Claude Code",
          createdAt: "2026-06-04T18:23:03+08:00",
        }}
        isStreaming={false}
        {...handlers}
      />,
    );

    expect(screen.getByText("Claude Code")).toBeInTheDocument();
    expect(screen.getByText("06-04 18:23")).toBeInTheDocument();
  });

  it("用户消息不显示头像和名称，时间戳由气泡悬停样式控制", () => {
    render(
      <MessageBubble
        message={{
          ...baseMessage,
          role: "user",
          content: "请继续",
          sourceName: "测试用户",
          createdAt: "2026-06-04T18:23:03+08:00",
        }}
        isStreaming={false}
        {...handlers}
      />,
    );

    expect(screen.queryByLabelText("测试用户")).not.toBeInTheDocument();
    expect(screen.queryByText("测试用户")).not.toBeInTheDocument();
    expect(screen.getByText("06-04 18:23")).toHaveClass("agenthub-message-time");
  });

  it("点击智能体头像进入具体配置", () => {
    const onOpenAgentSettings = vi.fn();
    const agent: AgentConfig = {
      id: "agent-1",
      name: "前端工程师",
      description: "负责桌面端界面实现",
      systemPrompt: "",
      rules: "",
      agentType: "cli_wrapper",
      cliTool: "codex",
      executable: "codex",
      initArgs: [],
      envVars: {},
      toolset: [],
      primarySkill: "frontend_engineer",
      auxiliarySkills: [],
      contextPolicy: "workspace_coding",
      avatar: "",
      status: "ready",
      isActive: true,
      createdAt: "2026-06-04T18:23:03.000Z",
      updatedAt: "2026-06-04T18:23:03.000Z",
    };
    render(
      <MessageBubble
        message={{ ...baseMessage, content: "完成", agentName: agent.name }}
        agent={agent}
        onOpenAgentSettings={onOpenAgentSettings}
        {...handlers}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "配置 前端工程师" }));
    expect(onOpenAgentSettings).toHaveBeenCalledWith("agent-1");
  });

  it("执行过程支持全屏查看", () => {
    render(
      <MessageBubble
        message={{
          ...baseMessage,
          content: "done",
          metadata: {
            executionTrace: {
              status: "completed",
              agentName: "Codex",
              items: [{
                id: "trace-1",
                kind: "command",
                text: "Codex 执行命令",
                title: "Codex 执行命令",
                command: "npm test",
                timestamp: "2026-06-04T18:23:02.000Z",
              }],
            },
          },
        }}
        isStreaming={false}
        {...handlers}
      />,
    );

    fireEvent.click(screen.getByLabelText("全屏查看执行过程"));
    expect(screen.getByRole("dialog", { name: "执行过程" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "执行过程" })).toBeInTheDocument();
    expect(screen.getByText("Codex 执行命令")).toBeInTheDocument();
  });

  it("执行摘要默认折叠并与回答气泡分离", () => {
    const { container } = render(
      <MessageBubble
        message={{
          ...baseMessage,
          content: "最终回答",
          metadata: {
            executionTrace: {
              status: "completed",
              startedAt: "2026-06-04T18:22:49.000Z",
              completedAt: "2026-06-04T18:23:03.000Z",
              items: [{
                id: "trace-1",
                kind: "tool",
                text: "读取文件",
                timestamp: "2026-06-04T18:23:03.000Z",
              }],
            },
          },
        }}
        {...handlers}
      />,
    );

    const summary = screen.getByRole("button", { name: /^执行过程/ });
    expect(summary).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("已完成，1 个步骤，1 次工具调用，用时 14 秒")).toBeInTheDocument();
    const bubble = container.querySelector(".agenthub-message-bubble");
    const execution = container.querySelector(".agenthub-message-execution");
    expect(bubble).not.toContainElement(execution);
  });
});
