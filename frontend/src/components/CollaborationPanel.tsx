import { useEffect, useState } from "react";
import { ArrowRight, ChevronDown, ChevronRight, Workflow } from "lucide-react";
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
  pending: "agenthub-status",
  running: "agenthub-status-info",
  completed: "agenthub-status-success",
  error: "agenthub-status-error",
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
    <section className="agenthub-card mx-6 my-3 overflow-hidden rounded-2xl border">
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        className="w-full min-h-12 px-4 py-3 flex items-center justify-between gap-3 text-left hover:bg-[color:var(--ah-accent-soft)]"
      >
        <div className="min-w-0">
          <div className="agenthub-strong flex items-center gap-2 truncate text-sm font-semibold">
            <Workflow size={15} className="agenthub-muted shrink-0" />
            <span className="truncate">编排器 · {title} · {tasks.length} 个智能体</span>
          </div>
          <div className="agenthub-muted text-xs mt-0.5">
            {isCompleted ? completedSummary ?? `${doneCount}/${tasks.length} 完成` : `${doneCount}/${tasks.length} 完成`}
          </div>
        </div>
        <span className="agenthub-icon-button rounded-full p-1" aria-hidden="true">
          {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
        </span>
      </button>

      {!collapsed && (
        <div className="overflow-x-auto border-t px-4 py-4" style={{ borderColor: "var(--ah-border)" }}>
          <div className="flex items-stretch gap-3 min-w-max">
            {visiblePhases.map((phase, index) => (
              <div key={phase.phase} className="flex items-center gap-3">
                <div className={`w-64 rounded-2xl border p-3 ${STATUS_STYLES[phase.status]}`}>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="text-xs font-semibold">阶段 {phase.phase}</span>
                    <span className="agenthub-status rounded-full px-2 py-0.5 text-[11px]">
                      {phase.mode === "parallel" ? "并行" : "串行"} · {STATUS_LABELS[phase.status]}
                    </span>
                  </div>
                  <div className="space-y-2">
                    {phase.tasks.map((task) => (
                      <div key={`${phase.phase}-${task.name}-${task.agent}`} className="agenthub-card rounded-xl border px-2 py-2 shadow-none">
                        <div className="flex items-center justify-between gap-2">
                          <span className="agenthub-strong truncate text-xs font-medium">@{task.agent}</span>
                          <span className="agenthub-muted shrink-0 text-[11px]">
                            {ROLE_LABELS[task.role] ?? task.role}
                          </span>
                        </div>
                        <div className="agenthub-muted mt-0.5 truncate text-[11px]">{task.name}</div>
                      </div>
                    ))}
                  </div>
                </div>
                {index < visiblePhases.length - 1 && (
                  <div className="agenthub-faint flex w-8 items-center justify-center" aria-hidden="true">
                    <ArrowRight size={17} />
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
