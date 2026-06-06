import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { CollaborationPanel } from "./CollaborationPanel";
import type { DAGPhase } from "../types";

const phases: DAGPhase[] = [
  {
    phase: 0,
    mode: "serial",
    status: "completed",
    tasks: [{ name: "planning", role: "planner", agent: "架构师", status: "completed", phase: 0 }],
  },
  {
    phase: 1,
    mode: "parallel",
    status: "running",
    tasks: [
      { name: "frontend", role: "executor", agent: "前端", status: "running", phase: 1 },
      { name: "backend", role: "executor", agent: "后端", status: "running", phase: 1 },
    ],
  },
];

describe("CollaborationPanel", () => {
  it("渲染 DAG phase 和并行任务", () => {
    render(
      <CollaborationPanel
        intent="code_gen"
        tasks={phases.flatMap((p) => p.tasks)}
        phases={phases}
        isCompleted={false}
        completedSummary={null}
      />,
    );

    expect(screen.getByText(/编排器/)).toBeInTheDocument();
    expect(screen.getByText("阶段 0")).toBeInTheDocument();
    expect(screen.getByText("阶段 1")).toBeInTheDocument();
    expect(screen.getByText("@前端")).toBeInTheDocument();
    expect(screen.getByText("@后端")).toBeInTheDocument();
  });
});
