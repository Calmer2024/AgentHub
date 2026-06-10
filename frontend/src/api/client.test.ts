import { describe, it, expect, vi, afterEach } from "vitest";
import {
  configureApiClient,
  configureBuiltinAgentsCodex,
  createDevCloudAuthProvider,
  createArtifactPreview,
  createDeployment,
  createProject,
  createTeam,
  createWorkspaceSnapshot,
  createProjectBuildPreview,
  createProjectPreview,
  createChatStream,
  fetchProjects,
  editArtifact,
  fetchArtifactDiff,
  fetchArtifactVersions,
  fetchArtifacts,
  fetchCurrentUser,
  fetchDeploymentLogs,
  fetchProjectBuildLogs,
  fetchProjectBuilds,
  fetchWorkspace,
  importWorkspaceGithub,
  fetchRuntimeImages,
  fetchRunnerNodes,
  projectBuildExportUrl,
  projectSourceExportUrl,
  readProjectFile,
  restoreArtifactVersion,
  saveArtifactContent,
  startProjectBuild,
  retryDeployment,
  resetApiClientForTests,
  fetchCliCredentials,
  loginWithEmail,
  saveCliCredential,
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
    resetApiClientForTests();
  });

  it("发送消息时把附件 ID 注入请求体", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse([
      JSON.stringify({ token: "", done: true, messageId: "m1" }),
    ]));

    createChatStream("s1", "hello", [], {
      onToken: vi.fn(),
      onDone: vi.fn(),
    }, undefined, null, ["att-1"]);

    await vi.waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    const init = vi.mocked(globalThis.fetch).mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body))).toMatchObject({
      content: "hello",
      attachmentIds: ["att-1"],
    });
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

  it("群聊完成后继续读取会话标题更新事件", async () => {
    const onDone = vi.fn();
    const onSessionTitleUpdated = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse([
      JSON.stringify({ type: "orchestrator.task_completed", summary: "done" }),
      JSON.stringify({
        type: "session.title_updated",
        sessionId: "s1",
        session: {
          id: "s1",
          title: "登录页优化",
          mode: "group",
          projectId: "p1",
          agentConfigId: null,
          createdAt: "2026-06-07T12:00:00+08:00",
          updatedAt: "2026-06-07T12:01:00+08:00",
        },
      }),
    ]));

    createChatStream("s1", "hello", [], {
      onToken: vi.fn(),
      onDone,
      onTaskCompleted: vi.fn(),
      onSessionTitleUpdated,
    });

    await vi.waitFor(() => expect(onSessionTitleUpdated).toHaveBeenCalled());
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(onSessionTitleUpdated.mock.calls[0][0]).toMatchObject({
      id: "s1",
      title: "登录页优化",
      mode: "group",
    });
  });

  it("没有任务完成回调时也会把群聊完成视为正常结束", async () => {
    const onDone = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse([
      JSON.stringify({ type: "orchestrator.task_completed", summary: "done" }),
    ]));

    createChatStream("s1", "hello", [], {
      onToken: vi.fn(),
      onDone,
    });

    await vi.waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(onDone).toHaveBeenCalledWith(undefined, undefined);
  });

  it("收到 Agent done 后自然 EOF 不误报连接中断", async () => {
    const onDone = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse([
      JSON.stringify({
        type: "agent.start",
        agentId: "agent-product",
        agentName: "产品经理",
        messageId: "m1",
        callKey: "agent-product:0:direct_dialog",
      }),
      JSON.stringify({
        type: "agent.output",
        agentId: "agent-product",
        agentName: "产品经理",
        messageId: "m1",
        callKey: "agent-product:0:direct_dialog",
        token: "页面信息顺序、视觉风格",
        chunkType: "text",
      }),
      JSON.stringify({
        agentId: "agent-product",
        agentName: "产品经理",
        done: true,
        messageId: "m1",
        callKey: "agent-product:0:direct_dialog",
      }),
    ]));

    createChatStream("s1", "hello", [], {
      onToken: vi.fn(),
      onDone,
      onAgentStart: vi.fn(),
      onAgentToken: vi.fn(),
    });

    await vi.waitFor(() => expect(onDone).toHaveBeenCalled());
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

  it("解析 Orchestrator 调度器的无 @ 分流决策", async () => {
    const onStewardDecision = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse([
      JSON.stringify({
        type: "orchestrator.steward_decision",
        decision: {
          routeType: "single_agent",
          confidence: 0.74,
          reason: "识别为单 Agent 快速响应",
          selectedAgents: [{ id: "backend", name: "后端专家" }],
          taskBrief: "后端看看这个 API",
          requiresApproval: false,
          riskLevel: "low",
          intent: "code_gen",
          requiredTags: ["API", "后端"],
        },
      }),
      JSON.stringify({ type: "orchestrator.task_completed", summary: "done" }),
    ]));

    createChatStream("s1", "后端看看这个 API", [], {
      onToken: vi.fn(),
      onDone: vi.fn(),
      onStewardDecision,
      onTaskCompleted: vi.fn(),
    });

    await vi.waitFor(() => expect(onStewardDecision).toHaveBeenCalled());
    expect(onStewardDecision).toHaveBeenCalledWith({
      routeType: "single_agent",
      confidence: 0.74,
      reason: "识别为单 Agent 快速响应",
      selectedAgents: [{ id: "backend", name: "后端专家" }],
      taskBrief: "后端看看这个 API",
      requiresApproval: false,
      riskLevel: "low",
      intent: "code_gen",
      requiredTags: ["API", "后端"],
    });
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
    expect((init.headers as Record<string, string>)["X-AgentHub-User-Email"]).toBeUndefined();
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

  it("把原生 engine session resume 显示为恢复会话而不是常驻进程", async () => {
    const onTraceDelta = vi.fn();
    const onProgress = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse([
      JSON.stringify({
        type: "agent.process.started",
        agentName: "Claude Code",
        messageId: "m1",
        callKey: "agent:m1",
        processId: "proc-2",
        persistentProcess: false,
        engineSessionMode: "resume",
      }),
      JSON.stringify({ token: "", done: true, messageId: "m1" }),
    ]));

    createChatStream("s1", "hello", [], {
      onToken: vi.fn(),
      onDone: vi.fn(),
      onTraceDelta,
      onProgress,
    });

    await vi.waitFor(() => expect(onTraceDelta).toHaveBeenCalled());
    expect(onTraceDelta.mock.calls[0][1]).toMatchObject({
      title: "恢复 Claude Code 会话",
      persistentProcess: false,
    });
    expect(onProgress).toHaveBeenCalledWith("恢复 Claude Code 会话...");
  });
});

describe("artifact APIs", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    resetApiClientForTests();
    localStorage.clear();
  });

  it("加载会话产物列表", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify([
      { id: "a1", version: 2, parentArtifactId: "a0" },
    ]), { status: 200 }));

    const artifacts = await fetchArtifacts("s1");

    expect(vi.mocked(globalThis.fetch).mock.calls[0][0]).toBe("/api/sessions/s1/artifacts");
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

  it("启动项目构建并读取构建列表与日志", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        buildId: "b1",
        status: "succeeded",
      }), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        items: [{ id: "b1", projectId: "p1", status: "succeeded", command: "npm run build", createdAt: "" }],
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        chunks: [{ sequence: 1, stream: "stdout", text: "done", createdAt: "" }],
      }), { status: 200 }));

    await startProjectBuild("p1", { artifactPath: "dist" });
    await fetchProjectBuilds("p1");
    await fetchProjectBuildLogs("p1", "b1");

    const startInit = vi.mocked(globalThis.fetch).mock.calls[0][1] as RequestInit;
    expect(vi.mocked(globalThis.fetch).mock.calls[0][0]).toBe("/api/projects/p1/builds");
    expect(JSON.parse(String(startInit.body))).toMatchObject({ artifactPath: "dist" });
    expect(vi.mocked(globalThis.fetch).mock.calls[1][0]).toBe("/api/projects/p1/builds");
    expect(vi.mocked(globalThis.fetch).mock.calls[2][0]).toBe("/api/projects/p1/builds/b1/logs");
  });

  it("为构建产物创建预览并生成导出 URL", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      previewId: "p-build",
      url: "/api/projects/p1/preview/p-build/dist/index.html",
      source: "build",
    }), { status: 200 }));

    const result = await createProjectBuildPreview("p1", {
      source: "build",
      buildId: "b1",
      path: "index.html",
    });

    expect(result.url).toContain("dist/index.html");
    const [url, init] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(url).toBe("/api/projects/p1/previews");
    expect(JSON.parse(String((init as RequestInit).body))).toMatchObject({
      source: "build",
      buildId: "b1",
      path: "index.html",
    });
    expect(projectSourceExportUrl("p1")).toBe("/api/projects/p1/exports/source");
    expect(projectBuildExportUrl("p1", "b1")).toBe("/api/projects/p1/exports/builds/b1");
  });

  it("创建云端预览、发布并读取发布日志与重试", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: "preview-1",
        artifactId: "a1",
        artifactVersionId: "v1",
        projectId: "p1",
        source: "static",
        status: "ready",
        url: "https://preview.agenthub.local/p/preview-1",
        visibility: "team",
        expiresAt: "",
        createdAt: "",
        revokedAt: null,
      }), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: "dep-1",
        projectId: "p1",
        artifactId: "a1",
        artifactVersionId: "v1",
        target: "static_hosting",
        status: "failed",
        stage: "build",
        url: null,
        visibility: "team",
        errorSummary: "发布构建失败",
        createdAt: "",
        updatedAt: "",
      }), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        deploymentId: "dep-1",
        chunks: [{ sequence: 1, stream: "stderr", text: "DEPLOY_FAIL", createdAt: "" }],
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: "dep-1",
        projectId: "p1",
        artifactId: "a1",
        artifactVersionId: "v1",
        target: "static_hosting",
        status: "published",
        stage: "verify",
        url: "https://deploy.agenthub.local/d/dep-1",
        visibility: "team",
        errorSummary: null,
        createdAt: "",
        updatedAt: "",
      }), { status: 202 }));

    await createArtifactPreview("a1", { artifactVersionId: "v1", visibility: "team" });
    await createDeployment({ artifactId: "a1", artifactVersionId: "v1" });
    const logs = await fetchDeploymentLogs("dep-1");
    const retried = await retryDeployment("dep-1", "build");

    expect(logs.chunks[0].text).toBe("DEPLOY_FAIL");
    expect(retried.status).toBe("published");
    const previewInit = vi.mocked(globalThis.fetch).mock.calls[0][1] as RequestInit;
    expect(vi.mocked(globalThis.fetch).mock.calls[0][0]).toBe("/api/artifacts/a1/previews");
    expect(JSON.parse(String(previewInit.body))).toMatchObject({
      source: "static",
      artifactVersionId: "v1",
      visibility: "team",
    });
    expect(vi.mocked(globalThis.fetch).mock.calls[1][0]).toBe("/api/deployments");
    expect(vi.mocked(globalThis.fetch).mock.calls[2][0]).toBe("/api/deployments/dep-1/logs");
    expect(vi.mocked(globalThis.fetch).mock.calls[3][0]).toBe("/api/deployments/dep-1/retry");
  });

  it("加载产物版本链", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify([
      { id: "a1", version: 1, content: "old", createdAt: "" },
    ]), { status: 200 }));

    await fetchArtifactVersions("a1");

    expect(vi.mocked(globalThis.fetch).mock.calls[0][0]).toBe("/api/artifacts/a1/versions");
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

describe("production auth headers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    resetApiClientForTests();
    localStorage.clear();
  });

  it("登录后用 bearer token 访问云端 API", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        accessToken: "access-1",
        refreshToken: "refresh-1",
        tokenType: "bearer",
        expiresAt: "2026-06-09T12:00:00",
        user: {
          id: "u1",
          email: "prod@example.com",
          displayName: "Prod User",
          createdAt: "2026-06-09T12:00:00",
          status: "active",
          teams: [],
          defaultSpace: { kind: "personal", id: "u1", name: "个人空间" },
        },
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }));

    await loginWithEmail({ identifier: "prod@example.com", password: "Prod-passw0rd" });
    await fetchProjects();

    const loginInit = vi.mocked(globalThis.fetch).mock.calls[0][1] as RequestInit;
    const init = vi.mocked(globalThis.fetch).mock.calls[1][1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(loginInit.credentials).toBe("include");
    expect(headers.Authorization).toBe("Bearer access-1");
    expect(headers["X-AgentHub-User-Email"]).toBeUndefined();
  });

  it("localStorage 丢失但 refresh cookie 有效时自动恢复登录态", async () => {
    const currentUser = {
      id: "u-cookie",
      email: "cookie@example.com",
      displayName: "Cookie User",
      createdAt: "2026-06-09T12:00:00",
      status: "active",
      teams: [],
      defaultSpace: { kind: "personal", id: "u-cookie", name: "个人空间" },
    };
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "请先登录后继续" }), { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        accessToken: "access-cookie",
        refreshToken: "refresh-cookie",
        tokenType: "bearer",
        expiresAt: "2026-06-09T12:15:00",
        user: currentUser,
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(currentUser), { status: 200 }));

    const user = await fetchCurrentUser();

    expect(user.email).toBe("cookie@example.com");
    expect(vi.mocked(globalThis.fetch).mock.calls[0][0]).toBe("/api/auth/me");
    expect(vi.mocked(globalThis.fetch).mock.calls[1][0]).toBe("/api/auth/refresh");
    expect(vi.mocked(globalThis.fetch).mock.calls[2][0]).toBe("/api/auth/me");
    const firstMeInit = vi.mocked(globalThis.fetch).mock.calls[0][1] as RequestInit;
    const refreshInit = vi.mocked(globalThis.fetch).mock.calls[1][1] as RequestInit;
    const retryInit = vi.mocked(globalThis.fetch).mock.calls[2][1] as RequestInit;
    expect(firstMeInit.credentials).toBe("include");
    expect(refreshInit.credentials).toBe("include");
    expect(refreshInit.body).toBeUndefined();
    expect(retryInit.credentials).toBe("include");
    expect((retryInit.headers as Record<string, string>).Authorization).toBe("Bearer access-cookie");
  });
});

describe("SaaS CLI credentials APIs", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    resetApiClientForTests();
    localStorage.clear();
  });

  it("读取并保存 CLI 凭据时使用云端认证头且不回传明文 key", async () => {
    configureApiClient({ cloudAuthProvider: createDevCloudAuthProvider() });
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        items: [{
          cliTool: "codex",
          scope: "user",
          ownerId: "u1",
          providerType: "proxy",
          providerId: "relay",
          providerName: "Relay",
          baseUrl: "https://relay.example/v1",
          model: "relay-codex",
          authEnvKey: "AGENTHUB_CODEX_API_KEY",
          configured: true,
          secretNames: ["AGENTHUB_CODEX_API_KEY"],
          updatedAt: "",
        }],
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        cliTool: "codex",
        scope: "user",
        ownerId: "u1",
        providerType: "proxy",
        providerId: "relay",
        providerName: "Relay",
        baseUrl: "https://relay.example/v1",
        model: "relay-codex",
        authEnvKey: "AGENTHUB_CODEX_API_KEY",
        configured: true,
        secretNames: ["AGENTHUB_CODEX_API_KEY"],
        updatedAt: "",
      }), { status: 200 }));

    const items = await fetchCliCredentials();
    const saved = await saveCliCredential("codex", {
      providerType: "proxy",
      providerId: "relay",
      providerName: "Relay",
      baseUrl: "https://relay.example/v1",
      model: "relay-codex",
      authEnvKey: "AGENTHUB_CODEX_API_KEY",
      apiKey: "secret-key",
    });

    expect(items[0].cliTool).toBe("codex");
    expect(saved.configured).toBe(true);
    const listInit = vi.mocked(globalThis.fetch).mock.calls[0][1] as RequestInit;
    const saveInit = vi.mocked(globalThis.fetch).mock.calls[1][1] as RequestInit;
    expect(vi.mocked(globalThis.fetch).mock.calls[0][0]).toBe("/api/cli-credentials");
    expect(vi.mocked(globalThis.fetch).mock.calls[1][0]).toBe("/api/cli-credentials/codex");
    expect((listInit.headers as Record<string, string>)["X-AgentHub-User-Email"]).toBe("demo@agenthub.local");
    expect(JSON.parse(String(saveInit.body))).toMatchObject({
      providerType: "proxy",
      apiKey: "secret-key",
    });
  });
});

describe("phase9 cloud workspace APIs", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    resetApiClientForTests();
  });

  it("创建云端项目和团队请求带开发态登录 header", async () => {
    configureApiClient({ cloudAuthProvider: createDevCloudAuthProvider() });
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: "t1",
        name: "研发团队",
        role: "owner",
        memberCount: 1,
        createdAt: "",
      }), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: "p1",
        name: "云端",
        workspaceMode: "cloud",
        workspaceId: "w1",
        workspacePath: null,
        status: "ready",
        fileCount: 0,
        totalSizeBytes: 0,
        createdAt: "",
      }), { status: 201 }));

    await createTeam("研发团队");
    await createProject({ name: "云端", workspaceMode: "cloud", teamId: "t1" });

    const teamInit = vi.mocked(globalThis.fetch).mock.calls[0][1] as RequestInit;
    const projectInit = vi.mocked(globalThis.fetch).mock.calls[1][1] as RequestInit;
    expect((teamInit.headers as Record<string, string>)["X-AgentHub-User-Email"]).toBe("demo@agenthub.local");
    expect((projectInit.headers as Record<string, string>)["X-AgentHub-User-Email"]).toBe("demo@agenthub.local");
    expect(JSON.parse(String(projectInit.body))).toMatchObject({
      workspaceMode: "cloud",
      teamId: "t1",
    });
  });

  it("读取 workspace、创建快照并排队 GitHub 导入", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: "w1",
        projectId: "p1",
        provider: "cloud",
        status: "ready",
        storageUri: "cloud://agenthub/workspaces/w1",
        snapshots: [],
        imports: [],
        restores: [],
        createdAt: "",
        updatedAt: "",
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: "snap1",
        workspaceId: "w1",
        label: "手动快照",
        storageUri: "cloud://agenthub/workspaces/w1/snapshots/snap1",
        createdAt: "",
      }), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        importId: "imp1",
        status: "queued",
      }), { status: 202 }));

    await fetchWorkspace("w1");
    await createWorkspaceSnapshot("w1", "手动快照");
    await importWorkspaceGithub("w1", { repoUrl: "https://github.com/example/repo", branch: "main" });

    expect(vi.mocked(globalThis.fetch).mock.calls[0][0]).toBe("/api/workspaces/w1");
    expect(vi.mocked(globalThis.fetch).mock.calls[1][0]).toBe("/api/workspaces/w1/snapshots");
    expect(vi.mocked(globalThis.fetch).mock.calls[2][0]).toBe("/api/workspaces/w1/imports/github");
  });
});

describe("phase15 runtime APIs", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    resetApiClientForTests();
  });

  it("读取 runtime images 和 runner nodes 时带云端身份 header", async () => {
    configureApiClient({ cloudAuthProvider: createDevCloudAuthProvider() });
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        items: [{
          id: "img-1",
          label: "默认 CLI Runtime",
          image: "agenthub/default-cli:phase15",
          provider: "local_dev",
          default: true,
          tools: ["custom-cli"],
        }],
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        items: [{
          id: "runner-1",
          provider: "local_dev",
          region: "local",
          status: "healthy",
          capacity: { concurrentRuns: 2 },
          createdAt: "",
        }],
      }), { status: 200 }));

    const images = await fetchRuntimeImages();
    const nodes = await fetchRunnerNodes();

    expect(images[0].image).toBe("agenthub/default-cli:phase15");
    expect(nodes[0].status).toBe("healthy");
    const imageInit = vi.mocked(globalThis.fetch).mock.calls[0][1] as RequestInit;
    const nodeInit = vi.mocked(globalThis.fetch).mock.calls[1][1] as RequestInit;
    expect(vi.mocked(globalThis.fetch).mock.calls[0][0]).toBe("/api/runtime/images");
    expect(vi.mocked(globalThis.fetch).mock.calls[1][0]).toBe("/api/runtime/runner-nodes");
    expect((imageInit.headers as Record<string, string>)["X-AgentHub-User-Email"]).toBe("demo@agenthub.local");
    expect((nodeInit.headers as Record<string, string>)["X-AgentHub-User-Email"]).toBe("demo@agenthub.local");
  });
});

describe("agent debug APIs", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("一键统一内置 Agent 为 Codex 引擎", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify([
      {
        id: "orchestrator",
        name: "Orchestrator 调度器",
        description: "",
        systemPrompt: "",
        rules: "",
        agentType: "cli_wrapper",
        cliTool: "codex",
        executable: "codex",
        initArgs: ["exec"],
        envVars: {},
        toolset: [],
        primarySkill: "orchestrator_planner",
        auxiliarySkills: [],
        contextPolicy: "planning_only",
        avatar: "preset:violet",
        status: "ready",
        isActive: true,
        createdAt: "",
        updatedAt: "",
      },
    ]), { status: 200 }));

    const agents = await configureBuiltinAgentsCodex();

    expect(globalThis.fetch).toHaveBeenCalledWith("/api/agents/configure-builtins-codex", {
      method: "POST",
      headers: {},
    });
    expect(agents[0].cliTool).toBe("codex");
  });
});
