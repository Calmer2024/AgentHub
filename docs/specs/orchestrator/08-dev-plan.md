# 08 — 开发计划

**最后更新**: 2026-06-01

---

## 1. 已完成 (5 Steps — Grill Part 1)

| Step | 名称 | 测试 |
|------|------|------|
| Step 1 | 领域层重构: 4 组件独立 + V1 删除 + Agent 元数据匹配 | 33 unit |
| Step 2 | 执行层完善: asyncio.timeout, 链中断, 全失败, 3 SSE 事件 | 117 backend |
| Step 3 | API 贯通: chainConfig 运行时 + PipelineRequest 透传 | 117 backend |
| Step 4 | 前端全链路: CollaborationView, StreamCallbacks, 删除链式开关 | 9 vitest + 23 E2E |
| Step 5 | 测试+文档+收尾: test_group_chat +5 条, phase3-dev-log | 122 backend |

**累计测试**: 122 backend + 9 frontend + 23 E2E = **154 条**。零回归。

## 2. 待实现 (Grill Part 2 — Phase 3.6 DAG)

### Step 6: SubTask DAG 模型

| 子任务 | 文件 | 预计行数 |
|--------|------|---------|
| SubTask 增加 `depends_on: list[str]` 字段 | `task_decomposer.py` | 10 |
| TASK_TEMPLATES 更新为带 depends_on 的完整 DAG | `task_decomposer.py` | 30 |
| `_assign_phases()`: 拓扑排序, 将 SubTask 分配到 Phase | `execution_planner.py` | 60 |
| DAGPhase 数据类 | `execution_planner.py` | 15 |

### Step 7: SharedContext + AgentExecutor._execute_dag()

| 子任务 | 文件 | 预计行数 |
|--------|------|---------|
| SharedContext 类 (共享上下文 + 定向注入) | `services/agent_executor.py` 或新文件 | 50 |
| `_execute_dag()` 方法 | `services/agent_executor.py` | 80 |
| `execute()` 入口增加 `mode="dag"` 分支 | `services/agent_executor.py` | 10 |
| `_execute_parallel_phase()` Phase 内并行 | `services/agent_executor.py` | 30 |
| phase_change TokenEvent + SSE | `agent_executor.py` + `chat_service_impl.py` | 30 |

### Step 8: SSE 协议 DAG 扩展

| 子任务 | 文件 | 预计行数 |
|--------|------|---------|
| `task_started` v2 (含 phases DAG) | `chat_service_impl.py` | 20 |
| `phase_change` SSE 事件 | `chat_service_impl.py` | 15 |
| `agent.start` 增加 role + phase 字段 | `chat_service_impl.py` | 5 |
| 前端 `onPhaseChange` 回调 | `client.ts` | 15 |

### Step 9: 前端 CollaborationPanel + 角色气泡

| 子任务 | 文件 | 预计行数 |
|--------|------|---------|
| CollaborationPanel 组件 (DAG 流程图) | `CollaborationPanel.tsx` (新) | 150 |
| MessageBubble 扩展 (role badge + 彩色竖线) | `MessageBubble.tsx` | 40 |
| ChatWindow 集成 CollaborationPanel | `ChatWindow.tsx` | 30 |
| Phase 并行气泡同时创建 | `App.tsx` | 30 |
| 前端 types 更新 (DAGPhase, PhaseChangeEvent) | `types/index.ts` | 20 |

### Step 10: 测试 + 文档 + 收尾

| 子任务 | 预计测试数 |
|--------|----------|
| SubTask DAG + 拓扑排序 单元测试 | 6 |
| SharedContext + _execute_dag 集成测试 | 8 |
| DAG 群聊全链路 SSE 验证 | 5 |
| E2E: 混合协作场景 (先设计→并行实现→审查) | 3 |
| 文档更新 (本文档集) | - |

**目标测试**: 新增 22 条，累计 176 条。

## 3. 依赖关系

```
Step 6 ──→ Step 7 ──→ Step 8 ──→ Step 9 ──→ Step 10
  DAG模型    Executor   SSE协议   前端组件    测试收尾
```

Steps 6-10 必须在 Steps 1-5 全部通过的基础上进行。Step 1-5 已交付。

## 4. 风险

| 风险 | 缓解 |
|------|------|
| DAG 拓扑排序逻辑复杂, 模板可能不完全覆盖真实场景 | Phase 3 接受模板覆盖不足, Phase 4 LLM 动态补充 |
| 并行 Phase 内所有 Agent 共享上下文可能产生数据竞争 | SharedContext 使用追加操作 (只读 + 追加), 不涉及修改删除 |
| CollaborationPanel DAG 可视化复杂度 | 先实现简单节点+箭头, 动画/交互增强可降级 |
