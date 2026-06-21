# Phase 3 开发日志

**阶段**: Phase 3 — Orchestrator + 基础设施
**分支**: `phase/phase3-smart-collab`
**时间线**: 2026-05-27 → 2026-06-02
**关联**: [Phase 3 审计报告](../audit/phase3-audit-report.md)

---

## 1. 阶段概述

| 模块 | 内容 | 规模 |
|------|------|------|
| Module 1: 基础设施 | EventBus + 6 DB 迁移 + Service ABC + SessionService | 10 files, ~800 LOC |
| Module 4: Orchestrator 核心 | Pipeline 四阶段 + AgentExecutor (4 模式) + SSE 6 事件 | 9 files, ~1500 LOC |
| Module 5: 链式协作 | Chain + DAG + SharedContext + 中枢总结 (合并入 M4) | — |
| 前端: CollaborationPanel | DAG 可视化 + Agent 角色气泡 + 协作横幅 | 4 files, ~600 LOC |

**验收**: 154 条测试 (122 backend + 9 frontend + 23 E2E)，零回归
**架构**: Pipeline 四阶段 → AgentExecutor 四模式 → SSE 事件驱动 → CollaborationPanel 渲染

---

## 2. 开发时间线

### Day 1-2 (5/27): Module 1 基础设施

- EventBus 内存实现 (pub/sub + 异常隔离 + fire-and-forget)
- 数据库迁移系统 (6 个 SQL 脚本 + migration_runner)
- MessageService/ChatService ABC + SessionService 实现
- AgentConfig + Message + Artifact 数据模型扩展
- 29 条单元测试

### Day 3 (5/28): Orchestrator V2 起步 + 文档体系

- Orchestrator V2 Pipeline 初版 + AgentExecutor + StreamMerger
- chat_service_impl → thin coordinator (委托 Pipeline + AgentExecutor)
- CollabProgressCard 前端组件 + Store 拆分 + GroupChatCreator 链式配置
- **ADR-0007 (当时称 ADR-0008) 初稿**: Pipeline 四阶段 + 3 种执行模式
- Phase 3 文档体系: 模块化拆解 + 并行开发指南 + 9 篇 orchestrator 设计文档
- 测试策略升级 (内存 DB → 文件 DB + 真实迁移)

### Day 4-5 (6/01): 密集开发 — Grill Sessions + 5 Steps

**Grill Part 1** (9 项架构决议):
- Step 1: 领域层重构 — 4 组件独立 (IntentAnalyzer/AgentSelector/TaskDecomposer/ExecutionPlanner) + V1 删除
- Step 2: 执行层完善 — asyncio.timeout + 链中断 + 全失败兜底 + 3 种 SSE 事件
- Step 3: API 层贯通 — chainConfig 运行时 + PipelineRequest 透传
- Step 4: 前端全链路 — CollaborationView 内联布局 + StreamCallbacks + 删除链式开关
- Step 5: 测试补盲 + 文档收尾

**QA Audit** (5 个 Bug 发现并修复):
- B1: asyncio.wait_for 包裹 async generator → 改为 asyncio.timeout
- B2: 前端 SSE 流被首个 Agent done 截断 → 区分 per-agent done
- B3: CollaborationView 缺少 status 字段 → 添加默认值
- B4: Route banner 遮挡 CollaborationView → 改为内联渲染
- B5: task_completed 在错误路径被跳过 → 统一路径发送

**Grill Part 2** (6 项交互设计决议):
- Step 6-10: DAG 拓扑、SharedContext、phase_change SSE、CollaborationPanel (DAG 图)、角色气泡
- 最终交付: 混合 DAG 模式 (Phase 间串行、Phase 内并行) + 对话流共享 + 中枢总结

### Day 6 (6/02): 审计 + 策略修正

- **Phase 3 全面审计**: PRD 符合性矩阵 + 架构偏离分析 + 模块完成度矩阵
- **ADR-0008**: 修订开发策略 — 功能板块制 + Phase 4-7 路线图
- **文档重构**: ADR 编号修复、Specs 按 Phase 重组、CONTEXT.md 更新
- **陈旧文档清理**: 归档无效文件、标记 Superseded 文档、修复交叉引用

---

## 3. 关键 Bug 与解决方案

### Bug 1: asyncio.wait_for 包裹 async generator (🔴 阻断)

- **现象**: Agent 报 `TypeError: 'async for' requires __aiter__ method, got coroutine`
- **根因**: `agent_executor._execute_single()` 用 `asyncio.wait_for()` 包裹 `adapter.chat_stream()` (async generator)。`wait_for()` 只接受 coroutine。
- **修复**: 改为 `async with asyncio.timeout(60):` (Python 3.11+ 原生支持 async generator)
- **教训**: 测试从未覆盖 group chat 消息发送路径 (单聊路径不经过 AgentExecutor)

### Bug 2: 前端 SSE 流被首个 Agent done 截断 (🔴 阻断)

- **现象**: 多 Agent 并行时只有第一个 Agent 的回复被显示
- **根因**: `client.ts` 中 `if (data.done) return` 未区分 per-agent done 和 global done
- **修复**: 改为 `if (data.done && !data.agentId) return`
- **发现者**: E2E 链路审计

### Bug 3: CollaborationView 缺少 status 字段导致渲染崩溃 (🔴 阻断)

- **现象**: `STATUS_CONFIG[undefined]` → TypeError
- **根因**: `task_started` SSE 事件的 tasks 数组无 `status` 字段
- **修复**: 添加 `"status": "running"`
- **发现者**: E2E 链路审计

### Bug 4: Route banner 遮挡 CollaborationView (🟡 UI)

- **现象**: 4px 重叠
- **根因**: CollaborationView 用 `absolute top-16` 浮在 ChatWindow 上方
- **修复**: 移入 ChatWindow 内部，改为自然流内联渲染
- **发现者**: E2E 布局检测

### Bug 5: task_completed 在错误路径被跳过 (🟢 流程)

- **现象**: 全失败时 SSE 无 `task_completed` 事件
- **根因**: 错误路径 `return` 在 `task_completed` yield 之前
- **修复**: 统一在所有路径后发送 `task_completed`
- **发现者**: SSE 协议逐帧验证

### Bug 6: Orchestrator 依赖 SQLAlchemy (架构违规)

- **现象**: Domain 层 `orchestrator.py` 直接 import `sqlalchemy`，违反 ADR-0005 "零框架依赖"
- **根因**: 原型阶段快速实现，未分层
- **修复**: DB 查询移到 API 层，Orchestrator 接收预查询数据 → 后来 V1 整体删除，V2 从零开始严格遵守分层架构

---

## 4. 文件变更统计

| 操作 | 数量 | 主要文件 |
|------|------|---------|
| 新建 | 22 | EventBus, migrations, Service ABCs, IntentAnalyzer, AgentSelector, TaskDecomposer, ExecutionPlanner, plan_summary, AgentExecutor, StreamMerger, SharedContext, GroupChatStream, OrchestratorSummarizer, TokenEvent, CollaborationPanel, CollaborationView, orchestrator 9 篇文档 |
| 重写 | 5 | orchestrator_v2, agent_executor, chat_service_impl, test_orchestrator_v2, client.ts |
| 修改 | 15 | App.tsx, ChatWindow.tsx, GroupChatCreator.tsx, MessageBubble, SessionList, chatStore, types, api/chat.py, schemas.py, main.py, CONTEXT.md, CLAUDE.md, 各适配器 |
| 删除 | 3 | orchestrator.py (V1), test_orchestrator.py (V1), CollabProgressCard.tsx |

---

## 5. 测试覆盖演变

| 阶段 | 后端 | 前端 | E2E | 总计 |
|------|------|------|-----|------|
| Phase 2 完成 | 39 | 7 | 0 | 46 |
| Module 1 完成 (+5/27) | 68 | 7 | 0 | 75 |
| Module 4 开发中 (+5/28) | 106 | 9 | 0 | 115 |
| Step 5 完成 (+6/01) | 122 | 9 | 23 | 154 |
| Step 10 完成 (+6/01) | 65 新增 | 12 新增 | 3 实景脚本 | +77 |

**测试类型分布** (Phase 3 最终):
- Unit: ~60 条 (EventBus 10 + Migration 6 + SessionService 13 + Orchestrator 33)
- API 集成: ~50 条
- E2E (Playwright): 23 条
- 前端 vitest: 9 条

---

## 6. 架构决策时间线

| 日期 | 决策 | 关联 ADR |
|------|------|---------|
| 5/27 | Phase 3 启动 — 8 模块并行策略 | phase3-modules.md |
| 5/28 | Orchestrator V2 Pipeline 四阶段 + 3 执行模式 | ADR-0007 v1.0 |
| 5/28 | Phase 3 模块化拆解 + 并行开发指南 | phase3-parallel-guide.md |
| 6/01 | Grill 1: 9 项架构决议 (组件拆分/链式自动/角色模板/协作面板) | ADR-0007 v1.1 |
| 6/01 | Grill 2: 混合 DAG + 上下文共享 + 面板气泡混合 + 中枢总结 | ADR-0007 v1.3 |
| 6/02 | **策略修正**: 发现 8 模块并行策略失败 → 功能板块制 | ADR-0008 |
| 6/02 | 文档治理规则 + 周期性审计 | ADR-0008 §9 |

---

## 7. 关键方法总结

### 做得好的
- **Grill Sessions**: 4 次极限追问快速收敛架构设计，避免了"边写边猜"的低效迭代
- **E2E 先行**: E2E 测试在设计阶段就介入，发现了 3 个仅靠单元测试无法覆盖的阻断 Bug
- **QA Audit 文化**: 人工验收 (非自动化测试) 发现了 `asyncio.wait_for` + async generator 的致命问题
- **自动化优先**: 链式触发、角色分配全部自动完成，无需用户配置

### 需要改进的
- **模块选择失焦**: 优先攻克最难的 Orchestrator，导致简单模块 (消息操作/搜索) 完全遗留
- **PRD 锚定不足**: 开发过程中没有人定期回头对照 PRD，导致 CLI 适配器完全被遗忘
- **文档债积累**: ADR 编号错位、幽灵引用等问题在 Phase 3 全程累积未被修复
- **虚假并行**: 并行开发策略在单人团队中根本不可执行

### 对后续 Phase 的指导
1. **功能板块制** — 每板块完整交付，严禁跨板块同时开发
2. **PRD 为唯一权威源** — 每个板块启动前对照 PRD 检查符合性
3. **板块结束时立即审计** — 不累积文档债到下一板块
4. **先易后难** — 优先实现用户直接感知的功能，架构修正放在中期
