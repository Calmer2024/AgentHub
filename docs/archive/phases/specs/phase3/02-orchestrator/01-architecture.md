# 01 — Orchestrator 架构总览

**关联 ADR**: [ADR-0007](../../../../../adr/0007-orchestrator-architecture.md) (决策理由)
**关联实现**: `backend/app/domain/orchestrator_v2.py`

---

## 1. 系统定位

Orchestrator 是 AgentHub 群聊模式的智能调度核心。它在架构中处于 **Domain 层** — 纯逻辑，零 FastAPI/SQLAlchemy 依赖。

```
Frontend (React)
  → API Gateway (FastAPI + WebSocket)
    → Service Layer (ChatServiceImpl) ← thin coordinator
      → Domain Layer (Orchestrator)   ← 本文档范围
        → Infrastructure (Agent Adapters, EventBus)
```

## 2. Pipeline 四阶段

```
PipelineRequest { session_id, content, mentions, member_agents, ... }
    │
    ▼
┌── Stage 1: Context Assembly ──────────────────────────────────┐
│  ContextManager.assemble()                                    │
│  · token 预算控制 (context_budget=100K, reserve_tokens=4096)  │
│  · Pin 消息优先级 (最多占用 50% 预算)                         │
│  · FIFO 截断 (超预算时从最早消息开始丢弃)                     │
│  输出: assembled_messages, truncated                          │
└───────────────────────────────────────────────────────────────┘
    │
    ▼
┌── Stage 2: Agent Selection ───────────────────────────────────┐
│  IntentAnalyzer.analyze(content) → IntentAnalysis             │
│  AgentSelector.select(tags, candidates, mentions) → ScoredAgent[]│
│  · @mention 精确匹配 (Agent.name, 最高优先)                   │
│  · 标签匹配 (required_tags vs Agent.description/system_prompt)│
│  · Fallback (全部返回)                                        │
│  输出: 排序后的 Agent 列表                                    │
└───────────────────────────────────────────────────────────────┘
    │
    ▼
┌── Stage 3: Execution Planning ────────────────────────────────┐
│  ExecutionPlanner.plan(agents, content, messages)              │
│  优先级链:                                                    │
│    1. chain_config 存在 → mode="chain"                        │
│    2. is_chain(content) AND agents >= 2 → mode="chain" (自动) │
│    3. is_complex(content) AND agents >= 2 → mode="parallel"   │
│    4. agents == 1 → mode="single"                             │
│    5. agents >= 2 → mode="parallel" (all primary)             │
│  最终目标: DAG 拓扑排序 (见 03-task-decomposition.md)         │
└───────────────────────────────────────────────────────────────┘
    │
    ▼
┌── Stage 4: Lifecycle Events ──────────────────────────────────┐
│  EventBus.publish(ORCHESTRATOR_TASK_STARTED, ...)             │
│  输出: PipelineResult { agent_calls, execution_mode, ... }    │
└───────────────────────────────────────────────────────────────┘
    │
    ▼
AgentExecutor.execute(calls, mode)
  ├── mode="single"   → _execute_single  (60s 超时)
  ├── mode="parallel" → _execute_parallel (StreamMerger)
  ├── mode="chain"    → _execute_chain   (角色注入 + 中断)
  └── mode="dag"      → _execute_dag     (✅ 已实现)
```

## 3. 组件树

```
OrchestratorV2 (thin coordinator, ~170 行)
├── IntentAnalyzer     (~90 行)  意图分析: 关键词 → IntentAnalysis
├── AgentSelector      (~110 行) Agent 选择: 标签匹配 → ScoredAgent[]
├── TaskDecomposer     (~130 行) 任务拆解: 6 角色 + depends_on DAG
└── ExecutionPlanner   (~180 行) 执行计划: 优先级链 → ExecutionPlan
```

每个组件独立文件，独立测试。组件之间通过 `OrchestratorV2.run()` 串联。

## 4. 执行模式状态机

```
                    ┌──────────┐
                    │  Start   │
                    └────┬─────┘
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
      ┌────────┐  ┌──────────┐  ┌─────────┐
      │ single │  │ parallel │  │  chain  │
      │1 agent │  │ N agents │  │ A→B→C   │
      └───┬────┘  └────┬─────┘  └────┬────┘
          │            │             │
          ▼            ▼             ▼
      ┌──────────────────────────────────────┐
      │         AgentExecutor.execute()       │
      │  ┌────────┐ ┌────────┐ ┌──────────┐ │
      │  │ direct │ │ gather │ │ seq+inj  │ │
      │  └────────┘ └────────┘ └──────────┘ │
      └──────────────────────────────────────┘
                         │
                         ▼
              ┌──────────────────┐
              │  SSE TokenEvent  │
              │  Stream → 前端    │
              └──────────────────┘
```

## 5. 数据流全链路

```
POST /sessions/{id}/chat
  body: { content, mentions?, chainConfig? }
    │
    ▼
ChatServiceImpl._group_chat()
    ├── 查询 SessionMembers → member_agents
    ├── 构建 PipelineRequest
    │
    ▼
OrchestratorV2.run(req) → PipelineResult
    │
    ▼
AgentExecutor.execute(calls, mode)
    → TokenEvent 流
    │
    ▼
ChatServiceImpl 格式化 SSE
    → orchestrator.route / task_started / agent.start / token / chain_step / task_completed
    │
    ▼
前端 SSE reader (client.ts)
    → onRoute / onTaskStarted / onChainStep / onAgentToken / onTaskCompleted
    │
    ▼
App.tsx → ChatWindow → CollaborationView + MessageBubble
```

## 6. 与外部系统的集成

| 外部系统 | 集成点 | 方向 |
|---------|--------|------|
| ContextManager | Stage 1: assemble() | Orchestrator → ContextManager |
| EventBus | Stage 4: publish(task_started/completed) | Orchestrator → EventBus |
| CLI Agent Runner | AgentExecutor: execute CLI Agent call | Executor → CLI adapter |
| StreamMerger | AgentExecutor._execute_parallel | Executor → Infrastructure |
| ChatServiceImpl | send_message_stream → _group_chat | Service → Orchestrator |
| WebSocket Manager | SSE 广播: message.completed, token | Service → WS |
