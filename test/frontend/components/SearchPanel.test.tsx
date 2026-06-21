import { describe, it, expect, vi, afterEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { SearchPanel } from "../../../frontend/src/components/SearchPanel";

describe("SearchPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("搜索并点击结果跳转到消息", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify([
      {
        id: "m1",
        sessionId: "s1",
        role: "user",
        content: "讨论向量数据库",
        highlight: "讨论<mark>向量数据库</mark>",
        agentName: null,
        createdAt: "2026-06-02T00:00:00",
      },
    ]), { status: 200 }));
    const onJump = vi.fn();

    render(
      <SearchPanel
        sessionId="s1"
        open
        onClose={vi.fn()}
        onJump={onJump}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("搜索当前会话"), {
      target: { value: "向量数据库" },
    });

    const result = await screen.findByText("向量数据库");
    expect(result.tagName.toLowerCase()).toBe("mark");

    fireEvent.click(screen.getByText(/讨论/).closest("button")!);
    expect(onJump).toHaveBeenCalledWith("s1", "m1");
  });
});
