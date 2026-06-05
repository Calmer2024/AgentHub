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
});
