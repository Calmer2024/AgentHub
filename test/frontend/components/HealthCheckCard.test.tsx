import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { HealthCheckCard } from "../../../frontend/src/components/HealthCheckCard";
import type { SystemHealthRead } from "../../../frontend/src/types";

const warningHealth: SystemHealthRead = {
  overall: "warning",
  checkedAt: "2026-06-10T10:00:00.000Z",
  projectId: "p1",
  sessionId: "s1",
  blockingReasons: [],
  items: [
    {
      key: "runtime.node",
      label: "node runtime",
      status: "missing",
      severity: "warning",
      detail: "未检测到 node runtime",
      action: { label: "重试", target: "retry" },
      metadata: { command: "node --version", exitCode: 127 },
    },
  ],
};

describe("HealthCheckCard", () => {
  it("环境告警可以展开查看详细信息", () => {
    render(<HealthCheckCard health={warningHealth} onRefresh={vi.fn()} />);

    expect(screen.getByText("环境有警告")).toBeInTheDocument();
    expect(screen.queryByText("未检测到 node runtime")).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("展开环境体检详情"));

    expect(screen.getByText("node runtime")).toBeInTheDocument();
    expect(screen.getByText("未检测到 node runtime")).toBeInTheDocument();
    expect(screen.getByText("command: node --version")).toBeInTheDocument();
    expect(screen.getByText("exitCode: 127")).toBeInTheDocument();
  });

  it("紧凑体检详情浮到页面顶层且标题不截断", () => {
    render(<HealthCheckCard health={warningHealth} compact onRefresh={vi.fn()} />);

    const trigger = screen.getByLabelText("展开环境体检详情：环境有警告");
    expect(trigger).toHaveClass("agenthub-health-dot");
    fireEvent.click(trigger);

    const details = screen.getByTestId("health-check-details");
    expect(details).toHaveClass("fixed");
    expect(details).toHaveClass("z-[1600]");
    expect(details).toHaveClass("agenthub-health-details");
    expect(details).toHaveClass("agenthub-solid-surface");
    expect(screen.getByText("node runtime").closest(".agenthub-health-detail-item")).toBeInTheDocument();
    expect(details.parentElement).toBe(document.body);
  });
});
