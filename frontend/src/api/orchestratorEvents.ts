import type { CollabTask, DAGPhase } from "../types";

export function parseTasks(raw: unknown): CollabTask[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((item) => {
    const t = item as Record<string, unknown>;
    const status = typeof t.status === "string" ? t.status : "pending";
    return {
      name: String(t.name ?? "primary"),
      role: String(t.role ?? "executor"),
      agent: String(t.agent ?? ""),
      agentId: typeof t.agentId === "string" ? t.agentId : undefined,
      status: status === "running" || status === "completed" || status === "error" ? status : "pending",
      dependsOn: Array.isArray(t.depends_on) ? t.depends_on.map(String) : [],
      phase: typeof t.phase === "number" ? t.phase : undefined,
    };
  });
}

export function parseDagPhases(raw: unknown): DAGPhase[] {
  const dag = raw as { phases?: unknown } | null;
  if (!dag || !Array.isArray(dag.phases)) return [];
  return dag.phases.map((item) => {
    const p = item as Record<string, unknown>;
    const phase = typeof p.phase === "number" ? p.phase : 0;
    const mode = p.mode === "parallel" ? "parallel" : "serial";
    const tasks = parseTasks(p.tasks).map((t) => ({ ...t, phase }));
    return { phase, mode, status: "pending", tasks };
  });
}
