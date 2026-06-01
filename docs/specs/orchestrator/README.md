# AgentHub Orchestrator — 设计文档总览

**最后更新**: 2026-06-01
**架构决策**: [ADR-0008](../../adr/0008-orchestrator-architecture.md)
**当前分支**: `phase/phase3-smart-collab`

---

## 阅读顺序

| 序号 | 文档 | 内容 | 读者 |
|------|------|------|------|
| 1 | [01-architecture.md](01-architecture.md) | 架构总览: Pipeline 四阶段、组件树、执行模式状态机、关键决策 | 所有人 |
| 2 | [02-agent-selection.md](02-agent-selection.md) | 意图分析 (IntentAnalyzer) + Agent 选择 (AgentSelector) + 标签匹配 | 后端开发者 |
| 3 | [03-task-decomposition.md](03-task-decomposition.md) | 任务拆解 (TaskDecomposer) + 6 角色模板 + DAG 依赖模型 | 后端开发者 |
| 4 | [04-execution-engine.md](04-execution-engine.md) | AgentExecutor: single/parallel/chain/dag、超时、中断、全失败 | 后端开发者 |
| 5 | [05-collaboration-interaction.md](05-collaboration-interaction.md) | 最终交互设计: 面板+气泡混合渲染、上下文共享机制、协作时序 | 全员 |
| 6 | [06-sse-protocol.md](06-sse-protocol.md) | SSE 事件协议: 全部事件类型、字段定义、序列示例 | 前后端 |
| 7 | [07-frontend.md](07-frontend.md) | 前端组件: CollaborationPanel、ChatWindow、GroupChatCreator | 前端开发者 |
| 8 | [08-dev-plan.md](08-dev-plan.md) | 开发计划: 已完成 vs 待实现，下一步 Step 计划 | 开发者 |
| 9 | [09-dev-log.md](09-dev-log.md) | 开发日志: 时间线、Bug 与教训 | 所有人 |

> **ADR-0008** 在 `docs/adr/0008-orchestrator-architecture.md`。收录了所有架构决策的"是什么 + 为什么"。本文档集只描述"是什么 + 怎么做"，不重复决策理由。

---

## 当前完成度

| 模块 | 状态 | 说明 |
|------|------|------|
| Pipeline 四阶段 | ✅ 已交付 | ContextAssembly → AgentSelection → ExecutionPlanning → Lifecycle |
| IntentAnalyzer | ✅ 已交付 | 关键词规则 + 能力标签提取 |
| AgentSelector | ✅ 已交付 | Agent.description + system_prompt 标签匹配 |
| TaskDecomposer | ✅ 已交付 | 6 角色模板 + is_complex/is_chain 检测 |
| ExecutionPlanner | ⚠️ 部分 | 优先级链已实现；DAG 拓扑排序未实现 |
| AgentExecutor (_execute_single) | ✅ 已交付 | 含 60s 超时 (asyncio.timeout) |
| AgentExecutor (_execute_parallel) | ✅ 已交付 | StreamMerger 交错合并 |
| AgentExecutor (_execute_chain) | ✅ 已交付 | 角色 Prompt 注入 + 中断检测 |
| AgentExecutor (_execute_dag) | ❌ 未实现 | 混合 DAG 执行器 |
| SSE 协议 (route/task/chain) | ✅ 已交付 | 6 种事件类型 |
| SSE 协议 (phase_change) | ❌ 未实现 | DAG Phase 切换事件 |
| 上下文共享 (SharedContext) | ❌ 未实现 | 对话流共享 + 定向注入 |
| CollaborationPanel (DAG 图) | ❌ 未实现 | 当前为 CollaborationView |
| Agent 气泡 (角色标签) | ❌ 未实现 | 当前无角色标签和 Phase 分组 |
| 错误处理矩阵 | ✅ 已交付 | 超时/不可用/全失败/链中断/截断 |
| 测试覆盖 | ⚠️ 部分 | Unit 33 + API 59 + E2E 23 = 115；缺 AgentExecutor 集成测试和 DAG 测试 |

---

## 文档 vs 旧 Phase 编号

| 旧编号 | 内容 | 新位置 |
|--------|------|--------|
| Phase 3.4 | Orchestrator 核心 (Pipeline + 组件 + ContextManager) | 01, 02, 03, 04 |
| Phase 3.5 | 链式协作 (Chain + CollabProgressCard) | 04 (chain), 06, 07 |
| Phase 3.6 | 协作交互设计 (DAG + 上下文共享 + 面板气泡) | 05, 07 |
| ADR-0008 | 架构决策 | docs/adr/0008-orchestrator-architecture.md |

> 旧 spec 文件 (`phase3.4-*`, `phase3.5-*`, `phase3.6-*`) 标记为 archived，以本文档集为准。
