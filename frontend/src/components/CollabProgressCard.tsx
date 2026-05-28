import { useState } from "react";

interface CollabTask {
  task: string;
  agentName: string;
  status: "pending" | "running" | "completed" | "error";
  summary?: string;
}

interface Props {
  title: string;
  tasks: CollabTask[];
  collapsed?: boolean;
}

export function CollabProgressCard({ title, tasks, collapsed: initialCollapsed = true }: Props) {
  const [collapsed, setCollapsed] = useState(initialCollapsed);

  const doneCount = tasks.filter((t) => t.status === "completed").length;
  const errorCount = tasks.filter((t) => t.status === "error").length;

  return (
    <div className="mx-6 mt-3 px-4 py-3 bg-indigo-50 border border-indigo-200 rounded-xl">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between text-left"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm">
            {collapsed ? "▶" : "▼"}
          </span>
          <span className="text-xs font-semibold text-indigo-700">{title}</span>
          <span className="text-xs text-indigo-500">
            {doneCount}/{tasks.length} 完成
            {errorCount > 0 && <span className="text-red-500 ml-1">({errorCount} 失败)</span>}
          </span>
        </div>
        {!collapsed && (
          <div className="flex gap-1">
            {tasks.map((t, i) => (
              <span
                key={i}
                className={`w-2 h-2 rounded-full ${
                  t.status === "completed" ? "bg-green-500" :
                  t.status === "error" ? "bg-red-500" :
                  t.status === "running" ? "bg-blue-500 animate-pulse" :
                  "bg-gray-300"
                }`}
              />
            ))}
          </div>
        )}
      </button>

      {!collapsed && (
        <div className="mt-3 space-y-2">
          {tasks.map((t, i) => (
            <div key={i} className="flex items-start gap-2 text-xs">
              <span className={`mt-0.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                t.status === "completed" ? "bg-green-500" :
                t.status === "error" ? "bg-red-500" :
                t.status === "running" ? "bg-blue-500" :
                "bg-gray-300"
              }`} />
              <div className="flex-1 min-w-0">
                <span className="font-medium text-gray-700">@{t.agentName}</span>
                <span className="text-gray-500 ml-1">— {t.task}</span>
                <span className={`ml-1 ${
                  t.status === "running" ? "text-blue-600" :
                  t.status === "completed" ? "text-green-600" :
                  t.status === "error" ? "text-red-600" :
                  "text-gray-400"
                }`}>
                  {t.status === "pending" && "等待中"}
                  {t.status === "running" && "执行中..."}
                  {t.status === "completed" && "完成"}
                  {t.status === "error" && "失败"}
                </span>
                {t.summary && (
                  <p className="text-gray-400 mt-0.5 truncate">{t.summary}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export type { CollabTask };
