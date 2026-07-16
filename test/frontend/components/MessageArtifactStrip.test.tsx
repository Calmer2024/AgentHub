import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ArtifactMessage, MessageArtifactStrip } from "../../../frontend/src/components/MessageArtifactStrip";
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
  it("产物不再嵌入普通消息气泡", () => {
    render(
      <MessageArtifactStrip
        message={message}
        artifacts={[
          artifact("a1", "m1", "file_tree"),
          artifact("a2", "other", "web_preview"),
        ]}
      />,
    );

    expect(screen.queryByTestId("artifact-card")).not.toBeInTheDocument();
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

  it("每个产物渲染为一条独立 IM 文件消息", () => {
    render(
      <>
        <ArtifactMessage artifact={artifact("a1", "m1", "web_preview")} agentName="Codex" />
        <ArtifactMessage artifact={artifact("a2", "m1", "code_diff")} agentName="Codex" />
      </>,
    );

    expect(screen.getAllByRole("article", { name: /产物消息/ })).toHaveLength(2);
    expect(screen.getAllByTestId("artifact-card")).toHaveLength(2);
    expect(screen.queryByText("本轮产物")).not.toBeInTheDocument();
  });
});
