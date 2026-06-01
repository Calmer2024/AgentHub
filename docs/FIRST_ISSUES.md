# 新成员推荐优先 Issue

**最后更新**: 2026-06-01
**目标读者**: 刚加入项目、希望快速上手的开发者

---

## 阅读顺序

1. 先读完 [ONBOARDING.md](ONBOARDING.md) + [CONTEXT.md](CONTEXT.md)
2. 启动项目，在浏览器中体验一遍完整流程（创建 Agent → 建单聊 → 建群聊 → 发消息）
3. 从下面选一个 Issue 开始

---

## Tier 1: 小规模熟悉项目 (1-2 天)

适合刚 fork 代码、想快速了解代码结构的开发者。

### Issue #1: AgentExecutor 集成测试补全

| 维度 | 内容 |
|------|------|
| **背景** | ADR-0008 §8 要求有独立的 `test_agent_executor.py`，当前不存在。AgentExecutor 的三个执行模式 (single/parallel/chain) 的测试分散在其他测试文件中 |
| **任务** | 新建 `backend/test_unit/test_agent_executor.py`，用 MockAgent 覆盖: single 正常流式、parallel 2 并发、chain A→B 顺序输出注入、chain 中断 |
| **文件** | `backend/test_unit/test_agent_executor.py` (新建) |
| **参考** | `backend/test_api/conftest.py` 中的 MockAgent, `backend/test_api/test_group_chat.py` 中的新测试 |
| **难度** | ⭐ |
| **预计** | 1 天 |

### Issue #2: IntentAnalyzer 技术标签扩展

| 维度 | 内容 |
|------|------|
| **背景** | 当前 `TECH_TAG_PATTERNS` 只有 14 个技术标签。用户输入 "帮我写一个 Rust WebSocket 服务器" → 只能匹配到 "后端"，无法匹配 "Rust" 和 "WebSocket" |
| **任务** | 新增至少 10 个技术标签 (Rust, Go, Docker, Kubernetes, Redis, MongoDB, GraphQL, WebSocket, gRPC, Nginx)，每个标签至少 3 个匹配关键词 |
| **文件** | `backend/app/domain/intent_analyzer.py` |
| **参考** | 文件中的 `TECH_TAG_PATTERNS` 字典 |
| **难度** | ⭐ |
| **预计** | 0.5 天 |

### Issue #3: 前端类型导出清理

| 维度 | 内容 |
|------|------|
| **背景** | `types/index.ts` 中有 `RouteAgent`, `CollabTask`, `ChainStep`, `ChainConfigInput` 等 Orchestrator 相关类型。部分类型可能只在一个组件中使用，可以就近定义 |
| **任务** | 审查 `types/index.ts`，将仅在一个组件中使用的类型移到该组件文件中，保留跨组件共享的类型在 `types/index.ts` |
| **文件** | `frontend/src/types/index.ts`, 各组件文件 |
| **参考** | TypeScript 的 `export interface` 就近原则 |
| **难度** | ⭐ |
| **预计** | 0.5 天 |

---

## Tier 2: 中等规模功能开发 (3-5 天)

适合已经跑通项目、理解核心数据流的开发者。

### Issue #4: Agent 聊天气泡角色标签

| 维度 | 内容 |
|------|------|
| **背景** | 当前 Agent 产出气泡和普通消息气泡完全一样 — 看不出是谁说的、什么角色。协作感缺失。详见 [orchestrator/07-frontend.md](specs/orchestrator/07-frontend.md) §3 |
| **任务** | 扩展 `MessageBubble` 组件: Agent 消息显示角色 badge (`[规划者]`/`[执行者]`...) + 左侧彩色竖线 (6 种角色各有颜色)。扩展 `agent.start` SSE 事件携带 `role` 字段 |
| **前端** | `MessageBubble.tsx`, `types/index.ts` |
| **后端** | `chat_service_impl.py` (agent.start 加 role) |
| **难度** | ⭐⭐ |
| **预计** | 3 天 |

### Issue #5: TaskDecomposer depends_on 字段

| 维度 | 内容 |
|------|------|
| **背景** | 当前 `SubTask` 无 `depends_on` 字段，无法声明任务间依赖。这是 DAG 调度的基础。详见 [orchestrator/03-task-decomposition.md](specs/orchestrator/03-task-decomposition.md) §4 |
| **任务** | 1) SubTask 增加 `depends_on: list[str]` 字段。2) TASK_TEMPLATES 更新为带 depends_on 声明。3) ExecutionPlanner 新增 `_assign_phases()` 拓扑排序方法。4) 单元测试 |
| **文件** | `domain/task_decomposer.py`, `domain/execution_planner.py`, `test_unit/test_orchestrator_v2.py` |
| **参考** | [orchestrator/03-task-decomposition.md](specs/orchestrator/03-task-decomposition.md) §4.2, §4.3 |
| **难度** | ⭐⭐ |
| **预计** | 4 天 |

### Issue #6: SharedContext 实现

| 维度 | 内容 |
|------|------|
| **背景** | 当前所有 Agent 接收相同的 input_messages，互不知晓对方的产出。需要 SharedContext 让 Agent 看到其他 Agent 说了什么。详见 [orchestrator/05-collaboration-interaction.md](specs/orchestrator/05-collaboration-interaction.md) §3 |
| **任务** | 实现 SharedContext 类 (对话流共享 + 定向注入)。Agent 完成后产出自动追加。依赖链上的前驱产出定向注入。集成到 AgentExecutor |
| **文件** | `services/agent_executor.py` 或新建 `domain/shared_context.py` |
| **参考** | [orchestrator/05-collaboration-interaction.md](specs/orchestrator/05-collaboration-interaction.md) §3.2 |
| **难度** | ⭐⭐ |
| **预计** | 4 天 |

---

## Tier 3: 核心架构升级 (1-2 周)

适合已经熟悉代码、想要参与核心功能设计的开发者。

### Issue #7: AgentExecutor._execute_dag() 混合执行器

| 维度 | 内容 |
|------|------|
| **背景** | 这是 Orchestrator 最终形态的核心: 同一请求内 Phase 间串行、Phase 内并行。依赖 Issue #5 (depends_on) 和 Issue #6 (SharedContext) 完成后才能开始。详见 [orchestrator/04-execution-engine.md](specs/orchestrator/04-execution-engine.md) §3.5 |
| **任务** | 实现 `_execute_dag()`: 按 Phase 拓扑顺序执行，Phase 内并行，Phase 间串行，phase_change 事件。集成 SharedContext |
| **文件** | `services/agent_executor.py`, `services/chat_service_impl.py` |
| **依赖** | Issue #5 + Issue #6 必须先完成 |
| **难度** | ⭐⭐⭐ |
| **预计** | 1 周 |

### Issue #8: CollaborationPanel DAG 可视化

| 维度 | 内容 |
|------|------|
| **背景** | 当前 CollaborationView 只展示简单任务列表。需要升级为 CollaborationPanel，展示 DAG 流程图 (Phase 节点 + 箭头 + 实时状态)。详见 [orchestrator/05-collaboration-interaction.md](specs/orchestrator/05-collaboration-interaction.md) §2.4 |
| **任务** | 新建 `CollaborationPanel.tsx`: Phase 节点 (角色图标 + Agent 名 + 状态圆点) + 箭头连接 + 展开/折叠。消费 `task_started` v2 (phases DAG) + `phase_change` SSE 事件 |
| **前端** | `CollaborationPanel.tsx` (新建), `ChatWindow.tsx`, `App.tsx`, `types/index.ts` |
| **后端** | `chat_service_impl.py` (task_started v2 + phase_change) |
| **依赖** | Issue #7 必须先完成 (需要 DAG 执行和 phase_change 事件) |
| **难度** | ⭐⭐⭐ |
| **预计** | 1 周 |

### Issue #9: 消息操作 (reply/regenerate/pin)

| 维度 | 内容 |
|------|------|
| **背景** | Phase 3 Module 2 — MessageService ABC 已定义接口，但无具体实现。API 路由和 DB 列 (parent_message_id, is_pinned) 已就位 |
| **任务** | 实现 MessageServiceImpl: reply_to_message, regenerate_message (SSE 流), pin_message, unpin_message。前端: MessageActions 操作栏 + ReplyPreview 引用卡片 |
| **文件** | `services/message_service_impl.py` (新建), `api/chat.py` 或新路由, `frontend/src/components/MessageActions.tsx` (新建) |
| **参考** | [phase3-modules.md](specs/phase3-modules.md) Module 2 |
| **难度** | ⭐⭐⭐ |
| **预计** | 1.5 周 |

---

## Issue 依赖图

```
Tier 1 (独立, 无依赖)
  ├── #1 AgentExecutor 测试
  ├── #2 技术标签扩展
  └── #3 类型清理

Tier 2 (可并行)
  ├── #4 角色标签
  ├── #5 depends_on 字段 ──── 依赖 ──── #7 _execute_dag
  └── #6 SharedContext ──────── 依赖 ──── #7 _execute_dag

Tier 3 (有依赖)
  ├── #7 _execute_dag ──────── 依赖 ──── #8 CollaborationPanel
  ├── #8 DAG 可视化
  └── #9 消息操作 (独立)
```

---

## 推荐路径

```
新手路径: #2 → #1 → #4 → #5
进阶路径: #5 → #6 → #7 → #8
独立路径: #9 (消息操作), #3 (类型清理)
```
