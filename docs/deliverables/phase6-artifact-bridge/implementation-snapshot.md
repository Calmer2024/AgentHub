# Phase 6F 实现快照

**日期**: 2026-06-06
**状态**: 验收通过

## 1. 后端桥接

本轮新增 `backend/app/services/artifact_output_bridge.py`，在 CLI assistant message 已经持久化、最终 `done` SSE 发出之前运行扫描。输入来自三类信号：

- workspace 执行前后 snapshot diff；
- assistant visible content / raw output preview 中的 fenced code block；
- `message.metadata.executionTrace.items[]` 中的文件、命令和 artifact 信号。

高置信候选通过 `ArtifactService.create_from_detection()` 统一创建 v1 Artifact，绑定 `session_id`、`message_id`、`project_id`、`file_path`、`source`、`confidence`、`task_id`。低置信候选只写入 `message.metadata.artifactCandidates`，不污染会话产物列表。

幂等边界采用 `message_id + artifact_type + source + file_path/content_hash`，同一条消息重复自动扫描或手动重扫不会重复创建产物。

2026-06-08 群聊链路已同步单聊桥接模型：`CliAgentExecutor` 在每个群聊 Agent 调用前创建 workspace snapshot，并把 `workspaceSnapshotId`、`workspacePath`、`engineRuntime`、`engineSession` 等 metadata 交给 `GroupChatStream`/`GroupChatFinalizer`；finalizer 持久化对应 Agent 子消息后调用 Artifact Bridge。这样同一群聊内多个 Agent 写出的文件会分别绑定到各自 Agent messageId/sourceId。

## 2. API 与事件

新增或扩展的关键能力：

- `POST /api/messages/{messageId}/artifacts/scan`：手动重扫/调试入口，支持 `force=true`。
- `GET /api/projects/{projectId}/files?path=`：文件编辑器读取 workspace 文件。
- `PUT /api/projects/{projectId}/files`：文件编辑器写回 workspace 文件。
- `POST /api/artifacts/{artifactId}/save`：保存 Artifact 新版本。
- `POST /api/artifacts/{artifactId}/restore`：恢复历史版本为新的当前版本。
- SSE `artifact.scan.started`、`artifact.created`、`artifact.scan.completed`、`artifact.detection_failed`：驱动消息局部产物状态。

## 3. 前端消息级产物

独立产物工作台已移除。产物现在由 `MessageArtifactStrip` 按 `messageId` 挂到对应 assistant 消息下方，`ArtifactCard` 负责四类产物展示：

- `web_preview`：更高的网页预览卡片，复用全局滚动条样式；
- `file_tree`：文件变更列表，hover 单文件 diff，点击打开完整文件 diff；
- `code_diff`：VS Code/GitHub 风格 unified diff；
- `document`：Markdown/文本内容预览。

`DiffViewer` 已取消“左右/上下”切换，统一使用紧凑清晰的 unified diff 表格，并保留行号、hunk、增删行背景。

## 4. 编辑器与代码引用

`FileEditorModal` 已升级为 IDE 风格编辑器，底层使用 CodeMirror：

- 行号、active line、fold gutter、括号匹配、搜索 keymap；
- HTML、CSS、JavaScript/TypeScript、JSON、Markdown、Python 语法高亮；
- 状态栏展示语言、行列、字符数和 modified 状态；
- 选中代码后显示“添加到对话”，把 `[Code reference: path:start-end]` 和 fenced code block 注入 ChatInput。

旧的 `CodeSelector` 在线编辑组件已删除，避免两套编辑心智并存。

## 5. 版本与会话管理

`ArtifactVersionManager` 提供专属版本界面：

- “撤销本次修改”恢复上一版本；
- 选择任意历史版本后可“跳转到此版本”；
- 恢复动作仍创建新版本，保持版本链可追溯。

`SessionArtifactManager` 由 Chat Header 搜索按钮旁的文件图标打开，集中查看当前会话产生的文件、资产与变更，并可直接预览卡片。

## 6. UI 调整

- “Agent 正在回答”状态已挪到左侧 Agent 头像旁边。
- Claude Code、Codex、OpenCode 头像改为具体厂商 logo 图像，不使用 emoji 或文本占位。
- 弹窗使用页面级 portal overlay，不再被消息气泡或滚动容器挤压。
- 新增按钮均使用 lucide 图标，保持产品整体设计语言。
