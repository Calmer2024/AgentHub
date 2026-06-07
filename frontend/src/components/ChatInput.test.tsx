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

  it("输入 @ 时即使成员还在加载也给出可见提示", () => {
    render(<ChatInput onSubmit={vi.fn()} mentionableAgents={[]} mentionLoading />);

    fireEvent.change(screen.getByPlaceholderText("输入消息，@ 提及智能体"), {
      target: { value: "@" },
    });

    expect(screen.getByText("正在加载可提及智能体...")).toBeInTheDocument();
  });

  it("从 @ 列表选择 Agent 后发送结构化 mentions", () => {
    const onSubmit = vi.fn();
    render(<ChatInput
      onSubmit={onSubmit}
      mentionableAgents={[{
        id: "agent-writer",
        name: "文档专家",
        description: "",
        systemPrompt: "",
        agentType: "cli_wrapper",
        cliTool: "custom",
        executable: null,
        initArgs: [],
        envVars: {},
        primarySkill: "technical_writer",
        auxiliarySkills: [],
        contextPolicy: "default",
        status: "ready",
        isActive: true,
        createdAt: "",
        updatedAt: "",
      }]}
    />);

    const input = screen.getByPlaceholderText("输入消息，@ 提及智能体");
    fireEvent.change(input, { target: { value: "@文" } });
    fireEvent.mouseDown(screen.getByText("@文档专家"));
    fireEvent.change(input, { target: { value: "@文档专家 帮我整理需求" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(onSubmit).toHaveBeenCalledWith("@文档专家 帮我整理需求", ["agent-writer"]);
  });
});
