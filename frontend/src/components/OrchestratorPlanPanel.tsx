import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, GitBranch, ListChecks } from "lucide-react";
import type { OrchestratorPlan, OrchestratorValidation } from "../types";

interface OrchestratorPlanMetadata {
  ok?: boolean;
  normalizedPlan?: OrchestratorPlan;
  validation?: OrchestratorValidation;
  visualization?: {
    mermaid?: string;
  };
}

interface Props {
  plan: OrchestratorPlanMetadata;
  rawJson: string;
}

export function OrchestratorPlanPanel({ plan, rawJson }: Props) {
  const [showRaw, setShowRaw] = useState(false);
  const normalized = plan.normalizedPlan;
  const tasks = normalized?.tasks ?? [];
  const validation = plan.validation;

  if (!normalized) return null;

  return (
    <div className="space-y-3 text-slate-900">
      <section className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
              <GitBranch size={15} className="text-indigo-600" />
              <span>{normalized.plan_id}</span>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              {tasks.length} 个任务 · {String(normalized.status || "draft")} · {policyText(normalized.execution_policy)}
            </p>
          </div>
          <StatusBadge ok={validation?.ok ?? plan.ok ?? true} />
        </div>
        <ValidationSummary validation={validation} />
      </section>

      <TaskTimeline plan={normalized} />

      {plan.visualization?.mermaid && (
        <section className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-950">
            <GitBranch size={15} className="text-indigo-600" />
            <span>DAG 预览</span>
          </div>
          <MermaidPreview chart={plan.visualization.mermaid} />
        </section>
      )}

      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <button
          type="button"
          onClick={() => setShowRaw((value) => !value)}
          className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs font-semibold text-slate-700 hover:bg-slate-50"
        >
          <span>原始 JSON</span>
          {showRaw ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        {showRaw && (
          <pre className="max-h-80 overflow-auto border-t border-slate-100 bg-slate-950 p-3 text-[11px] leading-5 text-slate-100">
            {rawJson}
          </pre>
        )}
      </section>
    </div>
  );
}

function StatusBadge({ ok }: { ok: boolean }) {
  return (
    <span className={`inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-semibold ${
      ok ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-red-200 bg-red-50 text-red-700"
    }`}>
      {ok ? <CheckCircle2 size={12} /> : <AlertTriangle size={12} />}
      {ok ? "校验通过" : "需要修正"}
    </span>
  );
}

function ValidationSummary({ validation }: { validation?: OrchestratorValidation }) {
  if (!validation || (validation.errors.length === 0 && validation.warnings.length === 0)) {
    return <p className="mt-3 text-xs text-emerald-700">结构校验通过，无 warning。</p>;
  }
  return (
    <div className="mt-3 grid gap-2 md:grid-cols-2">
      <MessageList title="Errors" items={validation.errors} tone="error" />
      <MessageList title="Warnings" items={validation.warnings} tone="warning" />
    </div>
  );
}

function MessageList({ title, items, tone }: { title: string; items: string[]; tone: "error" | "warning" }) {
  const cls = tone === "error"
    ? "border-red-200 bg-red-50 text-red-700"
    : "border-amber-200 bg-amber-50 text-amber-700";
  return (
    <div className={`rounded-md border px-2.5 py-2 ${cls}`}>
      <p className="text-[11px] font-semibold">{title}</p>
      {items.length === 0 ? (
        <p className="mt-1 text-[11px] opacity-70">无</p>
      ) : (
        <ul className="mt-1 space-y-1 text-[11px]">
          {items.map((item) => <li key={item}>{item}</li>)}
        </ul>
      )}
    </div>
  );
}

function TaskTimeline({ plan }: { plan: OrchestratorPlan }) {
  const phases = useMemo(() => groupByPhase(plan), [plan]);
  return (
    <section className="space-y-2">
      {phases.map((phase) => (
        <div key={phase.index} className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
              <ListChecks size={15} className="text-indigo-600" />
              <span>Phase {phase.index}</span>
            </div>
            <span className="rounded bg-slate-100 px-2 py-1 text-[11px] font-medium text-slate-600">
              {phase.tasks.length > 1 ? "并行" : "串行"}
            </span>
          </div>
          <div className="space-y-2">
            {phase.tasks.map((task) => (
              <article key={task.task_id} className="rounded-md border border-slate-100 bg-slate-50 p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h4 className="text-sm font-semibold text-slate-950">{task.task_id} · {task.title}</h4>
                    <p className="mt-1 text-xs leading-5 text-slate-600">{task.goal}</p>
                  </div>
                  <span className="rounded border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-600">
                    {task.is_blocking ? "阻塞" : "普通"}
                  </span>
                </div>
                <div className="mt-2 grid gap-2 text-[11px] text-slate-600 md:grid-cols-2">
                  <InfoLine label="Agent" value={task.assigned_agent_name || task.assigned_agent_id || "待分配"} />
                  <InfoLine label="依赖" value={task.depends_on.length ? task.depends_on.join(" / ") : "无"} />
                  <InfoLine label="能力" value={task.required_skills.join(" / ") || "未声明"} />
                  <InfoLine label="审批" value={task.needs_approval ? "需要确认" : "无需单独确认"} />
                </div>
                {task.assignment_reason && (
                  <p className="mt-2 rounded bg-white px-2 py-1.5 text-[11px] leading-5 text-slate-600">
                    {task.assignment_reason}
                  </p>
                )}
                <CompactList title="输出物" items={task.expected_outputs} />
                <CompactList title="验收" items={task.acceptance_criteria} />
              </article>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}

function InfoLine({ label, value }: { label: string; value: string }) {
  return (
    <p>
      <span className="font-semibold text-slate-500">{label}：</span>
      <span>{value}</span>
    </p>
  );
}

function CompactList({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="mt-2">
      <p className="text-[11px] font-semibold text-slate-500">{title}</p>
      <ul className="mt-1 list-disc space-y-1 pl-4 text-[11px] leading-5 text-slate-600">
        {items.slice(0, 5).map((item) => <li key={item}>{item}</li>)}
      </ul>
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
            primaryColor: "#eef2ff",
            primaryTextColor: "#0f172a",
            primaryBorderColor: "#4f46e5",
            lineColor: "#64748b",
            fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
          },
        });
        const id = `chat-orchestrator-plan-${Date.now()}-${Math.random().toString(36).slice(2)}`;
        const { svg } = await mermaid.render(id, chart);
        if (!cancelled && containerRef.current) containerRef.current.innerHTML = svg;
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

  if (error) return <p className="text-xs text-red-700">{error}</p>;
  return <div ref={containerRef} className="max-h-96 overflow-auto [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-none" />;
}

function groupByPhase(plan: OrchestratorPlan) {
  const phaseByTask = new Map<string, number>();
  for (const phase of plan.execution_strategy?.phases ?? []) {
    for (const taskId of phase.tasks) phaseByTask.set(taskId, phase.phase);
  }
  for (const [index, group] of (plan.execution_strategy?.parallelizable_groups ?? []).entries()) {
    for (const taskId of group) {
      if (!phaseByTask.has(taskId)) phaseByTask.set(taskId, index + 1);
    }
  }
  const grouped = new Map<number, OrchestratorPlan["tasks"]>();
  for (const task of plan.tasks) {
    const phase = phaseByTask.get(task.task_id) ?? dependencyDepth(task.task_id, plan);
    grouped.set(phase, [...(grouped.get(phase) ?? []), task]);
  }
  return [...grouped.entries()]
    .sort(([a], [b]) => a - b)
    .map(([index, tasks]) => ({ index, tasks }));
}

function dependencyDepth(taskId: string, plan: OrchestratorPlan, seen = new Set<string>()): number {
  if (seen.has(taskId)) return 0;
  seen.add(taskId);
  const task = plan.tasks.find((item) => item.task_id === taskId);
  if (!task || task.depends_on.length === 0) return 0;
  return 1 + Math.max(...task.depends_on.map((dep) => dependencyDepth(dep, plan, new Set(seen))));
}

function policyText(policy: OrchestratorPlan["execution_policy"]) {
  if (typeof policy === "string") return policy;
  if (!policy || typeof policy !== "object") return "plan_only";
  return String((policy as Record<string, unknown>).mode ?? "plan_only");
}
