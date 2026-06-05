import { useEffect, useState } from "react";
import { ArrowRight, ChevronDown, ChevronRight, Workflow } from "lucide-react";
import type { CollabTask, DAGPhase, DraftOrchestratorPlan } from "../types";

interface Props {
  intent: string | null;
  tasks: CollabTask[];
  phases: DAGPhase[];
  isCompleted: boolean;
  completedSummary: string | null;
  draftPlan?: DraftOrchestratorPlan | null;
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
  orchestrator_plan: "调度计划",
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
  intent, tasks, phases, isCompleted, completedSummary, draftPlan,
}: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const isDraftPlan = intent === "orchestrator_plan" || Boolean(draftPlan);
  const visiblePhases = phases.length > 0 ? phases : buildFallbackPhases(tasks);
  const doneCount = tasks.filter((t) => t.status === "completed" || t.status === "error").length;
  const title = intent ? INTENT_LABELS[intent] ?? intent : "协作任务";
  const planTaskCount = draftPlan?.normalizedPlan && Array.isArray(draftPlan.normalizedPlan.tasks)
    ? draftPlan.normalizedPlan.tasks.length
    : tasks.length;

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
          <div className="flex items-center gap-2 truncate text-sm font-semibold text-slate-900">
            <Workflow size={15} className="shrink-0 text-slate-500" />
            <span className="truncate">
              {isDraftPlan
                ? `Orchestrator · Draft Plan · ${planTaskCount} 任务`
                : `Orchestrator · ${title} · ${tasks.length} 任务`}
            </span>
          </div>
          <div className="text-xs text-slate-500 mt-0.5">
            {isDraftPlan
              ? completedSummary ?? "调度计划已生成，等待确认执行。"
              : isCompleted ? completedSummary ?? `${doneCount}/${tasks.length} 完成` : `${doneCount}/${tasks.length} 完成`}
          </div>
        </div>
        <span className="rounded-md border border-slate-200 p-1 text-slate-500" aria-hidden="true">
          {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
        </span>
      </button>

      {!collapsed && (
        <div className="border-t border-slate-100 px-4 py-4 overflow-x-auto">
          {draftPlan && (
            <div className={`mb-4 rounded-lg border px-3 py-3 text-xs ${
              draftPlan.ok ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-red-200 bg-red-50 text-red-800"
            }`}>
              <div className="font-semibold">
                {draftPlan.ok ? "调度计划校验通过" : "调度计划需要修正"}
              </div>
              {draftPlan.error && <div className="mt-1">{draftPlan.error}</div>}
              {draftPlan.validation?.errors.length ? (
                <div className="mt-2 space-y-1">
                  {draftPlan.validation.errors.map((error) => <div key={error}>错误：{error}</div>)}
                </div>
              ) : null}
              {draftPlan.validation?.warnings.length ? (
                <div className="mt-2 space-y-1 text-amber-700">
                  {draftPlan.validation.warnings.map((warning) => <div key={warning}>提醒：{warning}</div>)}
                </div>
              ) : null}
              {draftPlan.visualization?.mermaid && (
                <pre className="mt-3 max-h-40 overflow-auto rounded-md bg-white/70 p-2 font-mono text-[11px] leading-5 text-slate-700">
                  {draftPlan.visualization.mermaid}
                </pre>
              )}
            </div>
          )}
          {!isDraftPlan && (
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
                  <div className="flex w-8 items-center justify-center text-slate-300" aria-hidden="true">
                    <ArrowRight size={17} />
                  </div>
                )}
              </div>
            ))}
          </div>
          )}
        </div>
      )}
    </section>
  );
}
