import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(process.cwd(), "src/index.css"), "utf8");

describe("交互浮层样式", () => {
  it("更多按钮在所有交互状态都保持同一个垂直中心且不出现按钮底色", () => {
    expect(css).toMatch(
      /\.agenthub-row-more,\s*\.agenthub-row-more:hover,\s*\.agenthub-row-more:active,\s*\.agenthub-row-more:focus-visible\s*\{[^}]*transform:\s*translateY\(-50%\)\s*!important;[^}]*background:\s*transparent\s*!important;/s,
    );
  });

  it("下拉菜单与更多菜单统一为无边框阴影浮层", () => {
    expect(css).toMatch(
      /\.agenthub-menu\s*\{[^}]*border:\s*0\s*!important;[^}]*box-shadow:\s*0\s+10px\s+24px\s+rgb\(0\s+0\s+0\s*\/\s*0\.30\)/s,
    );
  });

  it("点击与聚焦状态不产生外发光或边缘滤镜", () => {
    expect(css).toMatch(
      /:where\(button, a, input, textarea, select, summary, \[role="button"\], \[tabindex\]\):(?:focus|active)[^{]*\{[^}]*box-shadow:\s*none\s*!important;[^}]*filter:\s*none\s*!important;/s,
    );
    expect(css).toMatch(
      /\.agenthub-focus-ring:focus,\s*\.agenthub-focus-ring:focus-within\s*\{[^}]*box-shadow:\s*none\s*!important;/s,
    );
  });

  it("菜单列表项使用非连续悬浮态", () => {
    expect(css).toMatch(
      /\.agenthub-menu\s*>\s*:is\([^}]+\)\s*\{[^}]*margin-top:\s*4px;/s,
    );
    expect(css).toMatch(
      /\.agenthub-menu\s+:is\([^}]+\)\s*\{[^}]*border:\s*0\s*!important;/s,
    );
  });
});
