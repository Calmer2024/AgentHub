import { describe, expect, it, vi, afterEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ArtifactCard } from "./ArtifactCard";
import type { Artifact } from "../types";

vi.mock("react-syntax-highlighter", () => ({
  Prism: ({ children }: { children: string }) => <pre>{children}</pre>,
}));

vi.mock("react-syntax-highlighter/dist/esm/styles/prism", () => ({
  oneDark: {},
}));

vi.mock("react-diff-viewer-continued", () => ({
  default: ({ oldValue, newValue, splitView }: { oldValue: string; newValue: string; splitView: boolean }) => (
    <div data-testid="diff-viewer" data-split={String(splitView)}>
      <span>{oldValue}</span>
      <span>{newValue}</span>
    </div>
  ),
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
  });

  it("打开后加载版本并展示 split/unified Diff", async () => {
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
    fireEvent.click(screen.getByText("打开"));

    await vi.waitFor(() => expect(screen.getAllByText("v1 (原始)").length).toBeGreaterThan(0));
    await vi.waitFor(() => expect(screen.getByTestId("diff-viewer")).toHaveAttribute("data-split", "true"));

    fireEvent.click(screen.getByText("上下"));

    expect(screen.getByTestId("diff-viewer")).toHaveAttribute("data-split", "false");
  });

  it("编辑预览后确认应用并通知父级刷新", async () => {
    const onChanged = vi.fn();
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/versions")) {
        return jsonResponse([
          { id: "a2", version: 2, content: artifact.content, createdAt: "" },
        ]);
      }
      if (url.includes("/diff")) {
        return jsonResponse({
          fromVersion: 1,
          toVersion: 2,
          diff: "",
          oldContent: "",
          newContent: "",
        });
      }
      if (url.endsWith("/edit")) {
        const body = JSON.parse(String((init as RequestInit).body));
        return jsonResponse({
          newVersion: body.apply ? 3 : null,
          diff: {
            fromVersion: 2,
            toVersion: 3,
            diff: "-v2\n+v3",
            oldContent: "return 'v2'",
            newContent: "return 'v3'",
          },
          artifact: body.apply ? { ...artifact, id: "a3", version: 3, content: "return 'v3'" } : null,
          proposedContent: "def hello():\n    return 'v3'\n",
          strategy: "fallback_context",
        });
      }
      return jsonResponse({});
    });

    render(<ArtifactCard artifact={artifact} onChanged={onChanged} />);
    fireEvent.click(screen.getByText("打开"));

    const textarea = await screen.findByDisplayValue(/return 'v2'/);
    (textarea as HTMLTextAreaElement).setSelectionRange(17, 28);
    fireEvent.mouseUp(textarea);
    fireEvent.change(screen.getByPlaceholderText("描述修改意图"), {
      target: { value: "改成 v3" },
    });
    fireEvent.click(screen.getByText("生成 Diff"));

    await screen.findByText(/Diff 已生成/);
    fireEvent.click(screen.getByText("确认应用"));

    await vi.waitFor(() => expect(onChanged).toHaveBeenCalled());
  });
});
