# Phase 3 并行开发指南

**版本**: v1.0
**创建日期**: 2026-05-28
**目标读者**: 开发团队成员、AI Agent

---

## 1. 为什么需要并行开发

Phase 3 包含 8 个模块，其中多个模块**可以同时开发**，因为它们操作不同的代码区域、不同的数据库表、不同的前端组件。合理的并行化可以将总开发时间从 **20 天串行** 压缩到 **12 天并行**。

---

## 2. 并行开发矩阵

```
模块       M1      M2     M3     M4     M5     M6     M7     M8
M1 (基础设施)  -      ✅     ✅     ✅     -      ✅     -      -
M2 (消息操作)  ✅      -     ✅     ❌     -      ✅     -      -
M3 (消息搜索)  ✅     ✅     -      ✅     -      ✅     -      -
M4 (Orch核心)  ✅     ❌     ✅     -      -      ✅     -      -
M5 (链式协作)  -      -      -     ❌     -      ✅     -      -
M6 (产物版本)  ✅     ✅     ✅     ✅     ✅     -      -      -
M7 (产物编辑)  -      -      -     -      -      ❌     -      -
M8 (收尾整合)  -      -      -     -      -      -      -      -

✅ = 可并行    ❌ = 依赖强耦合，需要串行    - = 无直接依赖
```

---

## 3. 两人团队分工（推荐）

```
          Week 1-2          Week 3-4          Week 5
Dev A:  M2 (消息操作)  →  M4 (Orch核心)  →  M5 (链式)
Dev B:  M3 (消息搜索)  →  M6 (产物版本)  →  M7 (产物编辑)
                              ↓
                        M8 (合流收尾, 共同)
```

### Dev A 详细路径

| Sprint | 模块 | 关键文件 | 测试 |
|--------|------|---------|------|
| 1 | M2: 消息操作 | `api/messages.py`, `services/message_service_impl.py`, `MessageActions.tsx`, `ReplyPreview.tsx` | 20 条 |
| 2 | M4: Orchestrator | `domain/orchestrator_v2.py`, `services/agent_executor.py`, `CollabProgressCard.tsx` | 35 条 |
| 3 | M5: 链式协作 | `services/agent_executor.py` (chain mode) | 12 条 |

### Dev B 详细路径

| Sprint | 模块 | 关键文件 | 测试 |
|--------|------|---------|------|
| 1 | M3: 消息搜索 | `api/messages.py` (search), `services/message_service_impl.py` (search), `SearchPanel.tsx` | 10 条 |
| 2 | M6: 产物版本 | `api/artifacts.py`, `services/artifact_service.py`, `VersionHistory.tsx`, `DiffViewer.tsx` | 18 条 |
| 3 | M7: 产物编辑 | `api/artifacts.py` (edit), `CodeSelector.tsx`, tool calling 集成 | 25 条 |

---

## 4. 协作契约：避免 merge conflict

### 4.1 API 路由文件分离

**当前问题**: `api/chat.py` 和 `api/sessions.py` 是共享文件，两个开发者同时修改会冲突。

**解决方案**: 新增独立路由文件，通过 `api/__init__.py` 聚合：

```
api/
  __init__.py      ← 只有 import router, 极少改动
  chat.py          ← Dev A 修改（M2: regenerate endpoint）
  sessions.py      ← Dev B 只读
  messages.py      ← NEW: Dev A (reply/regenerate/pin) + Dev B (search)
  artifacts.py     ← Dev B 修改（M6: versions/diff, M7: edit）
```

**契约**: `api/__init__.py` 中按模块注册 router，每个 router 有独立 prefix。

### 4.2 Service 层分离

```
services/
  __init__.py
  schemas.py             ← 共享，加字段时两边通知
  message_service.py     ← ABC 定义 (Module 1 已完成)
  message_service_impl.py ← Dev A 实现 reply/regenerate/pin
                            Dev B 实现 search (不同方法，无冲突)
  session_service.py     ← 只读
  chat_service_impl.py   ← Dev A 修改（M4 Orchestrator）
  agent_executor.py      ← Dev A 修改（M4/M5）
  artifact_service.py    ← NEW: Dev B (M6/M7)
```

### 4.3 前端组件分离

```
components/
  MessageBubble.tsx      ← Dev A 添加 hover 操作栏
  ChatInput.tsx          ← Dev A 添加 ReplyPreview slot
  ChatWindow.tsx         ← Dev A 添加搜索框 + Orch 横幅
  MessageActions.tsx     ← NEW: Dev A
  ReplyPreview.tsx       ← NEW: Dev A
  SearchPanel.tsx        ← NEW: Dev B (独立组件)
  CollabProgressCard.tsx ← Dev A 增强
  GroupChatCreator.tsx   ← Dev A 增强
  ArtifactCard.tsx       ← Dev B 新增版本选择器
  DiffViewer.tsx         ← NEW: Dev B
  VersionHistory.tsx     ← NEW: Dev B
  CodeSelector.tsx       ← NEW: Dev B
```

### 4.4 数据模型共享

以下模型在 Module 1 中已完成，两边只读：

| 模型 | 表 | 关键字段 |
|------|-----|---------|
| Message | messages | parent_message_id, is_pinned |
| Artifact | artifacts | version, parent_artifact_id |

---

## 5. 接口契约：跨模块依赖

以下接口在 Module 1 中已定义为 ABC，实现方和调用方需要遵守：

### MessageService (Dev A 实现, Dev B 也调用)

```python
class MessageService(ABC):
    # Dev A 实现:
    async def reply_to_message(input, parent_id) -> MessageRead: ...
    async def regenerate_message(msg_id) -> AsyncIterator[str]: ...
    async def pin_message(msg_id) -> None: ...
    async def unpin_message(msg_id) -> None: ...
    async def get_pinned_messages(session_id) -> list[MessageRead]: ...

    # Dev B 实现:
    async def search_messages(session_id, query, limit) -> list[MessageRead]: ...

    # 共用:
    async def get_session_messages(session_id, limit, before) -> list[MessageRead]: ...
```

### ArtifactService (Dev B 实现)

```python
class ArtifactService:
    # Module 6 (Dev B):
    async def get_versions(artifact_id) -> list[ArtifactVersion]: ...
    async def get_diff(artifact_id, v1, v2) -> str: ...

    # Module 7 (Dev B):
    async def apply_edit(artifact_id, selection, instruction) -> ArtifactEditResult: ...
```

---

## 6. 每日同步检查点

| 时间 | 检查项 |
|------|--------|
| 每天开始 | `git pull --rebase` 同步对方代码 |
| 每天结束 | `pytest test_smoke.py test_api/ test_unit/` 通过后推送 |
| 模块完成 | 对方 Code Review → 合并到 `phase/main` |
| Sprint 结束 | 集成测试 `pytest test_api/` + `npx vitest run` + E2E |

---

## 7. 模块独立 Spec 索引

| 模块 | Spec 文件 | 架构设计 |
|------|----------|---------|
| M1 | [phase3.1-infrastructure-spec.md](phase3.1-infrastructure-spec.md) | ADR-0005 |
| M2 | [phase3.2-message-actions-spec.md](phase3.2-message-actions-spec.md) | - |
| M3 | [phase3.3-message-search-spec.md](phase3.3-message-search-spec.md) | - |
| M4 | [phase3.4-orchestrator-core-spec.md](phase3.4-orchestrator-core-spec.md) | **[ADR-0008](../adr/0008-orchestrator-architecture.md)** |
| M5 | [phase3.5-chain-collab-spec.md](phase3.5-chain-collab-spec.md) | ADR-0008 §4.4 |
| M6 | [phase3.6-artifact-versioning-spec.md](phase3.6-artifact-versioning-spec.md) | - |
| M7 | [phase3.7-artifact-editing-spec.md](phase3.7-artifact-editing-spec.md) | ADR-0005 §3 (BaseAgentAdapter tools) |
| M8 | [phase3.8-integration-spec.md](phase3.8-integration-spec.md) | - |
