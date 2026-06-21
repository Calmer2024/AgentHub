# ADR-0010: 消息级 Artifact 体验取代 P1 右侧 Drawer

**Date**: 2026-06-06
**Status**: Accepted
**Context**: Phase 6F Artifact Bridge 验收后，用户明确要求移除独立产物工作台，并让文件代码变更、产物、Diff 和编辑能力都以具体卡片在对应对话消息下方呈现。

---

## Context

早期 PRD 与 Phase 7 文档将右侧 Artifact Drawer 作为 P1 体验闭环核心：Artifact Card 点击后滑出右区 Drawer，Drawer 内承载预览、Diff、版本切换和局部编辑。

Phase 6F 实现与人工验收后，产品路线发生调整：

- 独立产物工作台被移除；
- Artifact 与代码变更以 `MessageArtifactStrip` 跟随具体 assistant 消息展示；
- `ArtifactCard` 负责紧凑预览、VS Code/GitHub 风格 unified diff、页面级弹窗；
- 文件编辑由 `FileEditorModal` + CodeMirror 承担；
- 代码片段引用回流到 ChatInput；
- 版本管理由 `ArtifactVersionManager` 专属界面承担；
- Chat Header 的文件按钮打开当前会话资产管理界面。

继续保留 P1 Drawer 规格会造成两个问题：

1. 文档会驱动后续 Agent 重新实现已经被用户否定的 UI。
2. Artifact 的上下文归属会从“具体消息”漂移到“全局工作台”，削弱 IM 产品心智。

---

## Decision

P1 桌面版采用 **消息级 Artifact 体验** 作为产品基线：

```text
assistant message
  → ExecutionTracePanel
  → MessageArtifactStrip
  → ArtifactCard
  → 页面级 preview/edit/version modal
  → ChatInput code reference
```

具体决策：

1. **不恢复独立产物工作台**。会话资产由 Chat Header 文件按钮进入 `SessionArtifactManager`。
2. **不把右侧 Artifact Drawer 列为 Phase 7 P1 必做项**。Phase 7 继续做任务可控性、审批、环境体检和演示加固。
3. **Artifact 预览和编辑使用页面级弹窗**，必须通过 portal 挂载，不能被消息气泡或滚动容器裁剪。
4. **Diff 统一为 VS Code/GitHub 风格 unified diff**，不再提供“左右/上下”模式切换。
5. **版本比较默认最新版本 vs 上一版本**，不在预览弹窗中提供“起始/变更”版本选择；复杂版本操作进入 `ArtifactVersionManager`。
6. **审批卡片审阅 Artifact 时复用现有 ArtifactCard 弹窗**，不打开 Drawer。

---

## Consequences

- Phase 7 specs 必须删除或重构所有以 Drawer 为中心的内容。
- PRD 中关于 Drawer 的历史描述保留为早期产品意图，不再作为 P1 当前实现约束；后续如果重新评估 Drawer，应先新增 ADR 取代本决策。
- `CONTEXT.md`、`README.md`、`docs/README.md`、`docs/archive/phases/specs/README.md` 的 Phase 7 描述必须同步为消息级 Artifact 基线。
- 后续开发应优先维护 `MessageArtifactStrip`、`ArtifactCard`、`FileEditorModal`、`ArtifactVersionManager` 和 `SessionArtifactManager` 的一致性。

---

## Status Notes

- 2026-06-06：Phase 6F 人工验收通过，确认消息级 Artifact 卡片、页面级弹窗、IDE 风格编辑器、代码引用、版本管理、会话文件入口和 CLI Agent logo 头像均符合当前产品路线。
