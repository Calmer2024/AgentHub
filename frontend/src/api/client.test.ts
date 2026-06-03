import { describe, it, expect, vi, afterEach } from "vitest";
import {
  createChatStream,
  editArtifact,
  fetchArtifactDiff,
  fetchArtifactVersions,
  fetchArtifacts,
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
});
