# Spec: Phase 3 智能增强 —— Orchestrator 升级 + 产物深化 + 体验闭环

**版本**: v1.0
**创建日期**: 2026-05-27
**状态**: Draft
**关联 ADR**: ADR-0004 (开发方法论), ADR-0005 (7 层架构), ADR-0007 (AI 协作系统)

---

## 1. 目标

从 Phase 2 的"多人多 AI 协作"跨越到"智能协作"。三大主攻方向：

- **A. 智能协作**：Orchestrator 从路由分发升级为协作大脑（意图识别 + 任务拆解 + Agent 间自动对话）
- **B. 产物深化**：产物从只读预览升级为可编辑可迭代（版本管理 + Diff + 对话式局部修改）
- **C. 体验闭环**：补齐 IM 标准交互（消息引用 + 重新生成 + Pin + 搜索）

---

## 2. 架构演进

### 2.1 新启用的架构层

Phase 3 按 ADR-0004 触发条件，启用 4 个新架构组件：

| 组件 | 层 | 触发条件 | 职责 |
|------|-----|---------|------|
| **Event Bus** | Infrastructure | 多 Agent 并发协作 | pub/sub 解耦：Agent 流式 → 事件 → WS 推送 / 持久化 / 产物检测 |
| **MessageService** | Service | 消息引用/重生成/Pin | 消息持久化、历史查询、引用、Pin 管理 |
| **SessionService** | Service | 会话管理复杂度上升 | 会话 CRUD、成员管理、软删除、AI 标题 |
| **ArtifactService** | Service | 产物版本管理 | 产物 CRUD、版本链、编辑应用、Diff 生成 |
| **ContextManager** | Domain | 会话历史 + Pin 系统 | Token 预算、Pin 注入、System Prompt 组装 |

### 2.2 架构约束

- Event Bus 采用内存 Pub/Sub（`asyncio.Queue` + dict），零外部依赖
- ChatService 与 MessageService 平级，通过 Event Bus（`MESSAGE_COMPLETED` 事件）解耦——符合 ADR-0005 "同层不互依赖"规则
- ContextManager 是 Domain 层纯逻辑，不依赖任何框架
- Service 接口按需抽象：仅 ChatService、MessageService（被路由和 Event Bus 依赖）定义 ABC

---

## 3. 输入输出

### 3.1 新增 API 端点

```
# === 消息操作 ===
POST /api/messages/{id}/reply
  Body: { "content": "..." }
  → 201 { "id": "uuid", "parent_message_id": "uuid", "role": "user", ... }

POST /api/messages/{id}/regenerate
  → 200 SSE text/event-stream (流式输出新回复)
    完成事件: data: {"type": "message.regenerated", "message_id": "uuid", "version": N}

POST /api/messages/{id}/pin
  → 200 { "id": "uuid", "is_pinned": true }

DELETE /api/messages/{id}/pin
  → 200 { "id": "uuid", "is_pinned": false }

GET /api/messages/search?session_id={id}&q=关键词&limit=20
  → 200 [{ "id": "uuid", "content": "...", "highlight": "...", "role": "user|assistant", "created_at": "..." }, ...]

# === 产物版本 ===
GET /api/artifacts/{id}/versions
  → 200 [{ "version": 1, "content": "...", "created_at": "..." }, ...]

GET /api/artifacts/{id}/diff?v1=1&v2=2
  → 200 { "from_version": 1, "to_version": 2, "diff": "unified diff string" }

POST /api/artifacts/{id}/edit
  Body: { "selection": "选中代码片段", "instruction": "用户修改描述" }
  → 200 { "new_version": 3, "diff": "...", "artifact": { ... } }
```

### 3.2 扩展的 SSE 事件

```
POST /api/sessions/{id}/chat  新增以下 SSE 事件类型:

# Orchestrator 生命周期
data: {"type": "orchestrator.task_started", "intent": "code_gen", "tasks": [...], "agents": [...]}
data: {"type": "orchestrator.task_completed", "summary": "..."}

# Agent 调用生命周期
data: {"type": "agent.call_started", "agent_name": "claude", "task": "frontend"}
data: {"type": "agent.call_completed", "agent_name": "claude", "status": "ok"}

# 流式 token（扩展字段）
data: {"type": "message.streaming", "token": "...", "agent_name": "claude", "done": false}
data: {"type": "message.completed", "message_id": "uuid", "agent_name": "claude"}

# 产物创建（WebSocket 事件同步推送）
# 订阅者通过 EventBus 自动接收，前端通过 WS 实时展示
```

### 3.3 新增数据模型

```python
# 扩展 messages 表
class Message(Base):
    # 新增字段
    parent_message_id: str | None   # FK → messages.id，消息引用
    is_pinned: bool                 # 是否 Pin
    # 原有字段不变：id, session_id, role, content, agent_name, created_at

# 扩展 artifacts 表
class Artifact(Base):
    # 新增字段
    version: int = 1                # 版本号（同一 message 多次生成递增）
    parent_artifact_id: str | None  # FK → artifacts.id，版本链前驱
    # 原有字段不变：id, session_id, message_id, type, title, content, status, created_at

# FTS5 全文搜索虚拟表
# SQL: CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
#   content,
#   content_rowid='rowid',
#   tokenize='unicode61'
# );
# 与 messages 表用触发器同步
```

### 3.4 新增数据库表

```sql
-- 数据库迁移脚本 (migrations/ 目录)
-- 001_add_message_parent_id.sql
-- 002_add_message_is_pinned.sql
-- 003_add_artifact_version.sql
-- 004_add_artifact_parent_id.sql
-- 005_create_messages_fts.sql
-- 006_create_fts_triggers.sql  (INSERT/UPDATE/DELETE 触发器同步 FTS 索引)
```

---

## 4. Event Bus 事件体系

### 4.1 事件类型

| 事件类型 | 触发时机 | Payload | 订阅者 |
|---------|---------|---------|--------|
| `MESSAGE_STREAMING` | Agent 产出每个 token 块 | `{session_id, message_id, token, agent_name}` | WS Manager |
| `MESSAGE_COMPLETED` | 流式完成 | `{session_id, message_id, content, agent_name}` | MessageService, ArtifactService, WS Manager |
| `AGENT_CALL_STARTED` | Orchestrator 开始调用 Agent | `{session_id, agent_name, task}` | WS Manager |
| `AGENT_CALL_COMPLETED` | Agent 回复完成 | `{session_id, agent_name, status}` | Orchestrator, WS Manager |
| `ARTIFACT_CREATED` | 新产物被检测并创建 | `{session_id, artifact_id, type, title}` | WS Manager |
| `ARTIFACT_UPDATED` | 产物版本更新 | `{session_id, artifact_id, new_version}` | WS Manager |
| `ORCHESTRATOR_TASK_STARTED` | 任务拆解完成 | `{session_id, intent, tasks[], agents[]}` | WS Manager |
| `ORCHESTRATOR_TASK_COMPLETED` | 所有子任务完成 | `{session_id, summary}` | ChatService, WS Manager |

### 4.2 实现规范

- 基于 `asyncio.Queue` + `dict[EventType, list[EventHandler]]` 实现
- 零外部依赖，Domain 层纯 Python
- Payload 使用 `dict[str, Any]`（松散类型），符合 ADR-0005 EventBus 接口
- 发布者不关心订阅者是否存在（fire-and-forget）

---

## 5. 行为规格

### 5.1 智能协作（方向 A）

#### 5.1.1 Orchestrator L1: 意图识别

1. 用户在群聊中发送消息（未 @ 任何 Agent）
2. Orchestrator 分析消息内容，基于规则+关键词匹配判断任务类型：`code_gen` / `research` / `design_ui` / `general_qa`
3. 根据意图类型从群聊成员中筛选最合适的 Agent（code_gen → 优先 Claude/DeepSeek；research → 优先 Gemini）
4. 将消息路由到筛选后的 Agent

#### 5.1.2 Orchestrator L2: 任务拆解

1. Orchestrator 识别到复杂请求（含多个子任务关键词："前后端"、"API+UI"等）
2. 按预定义模板拆解为子任务：
   - 代码类：前端任务 + 后端任务（两个 Agent 并行执行）
   - 研究类：搜索任务 + 总结任务
3. 每个子任务分配给对应能力的 Agent
4. 通过 Event Bus 发布 `ORCHESTRATOR_TASK_STARTED` 事件
5. Agent 并行执行（最多 5 个），每个通过 `AGENT_CALL_STARTED/COMPLETED` 追踪
6. 全部完成后发布 `ORCHESTRATOR_TASK_COMPLETED`，聚合并展示结果

#### 5.1.3 L3: 预设链式协作（简化版）

1. 用户可在 GroupChatCreator 中配置链式管线（如"Claude 产出 → DeepSeek Review"）
2. 第一个 Agent (A) 完成后，其产出自动作为第二个 Agent (B) 的输入
3. Agent 间对话以**摘要模式**展示：折叠为"协作进行中"卡片，完成后展开可查看中间过程
4. 仅支持预设的 A→B 串联，不做完全自主的 Agent 间多轮对话

#### 5.1.4 ContextManager：Token 预算管理

1. 每次发消息前，ContextManager 计算当前会话历史的 token 总量
2. Pin 消息自动排入上下文前列（仅次于 System Prompt）
3. 非 Pin 消息按 FIFO 从最早开始移除，直到剩余 token 在模型上下文窗口限制内
4. 预留 4096 token 给本次回复
5. 返回 `PromptAssemblyOutput` 包含是否触发了截断

### 5.2 产物深化（方向 B）

#### 5.2.1 版本管理
1. 每次重新生成同一产物 → `version += 1`，`parent_artifact_id` 指向上一版本
2. 通过 `GET /api/artifacts/{id}/versions` 获取完整版本链
3. 通过 `GET /api/artifacts/{id}/diff?v1=1&v2=2` 获取任意两版本的 Diff

#### 5.2.2 Tool Calling 编辑流程

1. 用户在产物代码中选中片段 → 弹出"描述修改"输入框 → 输入修改意图
2. 前端检查 Agent `capability.supports_tool_call`：
   - **支持 tool calling 的 Agent**（Claude/OpenAI/DeepSeek/Gemini）：调用 `edit_artifact` tool schema
   - **不支持的 Agent**（GLM/MiniMax）：降级为上下文注入模式——将"请对代码执行修改：{selection}，意图：{instruction}，返回完整修改后代码"作为消息发给 Agent
3. Agent 返回修改结果 → 后端对比生成 Diff → 前端在 `react-diff-viewer-continued` 中展示
4. 用户确认 → 应用修改，创建新版本；用户拒绝 → 保持原版

#### 5.2.3 Tool: edit_artifact Schema

```json
{
  "name": "edit_artifact",
  "description": "对产物进行局部修改",
  "parameters": {
    "type": "object",
    "properties": {
      "artifact_id": { "type": "string" },
      "selection": { "type": "string", "description": "选中的原始代码片段" },
      "instruction": { "type": "string", "description": "修改意图描述" },
      "edit_type": {
        "type": "string",
        "enum": ["replace", "insert_after", "insert_before", "delete"]
      }
    },
    "required": ["artifact_id", "selection", "instruction", "edit_type"]
  }
}
```

### 5.3 体验闭环（方向 C）

#### 5.3.1 消息引用
1. 任何消息 hover 时显示操作按钮栏（引用/重新生成/Pin/复制）
2. 点击"引用"→ 输入框上方显示引用卡片（被引用消息摘要），输入框自动聚焦
3. 发送后新消息气泡上方显示被引用消息的缩略预览
4. 点击引用预览可滚动跳转到原消息

#### 5.3.2 重新生成
1. 仅 AI 消息显示"重新生成"按钮
2. 点击 → 该消息气泡进入 loading 状态 → 后端用相同上下文重新调用 Agent
3. 新回复**原地替换**旧内容（不追加新消息）
4. 气泡上显示"已重新生成"，带"查看原版"链接可展开旧内容
5. 每次重新生成自动创建产物新版本（如有关联产物）
6. 群聊中仅重新生成指定 Agent 的回复

#### 5.3.3 Pin 上下文
1. 任何消息 hover → 点击"Pin"按钮 → `POST /api/messages/{id}/pin`
2. Pin 后的消息显示图钉图标
3. Pin 消息由 ContextManager 处理：始终在后续 prompt 中优先包含
4. 点击已 Pin 消息的"取消 Pin"→ `DELETE /api/messages/{id}/pin`

#### 5.3.4 消息搜索
1. 聊天窗口顶部添加搜索框（或快捷键 Ctrl+K / Cmd+K）
2. 输入关键词 → `GET /api/messages/search?q=...` → 调用 FTS5 全文索引
3. 结果列表显示：匹配片段（含高亮标记）、所在消息角色、发送时间
4. 点击结果项 → 滚动到该消息位置并高亮闪烁

### 5.4 异常流程

| 异常场景 | 预期行为 |
|----------|---------|
| Tool calling Agent 返回非标准格式 | 降级为上下文注入模式重试一次 |
| FTS5 索引同步失败 | 消息正常保存，搜索时 fallback 使用 LIKE 查询 |
| Pin 消息数量超过 token 预算 | ContextManager 优先保留最近 Pin 的消息，丢弃最早 Pin 的 |
| 引用的消息被删除 | 引用卡片显示"原消息已删除" |
| 重新生成超时 | 保留旧内容不变，显示"重新生成超时，请重试" |
| Event Bus 订阅者异常 | 异常隔离：一个订阅者崩溃不影响其他订阅者和发布者 |
| 并行 Agent 中某个超时 | 其他 Agent 正常回复，超时的显示"@name 响应超时" |

---

## 6. 验收标准

### 6.1 智能协作
- [ ] 群聊中发送消息（未 @），Orchestrator 根据意图自动选择 Agent 回复
- [ ] 复杂请求（如"做一个登录页面，前后端都写"）被拆解为多个子任务并分配到不同 Agent
- [ ] Agent 间链式协作（A 产出 → B Review）在摘要卡片中展示
- [ ] Pin 消息在后续对话中始终被 Claude 引用
- [ ] 会话超过 20 轮时，早期非 Pin 消息被截断但不影响上下文连贯性

### 6.2 产物深化
- [ ] 产物有多个版本时，可通过版本下拉切换查看历史版本
- [ ] 两版本间 Diff 正确高亮增删行
- [ ] 选中代码片段 + 描述修改 → Agent 返回 Diff → 用户确认后应用
- [ ] 不支持 tool calling 的 Agent 降级为上下文注入，编辑功能仍可用
- [ ] Tool calling 模式下 Agent 返回 edit_artifact 调用，产物正确更新

### 6.3 体验闭环
- [ ] 消息引用：引用卡片显示在输入框上方，发送后新气泡显示引用预览
- [ ] 重新生成：旧内容被替换，"查看原版"可展开
- [ ] Pin：点击 Pin 后消息显示图钉图标，取消 Pin 后图标消失
- [ ] 搜索：输入关键词后匹配结果显示高亮片段，点击跳转到对应消息
- [ ] 消息 hover 操作按钮栏在所有消息类型上正确显示

### 6.4 架构质量
- [ ] API 路由变为 thin handler（≤ 30 行），业务逻辑全部在 Service 层
- [ ] Event Bus 解耦有效：ChatService 不 import MessageService
- [ ] ContextManager 纯 Python 实现，零 FastAPI/SQLAlchemy 依赖
- [ ] 所有 Service 接口遵循"按需抽象"原则（仅 ChatService/MessageService 有 ABC）
- [ ] Phase 1 + Phase 2 全量功能回归通过

### 6.5 测试覆盖
- [ ] 后端 API 测试 ≥ 60 条（含消息引用/重生成/Pin/搜索/产物版本/编辑）
- [ ] 后端单元测试 ≥ 20 条（Service/ContextManager/EventBus/Orchestrator）
- [ ] 前端组件测试 ≥ 25 条
- [ ] Playwright E2E ≥ 5 条关键路径
- [ ] FTS5 搜索使用临时磁盘文件数据库测试

---

## 7. 接口契约（Service 层新增）

### 7.1 MessageService

```python
class MessageService(ABC):
    @abstractmethod
    async def get_session_messages(self, session_id: str, limit: int = 50, before: str | None = None) -> list[MessageRead]: ...
    @abstractmethod
    async def reply_to_message(self, input: MessageCreate, parent_message_id: str) -> MessageRead: ...
    @abstractmethod
    async def regenerate_message(self, message_id: str) -> AsyncIterator[str]: ...
    @abstractmethod
    async def pin_message(self, message_id: str) -> None: ...
    @abstractmethod
    async def unpin_message(self, message_id: str) -> None: ...
    @abstractmethod
    async def get_pinned_messages(self, session_id: str) -> list[MessageRead]: ...
    @abstractmethod
    async def search_messages(self, session_id: str, query: str, limit: int = 20) -> list[MessageRead]: ...
```

### 7.2 ChatService

```python
class ChatService(ABC):
    @abstractmethod
    async def send_message_stream(self, session_id: str, content: str, mentions: list[str] | None = None, parent_message_id: str | None = None) -> AsyncIterator[str]: ...
```

### 7.3 SessionService（具体类）

```python
class SessionService:
    async def create_session(self, ...) -> SessionRead: ...
    async def get_session(self, session_id: str) -> SessionRead: ...
    async def list_sessions(self) -> list[SessionRead]: ...
    async def update_session(self, session_id: str, ...) -> SessionRead: ...
    async def delete_session(self, session_id: str) -> None: ...
    async def get_members(self, session_id: str) -> list[SessionMemberRead]: ...
    async def add_member(self, session_id: str, agent_config_id: str) -> None: ...
    async def generate_title(self, session_id: str) -> str: ...
```

### 7.4 ArtifactService（具体类）

```python
class ArtifactService:
    async def get_artifacts(self, session_id: str) -> list[ArtifactRead]: ...
    async def get_artifact(self, artifact_id: str) -> ArtifactRead: ...
    async def get_versions(self, artifact_id: str) -> list[ArtifactVersion]: ...
    async def get_diff(self, artifact_id: str, v1: int, v2: int) -> str: ...
    async def apply_edit(self, artifact_id: str, selection: str, instruction: str) -> ArtifactEditResult: ...
    async def detect_and_create_artifact(self, message: MessageRead) -> ArtifactRead | None: ...
```

---

## 8. BaseAgentAdapter 扩展

```python
@dataclass
class AgentCapability:
    # 原有字段
    name: str
    supports_streaming: bool = True
    supports_file_input: bool = False
    max_context_tokens: int = 100_000
    tags: list[str] = field(default_factory=list)
    # Phase 3 新增：Phase 2 中已预定义但始终为 False，Phase 3 按实际能力设为 True
    supports_tool_call: bool = False

class BaseAgentAdapter(ABC):
    # Phase 3 扩展：chat/chat_stream 增加 tools 参数
    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        system_prompt: str,
        on_token: Callable[[str], None] | None = None,
        tools: list[dict] | None = None,          # → 新增
    ) -> AgentResponse: ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict],
        system_prompt: str,
        tools: list[dict] | None = None,           # → 新增
    ) -> AsyncIterator[str]: ...
```

**各 Provider supports_tool_call 初始值**：
- Claude / OpenAI / DeepSeek / Gemini = `True`
- GLM / MiniMax = `False`（后续版本中按 SDK 成熟度升级）

---

## 9. 前端组件变更

### 9.1 Zustand Store 拆分

```
stores/
  chatStore.ts    ← messages, isStreaming, streamingError, currentSessionId
  sessionStore.ts  ← sessions, agents, providers, sidebarTab
```

### 9.2 新增组件

| 组件 | 用途 |
|------|------|
| `MessageActions.tsx` | hover 操作按钮栏（引用/重生成/Pin/复制） |
| `ReplyPreview.tsx` | 输入框上方的引用卡片 |
| `SearchPanel.tsx` | 消息搜索面板（输入框 + 结果列表） |
| `DiffViewer.tsx` | 产物版本 Diff 对比视图 |
| `VersionHistory.tsx` | 产物版本下拉选择器 |
| `CodeSelector.tsx` | 代码片段选择 + "描述修改"弹窗 |
| `CollabProgressCard.tsx` | Agent 协作进行中摘要卡片 |

### 9.3 修改组件

| 组件 | 变更 |
|------|------|
| `MessageBubble.tsx` | 新增引用预览渲染、Pin 图标、操作按钮栏集成、重新生成状态 |
| `ChatInput.tsx` | 新增引用卡片 slot、"描述修改"模式 |
| `ChatWindow.tsx` | 新增搜索框、Orchestrator 进度横幅、Agent 链式卡片 |
| `ArtifactCard.tsx` | 新增版本选择器、Diff 按钮、编辑模式 |
| `GroupChatCreator.tsx` | 新增链式协作管线配置 UI |
| `SessionList.tsx` | 搜索结果高亮闪烁跳转 |
| `App.tsx` | 迁移到拆分后的 store |

### 9.4 新依赖

```
react-diff-viewer-continued  ← Diff 视图（~15KB, split/unified 模式）
```

---

## 10. 测试计划

### 10.1 测试目标

| 层级 | 当前 (Phase 2) | 目标 (Phase 3) |
|------|---------------|---------------|
| 后端冒烟 | 10 | 12 |
| 后端 API | 39 | ≥ 60 |
| 后端单元（Service/EventBus/ContextManager） | 0 | ≥ 20 |
| 前端组件 | 7 | ≥ 25 |
| 前端 Store | 1 文件 | 2 文件 |
| E2E (Playwright) | 0 | ≥ 5 |

### 10.2 FTS5 测试注意

- 内存数据库不支持 FTS5，需 conftest fixture 使用临时磁盘文件数据库
- 测试执行后清理临时数据库文件

### 10.3 E2E 关键路径

1. 发消息 → 引用回复 → 验证引用预览
2. AI 消息重新生成 → 验证原地替换 + 查看原版
3. Pin 消息 → 发新消息 → 验证 Pin 内容在上下文中
4. 搜索关键词 → 点击结果 → 验证跳转
5. 产物编辑 → 选中代码 → 描述修改 → 验证 Diff → 确认应用

---

## 11. 不在范围内（Non-Goals / → Phase 4）

- ❌ 历史压缩（LLM 自动摘要替代原始消息）
- ❌ Orchestrator L4 动态重规划（失败自动切换 Agent）
- ❌ PPT 产物类型
- ❌ 产物导出下载
- ❌ 会话归档
- ❌ 消息富文本（图片/文件附件/语音）
- ❌ Monaco Editor 升级
- ❌ 部署发布（聊天中一键部署）
- ❌ 多端适配（Tauri 桌面端 / Capacitor 移动端）
- ❌ 用户认证与权限
- ❌ 性能优化（Redis 缓存、数据库索引优化）

---

## 12. 依赖

| 依赖模块 | 接口 | 状态 |
|---------|------|------|
| Phase 2 完整代码（API + DB + Agent 适配器） | 全部端点、5 张表、6 适配器 | 已完成 |
| Event Bus | asyncio.Queue | 待实现 |
| MessageService ABC | 见 7.1 节 | 待实现 |
| ChatService ABC | 见 7.2 节 | 待实现 |
| ContextManager | Domain 纯逻辑 | 待实现 |
| react-diff-viewer-continued | npm 包 | 待安装 |
| FTS5 | SQLite 内置模块 | 已可用（需验证编译选项） |

---

## 13. 数据库迁移策略

采用手动迁移脚本（`backend/migrations/` 目录），按编号顺序执行：

```
migrations/
  001_add_message_parent_id.sql
  002_add_message_is_pinned.sql
  003_add_artifact_version.sql
  004_add_artifact_parent_id.sql
  005_create_messages_fts.sql
  006_create_fts_triggers.sql
migration_runner.py          ← 按编号顺序执行所有 .sql 文件，记录已执行迁移
```

在 `main.py` lifespan 中调用 `migration_runner.run()`，替代当前的 ad-hoc ALTER TABLE。
