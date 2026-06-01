# 09 — 开发日志

**分支**: `phase/phase3-smart-collab`

---

## 时间线

| 日期 | 事件 |
|------|------|
| 2026-05-28 | ADR-0008 初稿: Pipeline 四阶段 + 3 种执行模式 |
| 2026-06-01 | Grill Part 1: 9 项架构决议确认 |
| 2026-06-01 | Step 1 完成: 领域层重构 (4 组件独立 + V1 删除) |
| 2026-06-01 | Step 2 完成: 执行层完善 (asyncio.timeout + 链中断 + 全失败) |
| 2026-06-01 | Step 3 完成: API 层贯通 (chainConfig 运行时传递) |
| 2026-06-01 | Step 4 完成: 前端全链路 (CollaborationView + 内联布局) |
| 2026-06-01 | Step 5 完成: 测试补盲 (test_group_chat +5) + 文档 |
| 2026-06-01 | QA Audit: 发现 5 Bug (2 阻断 + 2 中等 + 1 流程), 全部修复 |
| 2026-06-01 | Grill Part 2: 混合 DAG + 上下文共享 + 面板气泡 6 项决议 |

## Bug 清单

### B1: asyncio.wait_for 包裹 async generator (🔴 阻断)

**现象**: 所有 Agent 报 `TypeError: 'async for' requires __aiter__ method, got coroutine`
**根因**: `agent_executor._execute_single()` 用 `asyncio.wait_for()` 包裹 `adapter.chat_stream()` (async generator)。`wait_for()` 只接受 coroutine。
**修复**: 改为 `async with asyncio.timeout(60):` (Python 3.11+ 原生支持 async generator)
**发现者**: 人工验收
**教训**: 测试从未覆盖 group chat 消息发送路径 (mode=group → AgentExecutor._execute_single)。单聊路径 (mode=single) 直接调 adapter，不经过此代码。

### B2: 前端 SSE 流被首个 Agent done 截断 (🔴 阻断)

**现象**: 多 Agent 并行时只有第一个 Agent 的回复被显示
**根因**: `client.ts` 中 `if (data.done) return` 未区分 per-agent done 和 global done
**修复**: 改为 `if (data.done && !data.agentId) return`
**发现者**: E2E 链路审计

### B3: CollaborationView 缺少 status 字段导致渲染崩溃 (🔴 阻断)

**现象**: `STATUS_CONFIG[undefined]` → TypeError
**根因**: `task_started` SSE 事件的 tasks 数组无 `status` 字段
**修复**: 添加 `"status": "running"`
**发现者**: E2E 链路审计

### B4: Route banner 遮挡 CollaborationView (🟡 UI)

**现象**: 4px 重叠
**根因**: CollaborationView 用 `absolute top-16` 浮在 ChatWindow 上方
**修复**: 移入 ChatWindow 内部，改为自然流内联渲染
**发现者**: E2E 布局检测

### B5: task_completed 在错误路径被跳过 (🟢 流程)

**现象**: 全失败时 SSE 无 `task_completed` 事件
**根因**: 错误路径 `return` 在 `task_completed` yield 之前
**修复**: 统一在所有路径后发送 `task_completed`
**发现者**: SSE 协议逐帧验证

## 文件变更统计

| 操作 | 数量 | 主要文件 |
|------|------|---------|
| 新建 | 9 | IntentAnalyzer, AgentSelector, TaskDecomposer, ExecutionPlanner, CollaborationView, phase3.6-spec, 9 orchestrator docs |
| 重写 | 5 | orchestrator_v2, agent_executor, chat_service_impl, test_orchestrator_v2, client.ts |
| 修改 | 10 | App.tsx, ChatWindow.tsx, GroupChatCreator.tsx, chatStore.ts, types, api/chat.py, schemas.py, main.py, CONTEXT.md, CLAUDE.md |
| 删除 | 3 | orchestrator.py (V1), test_orchestrator.py (V1), CollabProgressCard.tsx |

## 测试覆盖演变

| 阶段 | 后端 | 前端 | E2E | 总计 |
|------|------|------|-----|------|
| Step 1 前 | 106 | 9 | 0 | 115 |
| Step 5 后 | 122 | 9 | 23 | 154 |
| Step 10 (目标) | 139 | 9 | 26 | 176 |
