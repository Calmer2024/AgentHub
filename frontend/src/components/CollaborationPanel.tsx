import { useEffect, useState } from "react";
import type { CollabTask, DAGPhase } from "../types";

interface Props {
  intent: string | null;
  tasks: CollabTask[];
  phases: DAGPhase[];
  isCompleted: boolean;
  completedSummary: string | null;
}

const ROLE_LABELS: Record<string, string> = {
  planner: "规划者",
  executor: "执行者",
  reviewer: "审查者",
  researcher: "研究员",
  synthesizer: "综合者",
  critic: "批判者",
};

const STATUS_LABELS = {
  pending: "等待",
  running: "运行中",
  completed: "完成",
  error: "异常",
};

const STATUS_STYLES = {
  pending: "border-gray-200 bg-gray-50 text-gray-500",
  running: "border-blue-300 bg-blue-50 text-blue-700",
  completed: "border-emerald-300 bg-emerald-50 text-emerald-700",
  error: "border-red-300 bg-red-50 text-red-700",
};

const INTENT_LABELS: Record<string, string> = {
  code_gen: "代码生成",
  research: "调研分析",
  design_ui: "UI 设计",
  general_qa: "通用问答",
};

function buildFallbackPhases(tasks: CollabTask[]): DAGPhase[] {
  if (tasks.length === 0) return [];
  return [{
    phase: 0,
    mode: tasks.length > 1 ? "parallel" : "serial",
    status: tasks.some((t) => t.status === "running") ? "running" : "pending",
    tasks,
  }];
}

export function CollaborationPanel({
  intent, tasks, phases, isCompleted, completedSummary,
}: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const visiblePhases = phases.length > 0 ? phases : buildFallbackPhases(tasks);
  const doneCount = tasks.filter((t) => t.status === "completed" || t.status === "error").length;
  const title = intent ? INTENT_LABELS[intent] ?? intent : "协作任务";

  useEffect(() => {
    if (!isCompleted) return;
    const timer = window.setTimeout(() => setCollapsed(true), 10000);
    return () => window.clearTimeout(timer);
  }, [isCompleted]);

  return (
    <section className="mx-6 my-3 border border-slate-200 rounded-lg bg-white">
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        className="w-full min-h-12 px-4 py-3 flex items-center justify-between gap-3 text-left hover:bg-slate-50"
      >
        <div className="min-w-0">
          <div className="text-sm font-semibold text-slate-900 truncate">
            Orchestrator · {title} · {tasks.length} Agent
          </div>
          <div className="text-xs text-slate-500 mt-0.5">
            {isCompleted ? completedSummary ?? `${doneCount}/${tasks.length} 完成` : `${doneCount}/${tasks.length} 完成`}
          </div>
        </div>
        <span className="text-xs text-slate-500 shrink-0">{collapsed ? "展开" : "收起"}</span>
      </button>

      {!collapsed && (
        <div className="border-t border-slate-100 px-4 py-4 overflow-x-auto">
          <div className="flex items-stretch gap-3 min-w-max">
            {visiblePhases.map((phase, index) => (
              <div key={phase.phase} className="flex items-center gap-3">
                <div className={`w-64 border rounded-lg p-3 ${STATUS_STYLES[phase.status]}`}>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="text-xs font-semibold">Phase {phase.phase}</span>
                    <span className="text-[11px] px-2 py-0.5 rounded-full bg-white/70">
                      {phase.mode === "parallel" ? "并行" : "串行"} · {STATUS_LABELS[phase.status]}
                    </span>
                  </div>
                  <div className="space-y-2">
                    {phase.tasks.map((task) => (
                      <div key={`${phase.phase}-${task.name}-${task.agent}`} className="bg-white rounded-md border border-white/70 px-2 py-2">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-medium text-slate-900 truncate">@{task.agent}</span>
                          <span className="text-[11px] text-slate-500 shrink-0">
                            {ROLE_LABELS[task.role] ?? task.role}
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-500 truncate mt-0.5">{task.name}</div>
                      </div>
                    ))}
                  </div>
                </div>
                {index < visiblePhases.length - 1 && (
                  <div className="w-8 h-px bg-slate-300 relative">
                    <span className="absolute right-0 -top-1 h-2 w-2 rotate-45 border-r border-t border-slate-300" />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
