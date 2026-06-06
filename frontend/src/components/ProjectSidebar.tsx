import { useEffect, useRef, useState } from "react";
import {
  Archive,
  Bot,
  Moon,
  Folder,
  FolderOpen,
  MessageCircle,
  MoreHorizontal,
  Pencil,
  Plus,
  Settings,
  Sun,
  Trash2,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import type { AgentConfig, Project } from "../types";
import { AgentAvatar } from "./AgentAvatar";
import type { SidebarTab } from "../stores/sessionStore";
import { useThemeStore, type ThemeMode } from "../stores/themeStore";

interface Props {
  projects: Project[];
  currentProjectId: string | null;
  agents: AgentConfig[];
  activePanel: SidebarTab;
  creating: boolean;
  onSelectProject: (id: string) => void;
  onCreateBlankProject: (name?: string) => Promise<void>;
  onPickExistingFolder: () => Promise<void>;
  onArchiveProject: (id: string) => Promise<void>;
  onRenameProject: (id: string, name: string) => Promise<void>;
  onDeleteProject: (id: string, deleteFiles: boolean) => Promise<void>;
  onOpenPanel: (panel: SidebarTab) => void;
  onStartAgentChat: (agentId: string) => Promise<void>;
  onCreateAgent: () => void;
  onEditAgent: (agentId: string) => void;
  onDeleteAgent: (agentId: string) => Promise<void>;
}

export function ProjectSidebar({
  projects,
  currentProjectId,
  agents,
  activePanel,
  creating,
  onSelectProject,
  onCreateBlankProject,
  onPickExistingFolder,
  onArchiveProject,
  onRenameProject,
  onDeleteProject,
  onOpenPanel,
  onStartAgentChat,
  onCreateAgent,
  onEditAgent,
  onDeleteAgent,
}: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [agentMenuOpen, setAgentMenuOpen] = useState<string | null>(null);
  const [projectMenuOpen, setProjectMenuOpen] = useState<string | null>(null);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [createName, setCreateName] = useState("新项目");
  const [renamingProjectId, setRenamingProjectId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);
  const agentMenuRef = useRef<HTMLDivElement>(null);
  const projectMenuRef = useRef<HTMLDivElement>(null);
  const activeAgents = agents.filter((agent) => agent.isActive).slice(0, 6);
  const theme = useThemeStore((state) => state.theme);
  const setTheme = useThemeStore((state) => state.setTheme);

  useEffect(() => {
    if (!menuOpen && !agentMenuOpen && !projectMenuOpen) return;
    const close = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!menuRef.current?.contains(target)) setMenuOpen(false);
      if (!agentMenuRef.current?.contains(target)) setAgentMenuOpen(null);
      if (!projectMenuRef.current?.contains(target)) setProjectMenuOpen(null);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [menuOpen, agentMenuOpen, projectMenuOpen]);

  const runCreateAction = async (action: () => Promise<void>) => {
    setMenuOpen(false);
    await action();
    onOpenPanel("sessions");
  };

  const openCreateProjectDialog = () => {
    setMenuOpen(false);
    setCreateName("新项目");
    setCreateModalOpen(true);
  };

  const submitCreateProject = async () => {
    const name = createName.trim();
    if (!name) return;
    setCreateModalOpen(false);
    await onCreateBlankProject(name);
  };

  const submitProjectRename = async (project: Project) => {
    const name = renameValue.trim();
    setRenamingProjectId(null);
    if (!name || name === project.name) return;
    await onRenameProject(project.id, name);
  };

  const confirmDeleteProject = async (project: Project) => {
    const confirmed = window.confirm(
      `永久删除项目「${project.name}」并删除本机目录？\n\n${project.workspacePath}`,
    );
    if (!confirmed) return;
    await onDeleteProject(project.id, true);
  };

  return (
    <aside className="agenthub-rail w-full md:w-[260px] h-[34dvh] md:h-full flex flex-col shrink-0 border-r transition-colors duration-300">
      <div className="px-3 py-3 space-y-3">
        <ThemeToggle theme={theme} onChange={setTheme} />
        <NavButton
          icon={MessageCircle}
          label="对话"
          active={activePanel === "sessions"}
          onClick={() => onOpenPanel("sessions")}
        />
        <NavButton
          icon={Workflow}
          label="调度器调试台"
          active={activePanel === "debug"}
          onClick={() => onOpenPanel("debug")}
        />
        <NavButton icon={Bot} label="添加 Agent" onClick={onCreateAgent} />
      </div>

      <div className="border-t px-3 py-3" style={{ borderColor: "var(--ah-border)" }}>
        <div className="agenthub-muted mb-2 flex items-center justify-between text-sm">
          <span className="inline-flex items-center gap-2">
            <Bot size={15} />
            好友
          </span>
          <IconButton
            icon={Plus}
            title="添加 CLI Agent"
            disabled={false}
            onClick={onCreateAgent}
          />
        </div>
        <div className="space-y-1">
          {activeAgents.length === 0 ? (
            <div className="agenthub-faint px-2 py-2 text-xs">暂无可用 Agent</div>
          ) : activeAgents.map((agent) => (
            <div key={agent.id} className="relative" ref={agentMenuOpen === agent.id ? agentMenuRef : undefined}>
              <div className="agenthub-nav-idle w-full rounded-2xl px-2 py-2 text-left transition">
                <div className="flex items-center gap-3">
                  <AgentAvatar agent={agent} size="sm" />
                  <button
                    type="button"
                    onClick={() => {
                      if (currentProjectId) void onStartAgentChat(agent.id);
                    }}
                    disabled={!currentProjectId}
                    className="min-w-0 flex-1 text-left disabled:cursor-not-allowed disabled:opacity-45"
                    title={currentProjectId ? "发起对话" : "请先选择项目"}
                  >
                    <span className="block truncate text-sm font-medium">{agent.name}</span>
                    <span className="agenthub-faint mt-0.5 block truncate text-xs">
                      {agent.version || (agent.status === "ready" ? "就绪" : "未找到 executable")}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setAgentMenuOpen((value) => (value === agent.id ? null : agent.id))}
                    className="agenthub-icon-button inline-flex h-7 w-7 items-center justify-center rounded-full"
                    title="Agent 操作"
                    aria-label="Agent 操作"
                  >
                    <MoreHorizontal size={15} />
                  </button>
                </div>
              </div>
              {agentMenuOpen === agent.id && (
                <div className="agenthub-menu absolute right-1 top-10 z-30 w-38 rounded-2xl border p-1">
                  <MenuItem
                    icon={MessageCircle}
                    label="发起对话"
                    onClick={() => {
                      setAgentMenuOpen(null);
                      if (currentProjectId) void onStartAgentChat(agent.id);
                    }}
                  />
                  <MenuItem
                    icon={Settings}
                    label="设置"
                    onClick={() => {
                      setAgentMenuOpen(null);
                      onEditAgent(agent.id);
                    }}
                  />
                  <MenuItem
                    icon={Trash2}
                    label="删除"
                    danger
                    onClick={() => {
                      setAgentMenuOpen(null);
                      void onDeleteAgent(agent.id);
                    }}
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="px-3 pt-2 pb-1">
        <div className="agenthub-muted mb-2 flex items-center justify-between text-sm">
          <span className="inline-flex items-center gap-2">
            <FolderOpen size={15} />
            项目
          </span>
          <div className="relative" ref={menuRef}>
            <IconButton
              icon={Plus}
              title="创建项目"
              disabled={creating}
              onClick={() => setMenuOpen((value) => !value)}
            />
            {menuOpen && (
              <div className="agenthub-menu absolute right-0 top-9 z-30 w-56 rounded-2xl border p-1.5">
                <MenuItem
                  icon={Plus}
                  label="新建空白项目"
                  onClick={openCreateProjectDialog}
                />
                <MenuItem
                  icon={Folder}
                  label="选择现有文件夹"
                  onClick={() => runCreateAction(onPickExistingFolder)}
                />
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {projects.length === 0 ? (
          <div className="agenthub-faint px-2 py-8 text-sm">暂无项目</div>
        ) : projects.map((project) => {
          const selected = currentProjectId === project.id && activePanel === "sessions";
          const isRenaming = renamingProjectId === project.id;
          return (
            <div key={project.id} className="group relative" ref={projectMenuOpen === project.id ? projectMenuRef : undefined}>
              <button
                type="button"
                onClick={() => { onSelectProject(project.id); onOpenPanel("sessions"); }}
                className={`w-full rounded-2xl px-2.5 py-2.5 text-left transition-all duration-200 ${
                  selected ? "agenthub-nav-active" : "agenthub-nav-idle"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="agenthub-soft flex h-8 w-8 shrink-0 items-center justify-center rounded-full border agenthub-muted">
                    <Folder size={15} />
                  </span>
                  <span className="min-w-0 flex-1">
                    {isRenaming ? (
                      <input
                        value={renameValue}
                        onChange={(event) => setRenameValue(event.target.value)}
                        onBlur={() => void submitProjectRename(project)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") void submitProjectRename(project);
                          if (event.key === "Escape") setRenamingProjectId(null);
                        }}
                        onClick={(event) => event.stopPropagation()}
                        className="w-full rounded-lg border px-2 py-1 text-sm outline-none agenthub-composer"
                        autoFocus
                      />
                    ) : (
                      <>
                        <span className="block truncate text-sm font-medium">{project.name}</span>
                        <span className="agenthub-faint mt-0.5 block truncate text-xs">{project.status}</span>
                      </>
                    )}
                  </span>
                </div>
              </button>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  setProjectMenuOpen((value) => (value === project.id ? null : project.id));
                }}
                className="agenthub-icon-button absolute right-2 top-3 inline-flex h-7 w-7 items-center justify-center rounded-full opacity-0 group-hover:opacity-100"
                title="项目操作"
                aria-label="项目操作"
              >
                <MoreHorizontal size={15} />
              </button>
              {projectMenuOpen === project.id && (
                <div className="agenthub-menu absolute right-1 top-10 z-30 w-44 rounded-2xl border p-1">
                  <MenuItem
                    icon={Pencil}
                    label="重命名"
                    onClick={() => {
                      setRenameValue(project.name);
                      setRenamingProjectId(project.id);
                      setProjectMenuOpen(null);
                    }}
                  />
                  <MenuItem
                    icon={Archive}
                    label="归档"
                    onClick={() => {
                      setProjectMenuOpen(null);
                      void onArchiveProject(project.id);
                    }}
                  />
                  <MenuItem
                    icon={Trash2}
                    label="删除目录"
                    danger
                    onClick={() => {
                      setProjectMenuOpen(null);
                      void confirmDeleteProject(project);
                    }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {createModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4 backdrop-blur-sm">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="blank-project-title"
            className="agenthub-modal w-full max-w-sm rounded-3xl border p-4"
          >
            <div className="mb-4 flex items-start gap-3">
              <span className="agenthub-soft agenthub-muted flex h-10 w-10 shrink-0 items-center justify-center rounded-full border">
                <FolderOpen size={18} />
              </span>
              <div>
                <h2 id="blank-project-title" className="agenthub-strong text-base font-semibold">新建项目</h2>
                <p className="agenthub-muted mt-0.5 text-xs">为空项目选择一个名称。</p>
              </div>
            </div>
            <label className="agenthub-muted block text-xs font-medium" htmlFor="blank-project-name">
              项目名称
            </label>
            <input
              id="blank-project-name"
              value={createName}
              onChange={(event) => setCreateName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void submitCreateProject();
                if (event.key === "Escape") setCreateModalOpen(false);
              }}
              className="agenthub-composer agenthub-textarea mt-2 h-11 w-full rounded-2xl border px-3 text-sm outline-none transition focus:ring-2 focus:ring-[color:var(--ah-accent-soft)]"
              autoFocus
            />
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setCreateModalOpen(false)}
                className="agenthub-icon-button h-10 rounded-full px-4 text-sm"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void submitCreateProject()}
                disabled={!createName.trim() || creating}
                className="h-10 rounded-full px-5 text-sm font-medium text-white transition active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50"
                style={{ background: "var(--ah-accent-strong)" }}
              >
                创建
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}

function ThemeToggle({
  theme,
  onChange,
}: {
  theme: ThemeMode;
  onChange: (theme: ThemeMode) => void;
}) {
  return (
    <div className="agenthub-theme-segment grid grid-cols-2 rounded-full p-1">
      <button
        type="button"
        data-active={theme === "dark"}
        onClick={() => onChange("dark")}
        className="agenthub-theme-choice inline-flex h-8 items-center justify-center gap-1.5 rounded-full text-xs font-medium transition"
      >
        <Moon size={13} aria-hidden="true" />
        暗黑
      </button>
      <button
        type="button"
        data-active={theme === "light"}
        onClick={() => onChange("light")}
        className="agenthub-theme-choice inline-flex h-8 items-center justify-center gap-1.5 rounded-full text-xs font-medium transition"
      >
        <Sun size={13} aria-hidden="true" />
        明亮
      </button>
    </div>
  );
}

function NavButton({
  icon: Icon,
  label,
  active = false,
  onClick,
}: {
  icon?: LucideIcon;
  label: string;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-center gap-2 rounded-2xl px-2.5 py-2 text-left text-sm transition-all duration-200 ${
        active ? "agenthub-nav-active" : "agenthub-nav-idle"
      }`}
    >
      {Icon && <Icon size={15} className="agenthub-muted shrink-0" />}
      {label}
    </button>
  );
}

function IconButton({
  icon: Icon,
  title,
  disabled,
  onClick,
}: {
  icon: LucideIcon;
  title: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="agenthub-icon-button inline-flex h-7 w-7 items-center justify-center rounded-full disabled:opacity-50"
      title={title}
      aria-label={title}
    >
      <Icon size={15} />
    </button>
  );
}

function MenuItem({
  icon: Icon,
  label,
  danger = false,
  onClick,
}: {
  icon?: LucideIcon;
  label: string;
  danger?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm transition ${
        danger ? "text-[color:var(--ah-danger)] hover:bg-red-500/15" : "agenthub-nav-idle"
      }`}
    >
      {Icon && <Icon size={15} className="agenthub-muted shrink-0" />}
      {label}
    </button>
  );
}
