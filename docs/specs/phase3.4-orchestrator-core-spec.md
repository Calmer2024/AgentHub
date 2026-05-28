# Spec: Phase 3.4 — Orchestrator 核心

**版本**: v1.0 | **状态**: Draft
**架构设计**: **[ADR-0008](../adr/0008-orchestrator-architecture.md)** (必读)
**关联**: [Phase 3 Spec](phase3-enhancements-spec.md) §5.1.1-5.1.4
**依赖**: Module 1 (EventBus, ContextManager)

---

## 1. 范围

Pipeline 四阶段 + ContextManager 集成 + SSE 事件标准化。

> 深度架构设计见 **[ADR-0008](../adr/0008-orchestrator-architecture.md)**。本文件为执行规格。

## 2. 交付清单

### 2.1 Domain 层 (纯逻辑)

| 文件 | 组件 | 状态 |
|------|------|------|
| `domain/orchestrator_v2.py` | Pipeline 四阶段 | 原型已存在 |
| `domain/context_manager.py` | Token 预算 + Pin 优先级 + FIFO | ✅ 已实现 |
| `domain/intent_analyzer.py` | 从 orchestrator_v2 独立 | 待抽取 |

### 2.2 Service 层

| 文件 | 组件 | 状态 |
|------|------|------|
| `services/agent_executor.py` | Single/Parallel/Chain 执行 | 原型已存在 |
| `services/chat_service_impl.py` | Thin coordinator | 已重构 |

### 2.3 Infrastructure 层

| 文件 | 组件 | 状态 |
|------|------|------|
| `infrastructure/stream_merger.py` | 交错合并 | ✅ 已实现 |

### 2.4 前端

| 组件 | 说明 |
|------|------|
| `ChatWindow.tsx` | Orchestrator 进度横幅增强 |
| `CollabProgressCard.tsx` | 完成态更新: 单 Agent 结果摘要 |

## 3. 行为规格

### 3.1 L1: 意图识别 + Agent 选择

1. 用户在群聊中发送消息（未 @）→ Pipeline Stage 2
2. IntentAnalyzer 匹配关键词 → code_gen / research / design_ui / general_qa
3. AgentSelector 按评分矩阵排序 → 返回排序后的 Agent 列表
4. 有 @mention → 跳过意图分析，直接精确匹配

### 3.2 L2: 任务拆解

1. 检测复杂标记 ("前后端"、"都要" 等) → `TaskDecomposer.is_complex()`
2. 按 `TASK_TEMPLATES` 拆解 → 子任务匹配 Agent
3. EventBus 发布 `ORCHESTRATOR_TASK_STARTED`
4. 两个 Agent 并行执行，各自独立 SSE 流

### 3.3 ContextManager 集成

1. 每次发消息前 → Pipeline Stage 1 → `ContextManager.assemble()`
2. Pin 消息自动插入上下文前列
3. 超 budget → FIFO 截断 → `result.truncated=True` → 日志记录

## 4. 验收标准

Spec 6.1:
- [ ] 群聊未 @ → Orchestrator 根据意图自动选择 Agent
- [ ] 复杂请求("前后端都要") → 拆解为多个子任务 + 分配到不同 Agent
- [ ] 会话 20+ 轮 → 早期非 Pin 消息被截断
- [ ] SSE 事件: `orchestrator.task_started/completed`, `agent.call_started/completed`

## 5. 测试

- Pipeline 单元: 20 条 (已完成)
- AgentExecutor 集成: single/parallel/chain + 错误处理 → 15 条
- E2E: 群聊未@ → Orchestrator banner; 复杂请求 → 拆解验证
- 目标: 35 条
