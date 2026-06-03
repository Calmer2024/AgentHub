import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { CodeSelector } from "./CodeSelector";

describe("CodeSelector", () => {
  it("选中代码片段后提交编辑意图", () => {
    const onPreview = vi.fn();
    render(
      <CodeSelector
        content={"def hello():\n    return 'hello'\n"}
        onPreview={onPreview}
      />,
    );

    const textarea = screen.getByDisplayValue(/def hello/);
    (textarea as HTMLTextAreaElement).setSelectionRange(17, 31);
    fireEvent.mouseUp(textarea);
    fireEvent.change(screen.getByPlaceholderText("描述修改意图"), {
      target: { value: "改成返回 Hello World" },
    });
    fireEvent.click(screen.getByText("生成 Diff"));

    expect(onPreview).toHaveBeenCalledWith(
      "return 'hello'",
      "改成返回 Hello World",
      "replace",
    );
  });

  it("未选择内容时不能提交", () => {
    const onPreview = vi.fn();
    render(
      <CodeSelector
        content="print('hello')"
        onPreview={onPreview}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("描述修改意图"), {
      target: { value: "改一下" },
    });

    expect(screen.getByText("生成 Diff")).toBeDisabled();
  });
});
