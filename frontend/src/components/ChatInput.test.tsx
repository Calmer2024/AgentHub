import { describe, expect, it, vi, afterEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ChatInput } from "./ChatInput";
import { useChatStore } from "../stores/chatStore";

describe("ChatInput", () => {
  afterEach(() => {
    useChatStore.setState({ codeReference: null, replyTarget: null });
  });

  it("发送时携带代码片段引用块并清空引用", () => {
    const onSubmit = vi.fn();
    useChatStore.setState({
      codeReference: {
        artifactId: "a1",
        projectId: "p1",
        filePath: "src/app.ts",
        language: "tsx",
        startLine: 2,
        endLine: 3,
        content: "const value = 1;",
      },
    });

    render(<ChatInput onSubmit={onSubmit} mentionableAgents={[]} />);
    fireEvent.change(screen.getByPlaceholderText("输入消息，@ 提及智能体"), {
      target: { value: "请把这里改成 2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(onSubmit).toHaveBeenCalledWith(expect.stringContaining("[代码引用：src/app.ts:2-3]"), []);
    expect(onSubmit.mock.calls[0][0]).toContain("```tsx\nconst value = 1;\n```");
    expect(onSubmit.mock.calls[0][0]).toContain("请把这里改成 2");
    expect(useChatStore.getState().codeReference).toBeNull();
  });
});
