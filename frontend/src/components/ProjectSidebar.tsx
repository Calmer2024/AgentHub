import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Archive,
  Bot,
  ChevronDown,
  ChevronUp,
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
  Users,
  type LucideIcon,
} from "lucide-react";
import type { AgentConfig, Project } from "../types";
import { AgentAvatar } from "./AgentAvatar";
import { ConfirmDialog } from "./ConfirmDialog";
import type { SidebarTab } from "../stores/sessionStore";
import { useThemeStore, type ThemeMode } from "../stores/themeStore";

interface Props {
  projects: Project[];
  currentProjectId: string | null;
  agents: AgentConfig[];
  activePanel: SidebarTab;
  creating: boolean;
  loading?: boolean;
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

type DeleteTarget = {
  kind: "project" | "agent";
  id: string;
  title: string;
  description: string;
  confirmLabel: string;
};

const NATIVE_CLI_AGENT_NAMES: Partial<Record<AgentConfig["cliTool"], string>> = {
  claude_code: "Claude Code",
  codex: "Codex",
  opencode: "OpenCode",
};

const NATIVE_CLI_AGENT_ORDER: Partial<Record<AgentConfig["cliTool"], number>> = {
  claude_code: 0,
  codex: 1,
  opencode: 2,
};

const COLLAPSED_CUSTOM_AGENT_LIMIT = 3;

export function ProjectSidebar({
  projects,
  currentProjectId,
  agents,
  activePanel,
  creating,
  loading = false,
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
  const [agentsExpanded, setAgentsExpanded] = useState(false);
  const [projectsExpanded, setProjectsExpanded] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const agentMenuRef = useRef<HTMLDivElement>(null);
  const projectMenuRef = useRef<HTMLDivElement>(null);
  const activeAgents = agents.filter((agent) => agent.isActive);
  const nativeCliAgents = activeAgents
    .filter(isNativeCliAgent)
    .sort((left, right) => nativeCliAgentRank(left) - nativeCliAgentRank(right));
  const customAgents = activeAgents.filter((agent) => !isNativeCliAgent(agent));
  const visibleCustomAgents = agentsExpanded
    ? customAgents
    : customAgents.slice(0, COLLAPSED_CUSTOM_AGENT_LIMIT);
  const showAgentExpand = customAgents.length > COLLAPSED_CUSTOM_AGENT_LIMIT;
  const visibleProjects = projectsExpanded ? projects : projects.slice(0, 3);
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

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    try {
      if (deleteTarget.kind === "project") {
        await onDeleteProject(deleteTarget.id, true);
      } else {
        await onDeleteAgent(deleteTarget.id);
      }
      setDeleteTarget(null);
    } finally {
      setDeleteBusy(false);
    }
  };

  const renderAgentItem = (agent: AgentConfig) => (
    <div
      key={agent.id}
      className={`group relative animate-[agenthub-slide-in_160ms_ease-out_both] ${agentMenuOpen === agent.id ? "z-40" : ""}`}
      ref={agentMenuOpen === agent.id ? agentMenuRef : undefined}
    >
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
            className={`agenthub-icon-button inline-flex h-7 w-7 items-center justify-center rounded-full transition-opacity group-hover:opacity-100 ${
              agentMenuOpen === agent.id ? "opacity-100" : "opacity-0"
            }`}
            title="智能体操作"
            aria-label="智能体操作"
          >
            <MoreHorizontal size={15} />
          </button>
        </div>
      </div>
      {agentMenuOpen === agent.id && (
        <div className="agenthub-menu absolute right-1 top-10 z-50 w-38 rounded-2xl border p-1">
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
              setDeleteTarget({
                kind: "agent",
                id: agent.id,
                title: "删除 Agent",
                description: `删除「${agent.name}」后，历史消息仍会保留。`,
                confirmLabel: "删除",
              });
            }}
          />
        </div>
      )}
    </div>
  );

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
        <NavButton icon={Bot} label="添加 Agent" onClick={onCreateAgent} />
      </div>

      <div className="border-t px-3 py-3" style={{ borderColor: "var(--ah-border)" }}>
        <div className="agenthub-muted mb-2 flex items-center justify-between text-sm">
          <span className="inline-flex items-center gap-2">
            <Users size={15} />
            好友
          </span>
          <IconButton
            icon={Plus}
            title="添加命令行智能体"
            disabled={false}
            onClick={onCreateAgent}
          />
        </div>
        <div
          className={`agenthub-expand-scroll agenthub-expand-scroll-friends space-y-1 transition-all duration-200 ${agentsExpanded ? "agenthub-expand-scroll-open" : ""}`}
          aria-label="好友列表"
        >
          {loading && activeAgents.length === 0 ? (
            <SidebarMiniSkeleton rows={3} />
          ) : activeAgents.length === 0 ? (
            <div className="agenthub-faint px-2 py-2 text-xs">暂无可用智能体</div>
          ) : (
            <>
              {nativeCliAgents.length > 0 && (
                <AgentGroup label="原生 CLI" count={nativeCliAgents.length}>
                  {nativeCliAgents.map(renderAgentItem)}
                </AgentGroup>
              )}
              {customAgents.length > 0 && (
                <AgentGroup
                  label="自定义 Agent"
                  count={customAgents.length}
                  className={nativeCliAgents.length > 0 ? "mt-2" : ""}
                >
                  {visibleCustomAgents.map(renderAgentItem)}
                </AgentGroup>
              )}
            </>
          )}
        </div>
        {showAgentExpand && (
          <ExpandButton
            expanded={agentsExpanded}
            count={activeAgents.length}
            expandedLabel="收起好友"
            collapsedLabel="展开全部好友"
            onClick={() => setAgentsExpanded((value) => !value)}
          />
        )}
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

      <div className="min-h-0 flex-1 px-2 pb-3">
        <div
          className={`agenthub-expand-scroll agenthub-expand-scroll-projects space-y-1 transition-all duration-200 ${projectsExpanded ? "agenthub-expand-scroll-open" : ""}`}
          aria-label="项目列表"
        >
          {loading && projects.length === 0 ? (
            <SidebarMiniSkeleton rows={3} />
          ) : projects.length === 0 ? (
            <div className="agenthub-faint px-2 py-8 text-sm">暂无项目</div>
          ) : visibleProjects.map((project) => {
            const selected = currentProjectId === project.id && activePanel === "sessions";
            const isRenaming = renamingProjectId === project.id;
            return (
              <div
                key={project.id}
                className={`group relative animate-[agenthub-slide-in_160ms_ease-out_both] ${projectMenuOpen === project.id ? "z-40" : ""}`}
                ref={projectMenuOpen === project.id ? projectMenuRef : undefined}
              >
                <button
                  type="button"
                  onClick={() => { onSelectProject(project.id); onOpenPanel("sessions"); }}
                  className={`w-full rounded-2xl px-2.5 py-2.5 text-left transition-all duration-200 ${
                    selected ? "agenthub-nav-active" : "agenthub-nav-idle"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="agenthub-project-icon agenthub-soft flex h-8 w-8 shrink-0 items-center justify-center rounded-full border agenthub-muted">
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
                          <span className="agenthub-faint mt-0.5 block truncate text-xs">{projectStatusLabel(project.status)}</span>
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
                  <div className="agenthub-menu absolute right-1 top-10 z-50 w-44 rounded-2xl border p-1">
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
                        setDeleteTarget({
                          kind: "project",
                          id: project.id,
                          title: "删除项目",
                          description: `永久删除「${project.name}」并删除本机目录：\n${project.workspacePath}`,
                          confirmLabel: "删除目录",
                        });
                      }}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
        {projects.length > 3 && (
          <ExpandButton
            expanded={projectsExpanded}
            count={projects.length}
            expandedLabel="收起项目"
            collapsedLabel="展开全部项目"
            onClick={() => setProjectsExpanded((value) => !value)}
          />
        )}
      </div>

      {createModalOpen && (
        <div className="agenthub-backdrop fixed inset-0 z-50 flex items-center justify-center px-4">
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
                className="agenthub-primary-button h-10 rounded-full px-5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50"
              >
                创建
              </button>
            </div>
          </div>
        </div>
      )}
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={deleteTarget?.title ?? ""}
        description={deleteTarget?.description ?? ""}
        confirmLabel={deleteTarget?.confirmLabel ?? "确认"}
        busy={deleteBusy}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void confirmDelete()}
      />
    </aside>
  );
}

function isNativeCliAgent(agent: AgentConfig) {
  return NATIVE_CLI_AGENT_NAMES[agent.cliTool] === agent.name;
}

function nativeCliAgentRank(agent: AgentConfig) {
  return NATIVE_CLI_AGENT_ORDER[agent.cliTool] ?? Number.MAX_SAFE_INTEGER;
}

function AgentGroup({
  label,
  count,
  children,
  className = "",
}: {
  label: string;
  count: number;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`space-y-1 ${className}`} aria-label={`${label} 分区`}>
      <div className="agenthub-session-section-label flex items-center justify-between px-2 pb-1 pt-1 text-[11px] font-normal">
        <span>{label}</span>
        <span>{count}</span>
      </div>
      {children}
    </div>
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

function projectStatusLabel(status: Project["status"]) {
  return {
    creating: "创建中",
    ready: "就绪",
    building: "构建中",
    error: "异常",
    archived: "已归档",
  }[status];
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

function ExpandButton({
  expanded,
  count,
  expandedLabel,
  collapsedLabel,
  onClick,
}: {
  expanded: boolean;
  count: number;
  expandedLabel: string;
  collapsedLabel: string;
  onClick: () => void;
}) {
  const Icon = expanded ? ChevronUp : ChevronDown;
  const label = expanded ? expandedLabel : collapsedLabel;
  return (
    <button
      type="button"
      onClick={onClick}
      className="agenthub-expand-button mt-1 flex w-full items-center justify-center gap-1.5 rounded-xl px-2.5 py-2 text-xs transition"
      aria-expanded={expanded}
      aria-label={`${label} (${count})`}
    >
      <Icon size={13} className="agenthub-muted" aria-hidden="true" />
      <span>{label}</span>
      <span className="agenthub-expand-count">({count})</span>
    </button>
  );
}

function SidebarMiniSkeleton({ rows }: { rows: number }) {
  return (
    <div className="space-y-1.5 py-1" aria-label="正在加载侧栏数据">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="agenthub-skeleton flex items-center gap-3 rounded-2xl border px-2 py-2">
          <span className="h-8 w-8 shrink-0 animate-pulse rounded-full bg-[color:var(--ah-panel-muted)]" />
          <span className="min-w-0 flex-1 space-y-1.5">
            <span className="block h-2.5 w-2/3 animate-pulse rounded-full bg-[color:var(--ah-panel-muted)]" />
            <span className="block h-2 w-1/2 animate-pulse rounded-full bg-[color:var(--ah-card-soft)]" />
          </span>
        </div>
      ))}
    </div>
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
        danger ? "text-[color:var(--ah-danger)] hover:bg-[color:var(--ah-danger-soft)]" : "agenthub-nav-idle"
      }`}
    >
      {Icon && <Icon size={15} className="agenthub-muted shrink-0" />}
      {label}
    </button>
  );
}
