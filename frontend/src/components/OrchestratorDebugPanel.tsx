import { useEffect, useMemo, useRef, useState } from "react";
import {
  buildOrchestratorInput,
  configureBuiltinAgentsCodex,
  fetchOrchestratorExecution,
  parseOrchestratorOutput,
  seedDefaultAgents,
} from "../api/client";
import type {
  AgentConfig,
  BuildOrchestratorInputResult,
  OrchestratorExecution,
  OrchestratorExecutionTask,
  OrchestratorDebugAgent,
  OrchestratorPlanTask,
  ParseOrchestratorOutputResult,
} from "../types";

interface Props {
  agents: AgentConfig[];
  onAgentsChanged?: () => Promise<void> | void;
}

const SAMPLE = "我们要给公司开发一个基础的员工报销单管理系统，员工可以增删改查自己的报销单，财务可以进行批量审批和查看。";
const DEFAULT_AGENT_NAMES = [
  "项目Leader",
  "产品经理",
  "UX/UI设计师",
  "测试工程师",
  "前端工程师",
  "后端工程师",
  "数据库工程师",
  "系统架构师",
];

export function OrchestratorDebugPanel({ agents, onAgentsChanged }: Props) {
  const [content, setContent] = useState(SAMPLE);
  const [useMockAgents, setUseMockAgents] = useState(true);
  const [selectedAgentIds, setSelectedAgentIds] = useState<string[]>([]);
  const [bridgeInput, setBridgeInput] = useState<BuildOrchestratorInputResult | null>(null);
  const [rawOutput, setRawOutput] = useState("");
  const [parsed, setParsed] = useState<ParseOrchestratorOutputResult | null>(null);
  const [executionId, setExecutionId] = useState("");
  const [execution, setExecution] = useState<OrchestratorExecution | null>(null);
  const [loading, setLoading] = useState<"build" | "parse" | "seed" | "codex" | "execution" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [seedMessage, setSeedMessage] = useState<string | null>(null);

  const selectedNames = useMemo(() => {
    const byId = new Map(agents.map((a) => [a.id, a.name]));
    return selectedAgentIds.map((id) => byId.get(id) ?? id);
  }, [agents, selectedAgentIds]);

  const defaultAgentStatus = useMemo(() => {
    const names = new Set(agents.map((agent) => agent.name));
    const byName = new Map(agents.map((agent) => [agent.name, agent]));
    const existing = DEFAULT_AGENT_NAMES.filter((name) => names.has(name));
    const codexConfigured = DEFAULT_AGENT_NAMES.filter((name) => {
      const agent = byName.get(name);
      return agent?.cliTool === "codex" && agent.executable === "codex";
    });
    return {
      existing,
      codexConfigured,
      missing: DEFAULT_AGENT_NAMES.filter((name) => !names.has(name)),
      nonCodex: DEFAULT_AGENT_NAMES.filter((name) => {
        const agent = byName.get(name);
        return agent && (agent.cliTool !== "codex" || agent.executable !== "codex");
      }),
    };
  }, [agents]);

  const seedDefaults = async () => {
    setLoading("seed");
    setError(null);
    setSeedMessage(null);
    try {
      const seeded = await seedDefaultAgents();
      await onAgentsChanged?.();
      const names = new Set(seeded.map((agent) => agent.name));
      const count = DEFAULT_AGENT_NAMES.filter((name) => names.has(name)).length;
      setSeedMessage(`已补齐/更新默认 Agent 小队：${count}/${DEFAULT_AGENT_NAMES.length}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建默认 Agent 失败");
    } finally {
      setLoading(null);
    }
  };

  const configureCodexDefaults = async () => {
    setLoading("codex");
    setError(null);
    setSeedMessage(null);
    try {
      const configured = await configureBuiltinAgentsCodex();
      await onAgentsChanged?.();
      const byName = new Map(configured.map((agent) => [agent.name, agent]));
      const count = DEFAULT_AGENT_NAMES.filter((name) => {
        const agent = byName.get(name);
        return agent?.cliTool === "codex" && agent.executable === "codex";
      }).length;
      setSeedMessage(`已统一内置角色 Agent 为 Codex 引擎：${count}/${DEFAULT_AGENT_NAMES.length}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "统一配置 Codex 引擎失败");
    } finally {
      setLoading(null);
    }
  };

  const generateInput = async () => {
    setLoading("build");
    setError(null);
    setParsed(null);
    try {
      const result = await buildOrchestratorInput({
        content,
        agentIds: useMockAgents ? undefined : selectedAgentIds,
        useMockAgents,
      });
      setBridgeInput(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成调度器输入失败");
    } finally {
      setLoading(null);
    }
  };

  const parseOutput = async () => {
    if (!bridgeInput) return;
    setLoading("parse");
    setError(null);
    try {
      setParsed(await parseOrchestratorOutput({
        rawOutput,
        candidateAgents: bridgeInput.candidateAgents,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "解析调度器输出失败");
    } finally {
      setLoading(null);
    }
  };

  const refreshExecution = async (id: string, showLoading = false) => {
    if (!id.trim()) return null;
    if (showLoading) setLoading("execution");
    if (showLoading) setError(null);
    try {
      const result = await fetchOrchestratorExecution(id.trim());
      setExecution(result);
      return result;
    } catch (err) {
      setExecution(null);
      if (showLoading) setError(err instanceof Error ? err.message : "查询执行状态失败");
      return null;
    } finally {
      if (showLoading) setLoading(null);
    }
  };

  const lookupExecution = async () => {
    await refreshExecution(executionId, true);
  };

  useEffect(() => {
    if (!execution || !["pending", "running"].includes(execution.status)) return;
    const timer = window.setInterval(() => {
      void refreshExecution(execution.executionId);
    }, 600);
    return () => window.clearInterval(timer);
  }, [execution?.executionId, execution?.status]);

  const copyPrompt = async () => {
    if (!bridgeInput) return;
    await navigator.clipboard.writeText(bridgeInput.prompt);
  };

  const importOutputFile = async (file: File | null) => {
    if (!file) return;
    setError(null);
    setParsed(null);
    try {
      setRawOutput(await file.text());
    } catch {
      setError("读取 JSON 文件失败");
    }
  };

  const toggleAgent = (id: string) => {
    setSelectedAgentIds((current) => (
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id]
    ));
  };

  return (
    <div className="h-full overflow-y-auto bg-[#f7f7f2] text-[#1f2421]">
      <div className="border-b border-[#d8d8cc] bg-[#fbfbf7] px-6 py-5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#6f766d]">
          Manual Orchestrator Bridge
        </p>
        <h2 className="mt-1 text-2xl font-semibold text-[#151814]">调度器手动桥接</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-[#667064]">
          生成最终调度器输入，复制给本机 ClaudeCode，再把输出粘回来解析、校验并可视化。这里不调用真实 Agent，也不自动执行。
        </p>
      </div>

      <div className="grid gap-5 px-6 py-5 xl:grid-cols-[420px_minmax(0,1fr)]">
        <div className="space-y-4">
          <section className="space-y-3 border border-[#d8d8cc] bg-white p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-[#30362f]">默认 Agent 小队</h3>
                <p className="mt-1 text-xs leading-5 text-[#697166]">
                  一键创建/更新 Orchestrator、产品、设计、测试、前端、后端、数据库和架构 Agent。
                </p>
              </div>
              <span className="shrink-0 bg-[#eef0e8] px-2 py-1 text-[11px] font-semibold text-[#4f594f]">
                {defaultAgentStatus.existing.length}/{DEFAULT_AGENT_NAMES.length}
              </span>
            </div>
            <button
              type="button"
              onClick={seedDefaults}
              disabled={loading !== null}
              className="w-full border border-[#1f2421] bg-white px-4 py-2 text-sm font-semibold text-[#1f2421] transition hover:bg-[#eef0e8] disabled:cursor-not-allowed disabled:border-[#c9cbbf] disabled:text-[#9ca397]"
            >
              {loading === "seed" ? "创建中..." : "补齐/更新默认 Agent"}
            </button>
            <button
              type="button"
              onClick={configureCodexDefaults}
              disabled={loading !== null}
              className="w-full border border-[#49624a] bg-[#49624a] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#384438] disabled:cursor-not-allowed disabled:border-[#c9cbbf] disabled:bg-[#d8d8cc] disabled:text-[#7f857b]"
            >
              {loading === "codex" ? "配置中..." : "一键统一为 Codex 引擎"}
            </button>
            {defaultAgentStatus.missing.length > 0 ? (
              <p className="text-[11px] leading-5 text-amber-700">
                缺少：{defaultAgentStatus.missing.join("、")}
              </p>
            ) : (
              <p className="text-[11px] leading-5 text-green-700">默认小队已存在，可直接拉群测试调度。</p>
            )}
            {defaultAgentStatus.existing.length > 0 && (
              <p className="text-[11px] leading-5 text-[#697166]">
                Codex 配置：{defaultAgentStatus.codexConfigured.length}/{DEFAULT_AGENT_NAMES.length}
                {defaultAgentStatus.nonCodex.length > 0 ? `；未统一：${defaultAgentStatus.nonCodex.join("、")}` : "；已统一"}
              </p>
            )}
            {seedMessage && <p className="text-[11px] leading-5 text-[#49624a]">{seedMessage}</p>}
          </section>

          <section className="space-y-2 border border-[#d8d8cc] bg-white p-4">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-[#30362f]">用户需求</label>
              <button
                type="button"
                onClick={() => setContent(SAMPLE)}
                className="text-xs text-[#49624a] underline-offset-4 hover:underline"
              >
                填入示例
              </button>
            </div>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={7}
              className="w-full resize-none border border-[#c9cbbf] bg-[#fbfbf7] px-3 py-2 text-sm leading-6 outline-none transition focus:border-[#49624a] focus:ring-2 focus:ring-[#49624a]/15"
              placeholder="输入要交给调度器拆解的需求。"
            />
          </section>

          <section className="space-y-3 border border-[#d8d8cc] bg-white p-4">
            <label className="flex items-center justify-between gap-3 text-sm">
              <span>
                <span className="block font-semibold text-[#30362f]">Mock Agent 小队</span>
                <span className="text-xs text-[#697166]">内置典型角色，方便先排除真实 Agent 配置噪声。</span>
              </span>
              <input
                type="checkbox"
                checked={useMockAgents}
                onChange={(e) => setUseMockAgents(e.target.checked)}
                className="h-4 w-4 accent-[#49624a]"
              />
            </label>

            {useMockAgents ? <MockAgentRoster /> : (
              <div className="space-y-2">
                <div className="text-xs text-[#697166]">
                  已选：{selectedNames.length ? selectedNames.join("、") : "未选择，将使用空 Agent 列表"}
                </div>
                <div className="max-h-48 space-y-1 overflow-y-auto pr-1">
                  {agents.map((agent) => (
                    <label
                      key={agent.id}
                      className="flex cursor-pointer items-start gap-2 border border-[#ecece4] px-2 py-2 text-xs hover:bg-[#f7f7f2]"
                    >
                      <input
                        type="checkbox"
                        checked={selectedAgentIds.includes(agent.id)}
                        onChange={() => toggleAgent(agent.id)}
                        className="mt-0.5 h-3.5 w-3.5 accent-[#49624a]"
                      />
                      <span>
                        <span className="block font-semibold text-[#30362f]">{agent.name}</span>
                        <span className="line-clamp-2 text-[#697166]">{agent.description}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            )}
          </section>

          <div className="grid gap-2">
            <button
              type="button"
              onClick={generateInput}
              disabled={loading !== null || !content.trim()}
              className="w-full border border-[#1f2421] bg-white px-4 py-2 text-sm font-semibold text-[#1f2421] transition hover:bg-[#eef0e8] disabled:cursor-not-allowed disabled:border-[#c9cbbf] disabled:text-[#9ca397]"
            >
              {loading === "build" ? "生成中..." : "仅生成调度器输入"}
            </button>
            <div className="border border-[#d8d8cc] bg-[#fbfbf7] px-3 py-2 text-xs leading-5 text-[#697166]">
              一步生成已迁移到群聊：创建群聊后 @项目Leader 即可直接生成 draft plan。
              本调试台保留手动桥接，方便复制 Prompt 给本机 ClaudeCode 并解析回填结果。
            </div>
          </div>

          {bridgeInput && (
            <section className="space-y-3 border border-[#d8d8cc] bg-white p-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-[#30362f]">复制给 ClaudeCode</h3>
                <button
                  type="button"
                  onClick={copyPrompt}
                  className="border border-[#c9cbbf] px-2 py-1 text-xs font-semibold text-[#49624a] hover:bg-[#f7f7f2]"
                >
                  复制 Prompt
                </button>
              </div>
              <textarea
                readOnly
                value={bridgeInput.prompt}
                rows={12}
                className="w-full resize-none border border-[#c9cbbf] bg-[#fbfbf7] px-3 py-2 font-mono text-[11px] leading-5 outline-none"
              />
            </section>
          )}

          <section className="space-y-3 border border-[#d8d8cc] bg-white p-4">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-sm font-semibold text-[#30362f]">粘贴调度器输出</h3>
              <label className="cursor-pointer border border-[#c9cbbf] px-2 py-1 text-xs font-semibold text-[#49624a] hover:bg-[#f7f7f2]">
                导入 JSON 文件
                <input
                  type="file"
                  accept=".json,application/json,text/plain"
                  className="hidden"
                  onChange={(e) => {
                    void importOutputFile(e.currentTarget.files?.[0] ?? null);
                    e.currentTarget.value = "";
                  }}
                />
              </label>
            </div>
            <textarea
              value={rawOutput}
              onChange={(e) => setRawOutput(e.target.value)}
              rows={10}
              className="w-full resize-none border border-[#c9cbbf] bg-[#fbfbf7] px-3 py-2 font-mono text-[11px] leading-5 outline-none transition focus:border-[#49624a] focus:ring-2 focus:ring-[#49624a]/15"
              placeholder="把 ClaudeCode 输出的 JSON 或 ```json 代码块粘贴到这里。"
            />
            <button
              type="button"
              onClick={parseOutput}
              disabled={loading !== null || !bridgeInput || !rawOutput.trim()}
              className="w-full border border-[#1f2421] bg-white px-4 py-2 text-sm font-semibold text-[#1f2421] transition hover:bg-[#eef0e8] disabled:cursor-not-allowed disabled:border-[#c9cbbf] disabled:text-[#9ca397]"
            >
              {loading === "parse" ? "解析中..." : "解析并校验输出"}
            </button>
          </section>

          <section className="space-y-3 border border-[#d8d8cc] bg-white p-4">
            <div>
              <h3 className="text-sm font-semibold text-[#30362f]">执行状态查询</h3>
              <p className="mt-1 text-xs leading-5 text-[#697166]">
                输入批准计划后返回的 exec_xxx，查看模拟 Scheduler 的 DAG 推进结果；运行中会自动刷新。
              </p>
            </div>
            <div className="flex gap-2">
              <input
                value={executionId}
                onChange={(e) => setExecutionId(e.target.value)}
                className="min-w-0 flex-1 border border-[#c9cbbf] bg-[#fbfbf7] px-3 py-2 font-mono text-xs outline-none transition focus:border-[#49624a] focus:ring-2 focus:ring-[#49624a]/15"
                placeholder="exec_xxxxxxxxxxxx"
              />
              <button
                type="button"
                onClick={lookupExecution}
                disabled={loading !== null || !executionId.trim()}
                className="shrink-0 border border-[#1f2421] bg-white px-3 py-2 text-xs font-semibold text-[#1f2421] transition hover:bg-[#eef0e8] disabled:cursor-not-allowed disabled:border-[#c9cbbf] disabled:text-[#9ca397]"
              >
                {loading === "execution" ? "查询中..." : "查询"}
              </button>
            </div>
            {execution && <ExecutionStatusCard execution={execution} autoRefreshing={["pending", "running"].includes(execution.status)} />}
          </section>

          {error && (
            <div className="border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {error}
            </div>
          )}
        </div>

        <div className="min-w-0">
          {parsed ? (
            <PlanResult
              parsed={parsed}
              candidateAgents={bridgeInput?.candidateAgents ?? []}
            />
          ) : bridgeInput ? (
            <BridgeInputSummary bridgeInput={bridgeInput} />
          ) : (
            <EmptyState />
          )}
        </div>
      </div>
    </div>
  );
}

function ExecutionStatusCard({
  execution,
  autoRefreshing,
}: {
  execution: OrchestratorExecution;
  autoRefreshing: boolean;
}) {
  return (
    <div className="space-y-3 border border-[#ecece4] bg-[#fbfbf7] p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-[11px] text-[#6f766d]">{execution.executionId}</p>
          <p className="mt-1 text-sm font-semibold text-[#1f2421]">{execution.planId}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {autoRefreshing && <span className="text-[11px] text-[#49624a]">自动刷新中</span>}
          <ExecutionStatusBadge status={execution.status} />
        </div>
      </div>

      <div className="grid gap-2 text-[11px] text-[#697166] sm:grid-cols-2">
        <p>任务数：{execution.tasks.length}</p>
        <p>事件数：{execution.events.length}</p>
        <p>开始：{shortTime(execution.startedAt)}</p>
        <p>完成：{shortTime(execution.completedAt)}</p>
      </div>

      <div className="space-y-2">
        {execution.tasks.map((task) => (
          <ExecutionTaskRow key={task.taskId} task={task} />
        ))}
      </div>

      <details>
        <summary className="cursor-pointer text-xs font-semibold text-[#49624a]">查看事件日志 / JSON</summary>
        <div className="mt-2 space-y-2">
          <div className="max-h-44 overflow-auto border border-[#d8d8cc] bg-white p-2">
            {execution.events.map((event, index) => (
              <p key={`${event.type}-${index}`} className="border-b border-[#ecece4] py-1 text-[11px] leading-5 text-[#4f594f] last:border-b-0">
                <span className="font-mono text-[#1f2421]">{event.type}</span>
                {typeof event.phase === "number" && <span> · phase {event.phase}</span>}
                <span> · {event.message}</span>
              </p>
            ))}
          </div>
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap bg-[#1f2421] p-3 font-mono text-[11px] leading-5 text-[#e8eadf]">
            {JSON.stringify(execution, null, 2)}
          </pre>
        </div>
      </details>
    </div>
  );
}

function ExecutionTaskRow({ task }: { task: OrchestratorExecutionTask }) {
  return (
    <article className="border border-[#d8d8cc] bg-white px-3 py-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-semibold text-[#30362f]">{task.taskId} · {task.title}</p>
          <p className="mt-1 text-[11px] leading-5 text-[#697166]">
            @{task.assignedAgentName ?? task.assignedAgentId ?? "未分配"} · 依赖：{task.dependsOn.length ? task.dependsOn.join(" / ") : "无"}
          </p>
        </div>
        <ExecutionStatusBadge status={task.status} compact />
      </div>
      {task.summary && (
        <p className="mt-2 bg-[#eef0e8] px-2 py-1.5 text-[11px] leading-5 text-[#384438]">
          {task.summary}
        </p>
      )}
    </article>
  );
}

function ExecutionStatusBadge({ status, compact = false }: { status: string; compact?: boolean }) {
  const cls = status === "completed"
    ? "border-green-200 bg-green-50 text-green-700"
    : status === "running"
      ? "border-blue-200 bg-blue-50 text-blue-700"
      : status === "failed" || status === "error"
        ? "border-red-200 bg-red-50 text-red-700"
        : "border-amber-200 bg-amber-50 text-amber-700";
  return (
    <span className={`shrink-0 border px-2 py-1 text-[11px] font-semibold ${cls} ${compact ? "" : "uppercase tracking-[0.12em]"}`}>
      {status}
    </span>
  );
}

function shortTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function EmptyState() {
  return (
    <div className="flex min-h-[520px] items-center justify-center border border-dashed border-[#c9cbbf] bg-[#fbfbf7] px-8 py-10 text-center">
      <div className="max-w-md">
        <p className="text-sm font-semibold text-[#30362f]">等待生成调度器输入</p>
        <p className="mt-2 text-sm leading-6 text-[#697166]">
          先生成 Prompt，再把本机 ClaudeCode 的输出粘回来解析。
        </p>
      </div>
    </div>
  );
}

function BridgeInputSummary({ bridgeInput }: { bridgeInput: BuildOrchestratorInputResult }) {
  return (
    <div className="space-y-4">
      <section className="border border-[#d8d8cc] bg-white p-4">
        <p className="text-[11px] uppercase tracking-[0.14em] text-[#6f766d]">Orchestrator Profile</p>
        <h3 className="mt-1 text-xl font-semibold text-[#1f2421]">{bridgeInput.orchestratorAgent.name}</h3>
        <p className="mt-2 text-xs text-[#697166]">
          {bridgeInput.orchestratorAgent.engine} · 工具集
        </p>
        <TagRow tags={bridgeInput.orchestratorAgent.toolset} />
      </section>
      <AgentSnapshot agents={bridgeInput.candidateAgents} />
    </div>
  );
}

function PlanResult({
  parsed,
  candidateAgents,
}: {
  parsed: ParseOrchestratorOutputResult;
  candidateAgents: OrchestratorDebugAgent[];
}) {
  const plan = parsed.normalizedPlan;
  return (
    <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_360px]">
      <section className="border border-[#d8d8cc] bg-white p-4 2xl:col-span-2">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.14em] text-[#6f766d]">Draft Plan</p>
            <h3 className="text-2xl font-semibold text-[#1f2421]">{plan.plan_id}</h3>
            <p className="mt-2 text-xs leading-5 text-[#697166]">{plan.execution_strategy.summary}</p>
          </div>
          <span className={parsed.validation.ok
            ? "border border-green-200 bg-green-50 px-2 py-1 text-xs font-semibold text-green-700"
            : "border border-red-200 bg-red-50 px-2 py-1 text-xs font-semibold text-red-700"}
          >
            {parsed.validation.ok ? "VALID" : "INVALID"}
          </span>
        </div>
      </section>

      <ValidationPanel parsed={parsed} />
      <TaskList tasks={plan.tasks} />
      <AgentSnapshot agents={candidateAgents} compact />

      <section className="border border-[#d8d8cc] bg-[#1f2421] p-4 text-[#e8eadf] 2xl:col-span-2">
        <MermaidPreview chart={parsed.visualization.mermaid} />
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold">Mermaid</h3>
          <span className="text-[11px] text-[#aeb6aa]">可复制到 Markdown</span>
        </div>
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap text-[11px] leading-5">
          {parsed.visualization.mermaid}
        </pre>
      </section>

      <section className="border border-[#d8d8cc] bg-white p-4 2xl:col-span-2">
        <h3 className="mb-3 text-sm font-semibold text-[#30362f]">Normalized Plan JSON</h3>
        <pre className="max-h-96 overflow-auto whitespace-pre-wrap bg-[#fbfbf7] p-3 font-mono text-[11px] leading-5 text-[#30362f]">
          {JSON.stringify(plan, null, 2)}
        </pre>
      </section>
    </div>
  );
}

function MermaidPreview({ chart }: { chart: string }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const render = async () => {
      if (!containerRef.current || !chart.trim()) return;
      setError(null);
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "base",
          themeVariables: {
            background: "#ffffff",
            primaryColor: "#eef0e8",
            primaryTextColor: "#1f2421",
            primaryBorderColor: "#49624a",
            lineColor: "#6f766d",
            fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
          },
        });
        const id = `orchestrator-plan-${Date.now()}-${Math.random().toString(36).slice(2)}`;
        const { svg } = await mermaid.render(id, chart);
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Mermaid 渲染失败");
          if (containerRef.current) containerRef.current.innerHTML = "";
        }
      }
    };

    void render();
    return () => {
      cancelled = true;
    };
  }, [chart]);

  return (
    <div className="mb-4 border border-[#d8d8cc] bg-white p-3 text-[#1f2421]">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-[#30362f]">Mermaid 预览</h3>
        {error && <span className="text-[11px] text-red-600">渲染失败</span>}
      </div>
      {error ? (
        <p className="text-xs leading-5 text-red-700">{error}</p>
      ) : (
        <div
          ref={containerRef}
          className="max-h-[520px] overflow-auto [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-none"
        />
      )}
    </div>
  );
}

function ValidationPanel({ parsed }: { parsed: ParseOrchestratorOutputResult }) {
  const { errors, warnings } = parsed.validation;
  return (
    <section className="border border-[#d8d8cc] bg-white p-4 2xl:col-span-2">
      <h3 className="mb-3 text-sm font-semibold text-[#30362f]">校验结果</h3>
      {errors.length === 0 && warnings.length === 0 ? (
        <p className="text-xs text-green-700">结构校验通过，无 warning。</p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          <MessageList title="Errors" items={errors} tone="error" />
          <MessageList title="Warnings" items={warnings} tone="warning" />
        </div>
      )}
    </section>
  );
}

function MessageList({ title, items, tone }: { title: string; items: string[]; tone: "error" | "warning" }) {
  const cls = tone === "error" ? "text-red-700 bg-red-50 border-red-200" : "text-amber-700 bg-amber-50 border-amber-200";
  return (
    <div className={`border px-3 py-2 ${cls}`}>
      <p className="text-xs font-semibold">{title}</p>
      {items.length === 0 ? (
        <p className="mt-2 text-xs opacity-70">无</p>
      ) : (
        <ul className="mt-2 space-y-1 text-xs">
          {items.map((item) => <li key={item}>{item}</li>)}
        </ul>
      )}
    </div>
  );
}

function TaskList({ tasks }: { tasks: OrchestratorPlanTask[] }) {
  return (
    <section className="border border-[#d8d8cc] bg-white p-3">
      <h3 className="mb-3 text-sm font-semibold text-[#30362f]">任务 DAG</h3>
      <div className="space-y-2">
        {tasks.map((task) => (
          <div key={task.task_id} className="border-l-4 border-[#49624a] bg-[#fbfbf7] px-3 py-2">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-sm font-semibold text-[#1f2421]">{task.task_id} · {task.title}</p>
                <p className="mt-1 text-xs leading-5 text-[#697166]">{task.goal}</p>
              </div>
              <span className="shrink-0 bg-[#e7eadf] px-2 py-1 text-[11px] font-semibold text-[#384438]">
                {task.is_blocking ? "阻塞" : "普通"}
              </span>
            </div>
            <p className="mt-2 text-[11px] text-[#6f766d]">
              @{task.assigned_agent_name ?? "未分配"} · 依赖：{task.depends_on.length ? task.depends_on.join(" / ") : "无"}
            </p>
            <TagRow tags={task.required_skills} />
          </div>
        ))}
      </div>
    </section>
  );
}

function AgentSnapshot({ agents, compact = false }: { agents: OrchestratorDebugAgent[]; compact?: boolean }) {
  return (
    <section className="border border-[#d8d8cc] bg-white p-4">
      <h3 className="mb-3 text-sm font-semibold text-[#30362f]">候选 Agent 快照</h3>
      <div className="space-y-2">
        {agents.map((agent) => (
          <div key={agent.id} className="border border-[#ecece4] px-3 py-2">
            <p className="text-sm font-semibold text-[#30362f]">{agent.name}</p>
            {!compact && <p className="mt-1 text-xs leading-5 text-[#697166]">{agent.description}</p>}
            <p className="mt-1 text-[11px] text-[#6f766d]">
              {agent.id} · {agent.provider}
            </p>
            <TagRow tags={agent.toolset ?? []} />
          </div>
        ))}
      </div>
    </section>
  );
}

function MockAgentRoster() {
  const roster = [
    ["系统架构师", "边界、契约、演进路径"],
    ["UX/UI设计师", "流程、界面、交互状态"],
    ["前端工程师", "React、状态、组件实现"],
    ["后端工程师", "API、服务、集成测试"],
    ["测试工程师", "风险、回归、验收报告"],
  ];
  return (
    <div className="grid gap-1 border-t border-[#ecece4] pt-3">
      {roster.map(([name, desc]) => (
        <div key={name} className="flex items-center justify-between gap-2 bg-[#fbfbf7] px-2 py-1.5 text-xs">
          <span className="font-semibold text-[#30362f]">{name}</span>
          <span className="text-right text-[#697166]">{desc}</span>
        </div>
      ))}
    </div>
  );
}

function TagRow({ tags }: { tags: string[] }) {
  if (tags.length === 0) {
    return <p className="mt-2 text-[11px] text-[#9a9f95]">无标签</p>;
  }
  return (
    <div className="mt-2 flex flex-wrap gap-1">
      {tags.map((tag) => (
        <span key={tag} className="bg-[#eef0e8] px-2 py-1 text-[11px] text-[#4f594f]">
          {tag}
        </span>
      ))}
    </div>
  );
}
