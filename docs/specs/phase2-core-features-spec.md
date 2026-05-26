# Spec: Phase 2 核心功能 —— 多 Agent + 群聊 + 产物预览

**版本**: v1.0 (Draft)
**创建日期**: 2026-05-26
**状态**: Draft
**关联 ADR**: ADR-0005 (7 层架构), ADR-0007 (AI 协作系统)

---

## 1. 目标

在 Phase 1 的行走骨架基础上，引入多 Agent 支持、群聊模式 + Orchestrator 协调、产物预览卡片。实现从"单人单 AI 对话"到"多人多 AI 协作"的跨越。

---

## 2. 输入输出

### 2.1 API 端点

```
# === Agent 管理 ===
GET /api/agents
  → 200 [{ "name": "claude", "display_name": "Claude", "capability": {...} }, ...]

# === 群聊（新） ===
POST /api/sessions
  Body: { "title": "...", "mode": "group", "agent_names": ["claude", "deepseek"] }
  → 201 { "id": "uuid", "mode": "group", ... }

GET /api/sessions/{id}/members
  → 200 [{ "agent_name": "claude", "joined_at": "...", "status": "active" }, ...]

POST /api/sessions/{id}/chat  (扩展，支持 @ 提及)
  Body: { "content": "@claude 帮我写一个函数", "mentions": ["claude"] }
  → SSE 事件增加 agent_name 字段

# === 产物（新） ===
GET /api/sessions/{id}/artifacts
  → 200 [{ "id": "uuid", "type": "code_diff"|"web_preview"|"document", ... }, ...]

GET /api/artifacts/{id}
  → 200 { ... } 或 WebSocket 推送渲染内容

# === WebSocket（新） ===
WS /ws/sessions/{id}
  → 实时推送：消息创建、流式 token、产物生成、Agent 状态变更
```

### 2.2 新增数据模型

```python
# backend/app/models/agent.py
class Agent(Base):
    __tablename__ = "agents"
    name: str          # "claude", "deepseek" — PK
    display_name: str  # "Claude 4 Opus"
    provider: str      # "anthropic", "deepseek"
    is_active: bool

# backend/app/models/session_member.py
class SessionMember(Base):
    __tablename__ = "session_members"
    session_id: str    # FK
    agent_name: str    # FK → agents.name
    joined_at: datetime

# backend/app/models/artifact.py
class Artifact(Base):
    __tablename__ = "artifacts"
    id: str
    session_id: str
    message_id: str       # 产生此产物的消息
    type: str             # "code_diff" | "web_preview" | "document"
    title: str
    content: str          # JSON 或 Markdown
    status: str           # "rendering" | "ready" | "error"
```

### 2.3 Orchestrator 接口（新架构层：Domain/Core）

```python
# backend/app/domain/orchestrator.py
class Orchestrator:
    async def route_message(
        self,
        session_id: str,
        content: str,
        mentions: list[str] | None,
    ) -> dict[str, AgentResponse]:
        """拆解消息 → 路由到对应 Agent → 聚合结果。"""
        ...

    async def coordinate_group_chat(
        self,
        session_id: str,
        messages: list[dict],
    ) -> AsyncIterator[OrchestratorEvent]:
        """群聊模式：自动选择 Agent、协调分工、合并产物。"""
        ...
```

---

## 3. 行为规格

### 3.1 正常流程

**单聊模式（Phase 1 已实现，保持不变）**

**Agent 切换**：
1. 创建新会话时选择 Agent（从 `GET /api/agents` 列表）
2. 已有会话中通过下拉菜单切换 Agent
3. 历史消息按 Agent 区分显示（不同颜色/图标）

**群聊模式**：
1. 创建群聊 → 选择 2+ Agent → 进入群聊界面
2. 用户发送消息 → Orchestrator 分析意图 → 自动选择 1+ Agent 回复
3. 用户可 @ 指定 Agent → Orchestrator 仅路由到指定 Agent
4. 多个 Agent 同时回复 → 消息按发送时间交错显示，标注发言人
5. Agent 之间可自动对话（Orchestrator 判断是否需要多轮）

**产物预览**：
1. Agent 生成代码 → 自动识别为 code_diff 类型 → 右侧预览面板显示 Diff 视图
2. Agent 生成网页 → 自动识别为 web_preview 类型 → 右侧内嵌 iframe 预览
3. 用户点击产物卡片 → 全屏预览
4. 产物状态：rendering → ready 或 error

### 3.2 异常流程

| 异常场景 | 预期行为 |
|----------|---------|
| Agent 未配置 API Key | 该 Agent 在列表中标记为"不可用"，hover 显示原因 |
| Orchestrator 无匹配 Agent | 返回"没有合适的 Agent 处理此请求，请尝试 @ 指定" |
| 产物渲染失败 | 状态变为 error，显示错误信息，支持重试 |
| WebSocket 断连 | 自动重连（指数退避），重连后拉取增量消息 |
| 群聊中一个 Agent 超时 | 其他 Agent 正常回复，超时的显示"@claude 响应超时" |

### 3.3 边界条件

- 群聊最多 5 个 Agent
- 产物大小限制：code_diff ≤ 50KB, web_preview ≤ 200KB
- WebSocket 心跳间隔 30 秒
- Orchestrator 路由决策在 1 秒内完成

---

## 4. 验收标准

- [ ] 创建会话时可选择不同的 Agent（从可用列表）
- [ ] 已有会话中切换 Agent 后，新消息发给新 Agent
- [ ] 创建群聊时选择 2+ Agent，发送消息后至少 1 个 Agent 回复
- [ ] @Agent 指定提问后，只有被 @ 的 Agent 回复
- [ ] Agent 生成的代码以 Diff 卡片形式展示（代码高亮）
- [ ] WebSocket 实时推送消息和流式 token（替代 Phase 1 的 SSE polling）
- [ ] Phase 1 全部功能（单聊 SSE 流式）保持正常

---

## 5. 依赖

| 依赖模块 | 接口 | 状态 |
|---------|------|------|
| Phase 1 API + 数据库 | sessions, messages 端点 | 已完成 |
| Claude API | anthropic SDK | 已接入 |
| DeepSeek API | openai SDK (兼容模式) | 已接入 |
| Diff 渲染库 | react-diff-viewer 或 monaco-editor | 待选型 |
| WebSocket (FastAPI) | starlette.websockets | 待实现 |

---

## 6. 不在范围内（Non-Goals）

- ❌ 用户认证与权限
- ❌ Agent 自定义配置（system prompt 用户可编辑）
- ❌ 产物版本管理 / 历史
- ❌ Tauri 桌面端 / Capacitor 移动端
- ❌ 消息搜索
- ❌ 性能优化（缓存、索引）

---

## 7. Phase 2 测试计划要点

- [ ] 新增 API 测试（agents、artifacts、session members）
- [ ] Orchestrator 单元测试（Mock 多个 Agent，验证路由逻辑）
- [ ] WebSocket 集成测试
- [ ] 前端 E2E 测试（Playwright）：Agent 切换、群聊流程、产物预览
- [ ] Phase 1 全量回归测试
