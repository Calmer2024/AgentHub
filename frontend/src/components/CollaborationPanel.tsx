import { useEffect, useState } from "react";
import { ArrowRight, ChevronDown, ChevronRight, Workflow } from "lucide-react";
import type { CollabTask, DAGPhase, DraftOrchestratorPlan, RunRead, TaskRead } from "../types";
import { RuntimeControlStrip } from "./RuntimeControlStrip";

interface Props {
  intent: string | null;
  tasks: CollabTask[];
  phases: DAGPhase[];
  isCompleted: boolean;
  completedSummary: string | null;
  draftPlan?: DraftOrchestratorPlan | null;
  run?: RunRead | null;
  runtimeTasks?: TaskRead[];
  onCancelRun?: (runId: string) => void;
  cancellingRunId?: string | null;
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
  orchestrator_plan: "调度计划",
};

function buildFallbackPhases(tasks: CollabTask[]): DAGPhase[] {
  if (tasks.length === 0) return [];
  return [{
    phase: 0,
    mode: "serial",
    status: tasks.some((t) => t.status === "running") ? "running" : "pending",
    tasks,
  }];
}

export function CollaborationPanel({
  intent, tasks, phases, isCompleted, completedSummary, draftPlan,
  run = null, runtimeTasks = [], onCancelRun, cancellingRunId = null,
}: Props) {
  const [collapsed, setCollapsed] = useState(() => isCompleted);
  const isDraftPlan = intent === "orchestrator_plan" || Boolean(draftPlan);
  const visiblePhases = phases.length > 0 ? phases : buildFallbackPhases(tasks);
  const doneCount = tasks.filter((t) => t.status === "completed" || t.status === "error").length;
  const title = intent ? INTENT_LABELS[intent] ?? intent : "协作任务";
  const planTaskCount = draftPlan?.normalizedPlan && Array.isArray(draftPlan.normalizedPlan.tasks)
    ? draftPlan.normalizedPlan.tasks.length
    : tasks.length;

  useEffect(() => {
    if (isCompleted) setCollapsed(true);
  }, [isCompleted]);

  useEffect(() => {
    if (!isCompleted && (run || isDraftPlan)) setCollapsed(false);
  }, [isCompleted, isDraftPlan, run]);

  return (
    <section className="agenthub-card mx-6 my-2 overflow-hidden rounded-xl border">
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        className="flex min-h-10 w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-[color:var(--ah-accent-soft)]"
        aria-expanded={!collapsed}
      >
        <div className="min-w-0">
          <div className="agenthub-strong flex items-center gap-2 truncate text-xs font-semibold">
            <Workflow size={15} className="agenthub-muted shrink-0" />
            <span className="truncate">
              {isDraftPlan
                ? `编排器 · Draft Plan · ${planTaskCount} 个任务`
                : `编排器 · ${title} · ${tasks.length} 个智能体`}
            </span>
          </div>
          <div className="agenthub-muted mt-0.5 truncate text-[11px]">
            {isDraftPlan
              ? completedSummary ?? "调度计划已生成，等待确认执行。"
              : isCompleted ? completedSummary ?? `${doneCount}/${tasks.length} 完成` : `${doneCount}/${tasks.length} 完成`}
          </div>
        </div>
        <span className="agenthub-icon-button rounded-full p-1" aria-hidden="true">
          {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
        </span>
      </button>
      {run && onCancelRun && (
        <div className="border-t px-4 pb-3 pt-0" style={{ borderColor: "var(--ah-border)" }}>
          <RuntimeControlStrip
            run={run}
            tasks={runtimeTasks}
            onCancel={onCancelRun}
            cancelling={cancellingRunId === run.id}
          />
        </div>
      )}

      {!collapsed && (
        <div className="overflow-x-auto border-t px-4 py-4" style={{ borderColor: "var(--ah-border)" }}>
          {draftPlan && (
            <div className={`mb-4 rounded-2xl border px-3 py-3 text-xs ${
              draftPlan.ok ? "agenthub-status-success" : "agenthub-status-error"
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
                <div className="mt-2 space-y-1 text-[color:var(--ah-warning)]">
                  {draftPlan.validation.warnings.map((warning) => <div key={warning}>提醒：{warning}</div>)}
                </div>
              ) : null}
              {draftPlan.visualization?.mermaid && (
                <pre className="agenthub-code-block mt-3 max-h-40 overflow-auto rounded-md p-2 font-mono text-[11px] leading-5">
                  {draftPlan.visualization.mermaid}
                </pre>
              )}
            </div>
          )}
          {!isDraftPlan && (
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
          )}
        </div>
      )}
    </section>
  );
}
