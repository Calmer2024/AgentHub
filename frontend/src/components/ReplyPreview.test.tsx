import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ReplyPreview } from "./ReplyPreview";
import type { Message } from "../types";

const message: Message = {
  id: "m-parent",
  sessionId: "s1",
  role: "user",
  content: "这是一条需要引用的消息",
  agentName: null,
  createdAt: "",
};

describe("ReplyPreview", () => {
  it("渲染引用摘要并支持跳转", () => {
    const onJump = vi.fn();
    render(<ReplyPreview message={message} onJump={onJump} />);

    fireEvent.click(screen.getByText("回复 用户"));
    expect(screen.getByText("这是一条需要引用的消息")).toBeInTheDocument();
    expect(onJump).toHaveBeenCalledWith("m-parent");
  });

  it("渲染已删除原消息状态", () => {
    render(<ReplyPreview message={null} />);

    expect(screen.getAllByText("原消息已删除").length).toBeGreaterThan(0);
  });
});
