# Spec: Phase 1 行走骨架 —— 单聊全链路

**版本**: v1.0
**创建日期**: 2026-05-26
**状态**: In Development
**关联 ADR**: ADR-0006

---

## 1. 目标

打通 AgentHub 的第一条完整链路：用户通过前端 IM 界面发送消息 → 后端调用 Claude API → 流式返回 → 前端实时渲染。证明技术选型可行，为后续增量开发提供可运行基底。

---

## 2. 输入输出

### 2.1 API 端点

```
POST /api/sessions
  Body: { "title": "新对话", "agent_name": "claude" }
  → 201 { "id": "uuid", "title": "新对话", "agent_name": "claude", "created_at": "..." }

GET /api/sessions
  → 200 [{ "id": "uuid", "title": "...", "updated_at": "..." }, ...]

GET /api/sessions/{id}
  → 200 { "id": "uuid", "title": "...", "agent_name": "claude", ... }

GET /api/sessions/{id}/messages
  → 200 [{ "id": "uuid", "role": "user"|"assistant", "content": "...", ... }, ...]

POST /api/sessions/{id}/chat
  Body: { "content": "用户输入的消息文本" }
  → 200 text/event-stream (SSE)
    每个事件: data: {"token": "逐", "done": false}
    结束事件: data: {"token": "", "done": true, "message_id": "uuid"}
```

### 2.2 数据模型

```python
# backend/app/models/session.py
class Session(Base):
    __tablename__ = "sessions"
    id: str          # UUID, PK
    title: str       # 会话标题，默认"新对话"
    agent_name: str  # Agent 标识，Phase 1 固定"claude"
    created_at: datetime
    updated_at: datetime

# backend/app/models/message.py
class Message(Base):
    __tablename__ = "messages"
    id: str          # UUID, PK
    session_id: str  # FK → sessions.id
    role: str        # "user" | "assistant" | "system"
    content: str     # 消息文本
    created_at: datetime
```

```typescript
// frontend/src/types/index.ts
interface Session {
  id: string;
  title: string;
  agentName: string;
  createdAt: string;
  updatedAt: string;
}

interface Message {
  id: string;
  sessionId: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt: string;
}
```

### 2.3 Agent Adapter 接口

```python
# 遵循 ADR-0005 定义的 BaseAgentAdapter 契约
class ClaudeAdapter(BaseAgentAdapter):
    @property
    def capability(self) -> AgentCapability: ...
    async def chat(self, messages, system_prompt, on_token) -> AgentResponse: ...
    async def chat_stream(self, messages, system_prompt) -> AsyncIterator[str]: ...
```

---

## 3. 行为规格

### 3.1 正常流程

1. 用户打开网页 → 左侧显示空会话列表
2. 点击"新建对话"→ 调用 `POST /api/sessions` → 新会话出现在列表顶部 → 自动选中
3. 在输入框输入文字 → 点击发送 → 调用 `POST /api/sessions/{id}/chat`
4. 用户消息立即渲染在聊天窗口（气泡靠右对齐）
5. 后端创建 Message(role="user") → 查询会话历史 → 组装 messages[] → 调用 `claude_adapter.chat_stream()`
6. 每个 token 通过 SSE 推送到前端 → 前端逐块追加到 AI 消息气泡（靠左对齐）
7. 流式完成后 → 创建 Message(role="assistant") → 持久化完整回复文本
8. 用户再次发送消息 → 后端查询历史时包含上一轮的完整对话 → Claude 能"记住"上下文

### 3.2 异常流程

| 异常场景 | 预期行为 |
|----------|---------|
| `ANTHROPIC_API_KEY` 未设置 | 后端启动时报错退出，或 `/chat` 端点返回 500 `{"error": "API key not configured"}` |
| Claude API 返回 429 (rate limit) | `/chat` 返回 429，前端显示"请求太频繁，请稍后重试" |
| Claude API 返回其他错误 (4xx/5xx) | 前端消息气泡显示错误信息（红色文字），不是白屏 |
| 发送空消息 | 后端返回 400 `{"error": "content must not be empty"}` |
| 访问不存在的 session | 返回 404 `{"error": "session not found"}` |
| 网络中断（SSE 连接断开） | 前端 EventSource `onerror` 捕获 → 在消息气泡显示"连接中断"，保留已接收的部分文本 |
| 用户快速切换会话后再切回 | 消息历史正确加载（从数据库读取，不依赖内存状态） |

### 3.3 边界条件

- 消息内容最长 10,000 字符（Phase 1 简单截断即可，不做精细 token 管理）
- 会话历史默认取最近 50 条消息发给 Claude
- 流式输出超过 60 秒无新 token → 视为超时，断开连接
- 同时多个会话各自独立，互不影响

---

## 4. 验收标准

- [ ] 打开网页，左侧显示空会话列表，点击"新建对话"创建第一个会话
- [ ] 发送一条文本消息后，3 秒内看到 AI 回复的第一个字（首个 token 到达）
- [ ] AI 回复以流式方式逐字/逐块出现（不是一次性显示），滚动条自动跟随
- [ ] 发送第二条消息时，AI 的回复能引用第一条消息的内容（验证上下文传递）
- [ ] 刷新页面后，所有会话和消息完整保留（SQLite 持久化验证）
- [ ] AI 回复完成后，关闭页面再打开，回复完整显示（非流式残留）
- [ ] Claude API Key 未配置时，前端显示明确错误提示（非白屏）
- [ ] `ClaudeAdapter` 继承自 `BaseAgentAdapter`，所有方法签名匹配

---

## 5. 依赖

| 依赖模块 | 接口 | 状态 |
|---------|------|------|
| SQLite 数据库 | SQLAlchemy async engine | 待实现 |
| Claude API | anthropic Python SDK, `ANTHROPIC_API_KEY` 环境变量 | API Key 已就绪 |
| BaseAgentAdapter | 接口契约（ADR-0005） | 已定义 |

---

## 6. 不在范围内（Non-Goals）

- ❌ WebSocket（Phase 1 用 SSE）
- ❌ 多 Agent 切换（硬编码 Claude）
- ❌ 群聊模式、Orchestrator
- ❌ 消息引用、重新生成、Pin
- ❌ 产物预览卡片（纯文本消息）
- ❌ 文件附件、图片上传
- ❌ 用户认证
- ❌ Service 层、Event Bus、Context Manager
