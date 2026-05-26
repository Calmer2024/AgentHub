import type { Agent } from "../types";

interface Props {
  agents: Agent[];
  selectedName: string;
  isLoading: boolean;
  error: string | null;
  onSelect: (name: string) => void;
  onRetry: () => void;
  onOpenSettings: () => void;
}

export function AgentSelector({ agents, selectedName, isLoading, error, onSelect, onRetry, onOpenSettings }: Props) {
  if (error) {
    return (
      <div className="px-4 pb-3">
        <div className="flex items-center justify-between px-3 py-2 bg-red-50 border border-red-200 rounded-xl">
          <span className="text-sm text-red-600">{error}</span>
          <button onClick={onRetry} className="text-sm text-red-600 hover:text-red-800 underline">
            重试
          </button>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="px-4 pb-3">
        <div className="flex items-center gap-2 px-3 py-2">
          <div className="w-5 h-5 border-2 border-blue-300 border-t-blue-600 rounded-full animate-spin" />
          <span className="text-sm text-gray-400">加载可用 Agent...</span>
        </div>
      </div>
    );
  }

  if (agents.length === 0) {
    return (
      <div className="px-4 pb-3">
        <div className="px-3 py-3 bg-gray-50 border border-gray-200 rounded-xl">
          <p className="text-sm text-gray-500 mb-2">暂无可用的 Agent</p>
          <button onClick={onRetry} className="text-sm text-blue-600 hover:text-blue-800 underline">
            刷新
          </button>
        </div>
      </div>
    );
  }

  const hasAvailable = agents.some((a) => a.isAvailable);

  if (!hasAvailable) {
    return (
      <div className="px-4 pb-3">
        <div className="px-3 py-3 bg-amber-50 border border-amber-200 rounded-xl text-sm">
          <p className="text-amber-800 font-medium mb-2">所有 Agent 均未配置 API Key</p>
          <ul className="text-amber-700 mb-3 space-y-0.5">
            {agents.map((a) => (
              <li key={a.name}>- {a.displayName}: {a.unavailableReason || "未配置"}</li>
            ))}
          </ul>
          <div className="flex gap-3">
            <button onClick={onOpenSettings} className="text-blue-600 hover:text-blue-800 underline">
              打开设置
            </button>
            <button onClick={onRetry} className="text-gray-500 hover:text-gray-700 underline">
              刷新
            </button>
          </div>
        </div>
      </div>
    );
  }

  const currentAvailable = agents.some((a) => a.name === selectedName && a.isAvailable);
  const displayValue = currentAvailable ? selectedName : agents.find((a) => a.isAvailable)?.name ?? "";

  return (
    <div className="px-4 pb-3">
      <label className="block text-xs text-gray-500 mb-1.5 px-1">选择 Agent</label>
      <select
        value={displayValue}
        onChange={(e) => onSelect(e.target.value)}
        className="w-full px-3 py-2 border border-gray-300 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        {agents.map((agent) => (
          <option
            key={agent.name}
            value={agent.name}
            disabled={!agent.isAvailable}
          >
            {agent.displayName}{agent.isAvailable ? "" : " (不可用)"}
          </option>
        ))}
      </select>
      {agents.some((a) => !a.isAvailable) && (
        <p className="text-xs text-gray-400 mt-1 px-1">
          不可用的 Agent 缺少 API Key 配置，点击
          <button onClick={onOpenSettings} className="text-blue-500 hover:text-blue-700 underline mx-0.5">
            设置
          </button>
          进行配置
        </p>
      )}
    </div>
  );
}
