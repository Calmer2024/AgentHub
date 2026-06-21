import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageArtifactStrip } from "../../../frontend/src/components/MessageArtifactStrip";
import type { Artifact, Message } from "../../../frontend/src/types";

vi.mock("../../../frontend/src/components/ArtifactCard", () => ({
  ArtifactCard: ({ artifact }: { artifact: Artifact }) => (
    <div data-testid="artifact-card">{artifact.title}</div>
  ),
}));

const message: Message = {
  id: "m1",
  sessionId: "s1",
  role: "assistant",
  content: "done",
  agentName: "Codex",
  createdAt: "2026-06-05T00:00:00.000Z",
};

const artifact = (id: string, messageId: string, type: Artifact["type"]): Artifact => ({
  id,
  sessionId: "s1",
  messageId,
  type,
  title: type === "file_tree" ? "本次文件变更" : "页面",
  content: "",
  status: "ready",
  version: 1,
  createdAt: "2026-06-05T00:00:00.000Z",
});

describe("MessageArtifactStrip", () => {
  it("只展示当前消息绑定的产物卡片", () => {
    render(
      <MessageArtifactStrip
        message={message}
        artifacts={[
          artifact("a1", "m1", "file_tree"),
          artifact("a2", "other", "web_preview"),
        ]}
      />,
    );

    expect(screen.getByText("本次文件变更")).toBeInTheDocument();
    expect(screen.queryByText("页面")).not.toBeInTheDocument();
    expect(screen.getAllByTestId("artifact-card")).toHaveLength(1);
  });

  it("扫描中显示局部状态", () => {
    render(
      <MessageArtifactStrip
        message={{ ...message, metadata: { artifactBridge: { status: "scanning" } } }}
        artifacts={[]}
      />,
    );

    expect(screen.getByText("分析产物中")).toBeInTheDocument();
  });

  it("失败和低置信候选使用局部提示", () => {
    const { rerender } = render(
      <MessageArtifactStrip
        message={{ ...message, metadata: { artifactBridge: { status: "failed" } } }}
        artifacts={[]}
      />,
    );

    expect(screen.getByText("产物分析失败")).toBeInTheDocument();

    rerender(
      <MessageArtifactStrip
        message={{ ...message, metadata: { artifactCandidates: [{ artifactType: "document" }] } }}
        artifacts={[]}
      />,
    );

    expect(screen.getByText("有 1 个低置信产物候选")).toBeInTheDocument();
  });

  it("多个产物都直接在消息下方展示为卡片", () => {
    render(
      <MessageArtifactStrip
        message={message}
        artifacts={[
          artifact("a1", "m1", "web_preview"),
          artifact("a2", "m1", "code_diff"),
          artifact("a3", "m1", "document"),
          artifact("a4", "m1", "file_tree"),
        ]}
      />,
    );

    expect(screen.getAllByTestId("artifact-card")).toHaveLength(4);
    expect(screen.getByText("4 个")).toBeInTheDocument();
  });
});
