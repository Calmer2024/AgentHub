import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AgentCliRow } from "./AgentCliRow";
import type { AgentConfig } from "../types";

const agent: AgentConfig = {
  id: "agent-1",
  name: "自定义 Agent",
  description: "",
  systemPrompt: "",
  rules: "",
  agentType: "cli_wrapper",
  cliTool: "custom",
  executable: "agent",
  initArgs: [],
  envVars: {},
  toolset: [],
  primarySkill: "general_coding",
  auxiliarySkills: [],
  contextPolicy: "workspace_coding",
  avatar: "preset:custom",
  status: "ready",
  isActive: true,
  createdAt: "",
  updatedAt: "",
};

describe("AgentCliRow", () => {
  it("删除按钮需要二次点击确认", () => {
    const onDelete = vi.fn().mockResolvedValue(undefined);

    render(<AgentCliRow agent={agent} onEdit={vi.fn()} onDelete={onDelete} />);

    fireEvent.click(screen.getByRole("button", { name: "删除" }));
    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "确认" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "确认" }));
    expect(onDelete).toHaveBeenCalledTimes(1);
  });
});
