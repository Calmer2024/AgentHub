# Spec: Phase 4A — 消息操作 (reply/regenerate/pin)

**版本**: v2.0
**创建日期**: 2026-05-28 (v1.0), 2026-06-02 (v2.0 重组)
**状态**: Completed
**完成日期**: 2026-06-02
**关联**: [PRD-03: User Experience](../../../../PRD/03-User_Experience.md), [PRD-04: Data & API](../../../../PRD/04-Data_API_Contracts.md)
**依赖**: Phase 3 (MessageService ABC, DB 列: parent_message_id, is_pinned)

## 1. 新增 API

```
POST /api/messages/{id}/reply      Body: { content } → 201 MessageRead
POST /api/messages/{id}/regenerate → 200 SSE text/event-stream
POST /api/messages/{id}/pin        → 200 { isPinned: true }
DELETE /api/messages/{id}/pin      → 200 { isPinned: false }
```

## 2. 后端实现

### 2.1 SqlAlchemyMessageService

实现 `message_service.py` 中的 ABC：

```python
class SqlAlchemyMessageService(MessageService):
    async def reply_to_message(input, parent_message_id) -> MessageRead
    async def regenerate_message(message_id) -> AsyncIterator[str]
    async def pin_message(message_id) -> None
    async def unpin_message(message_id) -> None
    async def get_pinned_messages(session_id) -> list[MessageRead]
```

### 2.2 行为规格

| 场景 | 预期 |
|------|------|
| 引用消息 | 保存 `parentMessageId` 和 `metadata.replyReference` 引用快照；发送到 Agent 前注入 `[Reply context]` prompt 块 |
| 引用原消息不在当前列表 | 气泡优先使用 `metadata.replyReference` 快照显示引用摘要；仍可通过 `parentMessageId` 尝试跳转 |
| 引用已删除且无快照消息 | 引用卡片显示 "原消息已删除" |
| 重新生成超时 (60s) | 保留旧内容，显示 "重新生成超时" |
| 重新生成时 ContextManager | 用原始上下文重新调用 Agent |
| Pin 消息 | ContextManager 注入 `[Pinned message]` 长期上下文块，Agent 可在 prompt 中感知 |
| Pin 消息 > token 预算 | 保留最近 Pin 的，丢弃最旧的 |

## 3. 前端实现

### MessageActions.tsx
- 任何消息 hover 时显示操作按钮栏: [引用] [重新生成] [Pin] [复制]
- AI 消息才显示 [重新生成]
- Pin 的消息显示 Pin 标记

### ReplyPreview.tsx
- 输入框上方引用卡片，显示被引用消息摘要
- 发送后气泡上方显示引用预览，点击跳转到原消息

### MessageBubble.tsx 修改
- 新增引用预览渲染
- 新增 Pin 图标
- 重新生成状态：旧内容被替换，"查看原版" 展开

## 4. 验收标准

- [x] 引用卡片显示在输入框上方 → 发送 → 新气泡显示引用预览
- [x] 引用不是 UI-only：`/chat` 主发送链路会把被引用消息快照写入 metadata，并在 Agent 输入中注入引用原文
- [x] 重新生成: 旧内容替换 + "查看原版" 可展开
- [x] Pin: 消息显示 Pin 标记 + 取消 Pin 标记消失
- [x] Pin 不是 UI-only：单聊/群聊 Agent 输入中可见 `[Pinned message]` 长期上下文块
- [x] 消息 hover 操作栏在所有消息类型上正确显示

## 5. 测试

- API: reply 正常/引用已删除, regenerate 正常/超时, pin/unpin
- Prompt: `/chat` 引用上下文进入 adapter 输入，Pin 上下文进入 ContextManager 输出
- 前端: MessageActions 渲染, ReplyPreview 渲染, hover 交互
- 已覆盖: `test_messages_phase4.py`, `test_phase4_acceptance.py`, `MessageActions.test.tsx`, `ReplyPreview.test.tsx`
- 真实验收: `e2e/phase4_real_acceptance.py`
