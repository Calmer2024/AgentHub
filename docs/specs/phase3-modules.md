# Phase 3 模块化开发计划

**版本**: v1.0
**创建日期**: 2026-05-28
**状态**: Draft
**关联**: [Phase 3 Spec](phase3-enhancements-spec.md), ADR-0005, ADR-0008

---

## 1. 动机

原始 Phase 3 Spec 将三大方向 (A: 智能协作, B: 产物深化, C: 体验闭环) 压缩在一份 500 行文档中，一次性开发不可行。本文件将其拆解为 **8 个渐进模块**，明确依赖关系、复杂度、和并行开发策略。

---

## 2. 模块总览

```
Module 1 ─── 基础设施 (已完成)
  ├─ Module 2 ─── 消息操作 (reply/regenerate/pin)
  ├─ Module 3 ─── 消息搜索 (FTS5)         ← 可与 Module 2 并行
  ├─ Module 4 ─── Orchestrator 核心        ← 高复杂度，需 ADR-0008
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

### Module 4: Orchestrator 核心 🔴 高复杂度

| 维度 | 内容 |
|------|------|
| **范围** | Pipeline 四阶段, L1 意图识别, L2 任务拆解, Agent 评分, SSE 生命周期事件, ContextManager 集成 |
| **设计文档** | **[ADR-0008](../adr/0008-orchestrator-architecture.md)** — 深度架构设计 |
| **依赖** | Module 1 (EventBus, ContextManager) |
| **复杂度** | **XL** |
| **不可并行** | 需要 1 人专注开发 |

核心工作:
1. 完善 `orchestrator_v2.py` 的 Pipeline（当前为 V1 原型）
2. `AgentExecutor` 的三种执行模式 (single/parallel/chain)
3. ContextManager 全量集成（Token 预算 + Pin 优先级 + FIFO 截断）
4. SSE 事件标准化：`orchestrator.task_started/completed`, `agent.call_started/completed`
5. 前端：`OrchestratorBanner` 增强、`CollabProgressCard` 完成态更新

详细设计见 **[ADR-0008: Orchestrator 架构设计](../adr/0008-orchestrator-architecture.md)**

### Module 5: 链式协作

| 维度 | 内容 |
|------|------|
| **范围** | Chain pipeline: Agent A 产出 → Agent B 输入（摘要模式展示） |
| **前端** | `CollabProgressCard.tsx` 增强 (展开查看中间过程) |
| **依赖** | Module 4 (Orchestrator Core, AgentExecutor.execute_chain) |
| **复杂度** | M |
| **关键挑战** | 中间产物格式化；超长内容截断注入 prompt；前端折叠/展开动画 |

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
| M4 | **XL** | 4 | 2 | 0 | 35 |
| M5 | M | 1 | 1 | 0 | 12 |
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
| M4 | **→ [ADR-0008](../adr/0008-orchestrator-architecture.md)** (独立深度设计) |
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
