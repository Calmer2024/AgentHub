import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  Archive,
  Bell,
  BellOff,
  Bot,
  Check,
  ChevronDown,
  CirclePlus,
  Cloud,
  FolderOpen,
  HardDrive,
  MessageCircle,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  Search,
  SquarePen,
  Trash2,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";
import { fetchSessions } from "../api/client";
import type { AgentConfig, Project, Session } from "../types";
import { formatChinaDateTime } from "../utils/time";
import { AgentAvatar } from "./AgentAvatar";
import { FloatingMenu } from "./FloatingMenu";

export type ActivityPanel = "sessions" | "agents" | "projects";

const BUILT_IN_CLI_AGENT_ORDER: Partial<Record<AgentConfig["cliTool"], number>> = {
  claude_code: 0,
  codex: 1,
  opencode: 2,
};

const PINNED_PROJECTS_STORAGE_KEY = "agenthub.pinnedProjects";
const PROJECT_ORDER_STORAGE_KEY = "agenthub.projectOrder";

interface ActivityPanelContentProps {
  panel: ActivityPanel;
  project: Project | null;
  projects: Project[];
  currentProjectId: string | null;
  currentTeamId: string | null;
  sessions: Session[];
  currentSessionId: string | null;
  sessionsLoading: boolean;
  projectsLoading: boolean;
  creatingProject: boolean;
  agents: AgentConfig[];
  canCreateLocalProject: boolean;
  canCreateCloudProject: boolean;
  onSelectSession: (id: string) => void;
  onNewSession: (agentId?: string) => Promise<void> | void;
  onNewGroupSession: () => void;
  onDeleteSession: (id: string) => Promise<void> | void;
  onRenameSession: (id: string, title: string) => Promise<void> | void;
  onPinSession: (id: string, isPinned: boolean) => Promise<void> | void;
  onArchiveSession: (id: string, archived?: boolean) => Promise<void> | void;
  onMuteSession: (id: string, isMuted: boolean) => Promise<void> | void;
  onSelectProject: (id: string) => Promise<void> | void;
  onSelectProjectSession: (projectId: string, sessionId: string) => Promise<void> | void;
  onCreateBlankProject: () => Promise<void> | void;
  onCreateCloudProject: () => Promise<void> | void;
  onPickExistingFolder: () => Promise<void> | void;
  onArchiveProject: (id: string) => Promise<void> | void;
  onRenameProject: (id: string, name: string) => Promise<void> | void;
  onDeleteProject: (id: string, deleteFiles: boolean) => Promise<void> | void;
  onNewProjectSession: (projectId: string, agentId: string) => Promise<void> | void;
  onStartAgentChat: (agentId: string) => Promise<void> | void;
  onCreateAgent: () => void;
  onEditAgent: (agentId: string) => void;
  onDeleteAgent: (agentId: string) => Promise<void> | void;
}

export function ActivityPanelContent({
  panel,
  project,
  projects,
  currentProjectId,
  currentTeamId,
  sessions,
  currentSessionId,
  sessionsLoading,
  projectsLoading,
  creatingProject,
  agents,
  canCreateLocalProject,
  canCreateCloudProject,
  onSelectSession,
  onNewSession,
  onNewGroupSession,
  onDeleteSession,
  onRenameSession,
  onPinSession,
  onArchiveSession,
  onMuteSession,
  onSelectProject,
  onSelectProjectSession,
  onCreateBlankProject,
  onCreateCloudProject,
  onPickExistingFolder,
  onArchiveProject,
  onRenameProject,
  onDeleteProject,
  onNewProjectSession,
  onStartAgentChat,
  onCreateAgent,
  onEditAgent,
  onDeleteAgent,
}: ActivityPanelContentProps) {
  if (panel === "agents") {
    return (
      <AgentsActivityPanel
        agents={agents}
        onStartAgentChat={onStartAgentChat}
        onCreateAgent={onCreateAgent}
        onEditAgent={onEditAgent}
        onDeleteAgent={onDeleteAgent}
      />
    );
  }

  if (panel === "projects") {
    return (
      <ProjectsActivityPanel
        agents={agents}
        projects={projects}
        currentProjectId={currentProjectId}
        currentTeamId={currentTeamId}
        currentSessionId={currentSessionId}
        currentProjectSessions={sessions}
        loading={projectsLoading}
        creating={creatingProject}
        canCreateLocalProject={canCreateLocalProject}
        canCreateCloudProject={canCreateCloudProject}
        onSelectProject={onSelectProject}
        onSelectProjectSession={onSelectProjectSession}
        onCreateBlankProject={onCreateBlankProject}
        onCreateCloudProject={onCreateCloudProject}
        onPickExistingFolder={onPickExistingFolder}
        onArchiveProject={onArchiveProject}
        onRenameProject={onRenameProject}
        onDeleteProject={onDeleteProject}
        onNewProjectSession={onNewProjectSession}
        onDeleteSession={onDeleteSession}
        onRenameSession={onRenameSession}
      />
    );
  }

  return (
    <SessionsActivityPanel
      project={project}
      sessions={sessions}
      currentSessionId={currentSessionId}
      loading={sessionsLoading}
      agents={agents}
      onSelectSession={onSelectSession}
      onNewSession={onNewSession}
      onNewGroupSession={onNewGroupSession}
      onDeleteSession={onDeleteSession}
      onRenameSession={onRenameSession}
      onPinSession={onPinSession}
      onArchiveSession={onArchiveSession}
      onMuteSession={onMuteSession}
    />
  );
}

function SessionsActivityPanel({
  project,
  sessions,
  currentSessionId,
  loading,
  agents,
  onSelectSession,
  onNewSession,
  onNewGroupSession,
  onDeleteSession,
  onRenameSession,
  onPinSession,
  onArchiveSession,
  onMuteSession,
}: {
  project: Project | null;
  sessions: Session[];
  currentSessionId: string | null;
  loading: boolean;
  agents: AgentConfig[];
  onSelectSession: (id: string) => void;
  onNewSession: (agentId?: string) => Promise<void> | void;
  onNewGroupSession: () => void;
  onDeleteSession: (id: string) => Promise<void> | void;
  onRenameSession: (id: string, title: string) => Promise<void> | void;
  onPinSession: (id: string, isPinned: boolean) => Promise<void> | void;
  onArchiveSession: (id: string, archived?: boolean) => Promise<void> | void;
  onMuteSession: (id: string, isMuted: boolean) => Promise<void> | void;
}) {
  const [query, setQuery] = useState("");
  const [agentPickerOpen, setAgentPickerOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [archiveCollapsed, setArchiveCollapsed] = useState(true);
  const agentButtonRef = useRef<HTMLButtonElement | null>(null);
  const agentMenuRef = useRef<HTMLDivElement | null>(null);
  const agentById = useMemo(() => new Map(agents.map((agent) => [agent.id, agent])), [agents]);

  useEffect(() => {
    if (!agentPickerOpen) return;
    const close = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (agentMenuRef.current?.contains(target) || agentButtonRef.current?.contains(target)) return;
      setAgentPickerOpen(false);
    };
    window.addEventListener("pointerdown", close, true);
    return () => window.removeEventListener("pointerdown", close, true);
  }, [agentPickerOpen]);

  const grouped = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const visible = sessions.filter((session) => {
      if (!needle) return true;
      const agentName = session.mode === "group"
        ? "群聊"
        : agentById.get(session.agentConfigId ?? "")?.name ?? "私聊";
      return `${session.title} ${agentName}`.toLowerCase().includes(needle);
    });
    const active = sortSessionsByUpdatedAt(visible.filter((session) => !session.archivedAt));
    const archived = sortSessionsByUpdatedAt(visible.filter((session) => Boolean(session.archivedAt)));
    return {
      active,
      archived,
      archivedCount: sessions.filter((session) => Boolean(session.archivedAt)).length,
    };
  }, [agentById, query, sessions]);

  const createSession = async (agentId?: string) => {
    setCreating(true);
    try {
      await onNewSession(agentId);
      setAgentPickerOpen(false);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="agenthub-activity-content">
      <div className="agenthub-panel-actions agenthub-panel-actions-search">
        <SearchInput value={query} onChange={setQuery} placeholder="搜索对话" />
        <span className="agenthub-panel-inline-actions">
          <button
              ref={agentButtonRef}
              type="button"
              onClick={() => setAgentPickerOpen((open) => !open)}
              disabled={!project || agents.length === 0 || creating}
              className="agenthub-panel-top-action agenthub-panel-top-action-primary"
              aria-label="新建私聊"
              title="新建私聊"
            >
              {creating ? <span className="agenthub-mini-spinner" /> : <CirclePlus size={21} aria-hidden="true" />}
          </button>
          <button
              type="button"
              onClick={onNewGroupSession}
              disabled={!project}
              className="agenthub-panel-top-action"
              aria-label="新建群聊"
              title="新建群聊"
            >
              <Users size={20} aria-hidden="true" />
          </button>
        </span>
      </div>

      <FloatingMenu
        open={agentPickerOpen}
        anchorRef={agentButtonRef}
        menuRef={agentMenuRef}
        width={276}
        placement="bottom-end"
        ariaLabel="选择私聊 Agent"
      >
        <div className="agenthub-floating-section-title">选择 Agent</div>
        {agents.map((agent) => (
          <button
            key={agent.id}
            type="button"
            onClick={() => void createSession(agent.id)}
            className="agenthub-floating-row"
          >
            <AgentAvatar agent={agent} size="sm" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{agent.name}</span>
              <span className="agenthub-muted block truncate text-xs">{agent.executable || agent.cliTool}</span>
            </span>
          </button>
        ))}
      </FloatingMenu>
      <div className="agenthub-activity-scroll">
        {!project ? (
          <EmptyPanel icon={FolderOpen} title="选择项目" description="所有对话都会归属到项目工作区。" />
        ) : loading && sessions.length === 0 ? (
          <PanelSkeleton />
        ) : sessions.length === 0 ? (
          <EmptyPanel icon={MessageCircle} title="还没有对话" description="新建私聊或群聊后会显示在这里。" />
        ) : (
          <div className="agenthub-session-list">
            {grouped.active.map((session) => (
              <SessionActivityRow
                key={session.id}
                session={session}
                archived={false}
                active={currentSessionId === session.id}
                agents={agents}
                onSelectSession={onSelectSession}
                onDeleteSession={onDeleteSession}
                onRenameSession={onRenameSession}
                onPinSession={onPinSession}
                onArchiveSession={onArchiveSession}
                onMuteSession={onMuteSession}
              />
            ))}
            <SessionSection
              title={`归档对话 · ${grouped.archivedCount}`}
              sessions={grouped.archived}
              collapsed={archiveCollapsed}
              onToggle={() => setArchiveCollapsed((value) => !value)}
              currentSessionId={currentSessionId}
              agents={agents}
              archived
              onSelectSession={onSelectSession}
              onDeleteSession={onDeleteSession}
              onRenameSession={onRenameSession}
              onPinSession={onPinSession}
              onArchiveSession={onArchiveSession}
              onMuteSession={onMuteSession}
            />
          </div>
        )}
      </div>
    </div>
  );
}

function AgentsActivityPanel({
  agents,
  onStartAgentChat,
  onCreateAgent,
  onEditAgent,
  onDeleteAgent,
}: {
  agents: AgentConfig[];
  onStartAgentChat: (agentId: string) => Promise<void> | void;
  onCreateAgent: () => void;
  onEditAgent: (agentId: string) => void;
  onDeleteAgent: (agentId: string) => Promise<void> | void;
}) {
  const [query, setQuery] = useState("");
  const [menuOpen, setMenuOpen] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const buttonRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (menuRef.current?.contains(target)) return;
      if (buttonRefs.current[menuOpen]?.contains(target)) return;
      setMenuOpen(null);
      setDeleteConfirm(null);
    };
    window.addEventListener("pointerdown", close, true);
    return () => window.removeEventListener("pointerdown", close, true);
  }, [menuOpen]);

  const visibleAgents = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return agents
      .filter((agent) => agent.isActive)
      .filter((agent) => {
        if (!needle) return true;
        return `${agent.name} ${agent.cliTool} ${agent.description}`.toLowerCase().includes(needle);
      });
  }, [agents, query]);

  const groupedAgents = useMemo(() => {
    const builtIn = visibleAgents
      .filter(isBuiltInCliAgent)
      .sort((a, b) => builtInCliAgentRank(a) - builtInCliAgentRank(b));
    const custom = visibleAgents
      .filter((agent) => !isBuiltInCliAgent(agent))
      .sort((a, b) => a.name.localeCompare(b.name, "zh-CN"));
    return { builtIn, custom };
  }, [visibleAgents]);

  const activeMenuAgent = useMemo(
    () => visibleAgents.find((agent) => agent.id === menuOpen) ?? null,
    [menuOpen, visibleAgents],
  );

  const renderAgentRow = (agent: AgentConfig) => {
    const menuIsOpen = menuOpen === agent.id;
    return (
      <div key={agent.id} className="agenthub-activity-list-row group">
        <button
          type="button"
          onClick={() => void onStartAgentChat(agent.id)}
          className="agenthub-row-main"
        >
          <AgentAvatar agent={agent} size="md" />
          <span className="min-w-0 flex-1">
            <span className="agenthub-strong block truncate text-sm font-semibold">{agent.name}</span>
            <span className="agenthub-muted block truncate text-xs">
              {isBuiltInCliAgent(agent) ? agent.executable || agent.cliTool : agent.description || "未填写备注"}
            </span>
          </span>
        </button>
        <button
          ref={(node) => { buttonRefs.current[agent.id] = node; }}
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            setDeleteConfirm(null);
            setMenuOpen(menuIsOpen ? null : agent.id);
          }}
          className="agenthub-row-more"
          aria-label={`${agent.name} 操作`}
          title="更多"
        >
          <MoreHorizontal size={15} aria-hidden="true" />
        </button>
      </div>
    );
  };

  return (
    <div className="agenthub-activity-content">
      <div className="agenthub-panel-actions agenthub-panel-actions-search">
        <SearchInput value={query} onChange={setQuery} placeholder="搜索 Agent" />
        <span className="agenthub-panel-inline-actions">
          <button
            type="button"
            onClick={onCreateAgent}
            className="agenthub-panel-top-action agenthub-panel-top-action-primary"
            aria-label="添加 Agent"
            title="添加 Agent"
          >
            <CirclePlus size={21} aria-hidden="true" />
          </button>
        </span>
      </div>
      <FloatingMenu
        open={Boolean(activeMenuAgent)}
        anchorElement={activeMenuAgent ? buttonRefs.current[activeMenuAgent.id] : null}
        menuRef={menuRef}
        placement="bottom-end"
        ariaLabel={activeMenuAgent ? `${activeMenuAgent.name} 操作` : "Agent 操作"}
      >
        {activeMenuAgent && (
          <>
            <button type="button" onClick={() => { onEditAgent(activeMenuAgent.id); setMenuOpen(null); }} className="agenthub-floating-row">
              <Pencil size={14} aria-hidden="true" />
              编辑
            </button>
            <button
              type="button"
              onClick={() => {
                if (deleteConfirm !== activeMenuAgent.id) {
                  setDeleteConfirm(activeMenuAgent.id);
                  return;
                }
                void onDeleteAgent(activeMenuAgent.id);
                setMenuOpen(null);
                setDeleteConfirm(null);
              }}
              className={`agenthub-floating-row ${deleteConfirm === activeMenuAgent.id ? "agenthub-danger-row" : ""}`}
            >
              {deleteConfirm === activeMenuAgent.id ? <Check size={14} aria-hidden="true" /> : <Trash2 size={14} aria-hidden="true" />}
              {deleteConfirm === activeMenuAgent.id ? "确认" : "删除"}
            </button>
          </>
        )}
      </FloatingMenu>
      <div className="agenthub-activity-scroll agenthub-activity-scroll-no-bar">
        {visibleAgents.length === 0 ? (
          <EmptyPanel icon={Bot} title="暂无匹配 Agent" description="添加或启用 Agent 后会显示在这里。" />
        ) : (
          <>
            <AgentGroup title="内置 CLI" count={groupedAgents.builtIn.length}>
              {groupedAgents.builtIn.map(renderAgentRow)}
            </AgentGroup>
            <AgentGroup title="自定义 Agent" count={groupedAgents.custom.length}>
              {groupedAgents.custom.map(renderAgentRow)}
            </AgentGroup>
          </>
        )}
      </div>
    </div>
  );
}

function ProjectsActivityPanel({
  agents,
  projects,
  currentProjectId,
  currentTeamId,
  currentSessionId,
  currentProjectSessions,
  loading,
  creating,
  canCreateLocalProject,
  canCreateCloudProject,
  onSelectProject,
  onSelectProjectSession,
  onCreateBlankProject,
  onCreateCloudProject,
  onPickExistingFolder,
  onArchiveProject,
  onRenameProject,
  onDeleteProject,
  onNewProjectSession,
  onDeleteSession,
  onRenameSession,
}: {
  agents: AgentConfig[];
  projects: Project[];
  currentProjectId: string | null;
  currentTeamId: string | null;
  currentSessionId: string | null;
  currentProjectSessions: Session[];
  loading: boolean;
  creating: boolean;
  canCreateLocalProject: boolean;
  canCreateCloudProject: boolean;
  onSelectProject: (id: string) => Promise<void> | void;
  onSelectProjectSession: (projectId: string, sessionId: string) => Promise<void> | void;
  onCreateBlankProject: () => Promise<void> | void;
  onCreateCloudProject: () => Promise<void> | void;
  onPickExistingFolder: () => Promise<void> | void;
  onArchiveProject: (id: string) => Promise<void> | void;
  onRenameProject: (id: string, name: string) => Promise<void> | void;
  onDeleteProject: (id: string, deleteFiles: boolean) => Promise<void> | void;
  onNewProjectSession: (projectId: string, agentId: string) => Promise<void> | void;
  onDeleteSession: (id: string) => Promise<void> | void;
  onRenameSession: (id: string, title: string) => Promise<void> | void;
}) {
  const [query, setQuery] = useState("");
  const [createMenuOpen, setCreateMenuOpen] = useState(false);
  const [expandedProjectIds, setExpandedProjectIds] = useState<Set<string>>(() => new Set(currentProjectId ? [currentProjectId] : []));
  const [expandedSessionListIds, setExpandedSessionListIds] = useState<Set<string>>(() => new Set());
  const [sessionsByProject, setSessionsByProject] = useState<Record<string, Session[]>>({});
  const [loadingProjectIds, setLoadingProjectIds] = useState<Set<string>>(() => new Set());
  const [menuOpen, setMenuOpen] = useState<string | null>(null);
  const [newSessionProjectId, setNewSessionProjectId] = useState<string | null>(null);
  const [renamingProjectId, setRenamingProjectId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [pinnedProjectIds, setPinnedProjectIds] = useState<Set<string>>(() => readPinnedProjectIds());
  const [projectOrder, setProjectOrder] = useState<string[]>(() => readProjectOrder());
  const [draggingProjectId, setDraggingProjectId] = useState<string | null>(null);
  const [dragOverProjectId, setDragOverProjectId] = useState<string | null>(null);
  const createButtonRef = useRef<HTMLButtonElement | null>(null);
  const createMenuRef = useRef<HTMLDivElement | null>(null);
  const projectMenuRef = useRef<HTMLDivElement | null>(null);
  const agentPickerMenuRef = useRef<HTMLDivElement | null>(null);
  const projectMenuButtonRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const newSessionButtonRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const sessionsByProjectRef = useRef<Record<string, Session[]>>({});
  const requestedProjectSessionIds = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!currentProjectId) return;
    setSessionsByProject((value) => ({ ...value, [currentProjectId]: currentProjectSessions }));
    setExpandedProjectIds((value) => new Set(value).add(currentProjectId));
  }, [currentProjectId, currentProjectSessions]);

  useEffect(() => {
    writePinnedProjectIds(pinnedProjectIds);
  }, [pinnedProjectIds]);

  useEffect(() => {
    writeProjectOrder(projectOrder);
  }, [projectOrder]);

  useEffect(() => {
    sessionsByProjectRef.current = sessionsByProject;
  }, [sessionsByProject]);

  useEffect(() => {
    if (!createMenuOpen && !menuOpen && !newSessionProjectId) return;
    const close = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      const inCreate = createMenuRef.current?.contains(target) || createButtonRef.current?.contains(target);
      const inProjectMenu = projectMenuRef.current?.contains(target)
        || (menuOpen ? projectMenuButtonRefs.current[menuOpen]?.contains(target) : false);
      const inAgentPicker = agentPickerMenuRef.current?.contains(target)
        || (newSessionProjectId ? newSessionButtonRefs.current[newSessionProjectId]?.contains(target) : false);
      if (!inCreate) setCreateMenuOpen(false);
      if (!inProjectMenu) {
        setMenuOpen(null);
        setDeleteConfirm(null);
      }
      if (!inAgentPicker) setNewSessionProjectId(null);
    };
    window.addEventListener("pointerdown", close, true);
    return () => window.removeEventListener("pointerdown", close, true);
  }, [createMenuOpen, menuOpen, newSessionProjectId]);

  const visibleProjects = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const orderIndex = new Map(projectOrder.map((id, index) => [id, index]));
    return projects
      .filter((project) => project.status !== "archived")
      .filter((project) => projectInCurrentSpace(project, currentTeamId))
      .filter((project) => {
        if (!needle) return true;
        return `${project.name} ${project.workspacePath ?? ""}`.toLowerCase().includes(needle);
      })
      .sort((left, right) => {
        const leftOrder = orderIndex.get(left.id);
        const rightOrder = orderIndex.get(right.id);
        if (leftOrder !== undefined || rightOrder !== undefined) {
          if (leftOrder === undefined) return 1;
          if (rightOrder === undefined) return -1;
          if (leftOrder !== rightOrder) return leftOrder - rightOrder;
        }
        const pinnedDelta = Number(pinnedProjectIds.has(right.id)) - Number(pinnedProjectIds.has(left.id));
        if (pinnedDelta) return pinnedDelta;
        return Date.parse(right.createdAt || "") - Date.parse(left.createdAt || "");
      });
  }, [currentTeamId, pinnedProjectIds, projectOrder, projects, query]);

  const moveProject = useCallback((sourceId: string, targetId: string) => {
    if (sourceId === targetId) return;
    const visibleIds = visibleProjects.map((project) => project.id);
    const sourceIndex = visibleIds.indexOf(sourceId);
    const targetIndex = visibleIds.indexOf(targetId);
    if (sourceIndex < 0 || targetIndex < 0) return;
    const reordered = reorderProjectIds(visibleIds, sourceIndex, targetIndex);
    const visibleSet = new Set(visibleIds);
    setProjectOrder((current) => [...reordered, ...current.filter((id) => !visibleSet.has(id))]);
  }, [visibleProjects]);

  const moveProjectByOffset = useCallback((projectId: string, offset: -1 | 1) => {
    const currentIndex = visibleProjects.findIndex((project) => project.id === projectId);
    const target = visibleProjects[currentIndex + offset];
    if (currentIndex < 0 || !target) return;
    moveProject(projectId, target.id);
  }, [moveProject, visibleProjects]);

  const activeMenuProject = useMemo(
    () => visibleProjects.find((project) => project.id === menuOpen) ?? null,
    [menuOpen, visibleProjects],
  );
  const newSessionProject = useMemo(
    () => visibleProjects.find((project) => project.id === newSessionProjectId) ?? null,
    [newSessionProjectId, visibleProjects],
  );
  const availableAgents = useMemo(() => agents.filter((agent) => agent.isActive), [agents]);

  const loadProjectSessions = useCallback(async (projectId: string) => {
    setLoadingProjectIds((value) => new Set(value).add(projectId));
    try {
      const loaded = await fetchSessions(projectId, true);
      setSessionsByProject((value) => ({ ...value, [projectId]: loaded }));
    } catch {
      setSessionsByProject((value) => ({ ...value, [projectId]: [] }));
    } finally {
      setLoadingProjectIds((value) => {
        const next = new Set(value);
        next.delete(projectId);
        return next;
      });
    }
  }, []);

  useEffect(() => {
    visibleProjects.forEach((project) => {
      if (project.id === currentProjectId || sessionsByProjectRef.current[project.id]) return;
      if (requestedProjectSessionIds.current.has(project.id)) return;
      requestedProjectSessionIds.current.add(project.id);
      void loadProjectSessions(project.id);
    });
  }, [currentProjectId, loadProjectSessions, visibleProjects]);

  const commitRename = useCallback((projectId: string) => {
    const name = renameValue.trim();
    if (name) void onRenameProject(projectId, name);
    setRenamingProjectId(null);
  }, [onRenameProject, renameValue]);

  const updateProjectSession = useCallback((projectId: string, sessionId: string, update: (session: Session) => Session) => {
    setSessionsByProject((current) => ({
      ...current,
      [projectId]: (current[projectId] ?? []).map((session) => session.id === sessionId ? update(session) : session),
    }));
  }, []);

  const renameProjectSession = useCallback(async (projectId: string, sessionId: string, title: string) => {
    await onRenameSession(sessionId, title);
    updateProjectSession(projectId, sessionId, (session) => ({ ...session, title }));
  }, [onRenameSession, updateProjectSession]);

  const deleteProjectSession = useCallback(async (projectId: string, sessionId: string) => {
    await onDeleteSession(sessionId);
    setSessionsByProject((current) => ({
      ...current,
      [projectId]: (current[projectId] ?? []).filter((session) => session.id !== sessionId),
    }));
  }, [onDeleteSession]);

  return (
    <div className="agenthub-activity-content">
      <div className="agenthub-panel-actions agenthub-panel-actions-search">
        <SearchInput value={query} onChange={setQuery} placeholder="搜索项目" />
        <span className="agenthub-panel-inline-actions">
          <button
            ref={createButtonRef}
            type="button"
            onClick={() => setCreateMenuOpen((open) => !open)}
            disabled={creating}
            className="agenthub-project-panel-action"
            aria-label="新建项目"
            title="新建项目"
          >
            {creating ? <span className="agenthub-mini-spinner" /> : <CirclePlus size={21} aria-hidden="true" />}
          </button>
        </span>
      </div>
      <FloatingMenu
        open={createMenuOpen}
        anchorRef={createButtonRef}
        menuRef={createMenuRef}
        width={232}
        placement="bottom-end"
        ariaLabel="新建项目"
      >
        {canCreateLocalProject && (
          <>
            <button type="button" onClick={() => { void onCreateBlankProject(); setCreateMenuOpen(false); }} className="agenthub-floating-row">
              <FolderOpen size={14} aria-hidden="true" />
              新建本机项目
            </button>
            <button type="button" onClick={() => { void onPickExistingFolder(); setCreateMenuOpen(false); }} className="agenthub-floating-row">
              <HardDrive size={14} aria-hidden="true" />
              绑定已有文件夹
            </button>
          </>
        )}
        {canCreateCloudProject && (
          <button type="button" onClick={() => { void onCreateCloudProject(); setCreateMenuOpen(false); }} className="agenthub-floating-row">
            <Cloud size={14} aria-hidden="true" />
            新建云端项目
          </button>
        )}
      </FloatingMenu>
      <FloatingMenu
        open={Boolean(activeMenuProject)}
        anchorElement={activeMenuProject ? projectMenuButtonRefs.current[activeMenuProject.id] : null}
        menuRef={projectMenuRef}
        placement="bottom-end"
        ariaLabel={activeMenuProject ? `${activeMenuProject.name} 操作` : "项目操作"}
      >
        {activeMenuProject && (
          <>
            <button
              type="button"
              onClick={() => {
                setRenamingProjectId(activeMenuProject.id);
                setRenameValue(activeMenuProject.name);
                setMenuOpen(null);
              }}
              className="agenthub-floating-row"
            >
              <Pencil size={14} aria-hidden="true" />
              重命名
            </button>
            <button
              type="button"
              onClick={() => {
                setPinnedProjectIds((value) => {
                  const next = new Set(value);
                  if (next.has(activeMenuProject.id)) next.delete(activeMenuProject.id);
                  else next.add(activeMenuProject.id);
                  return next;
                });
                setMenuOpen(null);
              }}
              className="agenthub-floating-row"
            >
              {pinnedProjectIds.has(activeMenuProject.id) ? <PinOff size={14} aria-hidden="true" /> : <Pin size={14} aria-hidden="true" />}
              {pinnedProjectIds.has(activeMenuProject.id) ? "取消置顶" : "置顶"}
            </button>
            <button type="button" onClick={() => { void onArchiveProject(activeMenuProject.id); setMenuOpen(null); }} className="agenthub-floating-row">
              <Archive size={14} aria-hidden="true" />
              归档
            </button>
            <button
              type="button"
              onClick={() => {
                if (deleteConfirm !== activeMenuProject.id) {
                  setDeleteConfirm(activeMenuProject.id);
                  return;
                }
                void onDeleteProject(activeMenuProject.id, false);
                setMenuOpen(null);
                setDeleteConfirm(null);
              }}
              className={`agenthub-floating-row ${deleteConfirm === activeMenuProject.id ? "agenthub-danger-row" : ""}`}
            >
              {deleteConfirm === activeMenuProject.id ? <Check size={14} aria-hidden="true" /> : <Trash2 size={14} aria-hidden="true" />}
              {deleteConfirm === activeMenuProject.id ? "确认" : "删除"}
            </button>
          </>
        )}
      </FloatingMenu>
      <FloatingMenu
        open={Boolean(newSessionProject)}
        anchorElement={newSessionProject ? newSessionButtonRefs.current[newSessionProject.id] : null}
        menuRef={agentPickerMenuRef}
        width={264}
        placement="bottom-end"
        ariaLabel={newSessionProject ? `为 ${newSessionProject.name} 选择 Agent` : "选择 Agent"}
      >
        {newSessionProject && (
          <div className="agenthub-agent-picker-menu">
            <div className="agenthub-floating-section-label px-3 pb-1.5 pt-2 text-[11px] font-medium">选择 Agent 后新建对话</div>
            {availableAgents.length === 0 ? (
              <div className="agenthub-muted px-3 py-4 text-center text-xs">暂无可用 Agent</div>
            ) : availableAgents.map((agent) => (
              <button
                key={agent.id}
                type="button"
                className="agenthub-floating-row min-h-12"
                onClick={() => {
                  void onNewProjectSession(newSessionProject.id, agent.id);
                  setNewSessionProjectId(null);
                }}
              >
                <AgentAvatar agent={agent} size="sm" />
                <span className="min-w-0 flex-1 text-left">
                  <span className="agenthub-strong block truncate text-sm">{agent.name}</span>
                  <span className="agenthub-muted block truncate text-[11px]">{agent.description || "未填写备注"}</span>
                </span>
              </button>
            ))}
          </div>
        )}
      </FloatingMenu>
      <div className="agenthub-activity-scroll">
        {loading && projects.length === 0 ? (
          <PanelSkeleton />
        ) : visibleProjects.length === 0 ? (
          <EmptyPanel icon={FolderOpen} title="没有匹配项目" description="新建项目或切换空间后继续。" />
        ) : (
          <div className="agenthub-project-list">
            {visibleProjects.map((project) => {
              const projectSessions = sortSessionsByUpdatedAt(sessionsByProject[project.id] ?? []);
              const projectExpanded = expandedProjectIds.has(project.id);
              const showAllSessions = expandedSessionListIds.has(project.id);
              const visibleSessions = showAllSessions ? projectSessions : projectSessions.slice(0, 8);
              const hiddenSessionCount = Math.max(0, projectSessions.length - visibleSessions.length);
              const projectLoading = loadingProjectIds.has(project.id);
              const menuIsOpen = menuOpen === project.id;
              const pinned = pinnedProjectIds.has(project.id);
              return (
                <div
                  key={project.id}
                  className={`agenthub-project-group ${pinned ? "agenthub-project-group-pinned" : ""} ${draggingProjectId === project.id ? "agenthub-project-group-dragging" : ""} ${dragOverProjectId === project.id ? "agenthub-project-group-drop-target" : ""}`}
                  onDragEnter={(event) => {
                    event.preventDefault();
                    if (draggingProjectId && draggingProjectId !== project.id) setDragOverProjectId(project.id);
                  }}
                  onDragOver={(event) => {
                    event.preventDefault();
                    event.dataTransfer.dropEffect = "move";
                  }}
                  onDrop={(event) => {
                    event.preventDefault();
                    const sourceId = event.dataTransfer.getData("text/plain") || draggingProjectId;
                    if (sourceId) moveProject(sourceId, project.id);
                    setDraggingProjectId(null);
                    setDragOverProjectId(null);
                  }}
                >
                  <div
                    className="agenthub-project-row"
                    draggable={renamingProjectId !== project.id}
                    aria-label={`拖动 ${project.name} 调整顺序`}
                    aria-grabbed={draggingProjectId === project.id}
                    title="拖动项目条目调整顺序（Alt + ↑/↓）"
                    tabIndex={0}
                    onDragStart={(event) => {
                      event.dataTransfer.effectAllowed = "move";
                      event.dataTransfer.setData("text/plain", project.id);
                      setDraggingProjectId(project.id);
                    }}
                    onDragEnd={() => {
                      setDraggingProjectId(null);
                      setDragOverProjectId(null);
                    }}
                    onKeyDown={(event) => {
                      if (!event.altKey || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) return;
                      event.preventDefault();
                      moveProjectByOffset(project.id, event.key === "ArrowUp" ? -1 : 1);
                    }}
                  >
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        setExpandedProjectIds((value) => {
                          const next = new Set(value);
                          if (next.has(project.id)) next.delete(project.id);
                          else next.add(project.id);
                          return next;
                        });
                      }}
                      className="agenthub-project-toggle"
                      aria-label={`${projectExpanded ? "收起" : "展开"} ${project.name} 的对话`}
                      aria-expanded={projectExpanded}
                    >
                      <ChevronDown className={projectExpanded ? "" : "-rotate-90"} aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        void onSelectProject(project.id);
                      }}
                      className="agenthub-project-title-button"
                    >
                      <span className="agenthub-project-glyph">
                        <FolderOpen size={15} aria-hidden="true" />
                      </span>
                      <span className="min-w-0 flex-1">
                        {renamingProjectId === project.id ? (
                          <input
                            value={renameValue}
                            onChange={(event) => setRenameValue(event.target.value)}
                            onClick={(event) => event.stopPropagation()}
                            onBlur={() => commitRename(project.id)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter") commitRename(project.id);
                              if (event.key === "Escape") setRenamingProjectId(null);
                            }}
                            className="agenthub-inline-input"
                            autoFocus
                          />
                        ) : (
                          <span className="agenthub-strong block truncate text-sm font-normal">{project.name}</span>
                        )}
                      </span>
                    </button>
                    <button
                      ref={(node) => { projectMenuButtonRefs.current[project.id] = node; }}
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        setDeleteConfirm(null);
                        setMenuOpen(menuIsOpen ? null : project.id);
                      }}
                      className="agenthub-project-inline-action"
                      aria-label={`${project.name} 操作`}
                      title="更多"
                    >
                      <MoreHorizontal size={15} aria-hidden="true" />
                    </button>
                    <button
                      ref={(node) => { newSessionButtonRefs.current[project.id] = node; }}
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        setNewSessionProjectId((current) => current === project.id ? null : project.id);
                      }}
                      className="agenthub-project-inline-action"
                      aria-label={`在 ${project.name} 新建对话`}
                      title="新建对话"
                    >
                      <SquarePen size={14} aria-hidden="true" />
                    </button>
                  </div>
                  <div className={`agenthub-project-sessions ${projectExpanded ? "agenthub-project-sessions-open" : "agenthub-project-sessions-closed"}`}>
                    {projectExpanded && <div className="agenthub-project-sessions-inner">
                      {projectLoading ? (
                        <PanelSkeleton rows={3} compact />
                      ) : projectSessions.length === 0 ? (
                        <div className="agenthub-project-empty">暂无对话</div>
                      ) : (
                        <>
                          {visibleSessions.map((session) => (
                            <ProjectSessionRow
                              key={session.id}
                              project={project}
                              session={session}
                              active={currentSessionId === session.id}
                              onSelect={onSelectProjectSession}
                              onRename={renameProjectSession}
                              onDelete={deleteProjectSession}
                            />
                          ))}
                          {hiddenSessionCount > 0 && (
                            <button
                              type="button"
                              onClick={() => {
                                setExpandedSessionListIds((value) => {
                                  const next = new Set(value);
                                  next.add(project.id);
                                  return next;
                                });
                              }}
                              className="agenthub-project-session-more-row"
                            >
                              展开显示
                            </button>
                          )}
                        </>
                      )}
                    </div>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function ProjectSessionRow({
  project,
  session,
  active,
  onSelect,
  onRename,
  onDelete,
}: {
  project: Project;
  session: Session;
  active: boolean;
  onSelect: (projectId: string, sessionId: string) => Promise<void> | void;
  onRename: (projectId: string, sessionId: string, title: string) => Promise<void> | void;
  onDelete: (projectId: string, sessionId: string) => Promise<void> | void;
}) {
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState(session.title);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => setTitle(session.title), [session.title]);

  const commitRename = () => {
    const nextTitle = title.trim();
    if (nextTitle && nextTitle !== session.title) void onRename(project.id, session.id, nextTitle);
    else setTitle(session.title);
    setRenaming(false);
  };

  return (
    <div className={`agenthub-project-session-row ${active ? "agenthub-project-session-row-active" : ""}`}>
      {renaming ? (
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          onBlur={commitRename}
          onKeyDown={(event) => {
            if (event.key === "Enter") commitRename();
            if (event.key === "Escape") { setTitle(session.title); setRenaming(false); }
          }}
          className="agenthub-project-session-input"
          aria-label={`重命名对话 ${session.title}`}
          autoFocus
        />
      ) : (
        <button
          type="button"
          onClick={() => void onSelect(project.id, session.id)}
          className="agenthub-project-session-main"
          title={`${session.title} · ${project.name}`}
        >
          <span className="agenthub-project-session-title">{session.title}</span>
          {session.mode === "group" && <Users size={12} className="agenthub-project-session-kind" aria-hidden="true" />}
          <span className="agenthub-project-session-time">{formatRelativeTime(session.updatedAt)}</span>
        </button>
      )}
      <span className="agenthub-project-session-actions">
        <button type="button" onClick={() => setRenaming(true)} aria-label={`重命名 ${session.title}`} title="重命名">
          <Pencil size={12} aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={() => {
            if (!confirmDelete) { setConfirmDelete(true); return; }
            void onDelete(project.id, session.id);
          }}
          onBlur={() => setConfirmDelete(false)}
          className={confirmDelete ? "agenthub-project-session-delete-confirm" : ""}
          aria-label={`${confirmDelete ? "确认" : "删除"} ${session.title}`}
          title={confirmDelete ? "再次点击确认" : "删除"}
        >
          {confirmDelete ? <Check size={12} aria-hidden="true" /> : <Trash2 size={12} aria-hidden="true" />}
        </button>
      </span>
    </div>
  );
}

function SessionSection({
  title,
  sessions,
  collapsed,
  archived = false,
  currentSessionId,
  agents,
  onToggle,
  onSelectSession,
  onDeleteSession,
  onRenameSession,
  onPinSession,
  onArchiveSession,
  onMuteSession,
}: {
  title: string;
  sessions: Session[];
  collapsed: boolean;
  archived?: boolean;
  currentSessionId: string | null;
  agents: AgentConfig[];
  onToggle: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => Promise<void> | void;
  onRenameSession: (id: string, title: string) => Promise<void> | void;
  onPinSession: (id: string, isPinned: boolean) => Promise<void> | void;
  onArchiveSession: (id: string, archived?: boolean) => Promise<void> | void;
  onMuteSession: (id: string, isMuted: boolean) => Promise<void> | void;
}) {
  if (sessions.length === 0) return null;
  return (
    <section className="agenthub-panel-section">
      <button
        type="button"
        onClick={onToggle}
        className="agenthub-panel-section-header"
        aria-expanded={!collapsed}
      >
        <ChevronDown size={13} className={collapsed ? "-rotate-90" : ""} aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate text-left">{title}</span>
        <span>{sessions.length}</span>
      </button>
      <div className={`agenthub-collapse-body ${collapsed ? "agenthub-collapse-body-closed" : "agenthub-collapse-body-open"}`}>
        <div className="agenthub-collapse-body-inner">
          {sessions.map((session) => (
            <SessionActivityRow
              key={session.id}
              session={session}
              archived={archived}
              active={currentSessionId === session.id}
              agents={agents}
              onSelectSession={onSelectSession}
              onDeleteSession={onDeleteSession}
              onRenameSession={onRenameSession}
              onPinSession={onPinSession}
              onArchiveSession={onArchiveSession}
              onMuteSession={onMuteSession}
            />
          ))}
        </div>
      </div>
    </section>
  );
}

function SessionActivityRow({
  session,
  active,
  archived,
  agents,
  onSelectSession,
  onDeleteSession,
  onRenameSession,
  onPinSession,
  onArchiveSession,
  onMuteSession,
}: {
  session: Session;
  active: boolean;
  archived: boolean;
  agents: AgentConfig[];
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => Promise<void> | void;
  onRenameSession: (id: string, title: string) => Promise<void> | void;
  onPinSession: (id: string, isPinned: boolean) => Promise<void> | void;
  onArchiveSession: (id: string, archived?: boolean) => Promise<void> | void;
  onMuteSession: (id: string, isMuted: boolean) => Promise<void> | void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(session.title);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const agent = agents.find((item) => item.id === session.agentConfigId) ?? null;

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (menuRef.current?.contains(target) || menuButtonRef.current?.contains(target)) return;
      setMenuOpen(false);
      setDeleteConfirm(false);
    };
    window.addEventListener("pointerdown", close, true);
    return () => window.removeEventListener("pointerdown", close, true);
  }, [menuOpen]);

  const commitRename = () => {
    const title = renameValue.trim();
    if (title) void onRenameSession(session.id, title);
    setRenaming(false);
  };

  return (
    <div className={`agenthub-activity-list-row agenthub-session-row group ${active ? "agenthub-activity-list-row-active" : ""}`}>
      <button type="button" onClick={() => onSelectSession(session.id)} className="agenthub-row-main">
        {session.mode === "group"
          ? <AgentAvatar kind="group" name="群聊" size="md" />
          : <AgentAvatar agent={agent} name={agent?.name ?? "私聊"} size="md" />}
        <span className="agenthub-session-copy">
          {renaming ? (
            <input
              value={renameValue}
              onChange={(event) => setRenameValue(event.target.value)}
              onClick={(event) => event.stopPropagation()}
              onBlur={commitRename}
              onKeyDown={(event) => {
                if (event.key === "Enter") commitRename();
                if (event.key === "Escape") setRenaming(false);
              }}
              className="agenthub-inline-input"
              autoFocus
            />
          ) : (
            <span className="agenthub-session-title-line">
              <span className="agenthub-strong min-w-0 truncate text-sm font-semibold">{session.title}</span>
              <span className="agenthub-session-time">{formatRelativeTime(session.updatedAt)}</span>
            </span>
          )}
          <span className="agenthub-session-preview">
            {sessionPreviewText(session, agent, archived)}
          </span>
        </span>
        {Boolean(session.unreadCount) && (
          <span className="agenthub-unread-dot">{Math.min(session.unreadCount ?? 0, 99)}</span>
        )}
      </button>
      <button
        ref={menuButtonRef}
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          setDeleteConfirm(false);
          setMenuOpen((open) => !open);
        }}
        className="agenthub-row-more"
        aria-label={`${session.title} 操作`}
        title="更多"
      >
        <MoreHorizontal size={15} aria-hidden="true" />
      </button>
      <FloatingMenu
        open={menuOpen}
        anchorRef={menuButtonRef}
        menuRef={menuRef}
        placement="bottom-end"
        ariaLabel={`${session.title} 操作`}
      >
        {archived ? (
          <button type="button" onClick={() => { void onArchiveSession(session.id, false); setMenuOpen(false); }} className="agenthub-floating-row">
            <Archive size={14} aria-hidden="true" />
            恢复对话
          </button>
        ) : (
          <>
            <button type="button" onClick={() => { void onPinSession(session.id, !session.isPinned); setMenuOpen(false); }} className="agenthub-floating-row">
              {session.isPinned ? <PinOff size={14} aria-hidden="true" /> : <Pin size={14} aria-hidden="true" />}
              {session.isPinned ? "取消置顶" : "置顶"}
            </button>
            <button type="button" onClick={() => { void onMuteSession(session.id, !session.isMuted); setMenuOpen(false); }} className="agenthub-floating-row">
              {session.isMuted ? <Bell size={14} aria-hidden="true" /> : <BellOff size={14} aria-hidden="true" />}
              {session.isMuted ? "关闭免打扰" : "免打扰"}
            </button>
          </>
        )}
        <button type="button" onClick={() => { setRenaming(true); setRenameValue(session.title); setMenuOpen(false); }} className="agenthub-floating-row">
          <Pencil size={14} aria-hidden="true" />
          重命名
        </button>
        {!archived && (
          <button type="button" onClick={() => { void onArchiveSession(session.id, true); setMenuOpen(false); }} className="agenthub-floating-row">
            <Archive size={14} aria-hidden="true" />
            归档
          </button>
        )}
        <button
          type="button"
          onClick={() => {
            if (!deleteConfirm) {
              setDeleteConfirm(true);
              return;
            }
            void onDeleteSession(session.id);
            setMenuOpen(false);
            setDeleteConfirm(false);
          }}
          className={`agenthub-floating-row ${deleteConfirm ? "agenthub-danger-row" : ""}`}
        >
          {deleteConfirm ? <Check size={14} aria-hidden="true" /> : <Trash2 size={14} aria-hidden="true" />}
          {deleteConfirm ? "确认" : "删除"}
        </button>
      </FloatingMenu>
    </div>
  );
}

function AgentGroup({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: ReactNode;
}) {
  if (count === 0) return null;
  return (
    <section className="agenthub-agent-group">
      <div className="agenthub-agent-group-title">
        <span>{title}</span>
        <span>{count}</span>
      </div>
      <div className="agenthub-list-stack">{children}</div>
    </section>
  );
}

function SearchInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <label className="agenthub-panel-search">
      <Search size={14} aria-hidden="true" />
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
      />
      {value && (
        <button type="button" onClick={() => onChange("")} aria-label="清空搜索">
          <X size={13} aria-hidden="true" />
        </button>
      )}
    </label>
  );
}

function isBuiltInCliAgent(agent: AgentConfig) {
  return agent.isBuiltIn === true;
}

function builtInCliAgentRank(agent: AgentConfig) {
  return BUILT_IN_CLI_AGENT_ORDER[agent.cliTool] ?? Number.MAX_SAFE_INTEGER;
}

function sortSessionsByUpdatedAt(items: Session[]) {
  return [...items].sort((left, right) => (
    Date.parse(right.updatedAt || "") - Date.parse(left.updatedAt || "")
  ));
}

function readPinnedProjectIds() {
  if (typeof window === "undefined") return new Set<string>();
  try {
    const value = window.localStorage.getItem(PINNED_PROJECTS_STORAGE_KEY);
    const parsed = value ? JSON.parse(value) : [];
    if (!Array.isArray(parsed)) return new Set<string>();
    return new Set(parsed.filter((item): item is string => typeof item === "string"));
  } catch {
    return new Set<string>();
  }
}

function writePinnedProjectIds(ids: Set<string>) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(PINNED_PROJECTS_STORAGE_KEY, JSON.stringify([...ids]));
  } catch {
    // Best-effort preference persistence.
  }
}

function readProjectOrder() {
  if (typeof window === "undefined") return [];
  try {
    const value = window.localStorage.getItem(PROJECT_ORDER_STORAGE_KEY);
    const parsed = value ? JSON.parse(value) : [];
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function writeProjectOrder(ids: string[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(PROJECT_ORDER_STORAGE_KEY, JSON.stringify(ids));
  } catch {
    // Best-effort preference persistence.
  }
}

function reorderProjectIds(ids: string[], sourceIndex: number, targetIndex: number) {
  const next = [...ids];
  const [moved] = next.splice(sourceIndex, 1);
  if (!moved) return ids;
  next.splice(targetIndex, 0, moved);
  return next;
}

function projectInCurrentSpace(project: Project, teamId: string | null) {
  return teamId ? project.teamId === teamId : !project.teamId;
}

function sessionPreviewText(session: Session, agent: AgentConfig | null, archived = false) {
  if (archived) return "已归档";
  const latest = session.latestMessagePreview?.trim();
  if (latest) {
    const speaker = session.latestMessageRole === "user" ? "你：" : session.mode === "group" ? "" : "";
    return `${speaker}${latest}`;
  }
  if (session.mode === "group") return "群聊协作";
  const agentName = agent?.name?.trim();
  if (agentName && agentName !== session.title) {
    return agentName;
  }
  return session.title || "私聊";
}

function formatRelativeTime(value: string) {
  const time = new Date(value).getTime();
  if (!Number.isFinite(time)) return "";
  const diff = Math.max(0, Date.now() - time);
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  const week = 7 * day;
  if (diff < minute) return "刚刚";
  if (diff < hour) return `${Math.max(1, Math.floor(diff / minute))}分钟前`;
  if (diff < day) return `${Math.floor(diff / hour)}小时前`;
  if (diff < 14 * day) return `${Math.floor(diff / day)}天前`;
  if (diff < 9 * week) return `${Math.floor(diff / week)}周前`;
  return formatChinaDateTime(value, { month: "numeric", day: "numeric" });
}

function EmptyPanel({
  icon: Icon,
  title,
  description,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
}) {
  return (
    <div className="agenthub-panel-empty">
      <Icon size={34} strokeWidth={1.6} aria-hidden="true" />
      <p className="agenthub-strong mt-3 text-sm font-semibold">{title}</p>
      <p className="agenthub-muted mt-1 text-xs leading-5">{description}</p>
    </div>
  );
}

function PanelSkeleton({
  rows = 6,
  compact = false,
}: {
  rows?: number;
  compact?: boolean;
}) {
  return (
    <div className="agenthub-list-stack px-1 py-2" aria-label="正在加载">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className={`agenthub-panel-skeleton-row ${compact ? "agenthub-panel-skeleton-row-compact" : ""}`}>
          <span />
          <span>
            <i style={{ width: `${54 + (index % 3) * 10}%` }} />
            <i style={{ width: `${38 + (index % 4) * 11}%` }} />
          </span>
        </div>
      ))}
    </div>
  );
}
