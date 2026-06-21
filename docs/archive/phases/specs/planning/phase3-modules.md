# Phase 3 模块化开发计划 (历史参考)

> ⚠️ **本文档为历史规划文档**，内容已被 [ADR-0008](../../../../adr/0008-revised-development-strategy.md) 替代。
> 其中的 `phase3-enhancements-spec.md` 从未作为独立文件创建——Phase 3 的实际 Spec 分散在 `phase3.1-3.8` 各独立文件中，
> 现在位于 [docs/specs/phase3/](../phase3/) 和 [docs/specs/phase4/](../phase4/) 等目录。
> 保留此文档仅供了解 Phase 3 开发过程的历史背景。

**版本**: v1.0
**创建日期**: 2026-05-28
**状态**: Superseded by ADR-0008
**关联**: [ADR-0008](../../../../adr/0008-revised-development-strategy.md), ADR-0005, ADR-0007

---

## 1. 动机

原始 Phase 3 Spec 将三大方向 (A: 智能协作, B: 产物深化, C: 体验闭环) 压缩在一份 500 行文档中，一次性开发不可行。本文件将其拆解为 **8 个渐进模块**，明确依赖关系、复杂度、和并行开发策略。

---

## 2. 模块总览

```
Module 1 ─── 基础设施 (已完成)
  ├─ Module 2 ─── 消息操作 (reply/regenerate/pin)
  ├─ Module 3 ─── 消息搜索 (FTS5)         ← 可与 Module 2 并行
  ├─ Module 4 ─── Orchestrator 核心        ← 高复杂度，需 ADR-0007
  │     ├─ Module 5 ─── 链式协作
  │     └─ (ContextManager 集成内嵌于 M4)
  ├─ Module 6 ─── 产物版本 + Diff
  │     └─ Module 7 ─── 产物在线编辑       ← 高复杂度
  └─ Module 8 ─── Store 拆分 + 体验收尾
```

## 3. 各模块详情

### Module 1: 基础设施 ✅ COMPLETED

| 维度 | 内容 |
|------|------|
| **范围** | EventBus, 6 个 DB 迁移, MessageService/ChatService ABC, SessionService, BaseAgentAdapter tools 参数 |
| **文件** | `event_bus/`, `migrations/`, `services/`, `models/`, `agents/base.py` |
| **依赖** | 无 |
| **复杂度** | M |
| **测试** | 29 条 Unit + 39 条 API = 68 条 |
| **产出** | 所有后续模块的基础 |

### Module 2: 消息操作

| 维度 | 内容 |
|------|------|
| **范围** | `POST /messages/{id}/reply`, `POST /messages/{id}/regenerate`, `POST/DELETE /messages/{id}/pin` |
| **前端** | `MessageActions.tsx` (hover 操作栏), `ReplyPreview.tsx` (引用卡片) |
| **依赖** | Module 1 (MessageService impl, DB 列: parent_message_id, is_pinned) |
| **可并行** | ✅ 与 Module 3 并行（不同 API 端点、不同前端组件） |
| **复杂度** | M |
| **关键挑战** | regenerate 的 SSE 流 + 原地替换；reply 的消息引用链；Pin 的 ContextManager 联动 |

**接口契约**:
```python
# MessageService (Module 1 已定义 ABC)
async def reply_to_message(input: MessageCreate, parent_message_id: str) -> MessageRead
async def regenerate_message(message_id: str) -> AsyncIterator[str]
async def pin_message(message_id: str) -> None
async def unpin_message(message_id: str) -> None
async def get_pinned_messages(session_id: str) -> list[MessageRead]
```

### Module 3: 消息搜索

| 维度 | 内容 |
|------|------|
| **范围** | `GET /messages/search?q=&session_id=&limit=`, FTS5 查询 + LIKE fallback |
| **前端** | `SearchPanel.tsx` (搜索框 + 结果列表 + 高亮跳转) |
| **依赖** | Module 1 (FTS5 虚拟表 + 触发器已在迁移中创建) |
| **可并行** | ✅ 与 Module 2 并行 |
| **复杂度** | S |
| **关键挑战** | FTS5 中文分词；搜索结果高亮；点击跳转到消息位置并闪烁 |

**接口契约**:
```python
# MessageService
async def search_messages(session_id: str, query: str, limit: int = 20) -> list[MessageRead]
```

### Module 4: Orchestrator 核心 ✅ 已交付 (Phase 3.4/3.5)

| 维度 | 内容 |
|------|------|
| **范围** | Pipeline 四阶段, 意图分析, Agent 元数据匹配, 任务拆解+6角色, 自动链式, SSE 生命周期事件, ContextManager 集成 |
| **设计文档** | **[docs/specs/phase3/02-orchestrator/](../phase3/02-orchestrator/README.md)** — 9 篇完整设计文档 |
| **架构 ADR** | **[ADR-0007](../../../../adr/0007-orchestrator-architecture.md)** |
| **状态** | ✅ **Phase 3.4 + 3.5 已交付** (Pipeline + 组件 + Chain + 错误处理) |
| **测试** | 122 backend + 9 frontend + 23 E2E = 154 条 |
| **遗留** | Phase 3.6 DAG 混合调度 (见 [08-dev-plan.md](../phase3/02-orchestrator/08-dev-plan.md)) |

已完成:
1. ✅ 4 组件独立 (IntentAnalyzer, AgentSelector, TaskDecomposer, ExecutionPlanner)
2. ✅ AgentExecutor 三种执行模式 (single/parallel/chain) + 60s 超时 + 中断 + 全失败兜底
3. ✅ SSE 6 种事件标准化 (route/task_started/agent.start/chain_step/task_completed/error)
4. ✅ 前端 CollaborationView + Orchestrator 横幅 + 删除链式开关
5. ✅ 协作状态持久化 (Zustand chatStore per-session)
6. ✅ 上下文截断检测 + Pin 优先级

待实现 (Phase 3.6):
- ❌ 混合 DAG 调度 (Phase 间串行, Phase 内并行)
- ❌ 上下文共享 (SharedContext) + 定向注入
- ❌ CollaborationPanel (DAG 流程图)
- ❌ Agent 聊天气泡角色标签
- ❌ AgentExecutor._execute_dag()

### Module 5: 链式协作 → 已合并入 Module 4

M5 的链式协作功能已在 M4 中完成。详见 [04-execution-engine.md](../phase3/02-orchestrator/04-execution-engine.md)。

### Module 6: 产物版本 + Diff

| 维度 | 内容 |
|------|------|
| **范围** | `GET /artifacts/{id}/versions`, `GET /artifacts/{id}/diff`, 版本链模型 |
| **前端** | `VersionHistory.tsx`, `DiffViewer.tsx` (react-diff-viewer-continued) |
| **依赖** | Module 1 (Artifact 模型: version, parent_artifact_id) |
| **可并行** | ✅ 与 Module 4 并行（不同代码区域） |
| **复杂度** | L |

### Module 7: 产物在线编辑 🔴 高复杂度

| 维度 | 内容 |
|------|------|
| **范围** | `POST /artifacts/{id}/edit`, `edit_artifact` tool schema, Tool Calling 集成, 降级策略 |
| **前端** | `CodeSelector.tsx`, Diff 确认/拒绝 UI |
| **依赖** | Module 6 (版本链), Module 1 (BaseAgentAdapter tools 参数) |
| **复杂度** | **XL** |
| **关键挑战** | Tool calling 响应解析 (各 provider 格式不同)；降级为上下文注入；Diff 生成 + 用户确认流程 |

### Module 8: Store 拆分 + 体验收尾

| 维度 | 内容 |
|------|------|
| **范围** | Zustand store 正式拆分 (chatStore/sessionStore/searchStore), SessionList 搜索跳转, 全局 UX polish |
| **依赖** | Module 2-7 全部完成后统一整合 |
| **复杂度** | S |

---

## 4. 依赖图

```
                    Module 1 (基础设施) ✅
                    /        |         \
                   /         |          \
          Module 2     Module 3      Module 6
        (消息操作)    (消息搜索)    (产物版本+Diff)
               \         |              \
                \        |               \
                 \   Module 4 (Orchestrator)  Module 7 (产物编辑)
                  \      /
                   \    /
                  Module 5 (链式协作)
                       |
                  Module 8 (Store拆分+体验收尾)
```

- **可并行开发的模块对**: (M2, M3), (M4, M6), (M2+M3 完成后的 M5, M7)
- **需要串行的关键路径**: M1 → M4 → M5 (Orchestrator 链路)

---

## 5. 复杂度矩阵

| 模块 | 复杂度 | 后端文件 | 前端文件 | 新增 API | 预估测试 |
|------|--------|---------|---------|---------|---------|
| M1 | M | 10 | 0 | 0 | 68 |
| M2 | M | 2 | 2 | 4 | 20 |
| M3 | S | 1 | 1 | 1 | 10 |
| M4 | **XL** (✅ Phase 3.4+3.5 已交付) | 9 | 4 | 0 | 154 |
| M5 | M (← 已合并入 M4) | - | - | - | - |
| M6 | L | 2 | 2 | 2 | 18 |
| M7 | **XL** | 3 | 3 | 1 | 25 |
| M8 | S | 0 | 4 | 0 | 8 |

---

## 6. 并行开发指南

详见 [Phase 3 并行开发指南](phase3-parallel-guide.md)

**两人团队最佳分工**:

```
Developer A: M2 (消息操作) → M4 (Orchestrator) → M5 (链式协作)
Developer B: M3 (搜索, 与 M2 同时) → M6 (产物版本) → M7 (产物编辑)
最后: 两人合流 M8 (Store 拆分 + 体验收尾)
```

**关键协作点**:
- M2 和 M4 共享 `parent_message_id`, `is_pinned` 数据模型——在 M1 中已定义
- M4 的 ContextManager 需要 M2 的 Pin 数据——接口已由 MessageService ABC 约定
- M6 和 M7 共享 `Artifact` 版本链模型——M6 先确定数据模型

---

## 7. 每个模块的 Spec 位置

复杂模块从主 Spec 中抽取到独立文件：

| 模块 | Spec 文件 |
|------|----------|
| M1 | 保留在 `phase3-enhancements-spec.md` §2-4,§7,§13 |
| M2 | 保留在 `phase3-enhancements-spec.md` §3.1(消息操作),§5.3.1-5.3.3 |
| M3 | 保留在 `phase3-enhancements-spec.md` §3.1(搜索),§5.3.4 |
| M4 | **→ [ADR-0007](../../../../adr/0007-orchestrator-architecture.md)** (独立深度设计) |
| M5 | 保留在 `phase3-enhancements-spec.md` §5.1.3 |
| M6 | 保留在 `phase3-enhancements-spec.md` §3.1(产物),§5.2.1 |
| M7 | 保留在 `phase3-enhancements-spec.md` §5.2.2-5.2.3 |
| M8 | 保留在 `phase3-enhancements-spec.md` §9.1 |

---

## 8. 开发顺序（推荐）

```
Sprint 1: M2 + M3 (并行, 3-4天) → 用户体验可感知的最大提升
Sprint 2: M4 (串行, 5-7天) → 最核心的智能协作大脑
Sprint 3: M5 + M6 (并行, 3-4天) → 链式协作 + 产物版本
Sprint 4: M7 (串行, 4-5天) → 产物在线编辑
Sprint 5: M8 (合流, 1-2天) → 收尾 + 全量回归
```
