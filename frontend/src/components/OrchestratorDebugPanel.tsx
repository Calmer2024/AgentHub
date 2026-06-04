import { useMemo, useState } from "react";
import { dryRunOrchestrator } from "../api/client";
import type {
  AgentConfig,
  OrchestratorDebugCall,
  OrchestratorDebugResult,
  OrchestratorDebugScoredAgent,
} from "../types";

interface Props {
  agents: AgentConfig[];
}

const SAMPLE = "先设计登录系统再前后端实现最后审查";

const ROLE_LABELS: Record<string, string> = {
  planner: "规划",
  executor: "执行",
  reviewer: "审查",
  researcher: "调研",
  synthesizer: "综合",
  critic: "质疑",
};

export function OrchestratorDebugPanel({ agents }: Props) {
  const [content, setContent] = useState(SAMPLE);
  const [useMockAgents, setUseMockAgents] = useState(true);
  const [selectedAgentIds, setSelectedAgentIds] = useState<string[]>([]);
  const [supplemental, setSupplemental] = useState(false);
  const [result, setResult] = useState<OrchestratorDebugResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedNames = useMemo(() => {
    const byId = new Map(agents.map((a) => [a.id, a.name]));
    return selectedAgentIds.map((id) => byId.get(id) ?? id);
  }, [agents, selectedAgentIds]);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      setResult(await dryRunOrchestrator({
        content,
        agentIds: useMockAgents ? undefined : selectedAgentIds,
        useMockAgents,
        supplemental,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "调试请求失败");
    } finally {
      setLoading(false);
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
          Orchestrator Lab
        </p>
        <h2 className="mt-1 text-2xl font-semibold text-[#151814]">调度器调试台</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-[#667064]">
          输入一段用户需求，观察当前 Orchestrator 如何识别意图、选择 Agent、决定执行模式并生成调度图。Dry-run 不调用真实 Agent。
        </p>
      </div>

      <div className="grid gap-5 px-6 py-5 xl:grid-cols-[380px_minmax(0,1fr)]">
        <div className="space-y-4">
          <section className="space-y-2 border border-[#d8d8cc] bg-white p-4">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-[#30362f]">输入文本</label>
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
              rows={8}
              className="w-full resize-none border border-[#c9cbbf] bg-[#fbfbf7] px-3 py-2 text-sm leading-6 outline-none transition focus:border-[#49624a] focus:ring-2 focus:ring-[#49624a]/15"
              placeholder="输入一段用户需求，观察调度器怎么拆。"
            />
          </section>

          <section className="space-y-3 border border-[#d8d8cc] bg-white p-4">
            <label className="flex items-center justify-between gap-3 text-sm">
              <span>
                <span className="block font-semibold text-[#30362f]">Mock Agent 小队</span>
                <span className="text-xs text-[#697166]">内置五个典型角色，用来排除真实 Agent 配置噪声。</span>
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
                <div className="max-h-56 space-y-1 overflow-y-auto pr-1">
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

            <label className="flex items-center justify-between gap-3 border-t border-[#ecece4] pt-3 text-sm">
              <span>
                <span className="block font-semibold text-[#30362f]">补充轮次</span>
                <span className="text-xs text-[#697166]">模拟“补上/缺失”场景，不重建完整 DAG。</span>
              </span>
              <input
                type="checkbox"
                checked={supplemental}
                onChange={(e) => setSupplemental(e.target.checked)}
                className="h-4 w-4 accent-[#49624a]"
              />
            </label>
          </section>

          <button
            type="button"
            onClick={run}
            disabled={loading || !content.trim()}
            className="w-full bg-[#1f2421] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#303830] disabled:cursor-not-allowed disabled:bg-[#9ca397]"
          >
            {loading ? "分析中..." : "运行调度 dry-run"}
          </button>

          {error && (
            <div className="border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {error}
            </div>
          )}
        </div>

        <div className="min-w-0">
          {result ? <DebugResult result={result} /> : <EmptyState />}
        </div>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex min-h-[520px] items-center justify-center border border-dashed border-[#c9cbbf] bg-[#fbfbf7] px-8 py-10 text-center">
      <div className="max-w-md">
        <p className="text-sm font-semibold text-[#30362f]">等待一次 dry-run</p>
        <p className="mt-2 text-sm leading-6 text-[#697166]">
          运行后会显示意图识别、Agent 评分、执行模式、DAG 阶段和 Mermaid 源码。
        </p>
      </div>
    </div>
  );
}

function DebugResult({ result }: { result: OrchestratorDebugResult }) {
  return (
    <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_360px]">
      <section className="border border-[#d8d8cc] bg-white p-4 2xl:col-span-2">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.14em] text-[#6f766d]">Intent / 意图识别</p>
            <h3 className="text-2xl font-semibold text-[#1f2421]">{result.intent.type}</h3>
          </div>
          <div className="text-right">
            <p className="text-[11px] text-[#6f766d]">confidence</p>
            <p className="text-lg font-semibold">{Math.round(result.intent.confidence * 100)}%</p>
          </div>
        </div>
        <p className="mt-2 text-xs text-[#697166]">{result.intent.evidence}</p>
        <TagRow tags={result.intent.requiredTags} />
      </section>

      <section className="border border-[#d8d8cc] bg-white p-4 2xl:col-span-2">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-[#30362f]">执行计划</h3>
          <span className="border border-[#c9cbbf] px-2 py-1 text-xs font-semibold uppercase text-[#49624a]">
            {result.executionPlan.mode}
          </span>
        </div>
        <p className="text-xs leading-5 text-[#4f594f]">{result.executionPlan.planSummary}</p>
        <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
          <Metric label="decomposer" value={result.executionPlan.decomposerUsed ? "used" : "off"} />
          <Metric label="auto chain" value={result.executionPlan.chainAutoTriggered ? "yes" : "no"} />
          <Metric label="tokens" value={String(result.context.estimatedTokens)} />
          <Metric label="messages" value={String(result.context.messageCount)} />
        </div>
      </section>

      <PhaseMap result={result} />

      <section className="border border-[#d8d8cc] bg-white p-4">
        <h3 className="mb-3 text-sm font-semibold text-[#30362f]">Agent 评分</h3>
        <div className="space-y-2">
          {result.agentSelection.map((agent) => (
            <AgentScore key={agent.id} agent={agent} />
          ))}
        </div>
      </section>

      <section className="border border-[#d8d8cc] bg-[#1f2421] p-4 text-[#e8eadf] 2xl:col-span-2">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold">Mermaid</h3>
          <span className="text-[11px] text-[#aeb6aa]">可复制到 Markdown</span>
        </div>
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap text-[11px] leading-5">
          {result.visualization.mermaid}
        </pre>
      </section>
    </div>
  );
}

function PhaseMap({ result }: { result: OrchestratorDebugResult }) {
  const phases = result.executionPlan.dagPhases.length
    ? result.executionPlan.dagPhases
    : [{ phase: 0, mode: result.executionPlan.mode === "parallel" ? "parallel" as const : "serial" as const, calls: result.executionPlan.calls }];

  return (
    <section className="border border-[#d8d8cc] bg-white p-3">
      <h3 className="mb-3 text-sm font-semibold text-[#30362f]">调度图</h3>
      <div className="space-y-3">
        {phases.map((phase, index) => (
          <div key={phase.phase} className="relative">
            {index > 0 && <div className="mx-auto mb-2 h-5 w-px bg-[#aeb6aa]" />}
            <div className="border border-[#c9cbbf] bg-[#fbfbf7]">
              <div className="flex items-center justify-between border-b border-[#e2e3d9] px-3 py-2">
                <span className="text-xs font-semibold text-[#30362f]">Phase {phase.phase}</span>
                <span className="text-[11px] uppercase tracking-[0.12em] text-[#6f766d]">{phase.mode}</span>
              </div>
              <div className="grid gap-2 p-2">
                {phase.calls.map((call) => <CallCard key={`${call.phase}-${call.task}-${call.agent.id}`} call={call} />)}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function MockAgentRoster() {
  const roster = [
    ["架构师", "架构设计、方案拆解"],
    ["前端专家", "React、UI、组件"],
    ["后端专家", "Python、API、数据库"],
    ["审查员", "测试、安全、质量评估"],
    ["研究员", "调研、分析、总结"],
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

function CallCard({ call }: { call: OrchestratorDebugCall }) {
  return (
    <div className="border-l-4 border-[#49624a] bg-white px-3 py-2 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-[#1f2421]">@{call.agent.name}</p>
          <p className="text-xs text-[#697166]">{call.task}</p>
        </div>
        <span className="shrink-0 bg-[#e7eadf] px-2 py-1 text-[11px] font-semibold text-[#384438]">
          {ROLE_LABELS[call.role] ?? call.role}
        </span>
      </div>
      {call.dependsOn.length > 0 && (
        <p className="mt-2 text-[11px] text-[#6f766d]">依赖：{call.dependsOn.join(" / ")}</p>
      )}
    </div>
  );
}

function AgentScore({ agent }: { agent: OrchestratorDebugScoredAgent }) {
  return (
    <div className="border border-[#ecece4] px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-[#30362f]">{agent.name}</p>
          <p className="text-[11px] text-[#697166]">{agent.reason}</p>
        </div>
        <span className="text-sm font-semibold text-[#1f2421]">{agent.score}</span>
      </div>
      <TagRow tags={agent.matchTags} />
    </div>
  );
}

function TagRow({ tags }: { tags: string[] }) {
  if (tags.length === 0) {
    return <p className="mt-2 text-[11px] text-[#9a9f95]">无命中标签</p>;
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

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-[#ecece4] bg-[#fbfbf7] px-2 py-2">
      <p className="text-[10px] uppercase tracking-[0.12em] text-[#7a8177]">{label}</p>
      <p className="mt-1 font-semibold text-[#30362f]">{value}</p>
    </div>
  );
}
