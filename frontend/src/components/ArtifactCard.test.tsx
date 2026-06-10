import { describe, expect, it, vi, afterEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import React, { forwardRef } from "react";
import { ArtifactCard } from "./ArtifactCard";
import type { Artifact } from "../types";
import { useChatStore } from "../stores/chatStore";
import { StaticShellProvider } from "../app/ShellProvider";
import { saasDesktopCapabilities } from "../app/capabilities";

vi.mock("react-syntax-highlighter", () => ({
  Prism: ({ children }: { children: string }) => <pre>{children}</pre>,
}));

vi.mock("react-syntax-highlighter/dist/esm/styles/prism", () => ({
  oneDark: {},
}));

vi.mock("./CodeMirrorFileEditor", () => ({
  CodeMirrorFileEditor: forwardRef<HTMLTextAreaElement, {
    value: string;
    onChange?: (value: string) => void;
    onUpdate?: (update: {
      state: {
        selection: { main: { from: number; to: number; head: number } };
        doc: {
          sliceString: (from: number, to: number) => string;
          lineAt: (pos: number) => { number: number; from: number };
        };
      };
    }) => void;
    "aria-label"?: string;
  }>(function MockCodeMirror({ value, onChange, onUpdate, "aria-label": ariaLabel }) {
    const innerRef = React.useRef<HTMLTextAreaElement | null>(null);

    const emitUpdate = () => {
      const el = innerRef.current;
      if (!el || !onUpdate) return;
      const from = el.selectionStart;
      const to = el.selectionEnd;
      onUpdate({
        state: {
          selection: { main: { from, to, head: to } },
          doc: {
            sliceString: (start: number, end: number) => value.slice(start, end),
            lineAt: (pos: number) => {
              const before = value.slice(0, pos);
              const lines = before.split("\n");
              return {
                number: lines.length,
                from: before.length - lines[lines.length - 1].length,
              };
            },
          },
        },
      });
    };

    return (
      <textarea
        aria-label={ariaLabel ?? "IDE 代码编辑器"}
        ref={innerRef}
        value={value}
        onChange={(event) => onChange?.(event.target.value)}
        onMouseUp={emitUpdate}
        onKeyUp={emitUpdate}
      />
    );
  }),
}));

const artifact: Artifact = {
  id: "a2",
  sessionId: "s1",
  messageId: "m1",
  type: "code_diff",
  title: "hello.py",
  content: "def hello():\n    return 'v2'\n",
  status: "ready",
  version: 2,
  parentArtifactId: "a1",
  createdAt: "",
};

function jsonResponse(data: unknown) {
  return Promise.resolve(new Response(JSON.stringify(data), { status: 200 }));
}

describe("ArtifactCard", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    useChatStore.setState({ codeReference: null, replyTarget: null });
  });

  it("打开后加载版本并展示统一 Diff", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/versions")) {
        return jsonResponse([
          { id: "a1", version: 1, content: "def hello():\n    return 'v1'\n", createdAt: "" },
          { id: "a2", version: 2, content: "def hello():\n    return 'v2'\n", createdAt: "" },
        ]);
      }
      if (url.includes("/diff")) {
        return jsonResponse({
          fromVersion: 1,
          toVersion: 2,
          diff: "-v1\n+v2",
          oldContent: "return 'v1'",
          newContent: "return 'v2'",
        });
      }
      return jsonResponse({});
    });

    render(<ArtifactCard artifact={artifact} />);
    fireEvent.click(screen.getByRole("button", { name: "打开产物预览：hello.py" }));

    await vi.waitFor(() => expect(screen.getAllByText("v1 → v2").length).toBeGreaterThan(0));
    expect(screen.queryByText("起点")).not.toBeInTheDocument();
    expect(screen.queryByText("目标")).not.toBeInTheDocument();
    expect(screen.queryByText("上下")).not.toBeInTheDocument();
    expect(screen.queryByText("左右")).not.toBeInTheDocument();

    const dialog = screen.getByRole("dialog", { name: /代码变更/ });
    expect(dialog.parentElement).toBe(document.body);
  });

  it("编辑文件保存后通知父级刷新", async () => {
    const onChanged = vi.fn();
    const webArtifact: Artifact = {
      ...artifact,
      id: "web-a1",
      type: "web_preview",
      title: "demo.html",
      content: "<html><body>old</body></html>",
      projectId: "proj-1",
      filePath: "demo.html",
      version: 1,
      parentArtifactId: null,
    };
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/versions")) {
        return jsonResponse([
          { id: "web-a1", version: 1, content: webArtifact.content, createdAt: "" },
        ]);
      }
      if (url.includes("/files?")) {
        return jsonResponse({ path: "demo.html", content: webArtifact.content, size: webArtifact.content.length });
      }
      if (url.endsWith("/save")) {
        const body = JSON.parse(String((init as RequestInit).body));
        return jsonResponse({ ...webArtifact, id: "web-a2", version: 2, content: body.content, parentArtifactId: "web-a1" });
      }
      return jsonResponse({});
    });

    render(<ArtifactCard artifact={webArtifact} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "编辑文件" }));

    const textarea = await screen.findByLabelText("IDE 代码编辑器");
    fireEvent.change(textarea, { target: { value: "<html><body>new</body></html>" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await screen.findByText("已保存");
    await vi.waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("文件编辑器选区可添加为对话代码引用", async () => {
    useChatStore.setState({ codeReference: null });
    const webArtifact: Artifact = {
      ...artifact,
      id: "web-a1",
      type: "web_preview",
      title: "demo.html",
      content: "<html><body>hello</body></html>",
      projectId: "proj-1",
      filePath: "demo.html",
      version: 1,
      parentArtifactId: null,
    };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/versions")) {
        return jsonResponse([{ id: "web-a1", version: 1, content: webArtifact.content, createdAt: "" }]);
      }
      if (url.includes("/files?")) {
        return jsonResponse({ path: "demo.html", content: webArtifact.content, size: webArtifact.content.length });
      }
      return jsonResponse({});
    });

    render(<ArtifactCard artifact={webArtifact} />);
    fireEvent.click(screen.getByRole("button", { name: "编辑文件" }));

    const textarea = await screen.findByLabelText("IDE 代码编辑器");
    const start = webArtifact.content.indexOf("hello");
    (textarea as HTMLTextAreaElement).setSelectionRange(start, start + "hello".length);
    fireEvent.mouseUp(textarea);
    fireEvent.click(screen.getByRole("button", { name: "添加到对话" }));

    expect(useChatStore.getState().codeReference?.content).toBe("hello");
    expect(useChatStore.getState().codeReference?.filePath).toBe("demo.html");
  });

  it("网页产物优先加载本机 workspace 预览 URL", async () => {
    const webArtifact: Artifact = {
      ...artifact,
      id: "web-a1",
      type: "web_preview",
      title: "demo.html",
      content: "<html><body>fallback</body></html>",
      projectId: "proj-1",
      filePath: "pages/demo.html",
      version: 1,
      parentArtifactId: null,
    };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/versions")) {
        return jsonResponse([
          { id: "web-a1", version: 1, content: webArtifact.content, createdAt: "" },
        ]);
      }
      if (url.endsWith("/preview")) {
        return jsonResponse({
          previewId: "p1",
          previewUrl: "/api/projects/proj-1/preview/p1/pages/demo.html",
        });
      }
      return jsonResponse({});
    });

    render(<ArtifactCard artifact={webArtifact} />);

    await vi.waitFor(() => {
      expect(String(vi.mocked(globalThis.fetch).mock.calls.some(([url]) => String(url).endsWith("/preview")))).toBe("true");
    });
    const iframe = screen.getByTitle("preview") as HTMLIFrameElement;
    await vi.waitFor(() => expect(iframe.getAttribute("src")).toContain("/api/projects/proj-1/preview/p1/pages/demo.html"));
  });

  it("网页产物提供构建、日志、导出与构建预览操作", async () => {
    const webArtifact: Artifact = {
      ...artifact,
      id: "web-a1",
      type: "web_preview",
      title: "demo.html",
      content: "<html><body>fallback</body></html>",
      projectId: "proj-1",
      filePath: "pages/demo.html",
      version: 1,
      parentArtifactId: null,
    };
    let buildListCalls = 0;
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      const method = (init as RequestInit | undefined)?.method ?? "GET";
      if (url.endsWith("/versions")) {
        return jsonResponse([{ id: "web-a1", version: 1, content: webArtifact.content, createdAt: "" }]);
      }
      if (url.endsWith("/preview")) {
        return jsonResponse({
          previewId: "p1",
          previewUrl: "/api/projects/proj-1/preview/p1/pages/demo.html",
        });
      }
      if (url.endsWith("/builds") && method === "POST") {
        return jsonResponse({ buildId: "b1", status: "succeeded" });
      }
      if (url.endsWith("/builds")) {
        buildListCalls += 1;
        return jsonResponse({
          items: buildListCalls > 1
            ? [{
              id: "b1",
              projectId: "proj-1",
              status: "succeeded",
              command: "npm run build",
              artifactPath: "dist",
              createdAt: "",
            }]
            : [],
        });
      }
      if (url.endsWith("/previews")) {
        return jsonResponse({
          previewId: "p-build",
          url: "/api/projects/proj-1/preview/p-build/dist/index.html",
          source: "build",
        });
      }
      if (url.endsWith("/logs")) {
        return jsonResponse({
          chunks: [{ sequence: 1, stream: "stdout", text: "build done", createdAt: "" }],
        });
      }
      return jsonResponse({});
    });

    render(<ArtifactCard artifact={webArtifact} />);

    await screen.findByText("暂无构建记录");
    expect(screen.queryByRole("button", { name: "创建云端预览" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "执行项目构建" }));

    await screen.findByText("构建成功");
    const iframe = screen.getByTitle("preview") as HTMLIFrameElement;
    await vi.waitFor(() => expect(iframe.getAttribute("src")).toContain("/api/projects/proj-1/preview/p-build/dist/index.html"));

    fireEvent.click(screen.getByRole("button", { name: "查看构建日志" }));
    await screen.findByRole("dialog", { name: "构建日志" });
    await screen.findByText(/\[stdout\] build done/);

    fireEvent.click(screen.getByRole("button", { name: "关闭构建日志" }));
    fireEvent.click(screen.getByRole("button", { name: "下载源码包" }));
    fireEvent.click(screen.getByRole("button", { name: "下载构建产物" }));

    expect(openSpy).toHaveBeenCalledWith("/api/projects/proj-1/exports/source", "_blank", "noopener,noreferrer");
    expect(openSpy).toHaveBeenCalledWith("/api/projects/proj-1/exports/builds/b1", "_blank", "noopener,noreferrer");
  });

  it("网页产物提供云端预览、发布日志与失败重试操作", async () => {
    const webArtifact: Artifact = {
      ...artifact,
      id: "web-a1",
      type: "web_preview",
      title: "demo.html",
      content: "<html><body>fallback</body></html>",
      projectId: "proj-1",
      filePath: "pages/demo.html",
      version: 1,
      parentArtifactId: null,
    };
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      const method = (init as RequestInit | undefined)?.method ?? "GET";
      if (url.endsWith("/versions")) {
        return jsonResponse([{ id: "web-v1", version: 1, content: webArtifact.content, createdAt: "" }]);
      }
      if (url.endsWith("/preview")) {
        return jsonResponse({
          previewId: "p-local",
          previewUrl: "/api/projects/proj-1/preview/p-local/pages/demo.html",
        });
      }
      if (url.endsWith("/builds")) {
        return jsonResponse({ items: [] });
      }
      if (url.endsWith("/artifacts/web-a1/previews") && method === "POST") {
        return jsonResponse({
          id: "preview-cloud",
          artifactId: "web-a1",
          artifactVersionId: "web-v1",
          projectId: "proj-1",
          source: "static",
          status: "ready",
          url: "https://preview.agenthub.local/p/preview-cloud",
          visibility: "team",
          expiresAt: "",
          createdAt: "",
          revokedAt: null,
        });
      }
      if (url.endsWith("/deployments") && method === "POST") {
        return jsonResponse({
          id: "dep-1",
          projectId: "proj-1",
          artifactId: "web-a1",
          artifactVersionId: "web-v1",
          target: "static_hosting",
          status: "failed",
          stage: "build",
          url: null,
          visibility: "team",
          errorSummary: "发布构建失败",
          createdBy: "user-1",
          createdAt: "",
          updatedAt: "",
          publishedAt: null,
        });
      }
      if (url.endsWith("/deployments/dep-1/logs")) {
        return jsonResponse({
          deploymentId: "dep-1",
          chunks: [{ sequence: 1, stream: "stderr", text: "DEPLOY_FAIL", createdAt: "" }],
        });
      }
      if (url.endsWith("/deployments/dep-1/retry")) {
        return jsonResponse({
          id: "dep-1",
          projectId: "proj-1",
          artifactId: "web-a1",
          artifactVersionId: "web-v1",
          target: "static_hosting",
          status: "published",
          stage: "verify",
          url: "https://deploy.agenthub.local/d/dep-1",
          visibility: "team",
          errorSummary: null,
          createdBy: "user-1",
          createdAt: "",
          updatedAt: "",
          publishedAt: "",
        });
      }
      return jsonResponse({});
    });

    render(
      <StaticShellProvider capabilities={saasDesktopCapabilities()}>
        <ArtifactCard artifact={webArtifact} />
      </StaticShellProvider>,
    );

    expect(screen.queryByRole("button", { name: "执行项目构建" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "创建云端预览" }));
    await screen.findByText("云端预览已就绪");
    const iframe = screen.getByTitle("preview") as HTMLIFrameElement;
    await vi.waitFor(() => expect(iframe.getAttribute("src")).toBe("https://preview.agenthub.local/p/preview-cloud"));

    fireEvent.click(screen.getByRole("button", { name: "发布云端版本" }));
    await screen.findByText("发布失败");

    fireEvent.click(screen.getByRole("button", { name: "查看发布日志" }));
    await screen.findByRole("dialog", { name: "发布日志" });
    await screen.findByText(/\[stderr\] DEPLOY_FAIL/);

    fireEvent.click(screen.getByRole("button", { name: "关闭发布日志" }));
    fireEvent.click(screen.getByRole("button", { name: "重试发布" }));
    await screen.findByText("已发布");
    await vi.waitFor(() => expect(iframe.getAttribute("src")).toBe("https://deploy.agenthub.local/d/dep-1"));
  });

  it("file_tree 产物也提供版本管理入口", async () => {
    const fileTreeArtifact: Artifact = {
      ...artifact,
      id: "tree-a1",
      type: "file_tree",
      title: "本次文件变更",
      content: JSON.stringify({ changes: [{ path: "src/App.tsx", change: "modified" }] }),
      version: 1,
      parentArtifactId: null,
    };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/versions")) {
        return jsonResponse([{ id: "tree-a1", version: 1, content: fileTreeArtifact.content, createdAt: "" }]);
      }
      return jsonResponse({});
    });

    render(<ArtifactCard artifact={fileTreeArtifact} />);

    expect(screen.getAllByRole("button", { name: "版本管理" }).length).toBeGreaterThan(0);
  });

  it("file_tree 差异悬停预览挂到 body 高层级浮层", async () => {
    const fileTreeArtifact: Artifact = {
      ...artifact,
      id: "tree-hover",
      type: "file_tree",
      title: "本次文件变更",
      content: JSON.stringify({
        changes: [{
          path: "src/App.tsx",
          change: "modified",
          diffPreview: "@@ -1,1 +1,1 @@\n-old\n+new",
        }],
      }),
      version: 1,
      parentArtifactId: null,
    };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/versions")) {
        return jsonResponse([{ id: "tree-hover", version: 1, content: fileTreeArtifact.content, createdAt: "" }]);
      }
      return jsonResponse({});
    });

    render(<ArtifactCard artifact={fileTreeArtifact} />);

    const path = screen.getByText("src/App.tsx");
    const row = path.parentElement?.parentElement;
    expect(row).toBeTruthy();
    row!.getBoundingClientRect = () => ({
      x: 120,
      y: 100,
      left: 120,
      right: 520,
      top: 100,
      bottom: 136,
      width: 400,
      height: 36,
      toJSON: () => ({}),
    });

    fireEvent.mouseEnter(row!);

    const preview = await screen.findByTestId("artifact-diff-hover-preview");
    expect(preview.parentElement).toBe(document.body);
    expect(preview).toHaveClass("fixed");
    expect(preview).toHaveClass("z-[1500]");

    fireEvent.mouseLeave(row!);
    await vi.waitFor(() => expect(screen.queryByTestId("artifact-diff-hover-preview")).not.toBeInTheDocument());
  });

  it("Markdown 文档产物以内联卡片渲染", async () => {
    const markdownArtifact: Artifact = {
      ...artifact,
      id: "md-a1",
      type: "document",
      title: "README.md",
      content: "# 项目说明\n\n- 支持 Markdown 预览\n- 支持表格和列表\n",
      filePath: "README.md",
      previewKind: "markdown",
      previewLabel: "Markdown 文档",
      version: 1,
      parentArtifactId: null,
    };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/versions")) {
        return jsonResponse([{ id: "md-a1", version: 1, content: markdownArtifact.content, createdAt: "" }]);
      }
      return jsonResponse({});
    });

    render(<ArtifactCard artifact={markdownArtifact} />);

    expect(await screen.findByText("项目说明")).toBeInTheDocument();
    expect(screen.getByText("支持 Markdown 预览")).toBeInTheDocument();
  });

  it("图片产物使用 rawUrl 预览并隐藏文本编辑入口", async () => {
    const imageArtifact: Artifact = {
      ...artifact,
      id: "img-a1",
      type: "document",
      title: "diagram.png",
      content: JSON.stringify({ path: "diagram.png", previewKind: "image" }),
      filePath: "diagram.png",
      previewKind: "image",
      previewLabel: "图片预览",
      mediaType: "image/png",
      rawUrl: "/api/artifacts/img-a1/raw",
      downloadUrl: "/api/artifacts/img-a1/raw?download=true",
      isBinary: true,
      version: 1,
      parentArtifactId: null,
    };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/versions")) {
        return jsonResponse([{ id: "img-a1", version: 1, content: imageArtifact.content, createdAt: "" }]);
      }
      return jsonResponse({});
    });

    render(<ArtifactCard artifact={imageArtifact} />);

    const img = await screen.findByRole("img", { name: "diagram.png" });
    expect(img).toHaveAttribute("src", "/api/artifacts/img-a1/raw");
    expect(screen.queryByRole("button", { name: "编辑文件" })).not.toBeInTheDocument();
  });
});
