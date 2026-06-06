import { describe, expect, it, vi, afterEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import React, { forwardRef } from "react";
import { ArtifactCard } from "./ArtifactCard";
import type { Artifact } from "../types";
import { useChatStore } from "../stores/chatStore";

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
});
