import { useEffect, useRef, useState } from "react";
import type { AgentConfig, Project } from "../types";

interface Props {
  projects: Project[];
  currentProjectId: string | null;
  agents: AgentConfig[];
  activePanel: "sessions" | "agents" | "settings";
  creating: boolean;
  onSelectProject: (id: string) => void;
  onCreateBlankProject: () => Promise<void>;
  onPickExistingFolder: () => Promise<void>;
  onArchiveProject: (id: string) => Promise<void>;
  onOpenPanel: (panel: "sessions" | "agents" | "settings") => void;
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
  onOpenPanel,
}: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const activeAgents = agents.filter((agent) => agent.isActive).slice(0, 4);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [menuOpen]);

  const runMenuAction = async (action: () => Promise<void>) => {
    setMenuOpen(false);
    await action();
    onOpenPanel("sessions");
  };

  return (
    <aside className="w-full md:w-[260px] h-[34dvh] md:h-full bg-[#202123] text-[#ececf1] flex flex-col shrink-0 border-r border-white/[0.08]">
      <div className="px-3 py-3 space-y-1">
        <NavButton label="快速对话" onClick={() => onOpenPanel("sessions")} />
        <NavButton label="搜索" onClick={() => onOpenPanel("sessions")} />
        <NavButton label="插件" onClick={() => onOpenPanel("agents")} />
        <NavButton label="自动化" onClick={() => onOpenPanel("settings")} />
        <NavButton label="Codex 移动版" onClick={() => onOpenPanel("settings")} />
      </div>

      <div className="px-3 pt-2 pb-1 flex items-center justify-between text-sm text-[#8f8f98]">
        <span>项目</span>
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setMenuOpen((value) => !value)}
            disabled={creating}
            className="h-7 w-7 rounded-lg bg-white/[0.06] hover:bg-white/10 text-[#c9c9d1] disabled:opacity-50"
            title="创建项目"
          >
            +
          </button>
          {menuOpen && (
            <div className="absolute right-0 top-9 z-30 w-56 rounded-xl border border-white/10 bg-[#2b2b2f] p-1.5 shadow-2xl">
              <MenuItem
                label="新建空白文件夹"
                onClick={() => runMenuAction(onCreateBlankProject)}
              />
              <MenuItem
                label="选择现有文件夹"
                onClick={() => runMenuAction(onPickExistingFolder)}
              />
            </div>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2">
        {projects.length === 0 ? (
          <div className="px-2 py-8 text-sm text-[#74747d]">暂无项目</div>
        ) : projects.map((project) => {
          const selected = currentProjectId === project.id && activePanel === "sessions";
          return (
            <div key={project.id} className="group relative">
              <button
                type="button"
                onClick={() => { onSelectProject(project.id); onOpenPanel("sessions"); }}
                className={`w-full rounded-lg px-2.5 py-2.5 text-left transition-colors ${
                    selected ? "bg-white/10 text-white" : "text-[#d8d8df] hover:bg-white/[0.07]"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="text-[#a4a4ad]">▱</span>
                  <span className="min-w-0 flex-1 truncate text-sm">{project.name}</span>
                </div>
                <div className="mt-1 pl-5 text-xs text-[#74747d]">ready</div>
              </button>
              <button
                type="button"
                onClick={() => onArchiveProject(project.id)}
                className="absolute right-1 top-1.5 rounded-md px-1.5 py-1 text-xs text-[#8f8f98] opacity-0 hover:bg-red-500/15 hover:text-red-300 group-hover:opacity-100"
                title="归档项目"
              >
                ×
              </button>
            </div>
          );
        })}
      </div>

      <div className="px-3 py-3 space-y-1 border-t border-white/[0.08]">
        <NavButton
          label="Agent"
          active={activePanel === "agents"}
          onClick={() => onOpenPanel("agents")}
        />
        <NavButton
          label="设置"
          active={activePanel === "settings"}
          onClick={() => onOpenPanel("settings")}
        />
        {activeAgents.length === 0 && (
          <div className="px-2 pt-2 text-xs text-[#74747d]">暂无可用 Agent</div>
        )}
      </div>
    </aside>
  );
}

function NavButton({
  label,
  active = false,
  onClick,
}: {
  label: string;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-lg px-2.5 py-2 text-left text-sm transition-colors ${
        active ? "bg-white/10 text-white" : "text-[#d8d8df] hover:bg-white/[0.07]"
      }`}
    >
      {label}
    </button>
  );
}

function MenuItem({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full rounded-lg px-3 py-2 text-left text-sm text-[#f3f3f4] hover:bg-white/[0.08]"
    >
      {label}
    </button>
  );
}
