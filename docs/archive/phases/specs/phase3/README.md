# Phase 3: Orchestrator + 基础设施 ✅ COMPLETED

**关联 ADR**: [ADR-0007](../../../../adr/0007-Orchestrator%20架构设计.md)
**开发策略**: [ADR-0008](../../../../archive/adr/0008-revised-development-strategy.md) §3

---

## 1. 交付总览

Phase 3 在基础设施之上构建了完整的 Orchestrator 智能调度引擎。

### 1.1 基础设施 (Module 1)

| 交付物 | 文件 | 测试 |
|--------|------|------|
| EventBus (InMemory) | `backend/app/event_bus/` | 10 unit |
| 6 个数据库迁移 | `backend/migrations/` | 6 unit |
| MessageService ABC | `backend/app/services/message_service.py` | - |
| ChatService ABC | `backend/app/services/chat_service.py` | - |
| SessionService | `backend/app/services/session_service.py` | 13 unit |

### 1.2 Orchestrator 核心 (Module 4 + 5)

| 交付物 | 文件 | 测试 |
|--------|------|------|
| IntentAnalyzer | `backend/app/domain/intent_analyzer.py` | 33 unit (含 orchestrator) |
| AgentSelector | `backend/app/domain/agent_selector.py` | ↑ |
| TaskDecomposer (6 角色) | `backend/app/domain/task_decomposer.py` | ↑ |
| ExecutionPlanner (DAG) | `backend/app/domain/execution_planner.py` | ↑ |
| AgentExecutor (4 模式) | `backend/app/services/agent_executor.py` | 122 backend |
| SharedContext | `backend/app/services/shared_context.py` | ↑ |
| OrchestratorSummarizer | `backend/app/services/orchestrator_summarizer.py` | ↑ |
| CollaborationPanel | `frontend/src/components/CollaborationPanel.tsx` | 9 vitest + 23 E2E |
| SSE 协议 (6 + phase_change) | `backend/app/api/chat.py` | ↑ |

**累计测试**: 122 backend + 9 frontend + 23 E2E = **154 条**

---

## 2. 子文档

| 文档 | 内容 |
|------|------|
| [01-infrastructure-spec.md](01-infrastructure-spec.md) | EventBus + 迁移 + Service ABC |
| [02-orchestrator/README.md](02-orchestrator/README.md) | Orchestrator 完整设计文档 (9 篇) |

---

## 3. 架构成果

- **Pipeline 四阶段**: ContextAssembly → AgentSelection → ExecutionPlanning → Lifecycle
- **4 种执行模式**: Single / Parallel / Chain / DAG (混合调度)
- **6 种动态角色**: planner / executor / reviewer / researcher / synthesizer / critic
- **上下文共享**: 对话流共享 + Chain 定向注入 + SharedContext
- **自动化优先**: 链式触发、角色分配、Agent 选择全部自动完成，无需用户配置

---

## 4. 遗留（移入后续 Phase）

| 遗留项 | 移入 |
|--------|------|
| 消息 reply/regenerate/pin | Phase 4 |
| 消息全文搜索 FTS5 | Phase 4 |
| 产物版本 + Diff | Phase 5 |
| 产物在线编辑 (Tool Calling) | Phase 5 |
| CLI PTY 适配器 | Phase 6 |
| 运行可控性 + 审批 + 环境体检 | Phase 7 |
