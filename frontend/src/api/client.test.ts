import { describe, it, expect, vi, afterEach } from "vitest";
import { createChatStream } from "./client";

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
