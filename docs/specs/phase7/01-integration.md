# Spec: Phase 7D — Store 拆分 + 体验收尾

**版本**: v2.0
**创建日期**: 2026-05-28 (v1.0), 2026-06-02 (v2.0 重组)
**状态**: Draft
**关联**: [PRD-03: User Experience](../../PRD/03-User_Experience.md)
**依赖**: Phase 4 + Phase 5 + Phase 6 全部完成

## 1. 范围

Zustand store 正式拆分 + SessionList 搜索跳转 + 全局 UX polish。

## 2. Store 拆分 (Spec §9.1)

```
stores/
  chatStore.ts    ← messages, isStreaming, streamingError
  sessionStore.ts ← sessions, agents, providers, sidebarTab
  searchStore.ts  ← searchQuery, searchResults, isSearchOpen (NEW)
```

每个 store 独立文件, 独立测试。

## 3. SessionList 搜索跳转

- 搜索面板点击结果 → 切换到对应会话 → 滚动到消息位置
- 高亮闪烁 2s

## 4. 全局 UX 收尾

- [ ] 所有新组件通过 UX_TEST_SPEC 6 状态检查
- [ ] P0/P1 UX 缺陷清零
- [ ] 全量回归: backend + frontend + E2E

## 5. 测试

- Store: chatStore + sessionStore + searchStore → 已部分完成
- E2E: 搜索 → 跳转 → 高亮
- 目标: 8 条
