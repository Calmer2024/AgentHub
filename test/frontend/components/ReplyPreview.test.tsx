import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ReplyPreview } from "../../../frontend/src/components/ReplyPreview";
import type { Message } from "../../../frontend/src/types";

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
    const { container } = render(<ReplyPreview message={message} onJump={onJump} />);

    fireEvent.click(screen.getByRole("button", { name: "你" }));
    expect(screen.getByText("这是一条需要引用的消息")).toBeInTheDocument();
    expect(container.querySelector(".agenthub-reference-card")).toBeInTheDocument();
    expect(onJump).toHaveBeenCalledWith("m-parent");
  });

  it("渲染已删除原消息状态", () => {
    render(<ReplyPreview message={null} />);

    expect(screen.getAllByText("原消息已删除").length).toBeGreaterThan(0);
  });
});
