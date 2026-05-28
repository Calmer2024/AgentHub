# Spec: Phase 3.2 — 消息操作 (reply/regenerate/pin)

**版本**: v1.0 | **状态**: Draft
**关联**: [Phase 3 Spec](phase3-enhancements-spec.md) §5.3.1-5.3.3
**依赖**: Module 1 (MessageService, DB 列)
**可并行**: ✅ 与 Module 3

## 1. 新增 API

```
POST /api/messages/{id}/reply      Body: { content } → 201 MessageRead
POST /api/messages/{id}/regenerate → 200 SSE text/event-stream
POST /api/messages/{id}/pin        → 200 { is_pinned: true }
DELETE /api/messages/{id}/pin      → 200 { is_pinned: false }
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
| 引用已删除消息 | 引用卡片显示 "原消息已删除" |
| 重新生成超时 (60s) | 保留旧内容，显示 "重新生成超时" |
| 重新生成时 ContextManager | 用原始上下文重新调用 Agent |
| Pin 消息 > token 预算 | 保留最近 Pin 的，丢弃最旧的 |

## 3. 前端实现

### MessageActions.tsx
- 任何消息 hover 时显示操作按钮栏: [引用] [重新生成] [Pin] [复制]
- AI 消息才显示 [重新生成]
- Pin 的消息显示 📌 图标

### ReplyPreview.tsx
- 输入框上方引用卡片，显示被引用消息摘要
- 发送后气泡上方显示引用预览，点击跳转到原消息

### MessageBubble.tsx 修改
- 新增引用预览渲染
- 新增 Pin 图标
- 重新生成状态：旧内容被替换，"查看原版" 展开

## 4. 验收标准

- [ ] 引用卡片显示在输入框上方 → 发送 → 新气泡显示引用预览
- [ ] 重新生成: 旧内容替换 + "查看原版" 可展开
- [ ] Pin: 消息显示图钉图标 + 取消 Pin 图标消失
- [ ] 消息 hover 操作栏在所有消息类型上正确显示

## 5. 测试

- API: reply 正常/引用已删除, regenerate 正常/超时, pin/unpin
- 前端: MessageActions 渲染, ReplyPreview 渲染, hover 交互
- 目标: 20 条测试
