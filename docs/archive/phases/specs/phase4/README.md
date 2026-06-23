# Phase 4: 消息交互闭环 ✅ COMPLETED

**关联 ADR**: [ADR-0008](../../../../archive/adr/0008-revised-development-strategy.md) §4
**依赖**: Phase 3 (MessageService ABC, DB 列: parent_message_id, is_pinned, FTS5 触发器)
**状态**: 已完成
**完成日期**: 2026-06-02

---

## 1. 板块目标

用户可以在聊天中：
- **引用回复**历史消息，构建对话线索
- **重新生成** AI 的回复，不满意就再来一次
- **Pin 固定**关键消息作为长期上下文锚点
- **全文搜索**对话历史，快速定位关键讨论

---

## 2. 子模块

### Module 4A: 消息操作 (reply/regenerate/pin)

| 维度 | 内容 |
|------|------|
| **Spec** | [01-message-actions.md](01-message-actions.md) |
| **API** | `POST /messages/{id}/reply`, `POST /messages/{id}/regenerate`, `POST/DELETE /messages/{id}/pin` |
| **后端** | `SqlAlchemyMessageService` 实现 MessageService ABC 的 5 个方法 |
| **前端** | `MessageActions.tsx` (hover 操作栏), `ReplyPreview.tsx` (引用卡片) |
| **测试** | API + 组件 + 真实 HTTP 验收 |

### Module 4B: 全文搜索 (FTS5)

| 维度 | 内容 |
|------|------|
| **Spec** | [02-message-search.md](02-message-search.md) |
| **API** | `GET /messages/search?q=&session_id=&limit=` |
| **后端** | FTS5 查询 + LIKE fallback, snippet 高亮 |
| **前端** | `SearchPanel.tsx` (搜索框 + 结果列表 + 跳转闪烁) |
| **测试** | 中文关键词、空结果、FTS/LIKE fallback、跳转高亮 |

---

## 3. 验收标准

- [x] **4A-1**: 鼠标 hover 消息 → 显示 [引用] [重新生成] [Pin] [复制] 操作栏
- [x] **4A-2**: 点击 [引用] → 输入框上方出现引用卡片 → 发送后气泡显示引用预览 → 点击跳转原消息
- [x] **4A-3**: 点击 [重新生成] → 保留旧内容 → SSE 流式替换 → 超时 60s 后显示"重新生成超时"
- [x] **4A-4**: 点击 [Pin] → 消息标记 → ContextManager 优先注入 Pin 消息 → 超出 token 预算时自动淘汰最旧
- [x] **4A-5**: AI 消息才显示 [重新生成]；任何消息都可 Pin/引用
- [x] **4A-6**: 真实 UI 中引用历史 AI 回复后再发送，新 `/chat` 请求带 `parentMessageId`，落库保存 `metadata.replyReference`，Agent 回复可证明已感知被引用内容
- [x] **4B-1**: `Ctrl+K` 或点击搜索 → 搜索面板滑出
- [x] **4B-2**: 输入中文关键词 → 返回高亮结果列表（含上下文片段）
- [x] **4B-3**: 点击搜索结果 → 滚动到消息位置 → 背景闪烁 2s
- [x] **4B-4**: FTS5 查询失败/无结果 → 自动降级为 SQL LIKE → 结果正确返回
- [x] **集成**: 单聊和群聊中 Pin 上下文均接入 ContextManager/Orchestrator

---

## 4. 接口契约

### 与 Phase 3 的契约（已由 Module 1 定义）

```python
# MessageService ABC — Phase 4 负责实现以下 5 个方法：
async def reply_to_message(input: MessageCreate, parent_message_id: str) -> MessageRead
async def regenerate_message(message_id: str) -> AsyncIterator[str]
async def pin_message(message_id: str) -> None
async def unpin_message(message_id: str) -> None
async def get_pinned_messages(session_id: str) -> list[MessageRead]
async def search_messages(session_id: str, query: str, limit: int = 20) -> list[MessageRead]
```

### 为 Phase 5/7 预留

- Pin 数据已由 ContextManager 在单聊与群聊 Orchestrator Pipeline 中使用
- 搜索结果跳转已在当前会话内完成；跨会话搜索可在 Phase 7 的全局体验中强化

---

## 5. 实现记录

- 新增 `backend/app/services/message_service_sqlalchemy.py`，实现 reply/regenerate/pin/search 与 DB→API 序列化。
- 新增 `backend/app/api/messages.py`，提供 `/api/messages/*` Phase 4 API。
- `ChatServiceImpl` 发送单聊时通过 ContextManager 组装上下文并传入 pinned ids；`GroupChatStream` 将 pinned ids 交给 `OrchestratorV2.PipelineRequest`。
- 前端新增 `MessageActions.tsx`、`ReplyPreview.tsx`、`SearchPanel.tsx`，并接入 `ChatWindow`、`ChatInput`、`useSendMessage`、`client.ts`。
- 新增迁移 `008_fix_messages_fts_update_trigger.sql`，修复 SQLite FTS5 trigger 在非 content 更新时导致 `SQL logic error` 的问题。

## 6. 验收记录

2026-06-02 执行：

```bash
cd backend && .\venv\Scripts\python.exe -m pytest test_unit test_api test_smoke.py -q
# 154 passed

cd frontend && npm exec vitest run
# 21 passed

cd frontend && npm run build
# passed

backend\venv\Scripts\python.exe e2e\phase4_real_acceptance.py
# Phase 4 real acceptance passed

backend\venv\Scripts\python.exe e2e\phase4_dev_proxy_check.py
# Phase 4 dev proxy check passed
```

真实 HTTP 验收覆盖：单聊发送、引用回复、Pin/Unpin、中文搜索、重新生成 SSE、群聊 Orchestrator 事件。
Dev proxy 预检覆盖：确认 `http://127.0.0.1:5173/api/messages/*` 代理到包含 Phase 4 路由的当前后端，避免旧 8000 进程导致 404。

人工验收复核（2026-06-02）：

- 已停止旧 `127.0.0.1:8000` uvicorn 进程，并用当前仓库 `backend\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000` 重新启动真实后端。
- 在真实前端 `http://127.0.0.1:5173` 新建对话，生成一份 4 天 3 夜攻略，引用该 AI 回复后要求改成一周版本。
- 浏览器抓包确认第二次 `/chat` 请求包含被引用 AI 回复的 `parentMessageId`；数据库消息确认 `metadata.replyReference` 保存了被引用消息快照。
- Agent 最终回复复述了只存在于被引用消息中的唯一代号，并输出一周版本内容，证明引用上下文已进入 Agent 输入链路。
- 人工验收结论：Phase 4 通过。
