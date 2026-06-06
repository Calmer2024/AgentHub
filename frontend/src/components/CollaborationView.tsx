/** CollaborationView — 独立多 Agent 协作面板。

替换当前的并行多气泡模式，展示每个智能体的:
  - 角色标签 (planner/executor/reviewer/researcher/synthesizer/critic)
  - 思考/计划/工具调用过程
  - 实时状态指示
  - 最终合成统一结果气泡
*/

import { useState } from "react";
import {
  ArrowRight,
  Bot,
  ChevronDown,
  ChevronRight,
  DraftingCompass,
  Lightbulb,
  Microscope,
  Puzzle,
  Search,
  Zap,
  type LucideIcon,
} from "lucide-react";
import type { CollabTask, ChainStep } from "../types";

interface Props {
  intent: string | null;
  tasks: CollabTask[];
  chainSteps: ChainStep[];
  isCompleted: boolean;
  completedSummary: string | null;
  children?: React.ReactNode;  // 最终结果气泡由父组件渲染
}

const ROLE_LABELS: Record<string, string> = {
  planner: "规划者",
  executor: "执行者",
  reviewer: "审查者",
  researcher: "研究员",
  synthesizer: "综合者",
  critic: "批判者",
};

const ROLE_ICONS: Record<string, LucideIcon> = {
  planner: DraftingCompass,
  executor: Zap,
  reviewer: Search,
  researcher: Microscope,
  synthesizer: Puzzle,
  critic: Lightbulb,
};

const STATUS_CONFIG = {
  pending: { color: "bg-[color:var(--ah-faint)]", text: "agenthub-muted", label: "等待中" },
  running: { color: "bg-[color:var(--ah-text-strong)] animate-pulse", text: "agenthub-strong", label: "进行中" },
  completed: { color: "bg-[color:var(--ah-text-strong)]", text: "agenthub-strong", label: "已完成" },
  error: { color: "bg-[color:var(--ah-danger)]", text: "text-[color:var(--ah-danger)]", label: "失败" },
};

export function CollaborationView({
  intent, tasks, chainSteps, isCompleted, completedSummary, children,
}: Props) {
  const [collapsed, setCollapsed] = useState(false);

  const doneCount = tasks.filter((t) => t.status === "completed" || t.status === "error").length;
  const isChain = chainSteps.length > 0;

  // 将 chainSteps 状态映射到 tasks
  const getTaskStatus = (taskIndex: number): "pending" | "running" | "completed" | "error" => {
    const step = chainSteps.find((s) => s.step === taskIndex);
    if (!step) return tasks[taskIndex]?.status ?? "pending";
    if (step.status === "interrupted") return "error";
    if (step.status === "completed") return "completed";
    return "running";
  };

  const intentLabel = intent
    ? { code_gen: "代码生成", research: "调研分析", design_ui: "UI 设计", general_qa: "通用问答" }[intent] ?? intent
    : "协作中";

  return (
    <div className="agenthub-card mx-6 my-3 overflow-hidden rounded-2xl border">
      {/* 面板头部 */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-4 py-3 transition-colors text-left hover:bg-[color:var(--ah-accent-soft)]"
      >
        <div className="flex items-center gap-2">
          {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
          <span className="agenthub-strong text-xs font-semibold">
            {isChain ? "链式协作" : "协作任务"} · {intentLabel} · {tasks.length} 个智能体
          </span>
          <span className={`text-xs ${isCompleted ? "agenthub-strong" : "agenthub-muted"}`}>
            {isCompleted
              ? completedSummary ?? `${doneCount}/${tasks.length} 完成`
              : `${doneCount}/${tasks.length} 完成`}
          </span>
        </div>

        {/* 状态圆点条 */}
        <div className="flex gap-1">
          {tasks.map((t, i) => {
            const status = isChain ? getTaskStatus(i) : t.status;
            const config = STATUS_CONFIG[status];
            return (
              <span
                key={i}
                title={`${t.agent} — ${ROLE_LABELS[t.role] ?? t.role}`}
                className={`w-2 h-2 rounded-full ${config.color}`}
              />
            );
          })}
        </div>
      </button>

      {/* 展开内容 */}
      {!collapsed && (
        <div className="space-y-3 border-t px-4 py-3" style={{ borderColor: "var(--ah-border)" }}>
          {isChain && (
            <p className="agenthub-muted text-xs">
              链式执行顺序: {chainSteps.map((s, i) => (
                <span key={i}>
                  {i > 0 && <ArrowRight size={12} className="agenthub-faint mx-1 inline-block" />}
                  <span className="agenthub-strong font-medium">@{s.agent}</span>
                  <span className="agenthub-muted">({ROLE_LABELS[s.role] ?? s.role})</span>
                </span>
              ))}
            </p>
          )}

          {tasks.map((t, i) => {
            const status = isChain ? getTaskStatus(i) : t.status;
            const config = STATUS_CONFIG[status];
            const RoleIcon = ROLE_ICONS[t.role] ?? Bot;
            return (
              <div key={i} className="agenthub-soft flex items-start gap-3 rounded-xl border p-2">
                {/* 状态圆点 */}
                <span className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${config.color}`} />

                {/* 智能体信息 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <RoleIcon size={13} className="agenthub-muted shrink-0" />
                    <span className="agenthub-strong text-xs font-semibold">@{t.agent}</span>
                    <span className="agenthub-status rounded px-1.5 py-0.5 text-xs font-medium">
                      {ROLE_LABELS[t.role] ?? t.role}
                    </span>
                    <span className={`text-xs ${config.text}`}>{config.label}</span>
                  </div>
                  <p className="agenthub-muted text-xs">{t.name}</p>
                  {t.summary && (
                    <p className="agenthub-faint mt-0.5 max-w-md truncate text-xs">{t.summary}</p>
                  )}
                </div>
              </div>
            );
          })}

          {/* 最终结果 */}
          {isCompleted && children && (
            <div className="border-t pt-2" style={{ borderColor: "var(--ah-border)" }}>
              {children}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
