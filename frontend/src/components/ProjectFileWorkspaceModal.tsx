import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from "react";
import type { ReactCodeMirrorRef } from "@uiw/react-codemirror";
import type { ViewUpdate } from "@codemirror/view";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Check,
  ChevronRight,
  CirclePlus,
  Code2,
  Download,
  File,
  FileCode2,
  FileText,
  Folder,
  FolderOpen,
  Pencil,
  Quote,
  RefreshCw,
  Save,
  Search,
  SplitSquareHorizontal,
  Trash2,
  X,
} from "lucide-react";
import type { CodeReference, Project, WorkspaceFile, WorkspaceSearchItem, WorkspaceTreeNode } from "../types";
import {
  WorkspaceFileConflict,
  createProjectDirectory,
  createProjectFile,
  deleteProjectPaths,
  fetchProjectTree,
  moveProjectPath,
  projectPathDownloadUrl,
  readProjectFile,
  searchProjectFiles,
  writeProjectFile,
} from "../api/client";
import { useChatStore } from "../stores/chatStore";
import { useToastStore } from "../stores/toastStore";

const CodeMirrorFileEditor = lazy(() => import("./CodeMirrorFileEditor").then((module) => ({
  default: module.CodeMirrorFileEditor,
})));

interface Props {
  open: boolean;
  project: Project | null;
  initialPath?: string | null;
  onClose: () => void;
  onChanged?: () => void;
}

type Tab = {
  path: string;
  file: WorkspaceFile;
  content: string;
  original: string;
  selection: { text: string; start: number; end: number } | null;
  cursor: { line: number; column: number };
};

interface TreeItem extends WorkspaceTreeNode {
  depth: number;
}

type PendingPathAction =
  | { kind: "create"; itemType: "file" | "folder"; value: string }
  | { kind: "rename"; path: string; value: string }
  | { kind: "delete"; path: string };

type FileContextMenuState = {
  path: string;
  x: number;
  y: number;
} | null;

const FILE_DOCK_MIN_WIDTH = 420;
const FILE_DOCK_MAX_WIDTH = 920;

function clampDockWidth(width: number) {
  if (typeof window === "undefined") return Math.min(Math.max(width, FILE_DOCK_MIN_WIDTH), FILE_DOCK_MAX_WIDTH);
  const viewportMax = Math.max(FILE_DOCK_MIN_WIDTH, Math.min(FILE_DOCK_MAX_WIDTH, window.innerWidth - 560));
  return Math.min(Math.max(width, FILE_DOCK_MIN_WIDTH), viewportMax);
}

function languageFromPath(path?: string | null) {
  if (!path) return "text";
  const ext = path.split(".").pop()?.toLowerCase();
  if (ext === "ts" || ext === "tsx") return "tsx";
  if (ext === "js" || ext === "jsx") return "jsx";
  if (ext === "html" || ext === "htm") return "html";
  if (ext === "css" || ext === "scss" || ext === "less") return "css";
  if (ext === "json") return "json";
  if (ext === "py") return "python";
  if (ext === "md" || ext === "markdown") return "markdown";
  return ext || "text";
}

function parentPath(path: string) {
  const parts = path.split("/").filter(Boolean);
  parts.pop();
  return parts.join("/");
}

function filename(path: string) {
  return path.split("/").filter(Boolean).pop() || path || "/";
}

function lineRange(content: string, start: number, end: number) {
  const prefix = content.slice(0, start);
  const selection = content.slice(start, end);
  const startLine = prefix.split("\n").length;
  const endLine = startLine + Math.max(selection.split("\n").length - 1, 0);
  return { startLine, endLine };
}

function formatSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function buildVisibleTree(entries: WorkspaceTreeNode[], collapsed: Set<string>): TreeItem[] {
  const folders = new Set<string>();
  for (const entry of entries) {
    const parts = entry.path.split("/").filter(Boolean);
    parts.pop();
    let cursor = "";
    for (const part of parts) {
      cursor = cursor ? `${cursor}/${part}` : part;
      folders.add(cursor);
    }
  }
  const withSyntheticFolders: WorkspaceTreeNode[] = [
    ...Array.from(folders).map((path) => ({
      path,
      name: filename(path),
      type: "dir",
      size: 0,
      hasChildren: true,
      previewKind: "directory",
    })),
    ...entries,
  ];
  const byPath = new Map<string, WorkspaceTreeNode>();
  for (const entry of withSyntheticFolders) byPath.set(entry.path, entry);
  const sorted = Array.from(byPath.values()).sort((left, right) => {
    const leftParent = parentPath(left.path);
    const rightParent = parentPath(right.path);
    if (leftParent === rightParent && left.type !== right.type) return left.type === "dir" ? -1 : 1;
    return left.path.localeCompare(right.path, "zh-Hans-CN");
  });
  return sorted.flatMap((entry) => {
    const depth = entry.path.split("/").filter(Boolean).length - 1;
    const ancestors = entry.path.split("/").filter(Boolean).slice(0, -1);
    let cursor = "";
    for (const part of ancestors) {
      cursor = cursor ? `${cursor}/${part}` : part;
      if (collapsed.has(cursor)) return [];
    }
    return [{ ...entry, depth: Math.max(depth, 0) }];
  });
}

function iconForEntry(entry: { type?: string | null; path?: string | null; previewKind?: string | null; extension?: string | null }, open = false) {
  const props = {
    size: 15,
    "aria-hidden": true,
    className: "agenthub-file-basic-icon",
  };
  if (entry.type === "dir") return open ? <FolderOpen {...props} /> : <Folder {...props} />;
  if (entry.previewKind === "markdown") return <FileText {...props} />;
  if (entry.previewKind === "html" || entry.previewKind === "json" || entry.previewKind === "code") return <FileCode2 {...props} />;
  return <File {...props} />;
}

function ancestorPaths(path: string) {
  const parts = path.split("/").filter(Boolean).slice(0, -1);
  const ancestors: string[] = [];
  let cursor = "";
  for (const part of parts) {
    cursor = cursor ? `${cursor}/${part}` : part;
    ancestors.push(cursor);
  }
  return ancestors;
}

export function ProjectFileWorkspaceModal({
  open,
  project,
  initialPath,
  onClose,
  onChanged,
}: Props) {
  const editorRef = useRef<ReactCodeMirrorRef | null>(null);
  const setCodeReference = useChatStore((state) => state.setCodeReference);
  const pushToast = useToastStore((state) => state.pushToast);
  const [tree, setTree] = useState<WorkspaceTreeNode[]>([]);
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [activePath, setActivePath] = useState<string | null>(null);
  const [treeLoading, setTreeLoading] = useState(false);
  const [fileLoadingPath, setFileLoadingPath] = useState<string | null>(null);
  const [savingPath, setSavingPath] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<WorkspaceSearchItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<{
    path: string;
    content: string;
    etag: string | null;
    mtime: number | null;
  } | null>(null);
  const [previewMode, setPreviewMode] = useState<"editor" | "preview" | "split">("editor");
  const [panelWidth, setPanelWidth] = useState(540);
  const [resizing, setResizing] = useState(false);
  const [pendingAction, setPendingAction] = useState<PendingPathAction | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingClosePath, setPendingClosePath] = useState<string | null>(null);
  const [fileContextMenu, setFileContextMenu] = useState<FileContextMenuState>(null);
  const previousProjectId = useRef<string | null>(null);
  const treeRequestRef = useRef(0);
  const fileRequestRef = useRef(0);

  const projectId = project?.id ?? null;
  const activeTab = tabs.find((tab) => tab.path === activePath) ?? null;
  const visibleTree = useMemo(() => buildVisibleTree(tree, collapsed), [collapsed, tree]);
  const dirtyCount = tabs.filter((tab) => tab.content !== tab.original).length;

  const loadTree = useCallback(async () => {
    const requestId = treeRequestRef.current + 1;
    treeRequestRef.current = requestId;
    if (!projectId) {
      setTree([]);
      setTreeLoading(false);
      return;
    }
    setTreeLoading(true);
    setError(null);
    try {
      const items = await fetchProjectTree(projectId);
      if (treeRequestRef.current === requestId) setTree(items);
    } catch (err) {
      if (treeRequestRef.current === requestId) {
        setError(err instanceof Error ? err.message : "项目文件加载失败");
      }
    } finally {
      if (treeRequestRef.current === requestId) setTreeLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (previousProjectId.current === projectId) return;
    previousProjectId.current = projectId;
    treeRequestRef.current += 1;
    fileRequestRef.current += 1;
    setTree([]);
    setCollapsed(new Set());
    setTabs([]);
    setActivePath(null);
    setFileLoadingPath(null);
    setSavingPath(null);
    setPreviewMode("editor");
    setQuery("");
    setSearchResults([]);
    setPendingAction(null);
    setPendingClosePath(null);
    setFileContextMenu(null);
    setError(null);
    setConflict(null);
  }, [projectId]);

  const openFile = useCallback(async (path: string) => {
    if (!projectId) return;
    const existing = tabs.find((tab) => tab.path === path);
    if (existing) {
      setActivePath(path);
      return;
    }
    const requestId = fileRequestRef.current + 1;
    fileRequestRef.current = requestId;
    setFileLoadingPath(path);
    setError(null);
    try {
      const file = await readProjectFile(projectId, path);
      if (fileRequestRef.current !== requestId) return;
      setTabs((items) => [
        ...items,
        {
          path: file.path,
          file,
          content: file.content,
          original: file.content,
          selection: null,
          cursor: { line: 1, column: 1 },
        },
      ]);
      setActivePath(file.path);
      if (file.previewKind && ["markdown", "html", "image", "pdf", "binary"].includes(file.previewKind)) {
        setPreviewMode(file.editable ? "split" : "preview");
      } else {
        setPreviewMode("editor");
      }
    } catch (err) {
      if (fileRequestRef.current === requestId) {
        setError(err instanceof Error ? err.message : "无法打开文件");
      }
    } finally {
      if (fileRequestRef.current === requestId) setFileLoadingPath(null);
    }
  }, [projectId, tabs]);

  useEffect(() => {
    if (!open) return;
    void loadTree();
  }, [loadTree, open]);

  useEffect(() => {
    if (open) return;
    setFileContextMenu(null);
  }, [open]);

  useEffect(() => {
    if (!fileContextMenu) return;
    const close = () => setFileContextMenu(null);
    window.addEventListener("click", close);
    window.addEventListener("keydown", close);
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("keydown", close);
      window.removeEventListener("resize", close);
    };
  }, [fileContextMenu]);

  useEffect(() => {
    if (!open || !initialPath) return;
    void openFile(initialPath);
  }, [initialPath, open, openFile]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing = target?.tagName === "INPUT" || target?.tagName === "TEXTAREA";
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void saveActive();
      }
      if (event.key === "Escape" && !typing) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  });

  useEffect(() => {
    if (!open || !projectId) return;
    const value = query.trim();
    if (!value) {
      setSearchResults([]);
      setSearching(false);
      return;
    }
    let alive = true;
    const timer = window.setTimeout(() => {
      setSearching(true);
      searchProjectFiles(projectId, value, { includeContent: true, limit: 40 })
        .then((items) => {
          if (alive) setSearchResults(items);
        })
        .catch(() => {
          if (alive) setSearchResults([]);
        })
        .finally(() => {
          if (alive) setSearching(false);
        });
    }, 220);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [open, projectId, query]);

  const updateTab = (path: string, patch: Partial<Tab>) => {
    setTabs((items) => items.map((tab) => (
      tab.path === path ? { ...tab, ...patch } : tab
    )));
  };

  const closeTab = (path: string, force = false) => {
    const tab = tabs.find((item) => item.path === path);
    if (tab && tab.content !== tab.original && !force) {
      setActivePath(path);
      setPendingClosePath(path);
      return;
    }
    setTabs((items) => {
      const next = items.filter((item) => item.path !== path);
      if (activePath === path) setActivePath(next[next.length - 1]?.path ?? null);
      return next;
    });
    if (pendingClosePath === path) setPendingClosePath(null);
  };

  const saveActive = async (force = false) => {
    if (!projectId || !activeTab || !activeTab.file.editable) return;
    setSavingPath(activeTab.path);
    setError(null);
    try {
      const saved = await writeProjectFile(projectId, activeTab.path, activeTab.content, {
        baseEtag: activeTab.file.etag,
        force,
      });
      updateTab(activeTab.path, {
        file: saved,
        content: saved.content,
        original: saved.content,
      });
      setConflict(null);
      await loadTree();
      onChanged?.();
      pushToast({ kind: "success", title: "文件已保存", description: saved.path });
    } catch (err) {
      if (err instanceof WorkspaceFileConflict) {
        setConflict({
          path: activeTab.path,
          content: err.currentContent,
          etag: err.currentEtag,
          mtime: err.currentMtime,
        });
        pushToast({ kind: "error", title: "文件已被外部修改", description: "请处理冲突后继续保存" });
      } else {
        setError(err instanceof Error ? err.message : "保存失败");
        pushToast({ kind: "error", title: "保存失败" });
      }
    } finally {
      setSavingPath(null);
    }
  };

  const beginCreate = (kind: "file" | "folder") => {
    if (!projectId) return;
    const base = activePath ? parentPath(activePath) : "";
    const suggested = kind === "file" ? `${base ? `${base}/` : ""}untitled.txt` : `${base ? `${base}/` : ""}new-folder`;
    setQuery("");
    setActionError(null);
    setPendingAction({ kind: "create", itemType: kind, value: suggested });
  };

  const commitCreate = async () => {
    if (!projectId || pendingAction?.kind !== "create") return;
    const path = pendingAction.value.trim();
    if (!path) {
      setActionError("请输入路径");
      return;
    }
    setActionBusy(true);
    setActionError(null);
    try {
      if (pendingAction.itemType === "file") {
        const file = await createProjectFile(projectId, path);
        await loadTree();
        onChanged?.();
        setPendingAction(null);
        await openFile(file.path);
      } else {
        await createProjectDirectory(projectId, path);
        await loadTree();
        onChanged?.();
        setPendingAction(null);
      }
      pushToast({ kind: "success", title: pendingAction.itemType === "file" ? "文件已创建" : "目录已创建" });
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "创建失败");
      pushToast({ kind: "error", title: "创建失败", description: err instanceof Error ? err.message : undefined });
    } finally {
      setActionBusy(false);
    }
  };

  const beginRename = (path: string) => {
    if (!projectId) return;
    setQuery("");
    setCollapsed((value) => {
      const next = new Set(value);
      for (const ancestor of ancestorPaths(path)) next.delete(ancestor);
      return next;
    });
    setActionError(null);
    setPendingAction({ kind: "rename", path, value: path });
  };

  const commitRename = async () => {
    if (!projectId || pendingAction?.kind !== "rename") return;
    const path = pendingAction.path;
    const nextPath = pendingAction.value.trim();
    if (!nextPath) {
      setActionError("请输入路径");
      return;
    }
    if (nextPath === path) {
      setPendingAction(null);
      setActionError(null);
      return;
    }
    setActionBusy(true);
    setActionError(null);
    try {
      const moved = await moveProjectPath(projectId, path, nextPath);
      setTabs((items) => items.map((tab) => (
        tab.path === path ? { ...tab, path: moved.path, file: { ...tab.file, ...moved, content: tab.content } } : tab
      )));
      if (activePath === path) setActivePath(moved.path);
      await loadTree();
      onChanged?.();
      setPendingAction(null);
      pushToast({ kind: "success", title: "路径已更新", description: moved.path });
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "重命名失败");
      pushToast({ kind: "error", title: "重命名失败", description: err instanceof Error ? err.message : undefined });
    } finally {
      setActionBusy(false);
    }
  };

  const beginDelete = (path: string) => {
    if (!projectId) return;
    setQuery("");
    setCollapsed((value) => {
      const next = new Set(value);
      for (const ancestor of ancestorPaths(path)) next.delete(ancestor);
      return next;
    });
    setActionError(null);
    setPendingAction({ kind: "delete", path });
  };

  const commitDelete = async () => {
    if (!projectId || pendingAction?.kind !== "delete") return;
    const path = pendingAction.path;
    setActionBusy(true);
    setActionError(null);
    try {
      await deleteProjectPaths(projectId, [path], true);
      setTabs((items) => items.filter((tab) => tab.path !== path));
      if (activePath === path) setActivePath(null);
      await loadTree();
      onChanged?.();
      setPendingAction(null);
      pushToast({ kind: "success", title: "已移入回收区" });
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "删除失败");
      pushToast({ kind: "error", title: "删除失败", description: err instanceof Error ? err.message : undefined });
    } finally {
      setActionBusy(false);
    }
  };

  const captureEditorState = (path: string, update: ViewUpdate) => {
    const range = update.state.selection.main;
    const selected = update.state.doc.sliceString(range.from, range.to);
    const line = update.state.doc.lineAt(range.head);
    updateTab(path, {
      cursor: {
        line: line.number,
        column: range.head - line.from + 1,
      },
      selection: selected.trim()
        ? { text: selected, start: range.from, end: range.to }
        : null,
    });
  };

  const addPathToChat = async (path: string) => {
    if (!projectId) return;
    setFileContextMenu(null);
    setFileLoadingPath(path);
    setError(null);
    try {
      const tab = tabs.find((item) => item.path === path);
      const file = tab?.file ?? await readProjectFile(projectId, path);
      const content = tab?.content ?? file.content;
      if (!content.trim()) return;
      const reference: CodeReference = {
        projectId,
        filePath: path,
        title: path,
        language: languageFromPath(path),
        startLine: 1,
        endLine: content.split("\n").length,
        content: content.slice(0, 12000),
      };
      setCodeReference(reference);
      onClose();
      window.setTimeout(() => {
        window.dispatchEvent(new CustomEvent("agenthub:focus-chat-input"));
      }, 40);
    } catch (err) {
      setError(err instanceof Error ? err.message : "引用文件失败");
      pushToast({ kind: "error", title: "引用文件失败", description: err instanceof Error ? err.message : undefined });
    } finally {
      setFileLoadingPath(null);
    }
  };

  const openFileContextMenu = (path: string, x: number, y: number) => {
    setFileContextMenu({ path, x, y });
  };

  const toggleDirectory = (path: string) => {
    const wasCollapsed = collapsed.has(path);
    setCollapsed((value) => {
      const next = new Set(value);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
    if (wasCollapsed) void loadTree();
  };

  const addSelectionForPathToChat = (path: string) => {
    const tab = tabs.find((item) => item.path === path);
    if (!tab?.selection?.text.trim()) return;
    setFileContextMenu(null);
    const range = lineRange(tab.content, tab.selection.start, tab.selection.end);
    setCodeReference({
      projectId,
      filePath: tab.path,
      title: tab.path,
      language: languageFromPath(tab.path),
      startLine: range.startLine,
      endLine: range.endLine,
      content: tab.selection.text.slice(0, 12000),
    });
    onClose();
    window.setTimeout(() => {
      window.dispatchEvent(new CustomEvent("agenthub:focus-chat-input"));
    }, 40);
  };

  const updatePendingValue = (value: string) => {
    setPendingAction((action) => {
      if (!action || action.kind === "delete") return action;
      return { ...action, value };
    });
    setActionError(null);
  };

  const cancelPendingAction = () => {
    if (actionBusy) return;
    setPendingAction(null);
    setActionError(null);
  };

  const commitPendingAction = () => {
    if (!pendingAction) return;
    if (pendingAction.kind === "create") void commitCreate();
    else if (pendingAction.kind === "rename") void commitRename();
    else void commitDelete();
  };

  const startResize = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (typeof window === "undefined") return;
    event.preventDefault();
    setResizing(true);
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const onMove = (moveEvent: PointerEvent) => {
      setPanelWidth(clampDockWidth(window.innerWidth - moveEvent.clientX - 10));
    };
    const onUp = () => {
      setResizing(false);
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }, []);

  const dockStyle = {
    "--agenthub-file-dock-width": `${panelWidth}px`,
  } as CSSProperties;
  const contextMenuTab = fileContextMenu
    ? tabs.find((tab) => tab.path === fileContextMenu.path) ?? null
    : null;
  const contextMenuStyle = fileContextMenu
    ? ({
      left: typeof window === "undefined"
        ? fileContextMenu.x
        : Math.max(12, Math.min(fileContextMenu.x, window.innerWidth - 224)),
      top: typeof window === "undefined"
        ? fileContextMenu.y
        : Math.max(12, Math.min(fileContextMenu.y, window.innerHeight - 238)),
    } as CSSProperties)
    : undefined;
  const dockClassName = `agenthub-file-dock relative flex min-h-0 shrink-0 flex-col overflow-hidden border max-lg:fixed max-lg:inset-2 max-lg:z-[1120] lg:h-full ${
    open ? "agenthub-file-dock-open" : "agenthub-file-dock-closed"
  } ${
    resizing ? "agenthub-file-dock-resizing" : ""
  }`;

  if (!open) {
    return (
      <section
        className={dockClassName}
        role="complementary"
        aria-label="项目文件工作台"
        aria-hidden="true"
        style={dockStyle}
      />
    );
  }

  return (
    <section
      className={dockClassName}
      role="complementary"
      aria-label="项目文件工作台"
      style={dockStyle}
    >
      <div
        className="agenthub-file-dock-resizer hidden lg:block"
        role="separator"
        aria-label="调整项目资源管理器宽度"
        aria-orientation="vertical"
        onPointerDown={startResize}
      />
      <div className="agenthub-file-dock-header flex items-center justify-between gap-3 px-4 py-3 md:px-6">
        <div className="agenthub-file-dock-title min-w-0">
          <span className="agenthub-file-dock-project-icon">
            <FolderOpen size={18} aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h3 className="agenthub-strong truncate text-base font-semibold">
              {project?.name ?? "未选择项目"}
            </h3>
            <div className="agenthub-muted mt-0.5 flex items-center gap-2 text-xs">
              <span>{tree.filter((entry) => entry.type === "file").length} 个文件</span>
              {dirtyCount > 0 && <span className="text-[color:var(--ah-warning)]">{dirtyCount} 个未保存</span>}
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            onClick={() => void loadTree()}
            disabled={treeLoading || !projectId}
            className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md disabled:opacity-50"
            title="刷新"
            aria-label="刷新项目文件"
          >
            <RefreshCw size={15} className={treeLoading ? "animate-pulse" : ""} />
          </button>
          <button
            type="button"
            onClick={onClose}
            className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-md"
            title="关闭"
            aria-label="关闭项目文件工作台"
          >
            <X size={15} />
          </button>
        </div>
      </div>

      {error && <div className="agenthub-status-warning border-b px-4 py-2 text-xs">{error}</div>}

      <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[minmax(240px,40%)_minmax(0,1fr)]">
          <aside className="agenthub-file-tree-pane flex min-h-0 flex-col border-b md:border-b-0 md:border-r">
            <div className="px-2.5 pb-1.5 pt-2.5">
              <div className="mb-1 flex items-center justify-between gap-2">
                <div className="agenthub-muted min-w-0 truncate text-xs font-medium">
                  Projects
                </div>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => beginCreate("file")}
                    disabled={!projectId}
                    className="agenthub-file-tool-button inline-flex h-7 w-7 items-center justify-center rounded-md disabled:opacity-45"
                    title="新建文件"
                    aria-label="新建文件"
                  >
                    <CirclePlus size={13} aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={() => beginCreate("folder")}
                    disabled={!projectId}
                    className="agenthub-file-tool-button inline-flex h-7 w-7 items-center justify-center rounded-md disabled:opacity-45"
                    title="新建目录"
                    aria-label="新建目录"
                  >
                    <Folder size={13} aria-hidden="true" />
                  </button>
                  <a
                    href={projectId ? projectPathDownloadUrl(projectId) : undefined}
                    className="agenthub-file-tool-button inline-flex h-7 w-7 items-center justify-center rounded-md"
                    aria-disabled={!projectId}
                    title="下载项目"
                    aria-label="下载项目"
                  >
                    <Download size={13} aria-hidden="true" />
                  </a>
                </div>
              </div>
              <label className="agenthub-file-search flex h-8 items-center gap-2 rounded-md border px-2.5">
                <Search size={15} className="agenthub-muted shrink-0" aria-hidden="true" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="搜索文件或内容"
                  className="min-w-0 flex-1 bg-transparent text-sm outline-none"
                />
                {searching && <span className="agenthub-file-search-pulse" aria-label="正在搜索" />}
              </label>
            </div>
            <div className={`agenthub-file-tree-content relative min-h-0 flex-1 overflow-auto p-1.5 ${
              treeLoading ? "agenthub-file-tree-content-loading" : ""
            }`}>
              {pendingAction?.kind === "create" && (
                <div className="agenthub-file-tree-edit-row mb-1 flex items-center gap-1 rounded-md px-1 py-1 text-sm">
                  <span className="agenthub-muted shrink-0">
                    {pendingAction.itemType === "file" ? <File size={15} aria-hidden="true" /> : <Folder size={15} aria-hidden="true" />}
                  </span>
                  <input
                    value={pendingAction.value}
                    onChange={(event) => updatePendingValue(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") commitPendingAction();
                      if (event.key === "Escape") cancelPendingAction();
                    }}
                    autoFocus
                    className="min-w-0 flex-1 bg-transparent font-mono text-xs outline-none"
                    aria-label={pendingAction.itemType === "file" ? "新文件路径" : "新目录路径"}
                  />
                  <button
                    type="button"
                    onClick={commitPendingAction}
                    disabled={actionBusy}
                    className="agenthub-file-mini-action inline-flex h-6 w-6 items-center justify-center rounded disabled:opacity-45"
                    aria-label="确认创建"
                    title="确认"
                  >
                    {actionBusy ? <BusyDot /> : <Check size={12} />}
                  </button>
                  <button
                    type="button"
                    onClick={cancelPendingAction}
                    disabled={actionBusy}
                    className="agenthub-file-mini-action inline-flex h-6 w-6 items-center justify-center rounded disabled:opacity-45"
                    aria-label="取消创建"
                    title="取消"
                  >
                    <X size={12} />
                  </button>
                </div>
              )}
              {actionError && <div className="agenthub-status-error mb-1 rounded-md border px-2 py-1 text-[11px]">{actionError}</div>}
              {query.trim() ? (
                <SearchResults
                  items={searchResults}
                  onOpen={(path) => void openFile(path)}
                />
              ) : treeLoading && tree.length === 0 ? (
                <FileTreeSkeleton label="正在加载文件" />
              ) : visibleTree.length === 0 ? (
                <div className="agenthub-faint px-3 py-8 text-sm">暂无文件</div>
              ) : (
                <div className="agenthub-file-list">
                  {visibleTree.map((entry) => {
                  const isDir = entry.type === "dir";
                  const isCollapsed = collapsed.has(entry.path);
                  const isActive = activePath === entry.path;
                  const renaming = pendingAction?.kind === "rename" && pendingAction.path === entry.path;
                  const deleting = pendingAction?.kind === "delete" && pendingAction.path === entry.path;
                  if (renaming) {
                    return (
                      <div
                        key={entry.path}
                        className="agenthub-file-tree-edit-row group flex items-center gap-1 rounded-md px-1 py-1 text-sm"
                        style={{ paddingLeft: `${6 + entry.depth * 14}px` }}
                      >
                        <span className="agenthub-muted shrink-0">{iconForEntry(entry, !isCollapsed)}</span>
                        <input
                          value={pendingAction.value}
                          onChange={(event) => updatePendingValue(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") commitPendingAction();
                            if (event.key === "Escape") cancelPendingAction();
                          }}
                          autoFocus
                          className="min-w-0 flex-1 bg-transparent font-mono text-xs outline-none"
                          aria-label={`重命名 ${entry.path}`}
                        />
                        <button
                          type="button"
                          onClick={commitPendingAction}
                          disabled={actionBusy}
                          className="agenthub-file-mini-action inline-flex h-6 w-6 items-center justify-center rounded disabled:opacity-45"
                          aria-label="确认重命名"
                          title="确认"
                        >
                          {actionBusy ? <BusyDot /> : <Check size={12} />}
                        </button>
                        <button
                          type="button"
                          onClick={cancelPendingAction}
                          disabled={actionBusy}
                          className="agenthub-file-mini-action inline-flex h-6 w-6 items-center justify-center rounded disabled:opacity-45"
                          aria-label="取消重命名"
                          title="取消"
                        >
                          <X size={12} />
                        </button>
                      </div>
                    );
                  }
                  if (deleting) {
                    return (
                      <div
                        key={entry.path}
                        className="agenthub-file-tree-edit-row agenthub-file-tree-delete-row group flex items-center gap-1 rounded-md px-1 py-1 text-sm"
                        style={{ paddingLeft: `${6 + entry.depth * 14}px` }}
                      >
                        <span className="agenthub-muted shrink-0">{iconForEntry(entry, !isCollapsed)}</span>
                        <span className="min-w-0 flex-1 truncate text-xs">
                          删除 {entry.name || filename(entry.path)}？
                        </span>
                        <button
                          type="button"
                          onClick={commitPendingAction}
                          disabled={actionBusy}
                          className="agenthub-file-mini-action inline-flex h-6 items-center justify-center rounded px-2 text-[11px] disabled:opacity-45"
                          aria-label={`确认删除 ${entry.path}`}
                          title="确认删除"
                        >
                          {actionBusy ? <BusyDot /> : "确认"}
                        </button>
                        <button
                          type="button"
                          onClick={cancelPendingAction}
                          disabled={actionBusy}
                          className="agenthub-file-mini-action inline-flex h-6 w-6 items-center justify-center rounded disabled:opacity-45"
                          aria-label="取消删除"
                          title="取消"
                        >
                          <X size={12} />
                        </button>
                      </div>
                    );
                  }
                  return (
                    <div
                      key={entry.path}
                      className={`agenthub-file-tree-row group flex items-center gap-1 rounded-md px-1 py-1 text-sm ${
                        isActive ? "agenthub-file-tree-row-active" : ""
                      }`}
                      style={{ paddingLeft: `${6 + entry.depth * 14}px` }}
                      onContextMenu={(event) => {
                        if (isDir) return;
                        event.preventDefault();
                        openFileContextMenu(entry.path, event.clientX, event.clientY);
                      }}
                    >
                      <button
                        type="button"
                        onClick={() => {
                          if (isDir) {
                            toggleDirectory(entry.path);
                          } else {
                            void openFile(entry.path);
                          }
                        }}
                        className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
                      >
                        {isDir && (
                          <ChevronRight
                            size={13}
                            className={`agenthub-faint shrink-0 transition ${isCollapsed ? "" : "rotate-90"}`}
                            aria-hidden="true"
                          />
                        )}
                        {!isDir && <span className="w-[13px] shrink-0" />}
                        <span className="agenthub-muted shrink-0">{iconForEntry(entry, !isCollapsed)}</span>
                        <span className="truncate">{entry.name || filename(entry.path)}</span>
                      </button>
                      {!isDir && projectId && (
                        <a
                          href={projectPathDownloadUrl(projectId, entry.path)}
                          onClick={(event) => event.stopPropagation()}
                          className="agenthub-file-mini-action inline-flex h-6 w-6 items-center justify-center rounded-md"
                          title="下载"
                          aria-label={`下载 ${entry.path}`}
                        >
                          <Download size={12} />
                        </a>
                      )}
                      {!isDir && (
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            void addPathToChat(entry.path);
                          }}
                          className="agenthub-file-mini-action inline-flex h-6 w-6 items-center justify-center rounded-md"
                          title="引用"
                          aria-label={`引用 ${entry.path}`}
                        >
                          <Quote size={12} />
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          beginRename(entry.path);
                        }}
                        className="agenthub-file-mini-action inline-flex h-6 w-6 items-center justify-center rounded-md"
                        title="重命名"
                        aria-label="重命名"
                      >
                        <Pencil size={12} />
                      </button>
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          beginDelete(entry.path);
                        }}
                        className="agenthub-file-mini-action inline-flex h-6 w-6 items-center justify-center rounded-md"
                        title="删除"
                        aria-label="删除"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  );
                  })}
                </div>
              )}
            </div>
          </aside>

          <main className="flex min-h-0 min-w-0 flex-col">
            {!activeTab ? (
              <WorkspaceEmptyState
                projectName={project?.name ?? "未选择项目"}
                fileCount={tree.filter((entry) => entry.type === "file").length}
                onCreateFile={() => beginCreate("file")}
                onCreateFolder={() => beginCreate("folder")}
                disabled={!projectId}
              />
            ) : (
              <>
                <div className="agenthub-header flex min-h-11 items-center gap-1 overflow-x-auto border-b px-2">
                  {tabs.map((tab) => {
                const dirty = tab.content !== tab.original;
                const confirmingClose = pendingClosePath === tab.path && dirty;
                return (
                  <button
                    key={tab.path}
                    type="button"
                    onClick={() => {
                      setActivePath(tab.path);
                      if (pendingClosePath && pendingClosePath !== tab.path) setPendingClosePath(null);
                    }}
                    className={`group inline-flex h-8 max-w-[240px] shrink-0 items-center gap-1.5 rounded-lg px-2 text-xs ${
                      activePath === tab.path ? "agenthub-nav-active" : "agenthub-nav-idle"
                    } ${confirmingClose ? "agenthub-file-tab-confirm" : ""}`}
                    title={tab.path}
                  >
                    {iconForEntry(tab.file)}
                    {confirmingClose ? (
                      <>
                        <span className="truncate text-[11px]">关闭未保存？</span>
                        <span
                          role="button"
                          tabIndex={0}
                          onClick={(event) => {
                            event.stopPropagation();
                            closeTab(tab.path, true);
                          }}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              event.stopPropagation();
                              closeTab(tab.path, true);
                            }
                          }}
                          className="agenthub-file-mini-action inline-flex h-5 items-center justify-center rounded px-1.5 text-[10px]"
                          aria-label="放弃修改并关闭标签"
                        >
                          放弃
                        </span>
                        <span
                          role="button"
                          tabIndex={0}
                          onClick={(event) => {
                            event.stopPropagation();
                            setPendingClosePath(null);
                          }}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              event.stopPropagation();
                              setPendingClosePath(null);
                            }
                          }}
                          className="agenthub-file-mini-action inline-flex h-5 w-5 items-center justify-center rounded"
                          aria-label="取消关闭标签"
                        >
                          <X size={11} />
                        </span>
                      </>
                    ) : (
                      <>
                        <span className="truncate">{filename(tab.path)}</span>
                        {dirty && <span className="text-[color:var(--ah-warning)]">*</span>}
                        <span
                          role="button"
                          tabIndex={0}
                          onClick={(event) => {
                            event.stopPropagation();
                            closeTab(tab.path);
                          }}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              event.stopPropagation();
                              closeTab(tab.path);
                            }
                          }}
                          className="agenthub-icon-button inline-flex h-5 w-5 items-center justify-center rounded"
                          aria-label="关闭标签"
                        >
                          <X size={12} />
                        </span>
                      </>
                    )}
                  </button>
                );
                  })}
                </div>

                <FileToolbar
                  tab={activeTab}
                  previewMode={previewMode}
                  saving={savingPath === activePath}
                  onPreviewModeChange={setPreviewMode}
                  onSave={() => void saveActive()}
                />

                <div className="relative min-h-0 flex-1">
                  {fileLoadingPath && (
                    <div className="agenthub-backdrop absolute inset-0 z-20 flex items-center justify-center p-6 text-sm">
                      <div className="agenthub-file-open-loading w-full max-w-sm rounded-xl border p-3" aria-label={`正在打开 ${filename(fileLoadingPath)}`}>
                        <div className="agenthub-skeleton flex items-center gap-3 rounded-2xl border px-3 py-2.5">
                          <span className="h-10 w-10 shrink-0 animate-pulse rounded-full bg-[color:var(--ah-panel-muted)]" />
                          <span className="min-w-0 flex-1 space-y-2">
                            <span className="block h-3 w-2/3 animate-pulse rounded-full bg-[color:var(--ah-panel-muted)]" />
                            <span className="block h-2.5 w-5/6 animate-pulse rounded-full bg-[color:var(--ah-card-soft)]" />
                          </span>
                        </div>
                        <div className="agenthub-muted mt-2 truncate px-1 text-xs">
                          正在打开 {filename(fileLoadingPath)}
                        </div>
                      </div>
                    </div>
                  )}
                  {activeTab.selection && activeTab.file.editable && (
                    <button
                      type="button"
                      onClick={() => addSelectionForPathToChat(activeTab.path)}
                      className="agenthub-selection-reference-button absolute right-4 top-4 z-10 inline-flex h-8 items-center gap-1.5 rounded-md border px-3 text-xs font-medium"
                      aria-label="引用选区"
                    >
                      <Quote size={13} aria-hidden="true" />
                      引用选区
                    </button>
                  )}
                <div className={`grid h-full min-h-0 ${previewMode === "split" ? "grid-cols-1 xl:grid-cols-2" : "grid-cols-1"}`}>
                  {(previewMode === "editor" || previewMode === "split") && (
                    <div className="agenthub-code-surface agenthub-editor-shell min-h-0 overflow-hidden border-r">
                      {activeTab.file.editable ? (
                        <Suspense fallback={<EditorLoading />}>
                          <CodeMirrorFileEditor
                            editorRef={editorRef}
                            value={activeTab.content}
                            language={languageFromPath(activeTab.path)}
                            onChange={(value) => updateTab(activeTab.path, { content: value })}
                            onUpdate={(update) => captureEditorState(activeTab.path, update)}
                          />
                        </Suspense>
                      ) : (
                        <ReadonlyFile tab={activeTab} projectId={projectId} />
                      )}
                    </div>
                  )}
                  {(previewMode === "preview" || previewMode === "split") && (
                    <FilePreview tab={activeTab} projectId={projectId} />
                  )}
                </div>
                </div>

                <div className="agenthub-header flex flex-wrap items-center justify-between gap-2 border-t px-3 py-2 text-[11px] agenthub-muted">
                  <span className="inline-flex items-center gap-2">
                    <Code2 size={13} aria-hidden="true" />
                    {`${languageFromPath(activeTab.path).toUpperCase()} · ${formatSize(activeTab.file.size)}`}
                  </span>
                  <span className="flex min-w-0 items-center gap-3 truncate font-mono">
                    <span>第 {activeTab.cursor.line} 行，第 {activeTab.cursor.column} 列</span>
                    {activeTab.selection ? <span>已选择 {activeTab.selection.text.length} 字符</span> : <span>未选择</span>}
                    {activeTab.content !== activeTab.original && <span className="text-[color:var(--ah-warning)]">已修改</span>}
                  </span>
                </div>
              </>
            )}
          </main>
      </div>

      {conflict && activeTab && (
        <ConflictDialog
          path={conflict.path}
          onClose={() => setConflict(null)}
          onUseCurrent={() => {
            updateTab(conflict.path, {
              content: conflict.content,
              original: conflict.content,
              file: { ...activeTab.file, etag: conflict.etag, mtime: conflict.mtime ?? activeTab.file.mtime, content: conflict.content },
            });
            setConflict(null);
          }}
          onOverwrite={() => void saveActive(true)}
        />
      )}

      {fileContextMenu && (
        <div
          className="agenthub-file-context-menu fixed z-[1600] w-52 rounded-xl border p-1.5 text-sm shadow-xl"
          role="menu"
          aria-label={`${fileContextMenu.path} 文件操作`}
          style={contextMenuStyle}
          onClick={(event) => event.stopPropagation()}
          onContextMenu={(event) => event.preventDefault()}
        >
          <div className="agenthub-faint truncate px-2 py-1 text-[11px] font-mono">
            {fileContextMenu.path}
          </div>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              const path = fileContextMenu.path;
              setFileContextMenu(null);
              void openFile(path);
            }}
            className="agenthub-file-menu-item"
          >
            <FileCode2 size={14} aria-hidden="true" />
            打开文件
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => void addPathToChat(fileContextMenu.path)}
            className="agenthub-file-menu-item"
          >
            <Quote size={14} aria-hidden="true" />
            引用文件
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => addSelectionForPathToChat(fileContextMenu.path)}
            disabled={!contextMenuTab?.selection}
            className="agenthub-file-menu-item disabled:cursor-not-allowed disabled:opacity-45"
          >
            <Code2 size={14} aria-hidden="true" />
            引用选区
          </button>
          {projectId && (
            <a
              href={projectPathDownloadUrl(projectId, fileContextMenu.path)}
              role="menuitem"
              className="agenthub-file-menu-item"
            >
              <Download size={14} aria-hidden="true" />
              下载文件
            </a>
          )}
        </div>
      )}
    </section>
  );
}

function FileTreeSkeleton({ label = "正在加载文件" }: { label?: string }) {
  const rows = 6;
  return (
    <div
      className="agenthub-file-tree-skeleton space-y-1.5 px-1 py-1"
      aria-label={label}
    >
      {Array.from({ length: rows }).map((_, index) => (
        <div
          key={index}
          className="agenthub-skeleton flex items-center gap-3 rounded-2xl border px-2 py-2"
        >
          <span className="h-8 w-8 shrink-0 animate-pulse rounded-full bg-[color:var(--ah-panel-muted)]" />
          <span className="min-w-0 flex-1 space-y-1.5">
            <span
              className="block h-2.5 animate-pulse rounded-full bg-[color:var(--ah-panel-muted)]"
              style={{ width: `${46 + (index % 3) * 13}%` }}
            />
            <span
              className="block h-2 animate-pulse rounded-full bg-[color:var(--ah-card-soft)]"
              style={{ width: `${34 + (index % 4) * 9}%` }}
            />
          </span>
        </div>
      ))}
    </div>
  );
}

function WorkspaceEmptyState({
  projectName,
  fileCount,
  onCreateFile,
  onCreateFolder,
  disabled,
}: {
  projectName: string;
  fileCount: number;
  onCreateFile: () => void;
  onCreateFolder: () => void;
  disabled: boolean;
}) {
  return (
    <div className="agenthub-file-empty-workspace flex min-h-0 flex-1 flex-col">
      <div className="agenthub-file-empty-canvas flex min-h-0 flex-1 items-center justify-center p-6">
        <div className="agenthub-file-empty-content w-full max-w-xl text-center">
          <div className="agenthub-file-empty-mark mx-auto flex h-14 w-14 items-center justify-center border">
            <FolderOpen size={24} aria-hidden="true" />
          </div>
          <h4 className="agenthub-strong mt-5 text-base font-semibold">项目文件工作台</h4>
          <p className="agenthub-muted mx-auto mt-2 max-w-sm text-sm leading-6">
            从左侧选择文件，或创建第一个项目文件。
          </p>
          <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
            <button
              type="button"
              onClick={onCreateFile}
              disabled={disabled}
              className="agenthub-primary-button inline-flex h-9 items-center gap-1.5 rounded-full px-3 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-45"
              aria-label="在工作台中新建文件"
            >
              <CirclePlus size={14} aria-hidden="true" />
              新建文件
            </button>
            <button
              type="button"
              onClick={onCreateFolder}
              disabled={disabled}
              className="agenthub-icon-button inline-flex h-9 items-center gap-1.5 rounded-full px-3 text-sm disabled:cursor-not-allowed disabled:opacity-45"
              aria-label="在工作台中新建目录"
            >
              <Folder size={14} aria-hidden="true" />
              新建目录
            </button>
          </div>
          <div className="agenthub-file-empty-meta mx-auto mt-6 flex w-full max-w-sm items-center justify-center gap-3 text-xs">
            <span className="truncate">{projectName}</span>
            <span className="agenthub-faint">/</span>
            <span>{fileCount} 个文件</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function FileToolbar({
  tab,
  previewMode,
  saving,
  onPreviewModeChange,
  onSave,
}: {
  tab: Tab | null;
  previewMode: "editor" | "preview" | "split";
  saving: boolean;
  onPreviewModeChange: (mode: "editor" | "preview" | "split") => void;
  onSave: () => void;
}) {
  const dirty = Boolean(tab && tab.content !== tab.original);
  return (
    <div className="agenthub-header flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
      <div className="flex min-w-0 items-center gap-2">
        {tab ? (
          <>
            <span className="agenthub-muted truncate text-xs">{tab.path}</span>
            {tab.file.etag && (
              <span className="agenthub-status rounded-md px-1.5 py-0.5 font-mono text-[10px]">
                {tab.file.etag.slice(0, 8)}
              </span>
            )}
          </>
        ) : (
          <span className="agenthub-faint text-xs">未选择文件</span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <div className="grid grid-cols-3 rounded-lg border p-0.5" style={{ borderColor: "var(--ah-border)" }}>
          {(["editor", "preview", "split"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => onPreviewModeChange(mode)}
              data-active={previewMode === mode}
              disabled={!tab}
              className="agenthub-theme-choice inline-flex h-7 items-center justify-center gap-1 rounded-md px-2 text-[11px] disabled:opacity-40"
              title={mode === "editor" ? "编辑" : mode === "preview" ? "预览" : "分屏"}
            >
              {mode === "split" ? <SplitSquareHorizontal size={13} aria-hidden="true" /> : mode === "preview" ? <FileText size={13} aria-hidden="true" /> : <FileCode2 size={13} aria-hidden="true" />}
              <span className="hidden sm:inline">{mode === "editor" ? "编辑" : mode === "preview" ? "预览" : "分屏"}</span>
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={onSave}
          disabled={!tab?.file.editable || !dirty || saving}
          className="agenthub-primary-button inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving ? <BusyDot /> : dirty ? <Save size={14} aria-hidden="true" /> : <Check size={14} aria-hidden="true" />}
          保存
        </button>
      </div>
    </div>
  );
}

function BusyDot() {
  return <span className="agenthub-file-action-pulse" aria-hidden="true" />;
}

function FilePreview({ tab, projectId }: { tab: Tab; projectId: string | null }) {
  const kind = tab.file.previewKind;
  if (kind === "markdown") {
    return (
      <div className="agenthub-chat min-h-0 overflow-auto p-4">
        <div className="agent-markdown agenthub-code-surface rounded-2xl border p-4 text-sm">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{tab.content || "暂无 Markdown 内容"}</ReactMarkdown>
        </div>
      </div>
    );
  }
  if (kind === "html") {
    return (
      <div className="agenthub-chat min-h-0 p-3">
        <iframe
          title={tab.path}
          srcDoc={tab.content}
          sandbox="allow-forms allow-modals allow-popups allow-scripts"
          className="h-full w-full rounded-2xl border bg-white"
        />
      </div>
    );
  }
  if (kind === "json" || kind === "code" || kind === "text") {
    return (
      <pre className="agenthub-code-surface min-h-0 overflow-auto p-4 text-xs leading-6">
        <code>{tab.content || "暂无内容"}</code>
      </pre>
    );
  }
  if ((kind === "image" || kind === "pdf") && projectId) {
    return <ReadonlyFile tab={tab} projectId={projectId} />;
  }
  return <ReadonlyFile tab={tab} projectId={projectId} />;
}

function ReadonlyFile({ tab, projectId }: { tab: Tab; projectId: string | null }) {
  const url = projectId ? projectPathDownloadUrl(projectId, tab.path) : undefined;
  if (url && tab.file.previewKind === "image") {
    return (
      <div className="agenthub-chat flex h-full min-h-0 items-center justify-center overflow-auto p-4">
        <img
          src={url}
          alt={filename(tab.path)}
          className="max-h-full max-w-full rounded-2xl border object-contain"
        />
      </div>
    );
  }
  if (url && tab.file.previewKind === "pdf") {
    return (
      <div className="agenthub-chat h-full min-h-0 p-3">
        <iframe
          title={tab.path}
          src={url}
          className="h-full w-full rounded-2xl border"
        />
      </div>
    );
  }
  return (
    <div className="agenthub-chat flex h-full min-h-0 items-center justify-center p-6">
      <div className="agenthub-card max-w-md rounded-2xl border p-5 text-center">
        {iconForEntry(tab.file)}
        <p className="agenthub-strong mt-3 text-sm font-semibold">{filename(tab.path)}</p>
        <p className="agenthub-muted mt-1 text-xs leading-5">
          {tab.file.readonlyReason === "too_large" ? "文件过大，无法在编辑器中打开。" : "该文件以只读方式提供下载。"}
        </p>
        {url && (
          <a
            href={url}
            className="agenthub-primary-button mt-4 inline-flex h-9 items-center gap-1.5 rounded-full px-4 text-sm font-medium"
          >
            <Download size={14} aria-hidden="true" />
            下载文件
          </a>
        )}
      </div>
    </div>
  );
}

function SearchResults({
  items,
  onOpen,
}: {
  items: WorkspaceSearchItem[];
  onOpen: (path: string) => void;
}) {
  if (items.length === 0) {
    return <div className="agenthub-faint px-3 py-8 text-sm">没有匹配结果</div>;
  }
  return (
    <div className="space-y-1">
      {items.map((item, index) => (
        <button
          key={`${item.path}-${item.line ?? "path"}-${index}`}
          type="button"
          onClick={() => onOpen(item.path)}
          className="agenthub-nav-idle w-full rounded-lg px-2.5 py-2 text-left"
        >
          <span className="block truncate text-sm">{item.path}</span>
          <span className="agenthub-faint mt-0.5 block truncate text-xs">
            {item.matchType === "content" && item.line ? `第 ${item.line} 行 · ` : ""}
            {item.snippet}
          </span>
        </button>
      ))}
    </div>
  );
}

function EditorLoading() {
  return (
    <div className="agenthub-editor-skeleton flex h-full flex-col gap-3 p-4" aria-label="正在加载编辑器">
      {Array.from({ length: 9 }).map((_, index) => (
        <div key={index} className="flex items-center gap-3">
          <span className="agenthub-faint w-8 shrink-0 text-right font-mono text-[11px]">{index + 1}</span>
          <span
            className="block h-3 animate-pulse rounded-full bg-[color:var(--ah-panel-muted)]"
            style={{ width: `${36 + (index % 5) * 10}%` }}
          />
        </div>
      ))}
    </div>
  );
}

function ConflictDialog({
  path,
  onClose,
  onUseCurrent,
  onOverwrite,
}: {
  path: string;
  onClose: () => void;
  onUseCurrent: () => void;
  onOverwrite: () => void;
}) {
  return (
    <div className="agenthub-backdrop absolute inset-0 z-30 flex items-center justify-center p-4">
      <div className="agenthub-modal agenthub-modal-pop w-full max-w-md rounded-3xl border p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h4 className="agenthub-strong text-base font-semibold">保存冲突</h4>
            <p className="agenthub-muted mt-1 text-sm leading-6">{path} 已在外部被修改。</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="agenthub-icon-button inline-flex h-8 w-8 items-center justify-center rounded-full"
            aria-label="关闭冲突提示"
          >
            <X size={15} />
          </button>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          <button
            type="button"
            onClick={onUseCurrent}
            className="agenthub-icon-button h-10 rounded-full px-4 text-sm"
          >
            载入当前版本
          </button>
          <button
            type="button"
            onClick={onOverwrite}
            className="agenthub-primary-button h-10 rounded-full px-4 text-sm font-medium"
          >
            覆盖保存
          </button>
        </div>
      </div>
    </div>
  );
}
