import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import {
  Archive,
  Bot,
  Check,
  ChevronDown,
  ChevronUp,
  Cloud,
  Copy,
  Moon,
  Folder,
  FolderOpen,
  HardDrive,
  MessageCircle,
  MoreHorizontal,
  Pencil,
  Plus,
  Settings,
  Sun,
  Trash2,
  UserPlus,
  Users,
  type LucideIcon,
} from "lucide-react";
import {
  addTeamMember,
  fetchTeamJoinCode,
  fetchTeamMembers,
  removeTeamMember,
  updateTeamMemberRole,
} from "../api/client";
import type { AgentConfig, CurrentUser, ProductEdition, Project, Team, TeamMember, TeamRole } from "../types";
import { AgentAvatar } from "./AgentAvatar";
import type { SidebarTab } from "../stores/sessionStore";
import { useThemeStore, type ThemeMode } from "../stores/themeStore";
import { GlobalModal } from "./GlobalModal";
import { MenuSelect } from "./MenuSelect";
import { UserAccountMenu } from "./UserAccountMenu";
import { WorkspaceSettingsPage } from "./WorkspaceSettingsPage";

interface Props {
  projects: Project[];
  currentProjectId: string | null;
  agents: AgentConfig[];
  activePanel: SidebarTab;
  currentUser: CurrentUser | null;
  teams: Team[];
  currentTeamId: string | null;
  creating: boolean;
  loading?: boolean;
  productEdition?: ProductEdition;
  onSelectProject: (id: string) => void;
  onSelectTeam: (id: string | null) => void;
  onCreateTeam: (name: string) => Promise<void>;
  onJoinTeam: (code: string) => Promise<void>;
  onUserUpdated?: () => Promise<void> | void;
  onRefreshProjects?: () => Promise<void> | void;
  onCreateBlankProject: (name?: string) => Promise<void>;
  onCreateCloudProject: (name: string, teamId?: string | null) => Promise<void>;
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

type DeleteConfirmTarget = { kind: "project" | "agent"; id: string };

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

const TEAM_ROLE_OPTIONS: Array<{ value: TeamRole; label: string }> = [
  { value: "owner", label: "owner" },
  { value: "admin", label: "admin" },
  { value: "member", label: "member" },
  { value: "viewer", label: "viewer" },
];

export function ProjectSidebar({
  projects,
  currentProjectId,
  agents,
  activePanel,
  currentUser,
  teams,
  currentTeamId,
  creating,
  loading = false,
  productEdition,
  onSelectProject,
  onSelectTeam,
  onCreateTeam,
  onJoinTeam,
  onUserUpdated,
  onRefreshProjects,
  onCreateBlankProject,
  onCreateCloudProject,
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
  const [createMode, setCreateMode] = useState<"local" | "cloud">("local");
  const [createTeamId, setCreateTeamId] = useState<string | null>(currentTeamId);
  const [renameTarget, setRenameTarget] = useState<Project | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [teamMenuOpen, setTeamMenuOpen] = useState(false);
  const [teamCreateOpen, setTeamCreateOpen] = useState(false);
  const [teamJoinOpen, setTeamJoinOpen] = useState(false);
  const [teamJoinCode, setTeamJoinCode] = useState("");
  const [teamJoining, setTeamJoining] = useState(false);
  const [teamManagementTarget, setTeamManagementTarget] = useState<Team | null>(null);
  const [teamName, setTeamName] = useState("");
  const [teamCreating, setTeamCreating] = useState(false);
  const [projectsExpanded, setProjectsExpanded] = useState(false);
  const [workspaceSettingsProject, setWorkspaceSettingsProject] = useState<Project | null>(null);
  const [deleteConfirmTarget, setDeleteConfirmTarget] = useState<DeleteConfirmTarget | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const agentMenuRef = useRef<HTMLDivElement>(null);
  const projectMenuRef = useRef<HTMLDivElement>(null);
  const teamMenuRef = useRef<HTMLDivElement>(null);
  const activeAgents = agents.filter((agent) => agent.isActive);
  const isLocalShell = productEdition === "local";
  const isSaasShell = productEdition === "saas";
  const canUseTeamSpaces = !isLocalShell;
  const canCreateLocalProject = !isSaasShell;
  const canCreateCloudProject = !isLocalShell;
  const modeProjectItems = productEdition
    ? projects.filter((project) => project.workspaceMode === (productEdition === "local" ? "local" : "cloud"))
    : projects;
  const visibleProjectItems = isSaasShell
    ? modeProjectItems.filter((project) => (
      currentTeamId ? project.teamId === currentTeamId : !project.teamId
    ))
    : modeProjectItems;
  const nativeCliAgents = activeAgents
    .filter(isNativeCliAgent)
    .sort((left, right) => nativeCliAgentRank(left) - nativeCliAgentRank(right));
  const customAgents = activeAgents.filter((agent) => !isNativeCliAgent(agent));
  const visibleProjects = projectsExpanded ? visibleProjectItems : visibleProjectItems.slice(0, 3);
  const theme = useThemeStore((state) => state.theme);
  const setTheme = useThemeStore((state) => state.setTheme);

  useEffect(() => {
    if (!menuOpen && !agentMenuOpen && !projectMenuOpen) return;
    const close = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!menuRef.current?.contains(target)) setMenuOpen(false);
      if (!agentMenuRef.current?.contains(target)) setAgentMenuOpen(null);
      if (!projectMenuRef.current?.contains(target)) setProjectMenuOpen(null);
      if (
        !menuRef.current?.contains(target) &&
        !agentMenuRef.current?.contains(target) &&
        !projectMenuRef.current?.contains(target)
      ) {
        setDeleteConfirmTarget(null);
      }
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [menuOpen, agentMenuOpen, projectMenuOpen]);

  useEffect(() => {
    setCreateTeamId(currentTeamId);
  }, [currentTeamId]);

  useEffect(() => {
    if (!teamMenuOpen) return;
    const close = (event: MouseEvent) => {
      if (!teamMenuRef.current?.contains(event.target as Node)) setTeamMenuOpen(false);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [teamMenuOpen]);

  const runCreateAction = async (action: () => Promise<void>) => {
    setMenuOpen(false);
    await action();
    onOpenPanel("sessions");
  };

  const openCreateProjectDialog = (mode: "local" | "cloud" = "local") => {
    setMenuOpen(false);
    setCreateName("新项目");
    if (mode === "cloud" && !canCreateCloudProject) setCreateMode("local");
    else if (mode === "local" && !canCreateLocalProject) setCreateMode("cloud");
    else setCreateMode(mode);
    setCreateTeamId(currentTeamId);
    setCreateModalOpen(true);
  };

  const submitCreateProject = async () => {
    const name = createName.trim();
    if (!name) return;
    if (createMode === "cloud" && !currentUser) return;
    setCreateModalOpen(false);
    if (createMode === "cloud") {
      await onCreateCloudProject(name, createTeamId);
    } else {
      await onCreateBlankProject(name);
    }
  };

  const submitCreateTeam = async () => {
    const name = teamName.trim();
    if (!name) return;
    setTeamCreating(true);
    try {
      await onCreateTeam(name);
      setTeamName("");
      setTeamCreateOpen(false);
      setTeamMenuOpen(false);
    } finally {
      setTeamCreating(false);
    }
  };

  const submitJoinTeam = async () => {
    const code = teamJoinCode.trim();
    if (!code) return;
    setTeamJoining(true);
    try {
      await onJoinTeam(code);
      setTeamJoinCode("");
      setTeamJoinOpen(false);
      setTeamMenuOpen(false);
    } finally {
      setTeamJoining(false);
    }
  };

  const submitProjectRename = async () => {
    if (!renameTarget) return;
    const name = renameValue.trim();
    setRenameTarget(null);
    if (!name || name === renameTarget.name) return;
    await onRenameProject(renameTarget.id, name);
  };

  const refreshWorkspaceProjects = async () => {
    await onRefreshProjects?.();
  };

  const selectTeamSpace = (teamId: string | null) => {
    onSelectTeam(teamId);
    setTeamMenuOpen(false);
    setProjectsExpanded(false);
    const nextProject = modeProjectItems.find((project) => (
      teamId ? project.teamId === teamId : !project.teamId
    ));
    if (nextProject && nextProject.id !== currentProjectId) {
      onSelectProject(nextProject.id);
      onOpenPanel("sessions");
    }
  };

  const isConfirmingDelete = (kind: DeleteConfirmTarget["kind"], id: string) => (
    deleteConfirmTarget?.kind === kind && deleteConfirmTarget.id === id
  );

  const requestDelete = async (
    target: DeleteConfirmTarget,
    action: () => Promise<void>,
  ) => {
    if (!isConfirmingDelete(target.kind, target.id)) {
      setDeleteConfirmTarget(target);
      return;
    }
    setDeleteBusy(true);
    try {
      await action();
      setDeleteConfirmTarget(null);
      setAgentMenuOpen(null);
      setProjectMenuOpen(null);
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
              {agent.version || agentStatusText(agent, isSaasShell)}
            </span>
          </button>
          <button
            type="button"
            onClick={() => {
              setDeleteConfirmTarget(null);
              setAgentMenuOpen((value) => (value === agent.id ? null : agent.id));
            }}
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
              setDeleteConfirmTarget(null);
              if (currentProjectId) void onStartAgentChat(agent.id);
            }}
          />
          <MenuItem
            icon={Settings}
            label="设置"
            onClick={() => {
              setAgentMenuOpen(null);
              setDeleteConfirmTarget(null);
              onEditAgent(agent.id);
            }}
          />
          <MenuItem
            icon={isConfirmingDelete("agent", agent.id) && !deleteBusy ? Check : Trash2}
            label={deleteBusy && isConfirmingDelete("agent", agent.id) ? "删除中" : isConfirmingDelete("agent", agent.id) ? "确认" : "删除"}
            danger={isConfirmingDelete("agent", agent.id)}
            disabled={deleteBusy}
            onClick={() => void requestDelete(
              { kind: "agent", id: agent.id },
              () => onDeleteAgent(agent.id),
            )}
          />
        </div>
      )}
    </div>
  );

  return (
    <aside className="agenthub-rail w-full lg:w-[min(22vw,260px)] xl:w-[260px] h-[30dvh] sm:h-[28dvh] lg:h-full flex flex-col shrink-0 border-r transition-colors duration-200">
      <div className="px-3 py-3 space-y-3">
        <UserAccountMenu currentUser={currentUser} teams={teams} onUserUpdated={onUserUpdated} />
        <ThemeToggle theme={theme} onChange={setTheme} />
        {canUseTeamSpaces && (
          <TeamSwitcher
            currentUser={currentUser}
            teams={teams}
            currentTeamId={currentTeamId}
            menuOpen={teamMenuOpen}
            menuRef={teamMenuRef}
            onToggle={() => setTeamMenuOpen((value) => !value)}
            onSelectTeam={selectTeamSpace}
            onOpenCreateTeam={() => {
              setTeamMenuOpen(false);
              setTeamName("");
              setTeamCreateOpen(true);
            }}
            onOpenJoinTeam={() => {
              setTeamMenuOpen(false);
              setTeamJoinCode("");
              setTeamJoinOpen(true);
            }}
            onOpenManageTeam={(team) => {
              setTeamMenuOpen(false);
              setTeamManagementTarget(team);
            }}
          />
        )}
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
            title={isSaasShell ? "添加云端智能体" : "添加命令行智能体"}
            disabled={false}
            onClick={onCreateAgent}
          />
        </div>
        <div
          className="agenthub-expand-scroll agenthub-friends-scroll space-y-1"
          aria-label="好友列表"
        >
          {loading && activeAgents.length === 0 ? (
            <SidebarMiniSkeleton rows={3} />
          ) : activeAgents.length === 0 ? (
            <div className="agenthub-faint px-2 py-2 text-xs">暂无可用智能体</div>
          ) : (
            <>
              {nativeCliAgents.length > 0 && (
                <AgentGroup label={isSaasShell ? "内置 Engine" : "原生 CLI"} count={nativeCliAgents.length}>
                  {nativeCliAgents.map(renderAgentItem)}
                </AgentGroup>
              )}
              {customAgents.length > 0 && (
                <AgentGroup
                  label="自定义 Agent"
                  count={customAgents.length}
                  className={nativeCliAgents.length > 0 ? "mt-2" : ""}
                >
                  {customAgents.map(renderAgentItem)}
                </AgentGroup>
              )}
            </>
          )}
        </div>
      </div>

      <div className="px-3 pt-2 pb-1">
        <div className="agenthub-muted mb-2 flex items-center justify-between text-sm">
          <span className="inline-flex items-center gap-2">
            <FolderOpen size={15} />
            {isLocalShell ? "本机项目" : isSaasShell ? "云端项目" : "项目"}
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
                {canCreateLocalProject && (
                  <MenuItem
                    icon={Plus}
                    label="新建空白项目"
                    onClick={() => openCreateProjectDialog("local")}
                  />
                )}
                {canCreateCloudProject && (
                  <MenuItem
                    icon={Cloud}
                    label="新建云端项目"
                    onClick={() => openCreateProjectDialog("cloud")}
                  />
                )}
                {canCreateLocalProject && (
                  <MenuItem
                    icon={Folder}
                    label="选择现有文件夹"
                    onClick={() => runCreateAction(onPickExistingFolder)}
                  />
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="agenthub-project-list-shell min-h-0 flex-1 px-2 pb-3">
        <div
          className={`agenthub-expand-scroll agenthub-expand-scroll-projects space-y-1 transition-all duration-200 ${projectsExpanded ? "agenthub-expand-scroll-open" : ""}`}
          aria-label="项目列表"
        >
          {loading && projects.length === 0 ? (
            <SidebarMiniSkeleton rows={3} />
          ) : visibleProjectItems.length === 0 ? (
            <div className="agenthub-faint px-2 py-8 text-sm">暂无项目</div>
          ) : visibleProjects.map((project) => {
            const selected = currentProjectId === project.id && activePanel === "sessions";
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
                      {project.workspaceMode === "cloud" ? <Cloud size={15} /> : <Folder size={15} />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{project.name}</span>
                      <span className="agenthub-faint mt-0.5 block truncate text-xs">
                        {projectSpaceLabel(project, teams)} · {projectStatusLabel(project.status)}
                      </span>
                    </span>
                  </div>
                </button>
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    setDeleteConfirmTarget(null);
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
                    {!isLocalShell && (
                      <MenuItem
                        icon={Settings}
                        label="工作区设置"
                        onClick={() => {
                          setWorkspaceSettingsProject(project);
                          setProjectMenuOpen(null);
                          setDeleteConfirmTarget(null);
                        }}
                      />
                    )}
                    <MenuItem
                      icon={Pencil}
                      label="重命名"
                      onClick={() => {
                        setRenameValue(project.name);
                        setRenameTarget(project);
                        setProjectMenuOpen(null);
                        setDeleteConfirmTarget(null);
                      }}
                    />
                    <MenuItem
                      icon={Archive}
                      label="归档"
                      onClick={() => {
                        setProjectMenuOpen(null);
                        setDeleteConfirmTarget(null);
                        void onArchiveProject(project.id);
                      }}
                    />
                    <MenuItem
                      icon={isConfirmingDelete("project", project.id) && !deleteBusy ? Check : Trash2}
                      label={deleteBusy && isConfirmingDelete("project", project.id)
                        ? "删除中"
                        : isConfirmingDelete("project", project.id)
                          ? "确认"
                          : project.workspaceMode === "cloud" ? "删除项目" : "删除目录"}
                      danger={isConfirmingDelete("project", project.id)}
                      disabled={deleteBusy}
                      onClick={() => void requestDelete(
                        { kind: "project", id: project.id },
                        () => onDeleteProject(project.id, true),
                      )}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
        {visibleProjectItems.length > 3 && (
          <ExpandButton
            expanded={projectsExpanded}
            count={visibleProjectItems.length}
            expandedLabel="收起项目"
            collapsedLabel="展开全部项目"
            onClick={() => setProjectsExpanded((value) => !value)}
          />
        )}
      </div>

      {createModalOpen && (
        <ProjectCreateDialog
          createMode={createMode}
          createName={createName}
          createTeamId={createTeamId}
          creating={creating}
          canCreateLocalProject={canCreateLocalProject}
          canCreateCloudProject={canCreateCloudProject}
          currentUser={currentUser}
          teams={teams}
          isLocalShell={isLocalShell}
          isSaasShell={isSaasShell}
          onModeChange={setCreateMode}
          onNameChange={setCreateName}
          onTeamChange={setCreateTeamId}
          onCancel={() => setCreateModalOpen(false)}
          onSubmit={() => void submitCreateProject()}
        />
      )}
      {teamCreateOpen && (
        <TeamCreateDialog
          teamName={teamName}
          busy={teamCreating}
          onNameChange={setTeamName}
          onCancel={() => setTeamCreateOpen(false)}
          onSubmit={() => void submitCreateTeam()}
        />
      )}
      {teamJoinOpen && (
        <TeamJoinDialog
          code={teamJoinCode}
          busy={teamJoining}
          onCodeChange={setTeamJoinCode}
          onCancel={() => setTeamJoinOpen(false)}
          onSubmit={() => void submitJoinTeam()}
        />
      )}
      {teamManagementTarget && (
        <TeamManagementDialog
          team={teamManagementTarget}
          onClose={() => setTeamManagementTarget(null)}
          onChanged={async () => {
            await onRefreshProjects?.();
            await onUserUpdated?.();
          }}
        />
      )}
      {workspaceSettingsProject && (
        <WorkspaceSettingsDialog
          project={workspaceSettingsProject}
          currentUser={currentUser}
          teams={teams}
          onRefreshProjects={refreshWorkspaceProjects}
          onClose={() => setWorkspaceSettingsProject(null)}
        />
      )}
      {renameTarget && (
        <ProjectRenameDialog
          project={renameTarget}
          value={renameValue}
          onValueChange={setRenameValue}
          onCancel={() => setRenameTarget(null)}
          onSubmit={() => void submitProjectRename()}
        />
      )}
    </aside>
  );
}

function isNativeCliAgent(agent: AgentConfig) {
  return NATIVE_CLI_AGENT_NAMES[agent.cliTool] === agent.name;
}

function nativeCliAgentRank(agent: AgentConfig) {
  return NATIVE_CLI_AGENT_ORDER[agent.cliTool] ?? Number.MAX_SAFE_INTEGER;
}

function agentStatusText(agent: AgentConfig, cloudShell: boolean) {
  if (agent.status === "ready") return "就绪";
  return cloudShell ? "待配置" : "未找到 executable";
}

function projectSpaceLabel(project: Project, teams: Team[]) {
  if (project.workspaceMode !== "cloud") return "本机";
  if (!project.teamId) return "个人空间";
  const team = teams.find((item) => item.id === project.teamId);
  return team ? `团队 · ${team.name}` : "团队项目";
}

async function copyTextToClipboard(text: string) {
  if (!text) return;
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

function ProjectCreateDialog({
  createMode,
  createName,
  createTeamId,
  creating,
  canCreateLocalProject,
  canCreateCloudProject,
  currentUser,
  teams,
  isLocalShell,
  isSaasShell,
  onModeChange,
  onNameChange,
  onTeamChange,
  onCancel,
  onSubmit,
}: {
  createMode: "local" | "cloud";
  createName: string;
  createTeamId: string | null;
  creating: boolean;
  canCreateLocalProject: boolean;
  canCreateCloudProject: boolean;
  currentUser: CurrentUser | null;
  teams: Team[];
  isLocalShell: boolean;
  isSaasShell: boolean;
  onModeChange: (mode: "local" | "cloud") => void;
  onNameChange: (value: string) => void;
  onTeamChange: (teamId: string | null) => void;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  const cloudDisabled = createMode === "cloud" && !currentUser;
  const teamOptions = [
    { value: "__personal__", label: "个人空间" },
    ...teams.map((team) => ({ value: team.id, label: team.name })),
  ];
  return (
    <GlobalModal
      title="新建项目"
      subtitle={isLocalShell ? "创建本机工作区项目" : isSaasShell ? "创建云端工作区项目" : "选择本机或云端工作区"}
      icon={<FolderOpen size={18} />}
      zIndexClass="z-[1200]"
      panelClassName="max-w-md"
      onClose={onCancel}
      footer={(
        <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onCancel}
            className="agenthub-icon-button h-10 rounded-full px-4 text-sm"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onSubmit}
            disabled={!createName.trim() || creating || cloudDisabled}
            className="agenthub-primary-button h-10 rounded-full px-5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50"
          >
            {createMode === "cloud" ? "创建云端项目" : "创建本机项目"}
          </button>
        </div>
      )}
    >
      <div className="space-y-5">
          {canCreateLocalProject && canCreateCloudProject && (
            <div className="grid max-w-md grid-cols-2 rounded-full border p-1" style={{ borderColor: "var(--ah-border)" }}>
              <button
                type="button"
                onClick={() => onModeChange("local")}
                data-active={createMode === "local"}
                className="agenthub-theme-choice inline-flex h-10 items-center justify-center gap-1.5 rounded-full text-sm font-medium transition"
              >
                <HardDrive size={15} />
                本机
              </button>
              <button
                type="button"
                onClick={() => onModeChange("cloud")}
                data-active={createMode === "cloud"}
                className="agenthub-theme-choice inline-flex h-10 items-center justify-center gap-1.5 rounded-full text-sm font-medium transition"
              >
                <Cloud size={15} />
                云端
              </button>
            </div>
          )}
          <label className="block space-y-2" htmlFor="blank-project-name">
            <span className="agenthub-muted text-xs font-medium">项目名称</span>
            <input
              id="blank-project-name"
              value={createName}
              onChange={(event) => onNameChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") onSubmit();
              }}
              className="agenthub-composer agenthub-textarea h-12 w-full rounded-2xl border px-4 text-base outline-none transition focus:ring-2 focus:ring-[color:var(--ah-accent-soft)]"
              autoFocus
            />
          </label>
          {createMode === "cloud" && (
            <div className="max-w-xl space-y-2">
              <span className="agenthub-muted block text-xs font-medium">团队空间</span>
              <MenuSelect
                value={createTeamId ?? "__personal__"}
                options={teamOptions}
                onChange={(value) => onTeamChange(value === "__personal__" ? null : value)}
                ariaLabel="团队空间"
                className="h-11"
              />
              {!currentUser && (
                <p className="text-xs text-[color:var(--ah-danger)]">云端登录态未就绪</p>
              )}
            </div>
          )}
      </div>
    </GlobalModal>
  );
}

function TeamCreateDialog({
  teamName,
  busy,
  onNameChange,
  onCancel,
  onSubmit,
}: {
  teamName: string;
  busy: boolean;
  onNameChange: (value: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  return (
    <GlobalModal
      title="创建团队"
      subtitle="团队项目会使用云端 workspace 与协作权限"
      icon={<Users size={18} />}
      zIndexClass="z-[1200]"
      panelClassName="max-w-sm"
      onClose={onCancel}
      closeDisabled={busy}
      footer={(
        <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="agenthub-icon-button h-10 rounded-full px-4 text-sm disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onSubmit}
            disabled={!teamName.trim() || busy}
            className="agenthub-primary-button h-10 rounded-full px-5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
          >
            创建团队
          </button>
        </div>
      )}
    >
      <label className="block space-y-2" htmlFor="team-name-input">
        <span className="agenthub-muted text-xs font-medium">团队名称</span>
        <input
          id="team-name-input"
          value={teamName}
          onChange={(event) => onNameChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") onSubmit();
          }}
          className="agenthub-composer agenthub-textarea h-11 w-full rounded-2xl border px-3 text-sm outline-none"
          placeholder="团队名称"
          autoFocus
        />
      </label>
    </GlobalModal>
  );
}

function TeamJoinDialog({
  code,
  busy,
  onCodeChange,
  onCancel,
  onSubmit,
}: {
  code: string;
  busy: boolean;
  onCodeChange: (value: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  return (
    <GlobalModal
      title="加入团队"
      subtitle="输入团队管理员提供的加入码"
      icon={<UserPlus size={18} />}
      zIndexClass="z-[1200]"
      panelClassName="max-w-sm"
      onClose={onCancel}
      closeDisabled={busy}
      footer={(
        <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="agenthub-icon-button h-10 rounded-full px-4 text-sm disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onSubmit}
            disabled={!code.trim() || busy}
            className="agenthub-primary-button h-10 rounded-full px-5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
          >
            加入团队
          </button>
        </div>
      )}
    >
      <label className="block space-y-2" htmlFor="team-join-code-input">
        <span className="agenthub-muted text-xs font-medium">团队加入码</span>
        <input
          id="team-join-code-input"
          value={code}
          onChange={(event) => onCodeChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") onSubmit();
          }}
          className="agenthub-composer agenthub-textarea h-11 w-full rounded-2xl border px-3 text-sm outline-none"
          placeholder="粘贴团队加入码"
          autoFocus
        />
      </label>
    </GlobalModal>
  );
}

function TeamManagementDialog({
  team,
  onClose,
  onChanged,
}: {
  team: Team;
  onClose: () => void;
  onChanged: () => Promise<void> | void;
}) {
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [joinCode, setJoinCode] = useState("");
  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole, setMemberRole] = useState<TeamRole>("member");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canManageOwners = team.role === "owner";
  const canAdmin = team.role === "owner" || team.role === "admin";
  const addRoleOptions = TEAM_ROLE_OPTIONS.filter((option) => option.value !== "owner" || canManageOwners);

  const load = async () => {
    setError(null);
    try {
      const [loadedMembers, code] = await Promise.all([
        fetchTeamMembers(team.id),
        canAdmin ? fetchTeamJoinCode(team.id) : Promise.resolve(null),
      ]);
      setMembers(loadedMembers);
      if (code) setJoinCode(code.code);
    } catch (err) {
      setError(err instanceof Error ? err.message : "团队信息加载失败");
    }
  };

  useEffect(() => {
    void load();
  }, [team.id]);

  const run = async (key: string, action: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    try {
      await action();
      await load();
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setBusy(null);
    }
  };

  return (
    <GlobalModal
      title="团队管理"
      subtitle={`${team.name} · ${team.role}`}
      icon={<Users size={18} />}
      zIndexClass="z-[1250]"
      panelClassName="max-w-2xl"
      onClose={onClose}
    >
      <div className="space-y-5">
        {error && (
          <div className="rounded-lg border border-[color:var(--ah-danger)] bg-[color:var(--ah-danger-soft)] px-3 py-2 text-sm text-[color:var(--ah-danger)]">
            {error}
          </div>
        )}
        {canAdmin && (
          <section className="space-y-2">
            <h3 className="agenthub-strong text-sm font-semibold">加入码</h3>
            <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_40px]">
              <input
                value={joinCode}
                readOnly
                className="agenthub-composer h-10 min-w-0 rounded-lg border px-3 text-sm outline-none"
                aria-label="团队加入码"
              />
              <IconAction
                title="复制加入码"
                disabled={!joinCode}
                icon={Copy}
                onClick={() => void copyTextToClipboard(joinCode)}
              />
            </div>
          </section>
        )}
        {canAdmin && (
          <section className="space-y-2">
            <h3 className="agenthub-strong text-sm font-semibold">添加成员</h3>
            <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_128px_40px]">
              <input
                value={memberEmail}
                onChange={(event) => setMemberEmail(event.target.value)}
                className="agenthub-composer h-10 min-w-0 rounded-lg border px-3 text-sm outline-none"
                placeholder="member@example.com"
                aria-label="团队成员邮箱"
              />
              <MenuSelect
                value={memberRole}
                options={addRoleOptions}
                onChange={setMemberRole}
                ariaLabel="团队成员角色"
                className="h-10"
              />
              <IconAction
                title="添加团队成员"
                disabled={Boolean(busy) || !memberEmail.trim()}
                icon={Plus}
                onClick={() => void run("add-member", async () => {
                  await addTeamMember(team.id, memberEmail, memberRole);
                  setMemberEmail("");
                })}
              />
            </div>
          </section>
        )}
        <section className="space-y-2">
          <h3 className="agenthub-strong text-sm font-semibold">成员</h3>
          <div className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
            {members.length === 0 ? (
              <p className="agenthub-faint rounded-lg border px-3 py-3 text-sm" style={{ borderColor: "var(--ah-border)" }}>
                暂无成员
              </p>
            ) : members.map((member) => (
              <div key={member.id} className="agenthub-nav-idle grid items-center gap-2 rounded-lg border px-3 py-2 text-sm md:grid-cols-[minmax(0,1fr)_128px_40px]">
                <span className="min-w-0">
                  <span className="agenthub-strong block truncate">{member.displayName || member.email}</span>
                  <span className="agenthub-faint block truncate text-xs">{member.email}</span>
                </span>
                <MenuSelect
                  value={member.role}
                  options={TEAM_ROLE_OPTIONS.filter((option) => (
                    option.value !== "owner" || canManageOwners || member.role === "owner"
                  ))}
                  onChange={(role) => void run(`role-${member.id}`, async () => {
                    await updateTeamMemberRole(team.id, member.id, role);
                  })}
                  disabled={!canAdmin || Boolean(busy)}
                  ariaLabel={`团队成员角色 ${member.email}`}
                  className="h-9"
                />
                <IconAction
                  title={`移除团队成员 ${member.email}`}
                  disabled={!canAdmin || Boolean(busy)}
                  icon={Trash2}
                  onClick={() => void run(`remove-${member.id}`, async () => {
                    await removeTeamMember(team.id, member.id);
                  })}
                />
              </div>
            ))}
          </div>
        </section>
      </div>
    </GlobalModal>
  );
}

function ProjectRenameDialog({
  project,
  value,
  onValueChange,
  onCancel,
  onSubmit,
}: {
  project: Project;
  value: string;
  onValueChange: (value: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  return (
    <GlobalModal
      title="重命名项目"
      subtitle={project.workspaceMode === "cloud" ? "更新云端项目显示名称" : "更新本机项目显示名称"}
      icon={<Pencil size={18} />}
      zIndexClass="z-[1200]"
      panelClassName="max-w-sm"
      onClose={onCancel}
      footer={(
        <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onCancel}
            className="agenthub-icon-button h-10 rounded-full px-4 text-sm"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onSubmit}
            disabled={!value.trim() || value.trim() === project.name}
            className="agenthub-primary-button h-10 rounded-full px-5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
          >
            保存名称
          </button>
        </div>
      )}
    >
      <label className="block space-y-2" htmlFor="project-rename-input">
        <span className="agenthub-muted text-xs font-medium">项目名称</span>
        <input
          id="project-rename-input"
          value={value}
          onChange={(event) => onValueChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") onSubmit();
          }}
          className="agenthub-composer agenthub-textarea h-11 w-full rounded-2xl border px-3 text-sm outline-none"
          autoFocus
        />
      </label>
    </GlobalModal>
  );
}

function WorkspaceSettingsDialog({
  project,
  currentUser,
  teams,
  onRefreshProjects,
  onClose,
}: {
  project: Project;
  currentUser: CurrentUser | null;
  teams: Team[];
  onRefreshProjects: () => Promise<void>;
  onClose: () => void;
}) {
  return (
    <GlobalModal
      title="工作区设置"
      subtitle={project.workspaceMode === "cloud" ? "云端项目运行时、导入、快照与权限" : "当前项目工作区"}
      icon={<Settings size={18} />}
      zIndexClass="z-[1300]"
      panelClassName="max-w-5xl"
      bodyClassName="p-0"
      onClose={onClose}
    >
      <div className="flex h-[min(78dvh,760px)] min-h-[420px] flex-col">
        <WorkspaceSettingsPage
          project={project}
          currentUser={currentUser}
          teams={teams}
          onRefreshProjects={onRefreshProjects}
        />
      </div>
    </GlobalModal>
  );
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

function TeamSwitcher({
  currentUser,
  teams,
  currentTeamId,
  menuOpen,
  menuRef,
  onToggle,
  onSelectTeam,
  onOpenCreateTeam,
  onOpenJoinTeam,
  onOpenManageTeam,
}: {
  currentUser: CurrentUser | null;
  teams: Team[];
  currentTeamId: string | null;
  menuOpen: boolean;
  menuRef: RefObject<HTMLDivElement>;
  onToggle: () => void;
  onSelectTeam: (id: string | null) => void;
  onOpenCreateTeam: () => void;
  onOpenJoinTeam: () => void;
  onOpenManageTeam: (team: Team) => void;
}) {
  const activeTeam = teams.find((team) => team.id === currentTeamId) ?? null;
  const label = activeTeam?.name ?? "个人空间";
  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        onClick={onToggle}
        className="agenthub-nav-idle flex w-full items-center gap-2 rounded-2xl px-2.5 py-2 text-left text-sm transition"
        aria-label="团队空间"
      >
        <span className="agenthub-soft agenthub-muted flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-[11px]">
          {activeTeam ? activeTeam.name.slice(0, 1) : "个"}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate">{label}</span>
          <span className="agenthub-faint block truncate text-[11px]">
            {currentUser ? currentUser.email : "云端登录态加载中"}
          </span>
        </span>
        <ChevronDown size={14} className="agenthub-muted" />
      </button>
      {menuOpen && (
        <div className="agenthub-menu absolute left-0 top-12 z-50 w-60 rounded-2xl border p-2">
          <button
            type="button"
            onClick={() => onSelectTeam(null)}
            className={`flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left text-sm transition ${
              !currentTeamId ? "agenthub-nav-active" : "agenthub-nav-idle"
            }`}
          >
            <HardDrive size={14} className="agenthub-muted" />
            个人空间
          </button>
          <div className="max-h-40 space-y-1 overflow-y-auto">
            {teams.length === 0 ? (
              <div className="agenthub-faint px-2 py-2 text-xs">暂无团队</div>
            ) : teams.map((team) => (
              <button
                key={team.id}
                type="button"
                onClick={() => onSelectTeam(team.id)}
                className={`flex w-full items-center justify-between rounded-xl px-2.5 py-2 text-left text-sm transition ${
                  currentTeamId === team.id ? "agenthub-nav-active" : "agenthub-nav-idle"
                }`}
              >
                <span className="min-w-0 truncate">{team.name}</span>
                <span className="agenthub-faint shrink-0 text-[11px]">{team.role}</span>
              </button>
            ))}
          </div>
          {activeTeam && (
            <button
              type="button"
              onClick={() => onOpenManageTeam(activeTeam)}
              className="agenthub-nav-idle mt-2 flex w-full items-center gap-2 rounded-xl border px-2.5 py-2 text-left text-sm transition"
              style={{ borderColor: "var(--ah-border)" }}
            >
              <Settings size={14} className="agenthub-muted" />
              管理团队
            </button>
          )}
          <button
            type="button"
            onClick={onOpenJoinTeam}
            className="agenthub-nav-idle mt-2 flex w-full items-center gap-2 rounded-xl border px-2.5 py-2 text-left text-sm transition"
            style={{ borderColor: "var(--ah-border)" }}
          >
            <UserPlus size={14} className="agenthub-muted" />
            加入团队
          </button>
          <button
            type="button"
            onClick={onOpenCreateTeam}
            className="agenthub-nav-idle mt-2 flex w-full items-center gap-2 rounded-xl border px-2.5 py-2 text-left text-sm transition"
            style={{ borderColor: "var(--ah-border)" }}
          >
            <Plus size={14} className="agenthub-muted" />
            创建团队
          </button>
        </div>
      )}
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

function IconAction({
  icon: Icon,
  title,
  disabled,
  onClick,
}: {
  icon: LucideIcon;
  title: string;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="agenthub-icon-button inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full disabled:cursor-not-allowed disabled:opacity-50"
      title={title}
      aria-label={title}
    >
      <Icon size={16} />
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
  disabled = false,
  onClick,
}: {
  icon?: LucideIcon;
  label: string;
  danger?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm transition disabled:cursor-not-allowed disabled:opacity-50 ${
        danger ? "agenthub-confirm-danger hover:bg-[color:var(--ah-danger-soft)]" : "agenthub-nav-idle"
      }`}
    >
      {Icon && <Icon size={15} className={danger ? "shrink-0" : "agenthub-muted shrink-0"} />}
      {label}
    </button>
  );
}

