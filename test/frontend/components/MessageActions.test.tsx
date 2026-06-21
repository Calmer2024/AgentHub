import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MessageActions } from "../../../frontend/src/components/MessageActions";
import type { Message } from "../../../frontend/src/types";

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
        open
        position={{ x: 10, y: 10 }}
        onReply={vi.fn()}
        onRegenerate={vi.fn()}
        onTogglePin={vi.fn()}
        onForward={vi.fn()}
        onMultiSelect={vi.fn()}
        onCopy={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByRole("menuitem", { name: "引用回复" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "重新生成" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Pin 消息" })).toBeInTheDocument();
  });

  it("用户消息不显示重新生成操作", () => {
    render(
      <MessageActions
        message={{ ...assistant, role: "user", agentName: null }}
        open
        position={{ x: 10, y: 10 }}
        onReply={vi.fn()}
        onRegenerate={vi.fn()}
        onTogglePin={vi.fn()}
        onForward={vi.fn()}
        onMultiSelect={vi.fn()}
        onCopy={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.queryByRole("menuitem", { name: "重新生成" })).not.toBeInTheDocument();
  });

  it("点击 Pin 触发回调", () => {
    const onTogglePin = vi.fn();
    render(
      <MessageActions
        message={assistant}
        open
        position={{ x: 10, y: 10 }}
        onReply={vi.fn()}
        onRegenerate={vi.fn()}
        onTogglePin={onTogglePin}
        onForward={vi.fn()}
        onMultiSelect={vi.fn()}
        onCopy={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("menuitem", { name: "Pin 消息" }));
    expect(onTogglePin).toHaveBeenCalledWith(assistant);
  });

  it("提供转发和多选入口", () => {
    const onForward = vi.fn();
    const onMultiSelect = vi.fn();
    render(
      <MessageActions
        message={assistant}
        open
        position={{ x: 10, y: 10 }}
        onReply={vi.fn()}
        onRegenerate={vi.fn()}
        onTogglePin={vi.fn()}
        onForward={onForward}
        onMultiSelect={onMultiSelect}
        onCopy={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("menuitem", { name: "转发" }));
    expect(onForward).toHaveBeenCalledWith(assistant);

    render(
      <MessageActions
        message={assistant}
        open
        position={{ x: 10, y: 10 }}
        onReply={vi.fn()}
        onRegenerate={vi.fn()}
        onTogglePin={vi.fn()}
        onForward={vi.fn()}
        onMultiSelect={onMultiSelect}
        onCopy={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(screen.getAllByRole("menuitem", { name: "多选" })[0]);
    expect(onMultiSelect).toHaveBeenCalledWith(assistant);
  });
});
