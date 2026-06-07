import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MessageBubble } from "./MessageBubble";
import type { Message } from "../types";

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

    fireEvent.contextMenu(screen.getByText("const ok = true"));
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

    expect(screen.getByText("@Claude Code")).toBeInTheDocument();
    expect(screen.getByText("2026/06/04 18:23:03")).toBeInTheDocument();
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
});
