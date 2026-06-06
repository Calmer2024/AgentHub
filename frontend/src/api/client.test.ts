import { describe, it, expect, vi, afterEach } from "vitest";
import {
  createProjectPreview,
  createChatStream,
  editArtifact,
  fetchArtifactDiff,
  fetchArtifactVersions,
  fetchArtifacts,
  readProjectFile,
  restoreArtifactVersion,
  saveArtifactContent,
  writeProjectFile,
} from "./client";

function sseResponse(events: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      events.forEach((event) => controller.enqueue(encoder.encode(`data: ${event}\n\n`)));
      controller.close();
    },
  });
  return new Response(body, { status: 200 });
}

describe("createChatStream", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("把 orchestrator.task_completed 视为群聊正常结束", async () => {
    const onDone = vi.fn();
    const onTaskCompleted = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse([
      JSON.stringify({ type: "orchestrator.task_completed", summary: "4 agents completed" }),
    ]));

    createChatStream("s1", "hello", [], {
      onToken: vi.fn(),
      onDone,
      onTaskCompleted,
    });

    await vi.waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(onTaskCompleted).toHaveBeenCalledWith("4 agents completed");
    expect(onDone).toHaveBeenCalledWith(undefined, undefined);
  });

  it("从 task_started 读取后端生成的分工解释", async () => {
    const onTaskStarted = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse([
      JSON.stringify({
        type: "orchestrator.task_started",
        intent: "code_gen",
        plan_summary: "已安排: 先由@架构师规划。",
        tasks: [],
      }),
      JSON.stringify({ type: "orchestrator.task_completed", summary: "done" }),
    ]));

    createChatStream("s1", "hello", [], {
      onToken: vi.fn(),
      onDone: vi.fn(),
      onTaskStarted,
      onTaskCompleted: vi.fn(),
    });

    await vi.waitFor(() => expect(onTaskStarted).toHaveBeenCalled());
    expect(onTaskStarted.mock.calls[0][3]).toBe("已安排: 先由@架构师规划。");
  });

  it("把 Orchestrator plan-only 当普通 Agent 输出解析", async () => {
    const onDone = vi.fn();
    const onAgentStart = vi.fn();
    const onAgentToken = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse([
      JSON.stringify({
        type: "agent.start",
        agentId: "agent-orchestrator",
        agentName: "Orchestrator 调度器",
        messageId: "plan-1",
        callKey: "agent-orchestrator:0:draft plan",
      }),
      JSON.stringify({
        type: "agent.output",
        agentId: "agent-orchestrator",
        agentName: "Orchestrator 调度器",
        messageId: "plan-1",
        callKey: "agent-orchestrator:0:draft plan",
        token: "{\"plan_id\":\"p1\"}",
        chunkType: "text",
      }),
      JSON.stringify({
        token: "",
        done: true,
        messageId: "plan-1",
      }),
    ]));

    createChatStream("s1", "hello", [], {
      onToken: vi.fn(),
      onDone,
      onAgentStart,
      onAgentToken,
    });

    await vi.waitFor(() => expect(onAgentToken).toHaveBeenCalled());
    expect(onAgentStart).toHaveBeenCalledWith(expect.objectContaining({
      agentName: "Orchestrator 调度器",
      messageId: "plan-1",
    }));
    expect(onAgentToken).toHaveBeenCalledWith(
      "agent-orchestrator",
      "Orchestrator 调度器",
      "{\"plan_id\":\"p1\"}",
      "plan-1",
      undefined,
      undefined,
      undefined,
    );
    expect(onDone).toHaveBeenCalledWith("plan-1", undefined);
  });

  it("发送引用消息时带上 parentMessageId", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse([
      JSON.stringify({ token: "", done: true, messageId: "m2" }),
    ]));

    createChatStream("s1", "hello", [], {
      onToken: vi.fn(),
      onDone: vi.fn(),
    }, undefined, "m-parent");

    await vi.waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    const init = vi.mocked(globalThis.fetch).mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body))).toMatchObject({
      content: "hello",
      parentMessageId: "m-parent",
    });
  });

  it("解析 Orchestrator 中枢总结流", async () => {
    const onStart = vi.fn();
    const onToken = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse([
      JSON.stringify({
        type: "orchestrator.summary_started",
        messageId: "sum-1",
        sourceName: "Orchestrator 中枢",
        contentType: "orchestrator_summary",
      }),
      JSON.stringify({
        type: "orchestrator.summary_delta",
        messageId: "sum-1",
        token: "综合结论",
      }),
      JSON.stringify({ type: "orchestrator.summary_completed", messageId: "sum-1" }),
      JSON.stringify({ type: "orchestrator.task_completed", summary: "done" }),
    ]));

    createChatStream("s1", "hello", [], {
      onToken: vi.fn(),
      onDone: vi.fn(),
      onOrchestratorSummaryStart: onStart,
      onOrchestratorSummaryToken: onToken,
      onTaskCompleted: vi.fn(),
    });

    await vi.waitFor(() => expect(onToken).toHaveBeenCalled());
    expect(onStart.mock.calls[0][0]).toMatchObject({
      messageId: "sum-1",
      sourceType: "orchestrator",
      contentType: "orchestrator_summary",
    });
    expect(onToken).toHaveBeenCalledWith("sum-1", "综合结论");
  });

  it("agent.output 文本事件即使缺少 token 字段也会进入回复流", async () => {
    const onToken = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse([
      JSON.stringify({
        type: "agent.output",
        messageId: "m1",
        chunkType: "text",
        chunk: "OpenCode visible text",
      }),
      JSON.stringify({ token: "", done: true, messageId: "m1" }),
    ]));

    createChatStream("s1", "hello", [], {
      onToken,
      onDone: vi.fn(),
    });

    await vi.waitFor(() => expect(onToken).toHaveBeenCalled());
    expect(onToken).toHaveBeenCalledWith("OpenCode visible text");
  });
});

describe("artifact APIs", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("加载会话产物列表", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify([
      { id: "a1", version: 2, parentArtifactId: "a0" },
    ]), { status: 200 }));

    const artifacts = await fetchArtifacts("s1");

    expect(globalThis.fetch).toHaveBeenCalledWith("/api/sessions/s1/artifacts");
    expect(artifacts[0].version).toBe(2);
  });

  it("为项目文件创建本机预览", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      previewId: "p1",
      previewUrl: "/api/projects/proj-1/preview/p1/pages/demo.html",
    }), { status: 200 }));

    const result = await createProjectPreview("proj-1", "pages/demo.html");

    expect(result.previewUrl).toContain("pages/demo.html");
    const [url, init] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(url).toBe("/api/projects/proj-1/preview");
    expect(JSON.parse(String((init as RequestInit).body))).toMatchObject({
      type: "static",
      filePath: "pages/demo.html",
    });
  });

  it("加载产物版本链", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify([
      { id: "a1", version: 1, content: "old", createdAt: "" },
    ]), { status: 200 }));

    await fetchArtifactVersions("a1");

    expect(globalThis.fetch).toHaveBeenCalledWith("/api/artifacts/a1/versions");
  });

  it("按版本号请求 Diff", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      fromVersion: 1,
      toVersion: 2,
      diff: "",
      oldContent: "old",
      newContent: "new",
    }), { status: 200 }));

    await fetchArtifactDiff("a1", 1, 2);

    expect(String(vi.mocked(globalThis.fetch).mock.calls[0][0])).toContain("v1=1&v2=2");
  });

  it("提交编辑预览请求", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      newVersion: null,
      diff: { fromVersion: 1, toVersion: 2, diff: "", oldContent: "", newContent: "" },
      artifact: null,
      proposedContent: "new",
      strategy: "fallback_context",
    }), { status: 200 }));

    await editArtifact("a1", {
      selection: "old",
      instruction: "改",
      editType: "replace",
      apply: true,
      proposedContent: "new",
    });

    const init = vi.mocked(globalThis.fetch).mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body))).toMatchObject({
      selection: "old",
      instruction: "改",
      editType: "replace",
      apply: true,
      proposedContent: "new",
    });
  });

  it("保存产物内容为新版本", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      id: "a2",
      version: 2,
      content: "new",
    }), { status: 200 }));

    const result = await saveArtifactContent("a1", "new", "demo.html");

    expect(result.version).toBe(2);
    const [url, init] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(url).toBe("/api/artifacts/a1/save");
    expect(JSON.parse(String((init as RequestInit).body))).toMatchObject({
      content: "new",
      title: "demo.html",
      writeWorkspace: true,
    });
  });

  it("恢复产物历史版本", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      id: "a3",
      version: 3,
      content: "old",
    }), { status: 200 }));

    await restoreArtifactVersion("a2", 1);

    const [url, init] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(url).toBe("/api/artifacts/a2/restore");
    expect(JSON.parse(String((init as RequestInit).body))).toMatchObject({
      version: 1,
      writeWorkspace: true,
    });
  });

  it("读写项目文件", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        path: "src/app.ts",
        content: "old",
        size: 3,
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        path: "src/app.ts",
        content: "new",
        size: 3,
      }), { status: 200 }));

    await readProjectFile("p1", "src/app.ts");
    await writeProjectFile("p1", "src/app.ts", "new");

    expect(String(vi.mocked(globalThis.fetch).mock.calls[0][0])).toBe("/api/projects/p1/files?path=src%2Fapp.ts");
    const writeInit = vi.mocked(globalThis.fetch).mock.calls[1][1] as RequestInit;
    expect(JSON.parse(String(writeInit.body))).toMatchObject({
      path: "src/app.ts",
      content: "new",
    });
  });
});
