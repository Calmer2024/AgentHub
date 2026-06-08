# Spec: Phase 6F — CLI 输出到 Artifact 桥接

**版本**: v3.6
**创建日期**: 2026-06-03
**更新日期**: 2026-06-08
**状态**: ✅ 本轮验收通过（消息内 Artifact 卡片、文件编辑、片段引用、版本管理已落地；群聊 Agent 子消息 workspace diff 归属已同步）
**关联 ADR/PRD**: [PRD-01](../../PRD/01-Architecture_Adapter.md) §3.4、[PRD-03](../../PRD/03-User_Experience.md) §3.3-3.4、[PRD-05](../../PRD/05-End_to_End_Product_Flow.md)、[PRD-06](../../PRD/06-MVP_Local_Workspace_Delivery.md)、[ADR-0005](../../adr/0005-target-architecture.md)、[ADR-0009](../../adr/0009-project-workspace-model.md)
**依赖模块**: Phase 6A Workspace Runtime、Phase 6B-6E CLI Adapter、Phase 5 ArtifactService、当前 Telegram 风格 Chat UI

> 本模块不是再设计一套新的产物系统，而是把已经落地的 Project workspace、真实 CLI 执行、执行轨迹、ArtifactService 和聊天流中的产物卡片接成一条可靠链路。

---

## 1. 目标

AgentHub 现在已经能在 Project workspace 中运行 Claude Code、Codex、OpenCode，并把回复文本和执行轨迹保存到消息里。但 Agent 写出的文件、输出的代码块、执行轨迹中的产物信号还没有稳定转换成 Artifact。Phase 6F 的目标是：在每次 CLI Agent 回复完成时，自动分析“消息内容 + 执行轨迹 + workspace 前后 diff”，生成可查询、可预览、可版本化的 Artifact，并让用户在聊天界面自然看到它。

目标用户是正在通过 CLI Agent 生成项目文件、网页、补丁或文档的本机桌面版用户。用户不需要手动复制代码块，也不需要去文件系统里找结果；产物应该在对话完成后自动出现在对应消息下方，以紧凑卡片流跟随具体对话上下文。

**成功标准**（可证伪）：

- [x] CLI Agent 在 workspace 写入 `index.html` 后，最终 SSE `done` 前已创建 `web_preview` Artifact，`GET /api/sessions/{id}/artifacts` 能查到该产物。
- [x] CLI Agent 输出完整 fenced `html` 或 `diff` 代码块但未写文件时，仍能创建 `web_preview` 或 `code_diff` Artifact。
- [x] 同一条消息创建出的 Artifact 会绑定 `sessionId`、`messageId`、`projectId`、`filePath?`、`source`、`version=1`；Agent 身份通过 `messageId -> message.sourceId` 追溯。
- [x] 前端收到 `artifact.created` 或消息完成后的 artifacts refresh 后，对应消息下方出现完整但紧凑的 ArtifactCard 卡片流。
- [x] 低置信检测结果不会落库，只写入 `message.metadata.artifactCandidates` 供后续 UI 或调试查看。
- [x] 不通过标准：只在执行轨迹里显示“发现产物”，但 `/api/sessions/{id}/artifacts` 查不到真实 Artifact；或 Adapter 直接写 Artifact 表，绕过本桥接模块。

---

## 2. 全局定位

### 2.1 北极星链路位置

```text
Project workspace + CLI Agent 回复
  → [本模块] ArtifactOutputBridge
  → ArtifactService.create_from_detection()
  → artifacts 表 + artifact.created 事件
  → MessageArtifactStrip + 消息下方 ArtifactCard
  → Phase 5 版本/Diff/编辑能力
  → Phase 7 运行可控性 / 审批 / 环境体检
```

### 2.2 上下游契约

| 方向 | 模块/事件/API | 本模块的角色 |
|------|-------------|------------|
| **上游输入** | `SingleCliChatStream` / `GroupChatStream` 的 assistant message 完成事件 | 在消息持久化后、最终 `done` 前接收完整可见回复、raw output preview、执行轨迹 metadata、agent 信息、project/session 信息 |
| **上游输入** | `FileChangeDetector` pre/post snapshot diff | 将本次 CLI 执行造成的 workspace 文件变更转成 `file_tree`、`web_preview`、`code_diff` 等 Artifact 候选 |
| **上游输入** | CLI Adapter 的 `chunkType="artifact_signal"` 与 `executionTrace.items[]` | 提升检测置信度，补足工具名、命令、目标路径等上下文 |
| **下游产出** | `ArtifactService.create_from_detection()` | 创建 Artifact v1，复用 Phase 5 版本链、Diff 和编辑能力 |
| **下游产出** | SSE `artifact.scan.*`、`artifact.created`；`GET /api/sessions/{id}/artifacts` | 让前端即时 upsert，消息完成后 refresh 作为兜底 |
| **本模块不通** | 不实现运行取消、审批断点、环境体检；不做部署发布；不做二进制文件在线预览 | Phase 7 / P2 处理 |

---

## 3. 跨模块契约

> 本章只定义其它模块必须遵守的接口。检测器内部如何分词、打分、排序，不写死到跨模块契约里。

### 3.1 API 端点

| 端点 | 方法 | 请求体 | 成功响应 | 错误响应 |
|------|------|--------|---------|---------|
| `/api/sessions/{sessionId}/artifacts` | GET | 无 | `200: ArtifactRead[]`，包含本模块创建的产物 | `404` 会话不存在 |
| `/api/artifacts/{artifactId}` | GET | 无 | `200: ArtifactRead` | `404` Artifact 不存在 |
| `/api/artifacts/{artifactId}/versions` | GET | 无 | `200: ArtifactVersionRead[]` | `404` Artifact 不存在 |
| `/api/artifacts/{artifactId}/diff?v1=&v2=` | GET | query: `v1`, `v2` | `200: DiffRead` | `404` 版本不存在 |
| `/api/artifacts/{artifactId}/save` | POST | `{ content, title?, writeWorkspace }` | `200: ArtifactRead` 新版本 | `404` Artifact 不存在；`400` workspace 写入失败 |
| `/api/artifacts/{artifactId}/restore` | POST | `{ version, writeWorkspace }` | `200: ArtifactRead` 新版本 | `404` Artifact/版本不存在；`400` workspace 写入失败 |
| `/api/projects/{projectId}/files?path=` | GET | query: `path` | `200: { path, content, size }` | `403` 越界；`404` 文件不存在；`400` 文件过大 |
| `/api/projects/{projectId}/files` | PUT | `{ path, content }` | `200: { path, content, size }` | `403` 越界；`404` workspace 不存在；`400` 非文件路径 |
| `/api/messages/{messageId}/artifacts/scan` | POST | `{ "force": boolean }` | `200: { "created": ArtifactRead[], "candidates": ArtifactCandidateRead[], "skipped": ArtifactSkipRead[] }` | `404` 消息不存在；`409` 消息不属于 Project session |

说明：

- `POST /api/messages/{messageId}/artifacts/scan` 是重试/调试入口。正常聊天链路不要求用户点击它。
- 自动桥接必须发生在 `/api/sessions/{id}/chat` 的服务端流里，且在最终 `done` SSE 之前完成，这样当前 `useSendMessage` 的 `fetchArtifacts(sessionId)` 兜底刷新能拿到最新产物。

### 3.2 事件

| 事件类型 | 方向 | payload 字段 |
|---------|------|-------------|
| `artifact.scan.started` | 后端 → SSE | `{ sessionId, messageId, projectId, agentId?, agentName?, processId? }` |
| `artifact.detected` | ArtifactOutputBridge → EventBus | `{ sessionId, messageId, projectId, agentId?, artifactType, title, source, confidence, filePath?, contentHash, reason }` |
| `artifact.created` | ArtifactService → EventBus/SSE | `{ artifactId, sessionId, messageId, projectId, artifactType, title, version, filePath?, source }` |
| `artifact.scan.completed` | 后端 → SSE | `{ sessionId, messageId, createdCount, candidateCount, skippedCount }` |
| `artifact.detection_failed` | ArtifactOutputBridge → EventBus/SSE | `{ sessionId, messageId, projectId?, reason, recoverable: boolean }` |

事件要求：

- EventBus 增加 `ARTIFACT_DETECTED`、`ARTIFACT_DETECTION_FAILED`。
- SSE 中的 `artifact.created` 用于即时 UI；消息完成后的 `fetchArtifacts` 是一致性兜底。
- `artifact.created` 不能替代 Artifact API 响应，前端最终以 API 返回的 ArtifactRead 为准。

### 3.3 数据库 Schema 变更

现有模型已经包含以下字段，迁移 `009_add_project_workspace_runtime.sql` 已写入：

```sql
ALTER TABLE artifacts ADD COLUMN project_id VARCHAR REFERENCES projects(id);
ALTER TABLE artifacts ADD COLUMN file_path VARCHAR;
ALTER TABLE artifacts ADD COLUMN preview_id VARCHAR;
ALTER TABLE artifacts ADD COLUMN source VARCHAR;
ALTER TABLE artifacts ADD COLUMN confidence VARCHAR;
ALTER TABLE artifacts ADD COLUMN task_id VARCHAR;
```

6F 不新增独立 detection 表。低置信候选写入对应 message metadata：

```json
{
  "artifactBridge": {
    "status": "completed",
    "createdCount": 2,
    "candidateCount": 1,
    "completedAt": "2026-06-05T..."
  },
  "artifactCandidates": [
    {
      "artifactType": "document",
      "title": "说明文档候选",
      "source": "message_code_block",
      "confidence": 0.63,
      "reason": "markdown heading but no expected output",
      "contentPreview": "# ..."
    }
  ]
}
```

Artifact 幂等性不依赖数据库唯一索引。`ArtifactService.create_from_detection()` 必须在创建前用 `message_id + type + source + file_path? + content_hash` 查重。

### 3.4 跨组件 TypeScript 类型（前端）

```typescript
type ArtifactType = "code_diff" | "web_preview" | "document" | "file_tree";
type ArtifactSource = "message_code_block" | "workspace_diff" | "cli_artifact_signal" | "manual_rescan";

interface Artifact {
  id: string;
  sessionId: string;
  messageId: string;
  projectId?: string | null;
  type: ArtifactType;
  title: string;
  content: string;
  status: "rendering" | "ready" | "error";
  version: number;
  parentArtifactId?: string | null;
  filePath?: string | null;
  previewId?: string | null;
  source?: ArtifactSource | string | null;
  createdAt: string;
}

interface ArtifactCandidate {
  artifactType: ArtifactType;
  title: string;
  source: ArtifactSource;
  confidence: number;
  reason: string;
  contentPreview: string;
}

interface ArtifactScanEvent {
  type: "artifact.scan.started" | "artifact.scan.completed" | "artifact.created" | "artifact.detection_failed";
  sessionId: string;
  messageId: string;
}
```

---

## 4. 行为规格

### 4.1 正常流程

```
1. ChatService 准备启动 CLI
   → 如果 session 绑定 Project，则创建 workspace pre-run snapshot
   → snapshotId 写入本次 run 的内存上下文，不暴露给前端

2. CLI Agent 执行
   → 前端继续看到流式回复和 ExecutionTracePanel
   → Adapter 输出 artifact_signal 时，只进入执行轨迹，不直接落库

3. CLI 进程完成且 assistant message 已持久化
   → SingleCliChatStream / GroupChatStream 调用 ArtifactOutputBridge.scan_completed_message()
   → 输入包含 messageId、sessionId、projectId、agentId、visibleContent、rawOutputPreview、executionTrace、snapshotId

4. ArtifactOutputBridge 收集候选
   → 从 workspace diff 生成文件变更候选
   → 从 message fenced code block 生成代码块候选
   → 从 executionTrace artifact/file/command items 提取辅助上下文
   → 合并相同 filePath 或相同 contentHash 的候选

5. ArtifactOutputBridge 决策
   → confidence >= 0.80：调用 ArtifactService.create_from_detection()
   → 0.50 <= confidence < 0.80：写入 message.metadata.artifactCandidates，不落库
   → confidence < 0.50：忽略

6. ArtifactService 创建 Artifact
   → version=1、status="ready" 或 "error"
   → 绑定 session_id、message_id、project_id、file_path、source、confidence；Agent 身份通过关联 message 追溯
   → 发布 artifact.created

7. SSE 输出
   → artifact.created 即时 upsert 到 chatStore.artifacts
   → artifact.scan.completed 更新消息 metadata 中的 artifactBridge 状态
   → 最终 done 事件发出
   → useSendMessage 继续 fetchMessages + fetchArtifacts 做兜底刷新

当前实现补充：

- `POST /api/messages/{messageId}/artifacts/scan { force: true }` 可基于消息文本和 executionTrace 中的路径线索从当前 workspace 读取文件，作为自动扫描失败后的手动重试路径。
- `manual_rescan` 与自动 `workspace_diff` 对同一 message/file/content hash 幂等，不重复落库。
- 群聊路径在每个 Agent 调用前创建 workspace snapshot，并在 finalizer 中把 `workspacePath`、`workspaceSnapshotId`、`engineRuntime`、`engineSession` 和 execution trace 合并到对应 Agent 子消息 metadata；Artifact Bridge 随后扫描该 Agent 消息的 workspace diff、文本/代码块与轨迹，产物绑定各自 messageId/sourceId，不挂到 Orchestrator 总结或会话级全局位置。
```

### 4.2 检测输入与产物类型

| 输入 | 产物类型 | 自动落库条件 | 内容写入方式 |
|------|----------|--------------|--------------|
| workspace 新增/修改 `index.html`、`*.html` | `web_preview` | 文件存在、可读、大小 <= 1MB，且包含 HTML 结构 | `content = 文件内容`，`file_path = 相对路径` |
| workspace 新增/修改 `package.json` + `src/App.tsx` 等前端项目文件 | `file_tree` | 本次 diff changedFiles >= 2，且至少一个前端入口/配置文件 | `content = JSON.stringify({ changes })` |
| workspace diffPreview 为 unified diff | `code_diff` | diffPreview 非空，且总 diff <= 1MB | `content = 合并后的 unified diff` |
| message fenced `html` 代码块 | `web_preview` | 代码块闭合，包含 HTML/JSX 可渲染结构，大小 <= 1MB | `content = 代码块内容`，`file_path = null` |
| message fenced `diff`/`patch` 代码块 | `code_diff` | 包含 `@@` 或 `--- a/` / `+++ b/` | `content = 代码块内容` |
| message fenced `md`/长 Markdown | `document` | 明确标题结构，或 executionTrace/expected output 指向 document | `content = Markdown 内容` |
| CLI `artifact_signal` | 不单独决定类型 | 只提升相关候选 confidence，并作为 trace 证据保存 | 不直接作为 Artifact content |

### 4.3 置信度决策

| 条件 | 分数影响 |
|------|----------|
| workspace 真实文件变更，且文件可读 | `+0.90` 基准 |
| message 完整 fenced code block | `+0.75` 基准 |
| executionTrace 中出现 artifact/file 轨迹，target 与候选路径一致 | `+0.10` |
| CLI 工具命令明确写入目标文件，例如 `cat > index.html`、`Write`、`Edit` | `+0.10` |
| 候选类型匹配 Orchestrator `expected_outputs`（如果存在） | `+0.15` |
| 内容过短或只有占位文本 | `-0.20` |
| 文件过大、二进制、不可读 | 自动降级为 `status="error"` 或跳过 |

最终分层：

| 置信度 | 行为 |
|--------|------|
| `>= 0.80` | 自动创建 Artifact |
| `0.50 - 0.79` | 不落库，写入 `message.metadata.artifactCandidates` |
| `< 0.50` | 忽略，不写 metadata |

### 4.4 UX 六态覆盖

| 状态 | 用户看到什么 | 触发条件 |
|------|------------|---------|
| **空态** | 聊天里只有普通消息和执行轨迹；没有任何独立产物工作台占位 | 当前 session 没有 Artifact |
| **加载态** | Agent 回复完成后，相关消息下方出现一行轻量状态：Loader2 图标 + “分析产物中” | 收到 `artifact.scan.started` |
| **正常态** | 消息下方出现 `MessageArtifactStrip`，直接展示 1-N 个紧凑 ArtifactCard | 收到 `artifact.created` 或 artifacts refresh 后有数据 |
| **完成态** | ArtifactCard 显示类型、标题、版本和预览；执行轨迹自动保持折叠；用户当前位置不被强制滚动到底部 | 收到 `artifact.scan.completed` |
| **错误态** | 消息下方显示小型错误条：AlertTriangle 图标 + “产物分析失败”；不遮挡 Agent 文本 | `artifact.detection_failed` 或 scan API 失败 |
| **边界态** | 多个产物按消息内卡片纵向排列；窄屏仍留在消息流中；超大文件显示 error 状态卡片 | 多产物、窄屏、超大内容 |

### 4.5 错误处理

| 错误场景 | 错误码 | 用户可见文案 | 恢复路径 |
|---------|--------|------------|---------|
| session 没有 project | `409 SESSION_WITHOUT_PROJECT` | “当前对话未绑定项目，无法生成产物” | 只保存文本；提示用户在 Project 下重新发起对话 |
| snapshot 不存在或 diff 失败 | `BRIDGE_DIFF_FAILED` | 不弹全局错误；消息下方显示“文件变更分析失败，已保留回复文本” | 允许点击重新分析；仍扫描消息代码块 |
| Artifact 落库失败 | `BRIDGE_CREATE_FAILED` | “产物创建失败” | `POST /api/messages/{messageId}/artifacts/scan` 重试 |
| 内容超过 1MB | `ARTIFACT_TOO_LARGE` | ArtifactCard 显示“内容过大，无法在线预览” | 保留 filePath；用户可从 workspace 打开 |
| 代码块未闭合 | 无 | 无额外提示 | 文本原样保留，不创建候选 |
| 重复扫描同一消息 | 无 | UI 不重复新增卡片 | 幂等返回已有 Artifact |

---

## 5. 前端页面设计

### 5.1 页面布局

```text
┌───────────────┬──────────────────────┬─────────────────────────────┐
│ ProjectSidebar │ SessionSidebar        │ ChatWindow                  │
│               │                      │ ┌─────────────────────────┐ │
│ CLI 好友       │ 会话列表              │ │ MessageList              │ │
│ Project 列表   │ 搜索/创建入口         │ │ MessageBubble            │ │
│               │                      │ │ ExecutionTracePanel      │ │
│               │                      │ │ MessageArtifactStrip     │ │
│               │                      │ └─────────────────────────┘ │
└───────────────┴──────────────────────┴─────────────────────────────┘
```

区域规则：

- `MessageList` 是主滚动区。产物创建不能强制滚到底部，只能在当前消息附近局部更新。
- `ExecutionTracePanel` 继续位于 Agent 回复下方，运行中可展开且内部独立滚动。
- `MessageArtifactStrip` 位于同一条 assistant 消息的执行轨迹之后，完整展示与该消息绑定的 ArtifactCard。
- 不再存在独立右侧产物工作台，也不再存在移动端底部产物 dock；产物与代码变更都跟随具体消息上下文呈现。

### 5.2 组件树

```text
ChatWindow
├── ChatHeader
├── MessageList
│   └── MessageBubble[]
│       ├── AgentAvatar
│       ├── ReactMarkdown
│       ├── ExecutionTracePanel
│       └── MessageArtifactStrip
│           └── ArtifactCard[]
├── SessionArtifactManager
├── FileEditorModal
├── ArtifactVersionManager
└── ChatInput
```

新增/调整组件：

- `MessageArtifactStrip`: 根据 `message.id` 从 `artifacts` 中筛选 `artifact.messageId === message.id`，并在消息下方渲染完整卡片组。
- `ArtifactCard`: 紧凑深色开发工具风格卡片，承载 web/code/document/file_tree 预览；点击卡片打开完整弹窗。
- `DiffViewer`: 使用统一 VS Code/GitHub 风格 diff 表格，保留行号、hunk、增删行底色，不再提供“左右/上下”切换。
- `ArtifactCard` 弹窗不提供“起始/变更”版本选择；存在版本链时固定比较最新版本与上一版本，v1 产物直接展示当前内容或本次 unified diff。
- `ArtifactCard` 全屏弹层挂载到页面级 overlay，不受消息气泡、iframe 或滚动容器的裁剪/挤压影响。
- `FileEditorModal`: 从 Artifact 或 workspace 文件打开页面级文件编辑器；支持直接输入修改、保存为 Artifact 新版本或写回 workspace 文件。
- `FileEditorModal` 选区交互：用户选中代码后显示“添加到对话”按钮，点击后聚焦 ChatInput，并附带 `[Code reference: path:start-end]` 代码引用块。
- `ArtifactVersionManager`: Artifact 专属版本管理界面；支持撤销本次修改，或选择历史版本并恢复为新的当前版本。
- `SessionArtifactManager`: Chat Header 搜索按钮旁的文件入口，按当前会话列出文件、资产和变更，用户可搜索并预览。

### 5.3 关键视觉元素

| 元素 | 位置 | 视觉规格 |
|------|------|---------|
| 产物分析状态 | MessageBubble 底部 | 高度 28px，半透明深色背景，Loader2 14px，文字 12px，圆角 8px |
| ArtifactCard | MessageArtifactStrip | 圆角 8px，紧凑 header，深色开发工具色，标题单行截断，右侧打开图标 |
| web_preview 图标 | ArtifactCard | lucide `Globe2`，不使用 emoji |
| code_diff 图标 | ArtifactCard | lucide `FileCode2` |
| document 图标 | ArtifactCard | lucide `FileText` |
| file_tree 图标 | ArtifactCard | lucide `Files` |
| 编辑文件按钮 | ArtifactCard / file_tree 行 | lucide `FilePenLine`，点击打开页面级文件编辑器 |
| 版本管理按钮 | ArtifactCard / 弹窗 | lucide `History`，点击打开版本管理界面 |
| 会话文件按钮 | ChatHeader 搜索按钮旁 | lucide `Files`，打开会话产物管理界面 |
| 代码引用卡片 | ChatInput 上方 | lucide `FileCode2` + `Code2`，显示路径、行号和字符数 |
| 文件变更 hover diff | file_tree 卡片文件行 | hover 时显示小型 diff 卡；点击卡片打开完整弹窗展示每个文件 diff |
| code_diff 预览 | ArtifactCard / 弹窗 | 统一 diff 表格，接近 VS Code/GitHub 风格，无左右/上下模式切换 |
| web_preview 卡片 | ArtifactCard | 预览区高度不低于 18rem，保留现有全局滚动条风格 |
| 错误状态 | MessageArtifactStrip / ArtifactCard | lucide `AlertTriangle`，琥珀色边框，不弹出阻断式 toast |

---

## 6. 前端交互序列

### 6.1 自动生成产物

```
用户: 发送消息
  → 前端: 用户新消息定位到视口顶部附近
  → 后端: CLI Agent 流式输出文本和执行轨迹
  → 前端: MessageBubble 流式更新；ExecutionTracePanel 运行中
  → SSE: agent.process.completed
  → SSE: artifact.scan.started
  → 前端: 对应 MessageBubble 底部显示“分析产物中”
  → SSE: artifact.created
  → 前端: chatStore.upsertArtifact(artifact)
  → 前端: MessageArtifactStrip 在对应消息下方出现 ArtifactCard
  → SSE: artifact.scan.completed
  → 前端: 去掉分析状态；不改变用户当前滚动位置
  → SSE: done
  → 前端: fetchMessages + fetchArtifacts 兜底刷新
```

### 6.2 打开产物

```
用户: hover file_tree 卡片中的文件变更行
  → 前端: 在光标附近显示小型 unified diff 卡片
用户: 点击消息下方 ArtifactCard
  → 前端: 打开 ArtifactCard 全屏预览/编辑弹层
  → 前端: code_diff 直接展示统一 diff；file_tree 展示每个文件对应的 diff 卡片
  → 后端: web_preview 若有 projectId/filePath，则调用 /api/projects/{projectId}/preview
```

### 6.3 重新分析产物

```
用户: 在产物分析失败条上点击重试
  → 前端: POST /api/messages/{messageId}/artifacts/scan { force: true }
  → 后端: 重新扫描 message content + 当前 workspace 文件状态；不重复创建已有 Artifact
  → 前端: 用响应中的 created/candidates 更新 UI；失败时只显示局部错误
```

### 6.4 候选产物

```
SSE/API: scan completed with candidateCount > 0 and createdCount = 0
  → 前端: 默认不打扰用户，不显示大卡片
  → MessageBubble: 可显示一行低强调提示“有 1 个低置信产物候选”
  → 后续 Phase: 可增加用户确认创建候选产物
```

### 6.5 编辑文件与片段引用

```
用户: 点击 ArtifactCard 或 file_tree 行内“编辑文件”
  → 前端: 打开 FileEditorModal 页面级弹窗
  → 后端: 若 artifact.projectId + filePath 存在，GET /api/projects/{projectId}/files?path=...
  → 用户: 直接修改文本并保存
  → 前端: Artifact 内容调用 /api/artifacts/{id}/save；workspace 文件调用 /api/projects/{projectId}/files PUT
  → 后端: 创建 Artifact 新版本或写回 workspace
  → 前端: refresh artifacts，卡片显示最新版本

用户: 在 FileEditorModal 选中代码片段
  → 前端: 显示“添加到对话”
  → 用户点击
  → 前端: ChatInput 显示代码引用卡片并聚焦输入框
  → 用户补充修改意见并发送
  → 后端: 收到包含 [Code reference: path:start-end] 和 fenced code block 的真实消息内容
```

### 6.6 版本管理

```
用户: 点击 ArtifactCard 的版本管理按钮
  → 前端: 打开 ArtifactVersionManager
  → 后端: GET /api/artifacts/{id}/versions
  → 用户: 点击“撤销本次修改”
  → 前端: POST /api/artifacts/{id}/restore { version: previous, writeWorkspace: true }
  → 后端: 将目标历史内容恢复为一个新的当前版本，并按需写回 workspace 文件

用户: 选择任意历史版本并点击“跳转到此版本”
  → 前端/后端: 同上，目标版本内容成为新的当前版本
```

---

## 7. 验收标准

- [x] AC-BR-01: 单聊 Claude Code 在 workspace 写入 `index.html` 后，最终 `done` 之前创建 `web_preview` Artifact，字段包含 `projectId`、`messageId`、`filePath="index.html"`。
- [x] AC-BR-02: Codex/CLI 只输出完整 fenced `diff` 代码块时，创建 `code_diff` Artifact，`content` 等于该 diff 内容。
- [x] AC-BR-03: CLI 创建或修改 2 个以上项目文件时，创建 `file_tree` Artifact，`content` JSON 中包含全部 changed file path 和 change 类型。
- [x] AC-BR-04: 未闭合代码块不会创建 Artifact，也不会写入候选。
- [x] AC-BR-05: confidence 0.50-0.79 的候选写入 `message.metadata.artifactCandidates`，`GET /api/sessions/{id}/artifacts` 不返回它。
- [x] AC-BR-06: 同一 message 重复扫描不会创建重复 Artifact；返回 skipped duplicate 记录。
- [x] AC-BR-07: Artifact 创建失败不影响 assistant message 保存、执行轨迹保存和最终 done。
- [x] AC-BR-08: 前端在 `artifact.created` 后不强制滚到底部；用户仍停留在新发消息附近。
- [x] AC-BR-09: MessageArtifactStrip 只展示与当前 messageId 绑定的 Artifact，并在消息下方直接渲染完整 ArtifactCard。
- [x] AC-BR-10: `file_tree`、`web_preview`、`code_diff`、`document` 四类产物均有 lucide 图标、加载态、错误态和移动端展示。
- [x] AC-BR-11: 代码 diff 与文件变更 diff 使用统一 VS Code/GitHub 风格展示；没有“左右/上下”切换。
- [x] AC-BR-12: file_tree 中的单文件变更 hover 显示具体 diff 小卡；点击卡片弹窗展示完整 diff 列表。
- [x] AC-BR-13: 新创建 Artifact 可继续使用 Phase 5 的 versions、diff、edit API。
- [x] AC-BR-14: 群聊中每个 Agent 子消息创建的 Artifact 绑定各自的 messageId，不挂到最终 Orchestrator 总结消息上。
- [x] AC-BR-15: Artifact 全屏弹窗不显示“起始/变更”版本选择；版本链固定按最新版本与上一版本比较。
- [x] AC-BR-16: Artifact 全屏弹窗从页面级 overlay 打开，不会被消息气泡或聊天滚动容器挤压在内部。
- [x] AC-BR-17: 每个可编辑 Artifact 或文件变更行提供编辑文件按钮；用户可在 FileEditorModal 直接输入修改并保存。
- [x] AC-BR-18: FileEditorModal 中选中代码后可添加到对话，ChatInput 展示代码引用卡片，发送内容包含代码引用块。
- [x] AC-BR-19: ArtifactVersionManager 支持撤销本次修改，并支持跳转到任意历史版本。
- [x] AC-BR-20: Chat Header 搜索按钮旁提供会话文件入口，打开当前会话的文件、资产与变更管理界面。
- [x] AC-BR-21: “Agent 正在回答”状态挪到左侧 Agent 头像区域旁边；搜索/文件按钮只保留明确图标按钮。
- [x] AC-BR-22: Claude Code、Codex、OpenCode 三个 Agent 头像显示厂商 logo 图像，不使用 emoji 或文本占位。
- [x] AC-BR-23: 群聊中两个 Agent 分别写入 workspace 文件时，生成的 `workspace_diff` `web_preview/code_diff` Artifact 分别绑定到各自 Agent 子消息，并可通过 `messageId -> sourceId` 追溯 Agent 身份。

验收记录（2026-06-05）：

- 自动测试：`cd backend && .\venv\Scripts\python.exe -m pytest test_api/test_artifact_output_bridge_phase6.py -q` → 10 passed。
- 邻近回归：`cd backend && .\venv\Scripts\python.exe -m pytest test_api/test_chat.py test_api/test_group_chat.py test_api/test_artifact_output_bridge_phase6.py test_api/test_artifacts_phase5.py test_unit/test_cli_adapter_runtime.py -q` → 76 passed。
- 前端：`cd frontend && npx tsc --noEmit`，`npx vitest run src/components/MessageArtifactStrip.test.tsx src/components/ArtifactCard.test.tsx` → 7 passed。
- 真实 cc 服务验收：`cd backend && .\venv\Scripts\python.exe test_real_api_claude_artifact_bridge.py` → ok=true；Claude Code 2.1.165 在临时 workspace 写入 `index.html`、`package.json`、`src/App.tsx`，最终 `done` 前创建 `web_preview`、`file_tree`、`code_diff` 三类 Artifact。
- UI 增强回归（2026-06-06）：`cd frontend && npx tsc --noEmit`，`npx vitest run src/components/MessageArtifactStrip.test.tsx src/components/ArtifactCard.test.tsx src/components/ChatInput.test.tsx src/api/client.test.ts` → 23 passed；`npm run build` → passed（仅 Vite chunk 体积告警）。
- 后端增强回归（2026-06-06）：`cd backend && .\venv\Scripts\python.exe -m pytest test_api/test_chat.py test_api/test_group_chat.py test_api/test_artifact_output_bridge_phase6.py test_api/test_artifacts_phase5.py test_api/test_projects_phase6.py test_unit/test_cli_adapter_runtime.py test_unit/test_codex_local_config_service.py -q` → 98 passed。
- 人工验收（2026-06-06）：确认产物工作台已移除，消息下方 Artifact 卡片、VS Code/GitHub 风格 diff、页面级弹窗、IDE 风格 CodeMirror 文件编辑器、代码片段引用、版本管理、会话文件入口和 CLI Agent logo 头像均通过本轮验收。交付快照见 [../../deliverables/phase6-artifact-bridge/README.md](../../deliverables/phase6-artifact-bridge/README.md)。
- 群聊同步验收（2026-06-08）：`backend/test_api/test_group_chat.py` 与 `backend/test_api/test_artifact_output_bridge_phase6.py` 覆盖群聊同一 Agent runtime 复用、EngineSession 持久化、两个 Agent 分别写入 HTML 后各自生成 `workspace_diff` `web_preview/code_diff` Artifact；真实 HTTP 服务验收创建临时 Project + 群聊 + 两个 custom CLI Agent，得到 2 个 web preview、2 个 code diff，均绑定到对应 Agent 消息。

---

## 8. 测试策略

### 8.1 单元测试（24 条）

| 测试对象 | 条数 | 覆盖内容 |
|---------|------|---------|
| `ArtifactDetector` | 8 | html/diff/document/file_tree/未闭合代码块/多代码块/超大内容/低置信候选 |
| `ArtifactOutputBridge` | 6 | scan input 组装、workspace diff 合并、trace 加权、候选写 metadata、失败不阻断、scan summary |
| `ArtifactService.create_from_detection` | 5 | v1 创建、字段绑定、幂等查重、error 状态、EventBus publish |
| `Message metadata merge` | 2 | 保留 executionTrace；追加 artifactBridge/artifactCandidates |
| `file_tree content builder` | 3 | created/modified/deleted、路径排序、JSON 格式稳定 |

### 8.2 集成测试

- 单聊真实服务路径：测试 CLI fixture 写入 `index.html` → message 持久化 → bridge 创建 `web_preview` → artifacts API 可查。
- workspace diff 路径：pre snapshot → 写 3 个文件 → post diff → 创建 `file_tree` Artifact。
- 低置信路径：Markdown 候选 → 不落库 → message metadata 有 candidate。
- 幂等路径：同一 message 调用 scan 两次 → Artifact 数量不增加。
- 群聊路径：两个 Agent 各自写入 workspace 文件 → 两个 Agent messageId 下分别生成 `workspace_diff` Artifact，且 `message.sourceId` 对应写入 Agent。

### 8.3 E2E 测试

- 浏览器真实流程：创建 Project → 选择 Claude Code/Codex/OpenCode → 让 Agent 生成 HTML 文件 → 对应消息下方出现网页 ArtifactCard → 打开预览。
- 移动宽度流程：生成产物后消息下方直接出现卡片，MessageArtifactStrip 不遮挡聊天输入框。
- 错误流程：模拟 scan failed，Agent 文本和执行轨迹仍可阅读，错误只出现在消息局部。

---

## 9. 架构约束追溯

| 本模块的决策 | 依据 |
|------------|------|
| CLI 进程必须在 `Project.workspace_path` 执行，Artifact 绑定 project_id | ADR-0009 核心规则 1-3；PRD-06 |
| Adapter 不直接写 Artifact 表 | PRD-01 §3.4；Phase 6 README 关键原则 |
| Artifact 创建统一进入 ArtifactService | PRD-05 端到端产品闭环；Phase 5 ArtifactService |
| 执行过程继续由 ExecutionTracePanel 承载，产物作为消息下方卡片展示 | ADR-0009 分层渲染；当前 CLI Adapter 交付文档 |
| 前端使用 Telegram 风格消息气泡、独立执行流程块、lucide 图标 | PRD-03；当前 ChatWindow/MessageBubble/ArtifactCard 设计 |
| 低置信结果不自动落库 | PRD-05 产物创建规则；避免污染用户 workspace 产物列表 |

---

## 10. 依赖

| 依赖模块 | 需要的接口 | 当前状态 |
|---------|-----------|---------|
| Phase 6A Workspace Runtime | Project/session 绑定、workspace path、FileChangeDetector、preview API | 已就绪 |
| Phase 6B-6E CLI Adapter | `agent.output`、`agent.trace.delta`、`agent.process.completed`、message metadata executionTrace | 实现基线已落地 |
| Phase 5 ArtifactService | versions、diff、edit、list_current_artifacts | 已就绪；需新增 `create_from_detection` |
| EventBus | `ARTIFACT_CREATED` 已有 | 需新增 `ARTIFACT_DETECTED`、`ARTIFACT_DETECTION_FAILED` |
| 前端 Chat UI | ChatWindow、MessageBubble、ExecutionTracePanel、ArtifactCard、chatStore.upsertArtifact | 已就绪；需新增 MessageArtifactStrip 和 artifact SSE handler |

---

## 11. Non-Goals（明确不做什么）

| 不做的事 | 原因 | 由谁负责 |
|---------|------|---------|
| 不做完整 VS Code/IDE 级项目浏览器、调试器或实时协作编辑 | 6F 只提供产物级/文件级编辑、引用和版本管理，主流程仍是聊天 | P2/远期 |
| 不实现部署发布按钮 | P2 Roadmap | SaaS/部署模块 |
| 不解析或预览二进制图片、压缩包、视频 | 当前 Artifact content 是文本模型 | 后续多媒体 Artifact |
| 不要求用户确认高置信 Artifact | 6F 目标是自动打通链路 | 低置信候选确认可由后续 UI 增强 |
| 不把所有代码块都变成 Artifact | 避免污染用户的产物列表 | 本模块按置信度过滤 |
| 不把 ArtifactCard 迁移到全局 Drawer | 当前已有页面级弹层可用；P1 路线已由 ADR-0010 收敛为消息级 Artifact 体验 | 无 |

---

## 12. 破坏性变更与迁移

| 维度 | V1 行为 | V2 行为 | 迁移路径 |
|------|--------|--------|---------|
| Artifact 创建入口 | 主要依赖手工 seed 或测试创建，Agent 输出不稳定落库 | CLI 消息完成后自动扫描并创建 Artifact | 新增 `ArtifactOutputBridge`，接入 single/group chat stream |
| 产物 UI | session 级右侧 ArtifactCard 列表 | message 级完整 ArtifactCard 卡片流 | `MessageArtifactStrip` 承载卡片组，移除独立工作台 |
| Artifact 类型 | 前端类型只有 `code_diff/web_preview/document` | 增加 `file_tree` | 扩展 TypeScript union、ArtifactCard label/icon/preview |
| Artifact 编辑 UI | 独立 CodeSelector 选区编辑组件 | ArtifactCard/FileEditorModal 内联编辑 + ChatInput 代码引用 | 删除 `CodeSelector`，保留后端 edit/save/restore API |
| Artifact 版本 UI | `VersionHistory` 下拉选择 | `ArtifactVersionManager` 专属界面 | 删除 `VersionHistory`，支持撤销与跳转历史版本 |
| 低置信检测 | 无记录 | 写入 message metadata，不落库 | metadata 兼容旧消息；无 DB 迁移 |
| EventBus | 只有 `artifact.created/updated` | 增加 `artifact.detected/detection_failed` | 扩展 `EventType`，旧订阅者不受影响 |

> **版本历史**
> - v1.0 (2026-06-03): 初始版本
> - v2.0 (2026-06-04): 按旧版 Phase 6 设计加入 `artifact.detected`、workspace diff、置信度分层
> - v2.1 (2026-06-04): 同步 Phase 6A workspace runtime 已验收状态
> - v3.0 (2026-06-05): 按新版 SPEC_TEMPLATE 和当前 CLI Adapter/Telegram UI/ArtifactCard 实现重构，明确自动桥接触发点、真实字段、前端消息附件条和剩余实现契约
> - v3.1 (2026-06-05): 记录 6F 核心闭环完成：自动扫描、手动重扫、幂等、低置信候选、MessageArtifactStrip、真实 Claude Code 验收
> - v3.2 (2026-06-05): 移除独立产物工作台，产物与代码变更改为消息下方紧凑卡片流；diff UI 收敛为 VS Code/GitHub 风格统一视图，支持文件行 hover diff 与点击完整弹窗
> - v3.3 (2026-06-05): 移除 Artifact 弹窗中的起始/变更版本选择，固定比较最新版本与上一版本；全屏弹层改为页面级 overlay，避免被消息气泡容器挤压
> - v3.4 (2026-06-06): 增加产物/文件编辑器、代码片段引用、Artifact 专属版本管理、会话文件入口、Agent 状态位置调整和三类 CLI Agent logo 头像
> - v3.5 (2026-06-06): 记录本轮人工验收通过，并补充 Phase 6F deliverables 交付快照
> - v3.6 (2026-06-08): 同步群聊重构：每个 Agent 调用前创建 workspace snapshot，finalizer 按 Agent 子消息扫描 workspace diff 并绑定 Artifact
