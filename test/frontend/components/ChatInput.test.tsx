import { describe, expect, it, vi, afterEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ChatInput } from "../../../frontend/src/components/ChatInput";
import { useChatStore } from "../../../frontend/src/stores/chatStore";

describe("ChatInput", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    useChatStore.setState({ codeReference: null, replyTarget: null });
  });

  it("输入栏外层只作为透明悬浮层，内部聊天框保留半透明背景", () => {
    const { container } = render(<ChatInput onSubmit={vi.fn()} mentionableAgents={[]} />);

    const inputbar = container.querySelector("form.agenthub-inputbar");
    const composer = container.querySelector(".agenthub-chat-composer");

    expect(inputbar).toBeInTheDocument();
    expect(inputbar).not.toHaveClass("agenthub-composer");
    expect(inputbar).not.toHaveClass("agenthub-card");
    expect(inputbar).not.toHaveClass("agenthub-soft");
    expect(composer).toBeInTheDocument();
    expect(composer).toHaveClass("agenthub-chat-composer");
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
        rules: "",
        agentType: "cli_wrapper",
        cliTool: "custom",
        executable: null,
        initArgs: [],
        envVars: {},
        toolset: [],
        primarySkill: "technical_writer",
        auxiliarySkills: [],
        contextPolicy: "default",
        avatar: "preset:slate",
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

  it("上传附件后发送 attachmentIds 作为下一轮上下文", async () => {
    const onSubmit = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      id: "att-1",
      projectId: "p1",
      sessionId: "s1",
      filename: "brief.md",
      mimeType: "text/markdown",
      sizeBytes: 12,
      storageUri: "attachment://agenthub/p1/att-1/brief.md",
      createdAt: "",
    }), { status: 201 }));

    const { container } = render(
      <ChatInput
        onSubmit={onSubmit}
        mentionableAgents={[]}
        currentProjectId="p1"
        currentSessionId="s1"
      />,
    );
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, {
      target: { files: [new File(["# brief"], "brief.md", { type: "text/markdown" })] },
    });

    await screen.findByText("brief.md");
    fireEvent.change(screen.getByPlaceholderText("输入消息，@ 提及智能体"), {
      target: { value: "请阅读附件" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(onSubmit).toHaveBeenCalledWith("请阅读附件", [], ["att-1"]);
  });
});
