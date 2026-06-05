import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MessageActions } from "./MessageActions";
import type { Message } from "../types";

const assistant: Message = {
  id: "m1",
  sessionId: "s1",
  role: "assistant",
  content: "hello",
  agentName: "测试 Agent",
  createdAt: "",
};

describe("MessageActions", () => {
  it("assistant 消息显示重新生成操作", () => {
    render(
      <MessageActions
        message={assistant}
        onReply={vi.fn()}
        onRegenerate={vi.fn()}
        onTogglePin={vi.fn()}
        onCopy={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("引用回复")).toBeInTheDocument();
    expect(screen.getByLabelText("重新生成")).toBeInTheDocument();
    expect(screen.getByLabelText("Pin 消息")).toBeInTheDocument();
  });

  it("用户消息不显示重新生成操作", () => {
    render(
      <MessageActions
        message={{ ...assistant, role: "user", agentName: null }}
        onReply={vi.fn()}
        onRegenerate={vi.fn()}
        onTogglePin={vi.fn()}
        onCopy={vi.fn()}
      />,
    );

    expect(screen.queryByLabelText("重新生成")).not.toBeInTheDocument();
  });

  it("点击 Pin 触发回调", () => {
    const onTogglePin = vi.fn();
    render(
      <MessageActions
        message={assistant}
        onReply={vi.fn()}
        onRegenerate={vi.fn()}
        onTogglePin={onTogglePin}
        onCopy={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByLabelText("Pin 消息"));
    expect(onTogglePin).toHaveBeenCalledWith(assistant);
  });
});
