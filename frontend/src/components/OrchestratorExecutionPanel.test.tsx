import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OrchestratorExecutionPanel } from "./OrchestratorExecutionPanel";
import {
  cancelOrchestratorExecution,
  fetchOrchestratorExecution,
  interruptOrchestratorExecution,
  resumeOrchestratorExecution,
} from "../api/client";
import type { OrchestratorExecution } from "../types";

vi.mock("../api/client", () => ({
  cancelOrchestratorExecution: vi.fn(),
  fetchOrchestratorExecution: vi.fn(),
  interruptOrchestratorExecution: vi.fn(),
  resumeOrchestratorExecution: vi.fn(),
}));

function execution(status: string): OrchestratorExecution {
  return {
    executionId: "exec_resume",
    sessionId: "session-1",
    planId: "plan_resume",
    runId: "run-1",
    status,
    createdAt: "",
    updatedAt: "",
    startedAt: "",
    completedAt: null,
    validation: { ok: true, errors: [], warnings: [] },
    tasks: [
      {
        taskId: "T1",
        title: "需求确认",
        goal: "",
        status: "completed",
        startedAt: "",
        completedAt: "",
        updatedAt: "",
        summary: "T1 已完成",
        runnerType: "cli",
        visibleMessageId: "msg-1",
        assignedAgentId: "agent-1",
        assignedAgentName: "产品经理",
        dependsOn: [],
        requiredSkills: [],
        needsApproval: false,
        isBlocking: false,
        expectedOutputs: [],
        acceptanceCriteria: [],
      },
      {
        taskId: "T2",
        title: "后端实现",
        goal: "",
        status: status === "interrupted" ? "interrupted" : "running",
        startedAt: "",
        completedAt: null,
        updatedAt: "",
        summary: null,
        runnerType: "cli",
        visibleMessageId: "msg-2",
        assignedAgentId: "agent-2",
        assignedAgentName: "后端工程师",
        dependsOn: ["T1"],
        requiredSkills: [],
        needsApproval: false,
        isBlocking: false,
        expectedOutputs: [],
        acceptanceCriteria: [],
      },
    ],
    events: [{
      type: "execution_created",
      status,
      timestamp: "",
      message: "created",
    }],
  };
}

describe("OrchestratorExecutionPanel resume controls", () => {
  it("运行中点击停止会调用 interrupt，而不是 cancel", async () => {
    vi.mocked(fetchOrchestratorExecution).mockResolvedValue(execution("running"));
    vi.mocked(interruptOrchestratorExecution).mockResolvedValue(execution("interrupted"));
    render(<OrchestratorExecutionPanel initialExecution={execution("running")} />);

    fireEvent.click(screen.getByRole("button", { name: "停止" }));

    await waitFor(() => {
      expect(interruptOrchestratorExecution).toHaveBeenCalledWith(
        "exec_resume",
        "用户在调度执行面板停止运行",
      );
    });
    expect(cancelOrchestratorExecution).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "继续执行" })).toBeInTheDocument();
  });

  it("中断状态显示继续执行与放弃执行", async () => {
    vi.mocked(resumeOrchestratorExecution).mockResolvedValue(execution("running"));
    vi.mocked(cancelOrchestratorExecution).mockResolvedValue(execution("cancelled"));

    render(<OrchestratorExecutionPanel initialExecution={execution("interrupted")} />);

    expect(screen.getByText(/执行已中断/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "继续执行" }));
    await waitFor(() => {
      expect(resumeOrchestratorExecution).toHaveBeenCalledWith("exec_resume");
    });

    render(<OrchestratorExecutionPanel initialExecution={execution("interrupted")} />);
    fireEvent.click(screen.getByRole("button", { name: "放弃执行" }));
    await waitFor(() => {
      expect(cancelOrchestratorExecution).toHaveBeenCalledWith("exec_resume");
    });
  });
});

