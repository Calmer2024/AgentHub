import React, { forwardRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ProjectFileWorkspaceModal } from "../../../frontend/src/components/ProjectFileWorkspaceModal";
import { useChatStore } from "../../../frontend/src/stores/chatStore";
import type { Project } from "../../../frontend/src/types";

const apiMocks = vi.hoisted(() => ({
  WorkspaceFileConflict: class WorkspaceFileConflict extends Error {
    currentContent = "";
    currentEtag: string | null = null;
    currentMtime: number | null = null;
  },
  createProjectDirectory: vi.fn(),
  createProjectFile: vi.fn(),
  deleteProjectPaths: vi.fn(),
  fetchProjectTree: vi.fn(),
  moveProjectPath: vi.fn(),
  projectPathDownloadUrl: vi.fn((projectId: string, path?: string | null) => (
    path ? `/api/projects/${projectId}/download?path=${encodeURIComponent(path)}` : `/api/projects/${projectId}/download`
  )),
  readProjectFile: vi.fn(),
  searchProjectFiles: vi.fn(),
  writeProjectFile: vi.fn(),
}));

vi.mock("../../../frontend/src/api/client", () => apiMocks);

vi.mock("../../../frontend/src/components/CodeMirrorFileEditor", () => ({
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
  }>(function MockCodeMirror({ value, onChange, onUpdate }, ref) {
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
        ref={(node) => {
          innerRef.current = node;
          if (typeof ref === "function") ref(node);
          else if (ref) ref.current = node;
        }}
        aria-label="IDE 代码编辑器"
        value={value}
        onChange={(event) => onChange?.(event.target.value)}
        onMouseUp={emitUpdate}
        onKeyUp={emitUpdate}
      />
    );
  }),
}));

const project: Project = {
  id: "p1",
  name: "文件项目",
  workspaceMode: "local",
  status: "ready",
  fileCount: 1,
  totalSizeBytes: 20,
  createdAt: "",
};

describe("ProjectFileWorkspaceModal", () => {
  afterEach(() => {
    vi.clearAllMocks();
    useChatStore.setState({ codeReference: null });
  });

  it("打开文件、保存并把选区添加到对话", async () => {
    apiMocks.fetchProjectTree.mockResolvedValue([
      {
        path: "src/app.ts",
        name: "app.ts",
        type: "file",
        size: 24,
        editable: true,
        previewKind: "code",
      },
    ]);
    apiMocks.readProjectFile.mockResolvedValue({
      path: "src/app.ts",
      name: "app.ts",
      type: "file",
      size: 24,
      editable: true,
      previewKind: "code",
      etag: "etag-1",
      content: "const value = 1;\n",
    });
    apiMocks.writeProjectFile.mockResolvedValue({
      path: "src/app.ts",
      name: "app.ts",
      type: "file",
      size: 24,
      editable: true,
      previewKind: "code",
      etag: "etag-2",
      content: "const value = 2;\n",
    });

    render(
      <ProjectFileWorkspaceModal
        open
        project={project}
        onClose={vi.fn()}
      />,
    );

    const fileLabel = await screen.findByText("app.ts");
    const fileRow = fileLabel.closest(".agenthub-file-tree-row") as HTMLElement;
    expect(within(fileRow).getByRole("link", { name: "下载 src/app.ts" })).toHaveAttribute(
      "href",
      "/api/projects/p1/download?path=src%2Fapp.ts",
    );
    fireEvent.click(fileLabel);
    const editor = await screen.findByLabelText("IDE 代码编辑器");
    fireEvent.change(editor, { target: { value: "const value = 2;\n" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(apiMocks.writeProjectFile).toHaveBeenCalledWith(
      "p1",
      "src/app.ts",
      "const value = 2;\n",
      { baseEtag: "etag-1", force: false },
    ));

    fireEvent.click(within(fileRow).getByRole("button", { name: "引用 src/app.ts" }));
    expect(useChatStore.getState().codeReference?.filePath).toBe("src/app.ts");
    expect(useChatStore.getState().codeReference?.content).toBe("const value = 2;\n");
    useChatStore.setState({ codeReference: null });

    (editor as HTMLTextAreaElement).setSelectionRange(6, 11);
    fireEvent.mouseUp(editor);
    fireEvent.click(screen.getByRole("button", { name: "引用选区" }));

    expect(useChatStore.getState().codeReference?.filePath).toBe("src/app.ts");
    expect(useChatStore.getState().codeReference?.content).toBe("value");
  });

  it("空状态只显示工作台画布，不显示文件标签栏和编辑工具栏", async () => {
    apiMocks.fetchProjectTree.mockResolvedValue([]);

    render(<ProjectFileWorkspaceModal open project={project} onClose={vi.fn()} />);

    await screen.findByText("项目文件工作台");
    expect(screen.queryByText("选择一个文件开始编辑")).not.toBeInTheDocument();
    expect(screen.queryByText("未选择文件")).not.toBeInTheDocument();
    expect(screen.queryByText("未打开文件")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "保存" })).not.toBeInTheDocument();
  });

  it("刷新已有文件树时不在树顶部插入额外加载块", async () => {
    apiMocks.fetchProjectTree
      .mockResolvedValueOnce([
        {
          path: "src/app.ts",
          name: "app.ts",
          type: "file",
          size: 24,
          editable: true,
          previewKind: "code",
        },
      ])
      .mockReturnValueOnce(new Promise(() => undefined));

    render(<ProjectFileWorkspaceModal open project={project} onClose={vi.fn()} />);

    await screen.findByText("app.ts");
    fireEvent.click(screen.getByRole("button", { name: "刷新项目文件" }));

    expect(screen.getByText("app.ts")).toBeInTheDocument();
    expect(screen.queryByLabelText("正在刷新文件树")).not.toBeInTheDocument();
  });

  it("切换项目时清空旧项目打开的文件标签", async () => {
    apiMocks.fetchProjectTree
      .mockResolvedValueOnce([
        {
          path: "src/app.ts",
          name: "app.ts",
          type: "file",
          size: 24,
          editable: true,
          previewKind: "code",
        },
      ])
      .mockResolvedValueOnce([]);
    apiMocks.readProjectFile.mockResolvedValue({
      path: "src/app.ts",
      name: "app.ts",
      type: "file",
      size: 24,
      editable: true,
      previewKind: "code",
      etag: "etag-1",
      content: "const value = 1;\n",
    });

    const { rerender } = render(<ProjectFileWorkspaceModal open project={project} onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText("app.ts"));
    await screen.findByLabelText("IDE 代码编辑器");
    expect(screen.getByText("src/app.ts")).toBeInTheDocument();

    rerender(
      <ProjectFileWorkspaceModal
        open
        project={{ ...project, id: "p2", name: "另一个项目" }}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("项目文件工作台")).toBeInTheDocument();
    expect(screen.queryByText("src/app.ts")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(apiMocks.fetchProjectTree).toHaveBeenLastCalledWith("p2");
    });
  });

  it("搜索结果可直接打开文件", async () => {
    apiMocks.fetchProjectTree.mockResolvedValue([]);
    apiMocks.searchProjectFiles.mockResolvedValue([
      { path: "README.md", type: "file", matchType: "content", line: 1, snippet: "hello" },
    ]);
    apiMocks.readProjectFile.mockResolvedValue({
      path: "README.md",
      name: "README.md",
      type: "file",
      size: 9,
      editable: true,
      previewKind: "markdown",
      etag: "md-1",
      content: "# hello\n",
    });

    render(<ProjectFileWorkspaceModal open project={project} onClose={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText("搜索文件或内容"), {
      target: { value: "hello" },
    });
    fireEvent.click(await screen.findByText("README.md"));

    await waitFor(() => expect(apiMocks.readProjectFile).toHaveBeenCalledWith("p1", "README.md"));
    await waitFor(() => expect(screen.getAllByText("README.md").length).toBeGreaterThan(1));
  });

  it("新建文件在文件树内原地输入并打开创建后的文件", async () => {
    apiMocks.fetchProjectTree.mockResolvedValue([]);
    apiMocks.createProjectFile.mockResolvedValue({
      path: "src/new.ts",
      name: "new.ts",
      type: "file",
      size: 0,
      editable: true,
      previewKind: "code",
      etag: "new-1",
      content: "",
    });
    apiMocks.readProjectFile.mockResolvedValue({
      path: "src/new.ts",
      name: "new.ts",
      type: "file",
      size: 0,
      editable: true,
      previewKind: "code",
      etag: "new-1",
      content: "",
    });

    render(<ProjectFileWorkspaceModal open project={project} onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "新建文件" }));
    const input = screen.getByLabelText("新文件路径");
    fireEvent.change(input, { target: { value: "src/new.ts" } });
    fireEvent.click(screen.getByRole("button", { name: "确认创建" }));

    await waitFor(() => {
      expect(apiMocks.createProjectFile).toHaveBeenCalledWith("p1", "src/new.ts");
    });
    await waitFor(() => {
      expect(apiMocks.readProjectFile).toHaveBeenCalledWith("p1", "src/new.ts");
    });
  });

  it("重命名和删除在文件树内原地完成", async () => {
    apiMocks.fetchProjectTree.mockResolvedValue([
      {
        path: "src/app.ts",
        name: "app.ts",
        type: "file",
        size: 24,
        editable: true,
        previewKind: "code",
      },
    ]);
    apiMocks.moveProjectPath.mockResolvedValue({
      path: "src/main.ts",
      name: "main.ts",
      type: "file",
      size: 24,
      editable: true,
      previewKind: "code",
      etag: "main-1",
      content: "",
    });
    apiMocks.deleteProjectPaths.mockResolvedValue({ deleted: ["src/app.ts"] });

    render(<ProjectFileWorkspaceModal open project={project} onClose={vi.fn()} />);

    const firstRow = (await screen.findByText("app.ts")).closest(".agenthub-file-tree-row") as HTMLElement;
    fireEvent.click(within(firstRow).getByRole("button", { name: "重命名" }));
    const renameInput = screen.getByLabelText("重命名 src/app.ts");
    fireEvent.change(renameInput, { target: { value: "src/main.ts" } });
    fireEvent.click(screen.getByRole("button", { name: "确认重命名" }));

    await waitFor(() => {
      expect(apiMocks.moveProjectPath).toHaveBeenCalledWith("p1", "src/app.ts", "src/main.ts");
    });

    const secondRow = screen.getByText("app.ts").closest(".agenthub-file-tree-row") as HTMLElement;
    fireEvent.click(within(secondRow).getByRole("button", { name: "删除" }));
    fireEvent.click(screen.getByRole("button", { name: "确认删除 src/app.ts" }));

    await waitFor(() => {
      expect(apiMocks.deleteProjectPaths).toHaveBeenCalledWith("p1", ["src/app.ts"], true);
    });
  });
});
