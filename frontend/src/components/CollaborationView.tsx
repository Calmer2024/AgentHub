/** CollaborationView — 独立多 Agent 协作面板。

替换当前的并行多气泡模式，展示每个 Agent 的:
  - 角色标签 (planner/executor/reviewer/researcher/synthesizer/critic)
  - 思考/计划/工具调用过程
  - 实时状态指示
  - 最终合成统一结果气泡
*/

import { useState } from "react";
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

const ROLE_ICONS: Record<string, string> = {
  planner: "📐",
  executor: "⚡",
  reviewer: "🔍",
  researcher: "🔬",
  synthesizer: "🧩",
  critic: "💡",
};

const STATUS_CONFIG = {
  pending: { color: "bg-gray-300", text: "text-gray-400", label: "等待中" },
  running: { color: "bg-blue-500 animate-pulse", text: "text-blue-600", label: "进行中" },
  completed: { color: "bg-green-500", text: "text-green-600", label: "已完成" },
  error: { color: "bg-red-500", text: "text-red-600", label: "失败" },
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
    <div className="mx-6 my-3 border border-indigo-200 rounded-xl overflow-hidden bg-white shadow-sm">
      {/* 面板头部 */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-4 py-3 bg-indigo-50 hover:bg-indigo-100 transition-colors text-left"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm">{collapsed ? "▶" : "▼"}</span>
          <span className="text-xs font-semibold text-indigo-700">
            {isChain ? "链式协作" : "协作任务"} · {intentLabel} · {tasks.length} 个 Agent
          </span>
          <span className={`text-xs ${isCompleted ? "text-green-600" : "text-indigo-500"}`}>
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
        <div className="px-4 py-3 space-y-3 border-t border-indigo-100">
          {isChain && (
            <p className="text-xs text-gray-400">
              链式执行顺序: {chainSteps.map((s, i) => (
                <span key={i}>
                  {i > 0 && <span className="mx-1">→</span>}
                  <span className="font-medium text-gray-500">@{s.agent}</span>
                  <span className="text-gray-400">({ROLE_LABELS[s.role] ?? s.role})</span>
                </span>
              ))}
            </p>
          )}

          {tasks.map((t, i) => {
            const status = isChain ? getTaskStatus(i) : t.status;
            const config = STATUS_CONFIG[status];
            const roleIcon = ROLE_ICONS[t.role] ?? "🤖";
            return (
              <div key={i} className="flex items-start gap-3 p-2 rounded-lg bg-gray-50">
                {/* 状态圆点 */}
                <span className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${config.color}`} />

                {/* Agent 信息 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span className="text-xs">{roleIcon}</span>
                    <span className="text-xs font-semibold text-gray-800">@{t.agent}</span>
                    <span className="text-xs px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-600 font-medium">
                      {ROLE_LABELS[t.role] ?? t.role}
                    </span>
                    <span className={`text-xs ${config.text}`}>
                      — {config.label}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500">{t.name}</p>
                  {t.summary && (
                    <p className="text-xs text-gray-400 mt-0.5 truncate max-w-md">{t.summary}</p>
                  )}
                </div>
              </div>
            );
          })}

          {/* 最终结果 */}
          {isCompleted && children && (
            <div className="pt-2 border-t border-gray-100">
              {children}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
