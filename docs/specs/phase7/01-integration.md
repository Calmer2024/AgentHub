# Spec: Phase 7D — Store 拆分 + MVP 体验收尾

**版本**: v2.0
**创建日期**: 2026-05-28 (v1.0), 2026-06-02 (v2.0 重组)
**状态**: Draft
**关联**: [PRD-03: User Experience](../../PRD/03-User_Experience.md), [PRD-05: End-to-End Flow](../../PRD/05-End_to_End_Product_Flow.md)
**依赖**: Phase 4 + Phase 5 + Phase 6 全部完成，Phase 7A/7B/7C 状态已定义

## 1. 范围

Zustand store 正式拆分 + SessionList 搜索跳转 + 全局 UX polish。Phase 7D 的重点是承载最终演示闭环中的共享状态，避免所有状态继续堆在 `chatStore` 或 `App.tsx` 里。

---

## 2. 全局链路定位

```text
Artifact Card / Approval Card / HealthCheck
  -> 独立 Store 管理
  -> Drawer / ChatInput / SessionList 状态同步
  -> MVP 演示脚本稳定运行
```

| 问题 | 回答 |
|------|------|
| 上游 | Phase 4 搜索与引用、Phase 5 Artifact API、Phase 6/7 事件 |
| 下游 | 稳定的 UI 状态管理、跨会话搜索跳转、全局回归 |
| 用户可完成任务 | 在复杂演示中切换会话、打开抽屉、审批、搜索，不丢失上下文 |
| 不打通 | 新业务能力；本模块只做集成与稳定性 |

## 3. Store 拆分

```
stores/
  chatStore.ts    ← messages, isStreaming, streamingError
  sessionStore.ts ← sessions, agents, providers, sidebarTab
  searchStore.ts  ← searchQuery, searchResults, isSearchOpen (NEW)
  artifactStore.ts ← drawerState, selectedArtifact, versions, diffMode (NEW)
  taskStore.ts     ← collaboration tasks, approval checkpoints (NEW)
  systemStore.ts   ← health checks, runtime warnings (NEW)
```

每个 store 独立文件, 独立测试。

## 4. SessionList 搜索跳转

- 搜索面板点击结果 → 切换到对应会话 → 滚动到消息位置
- 高亮闪烁 2s

## 5. MVP 闭环状态同步

| 状态 | Store | 必须同步到 |
|------|-------|------------|
| 当前引用消息 | `chatStore` | ChatInput / MessageBubble |
| 当前引用 Artifact | `artifactStore` | ChatInput / ArtifactDrawer |
| Drawer 打开宽度与模式 | `artifactStore` | AppShell / ArtifactDrawer |
| 待审批任务 | `taskStore` | CollaborationPanel / ApprovalCard / ChatInput |
| 健康检查结果 | `systemStore` | Sidebar / AgentPanel / 新建会话弹窗 |
| 搜索目标消息 | `searchStore` | SessionList / ChatWindow |

## 6. 全局 UX 收尾

- [ ] 所有新组件通过 UX_TEST_SPEC 6 状态检查
- [ ] P0/P1 UX 缺陷清零
- [ ] 全量回归: backend + frontend + E2E
- [ ] MVP 演示脚本中不出现状态丢失、抽屉错位、输入框遮挡、卡片重叠

## 7. 测试

- Store: chatStore + sessionStore + searchStore + artifactStore + taskStore + systemStore
- E2E: 搜索 → 跳转 → 高亮
- E2E: Artifact Card → Drawer → 引用 → 编辑 → 新版本
- E2E: Approval Card → Drawer → 确认继续
- E2E: Health warning → AgentPanel/Settings 跳转
- 目标: 20 条
