# 需求规格说明书 (PRD)：04 - 数据结构与 API 契约 (Data Model & API Contracts)

## 1. 文档定位
本文档专为**全栈研发工程师**及**数据库管理员 (DBA)** 编写。
它将前文所有的宏观产品愿景、复杂的 Orchestrator DAG 调度算法，收敛为了具体、可执行的数据表结构与 REST/SSE 接口规范。这里是代码落地的第一站。

---

## 2. 数据库实体关系 (Entity Relationship Schema)

建议使用 PostgreSQL 或 SQLite。以下采用标准的 SQL 或 ORM 伪代码描述核心业务表。

### 2.1 Agent Profile 实体表 (`agents`)
代表平台中“专家”的用户可见身份。注意，我们剥离了传统的 LLM Provider 概念，也不再把 Claude Code / Codex / OpenCode 这些 CLI 工具直接等同为 Agent。CLI 工具是 Engine；Agent Profile = Engine + Toolset + Context Policy + Runtime Config + System Prompt + Rules。

```sql
CREATE TABLE agents (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL, -- 展示名称，如 "前端专家"
    avatar VARCHAR(4096),       -- 头像：preset:* 或用户上传的 data:image
    agent_type VARCHAR(50) NOT NULL, -- 当前主要为 'cli_wrapper'
    engine_type VARCHAR(50) NOT NULL, -- claude_code, codex, opencode, custom
    executable VARCHAR(255),    -- Engine 可执行文件，如 'claude', 'codex', 'opencode'
    init_args JSONB,            -- CLI 启动参数，如 ["--theme=dark", "--compact"]
    toolset JSONB,              -- 工具集 ID 数组；自定义 Agent 不区分主/辅
    context_policy VARCHAR(100),-- workspace_coding, planning_only, review_only 等
    system_prompt TEXT,         -- Agent 身份提示
    rules TEXT,                 -- Agent 行为规则
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

兼容说明：当前实现表名为 `agent_configs`，字段 `cli_tool` 对应此处的 `engine_type`。旧字段 `primary_skill` / `auxiliary_skills` 仅作为内部匹配和历史数据兼容，不再作为用户自定义 Agent 的主模型。

### 2.2 Project、会话与历史记录 (`projects`, `sessions` & `messages`)
由于我们需要高度复用传统 IM 聊天的 UI，会话表设计接近微信/Slack。

```sql
CREATE TABLE projects (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    workspace_path VARCHAR(1024) NOT NULL UNIQUE, -- 后端内部使用的绝对物理路径，不直接暴露给前端
    status VARCHAR(50) DEFAULT 'ready', -- creating, ready, building, error, archived
    metadata_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sessions (
    id UUID PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    project_id UUID REFERENCES projects(id), -- 所有会话归属 Project，并继承 Project.workspace_path
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE messages (
    id UUID PRIMARY KEY,
    session_id UUID REFERENCES sessions(id),
    sender_type VARCHAR(50), -- 'user', 'agent', 'system'
    sender_id UUID,          -- 如果是 agent 发的，关联 agent_id
    content_type VARCHAR(50),-- 'text', 'artifact_card', 'dag_card'
    content TEXT,            -- 纯文本内容，或 JSON String (对于卡片类型)
    reply_to_id UUID,        -- 用于实现“引用历史版本重试”功能
    referenced_artifact_id UUID, -- 用户从产物卡片/抽屉发起修改时携带
    referenced_artifact_version INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2.3 Orchestrator 核心调度表 (`tasks` & `task_dependencies`)
这部分表结构支撑了整个系统的“大脑”（DAG 引擎）的运转。

```sql
CREATE TABLE tasks (
    id UUID PRIMARY KEY,
    session_id UUID REFERENCES sessions(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    assigned_agent_id UUID REFERENCES agents(id),
    required_skills JSONB, -- Orchestrator 声明该任务需要的能力标签，如 ["frontend", "react"]
    assignment_reason TEXT,
    status VARCHAR(50) DEFAULT 'PENDING', -- PENDING, RUNNING, PAUSED, COMPLETED, FAILED
    requires_approval BOOLEAN DEFAULT FALSE,
    expected_outputs JSONB, -- [{ type: 'artifact', artifact_type: 'web_preview', title_hint: 'LoginPage' }]
    pid INTEGER, -- 当处于 RUNNING 状态时，记录后台真实的进程号，方便强杀
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 有向无环图关联表
CREATE TABLE task_dependencies (
    task_id UUID REFERENCES tasks(id),      -- 当前任务
    depends_on_id UUID REFERENCES tasks(id),-- 依赖的前置任务
    PRIMARY KEY (task_id, depends_on_id)
);
```

### 2.4 Artifact 与版本链 (`artifacts`)

Artifact 是 AgentHub 的核心富媒体产物。它必须能从聊天消息、Orchestrator 任务、版本历史三个维度追溯。

```sql
CREATE TABLE artifacts (
    id UUID PRIMARY KEY,
    session_id UUID REFERENCES sessions(id),
    message_id UUID REFERENCES messages(id),
    task_id UUID REFERENCES tasks(id),
    project_id UUID REFERENCES projects(id),
    artifact_type VARCHAR(50) NOT NULL, -- code_diff, web_preview, document, file_tree
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'ready', -- rendering, ready, error
    version INTEGER DEFAULT 1,
    parent_artifact_id UUID REFERENCES artifacts(id),
    file_path VARCHAR(1024), -- workspace 内相对路径
    preview_id UUID,
    source VARCHAR(50), -- api_agent, cli_agent, orchestrator, user_edit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

关键约束：
- 会话产物列表默认只展示版本链头节点，即每条链的最新版本。
- `parent_artifact_id` 用于版本追溯，不能用于表达多个文件之间的包含关系。
- workspace 产物必须记录 `project_id`；`file_path` 只能保存 Project workspace 内相对路径。
- Artifact 创建后必须发布 `artifact.created` 事件，前端据此刷新聊天流消息级卡片和页面级预览/编辑入口。

---

## 3. 核心 API 路由与契约 (API Routes & Contracts)

### 3.1 意图拆解与调度组 (Orchestration Group)
大管家拆解任务的核心入口，由大模型（如 GPT-4o）的 Structural Output 驱动。

*   **`POST /api/sessions/{session_id}/orchestrate`**
    *   **业务逻辑**：接收用户的巨型 prompt。后端挂起请求，调用大模型生成 WBS 任务树。写入 `tasks` 和 `task_dependencies` 表。
    *   **Request Body**:
        ```json
        { "intent": "帮我写一个电商网站的登录和购物车功能。" }
        ```
    *   **Response**: 返回新创建的 DAG 结构，前端借此渲染“任务看板卡片”。

*   **`POST /api/tasks/{task_id}/approve`**
    *   **业务逻辑**：【人工干预点】。当任务状态为 `PAUSED` 时，用户在前端点击【确认批准】按钮，请求此接口。后端将该任务标记为 `COMPLETED`，并扫描所有 `PENDING` 的下游任务，若其依赖已清空，则立即触发 `RUNNING`。

### 3.2 进程长连接通信组 (Real-time Communication Group)
处理底层 CLI 输出的乱码，以及向前端打字机推流。

*   **`GET /api/sessions/{session_id}/stream`**
    *   **协议**：Server-Sent Events (SSE)
    *   **业务逻辑**：后端不断读取后台 `claude` 进程的 `stdout`，用正则剥离 ANSI 颜色码后，封装成 SSE 事件推送。
    *   **Event Types**:
        *   `event: text_chunk` (常规打字机文字)
        *   `event: interactive_prompt` (遇到 y/n 确认拦截)
        *   `event: task_status_change` (某任务从 RUNNING 变为了 COMPLETED)

*   **`POST /api/sessions/{session_id}/input`**
    *   **业务逻辑**：将用户在前端输入框打的字，塞回给后台进程。
    *   **Request Body**:
        ```json
        {
          "type": "chat_message", // 或者 "interactive_reply" (用于回复 y/n)
          "text": "把按钮改成红色"
        }
        ```

### 3.3 产物与资源组 (Artifacts Group)
为消息级 Artifact Card 和页面级预览/编辑弹窗提供渲染物料。

*   **`GET /api/artifacts/{artifact_id}/content`**
    *   **业务逻辑**：当前端页面级 Artifact 弹窗打开时，获取产物的具体内容（如 HTML 源码，或 Markdown 长文）。
    *   **注意**：如果是 `full_project` 级别的修改，此接口返回的应该是文件树结构 (Tree) 和 Diff patch 数组，供 Monaco Editor 渲染。

*   **`GET /api/artifacts/{artifact_id}/versions`**
    *   **业务逻辑**：返回该 Artifact 版本链的所有版本，用于版本下拉和历史回溯。

*   **`GET /api/artifacts/{artifact_id}/diff?v1=&v2=`**
    *   **业务逻辑**：返回两个版本之间的 diff，供页面级版本/Diff 弹窗渲染。

*   **`POST /api/artifacts/{artifact_id}/edit`**
    *   **业务逻辑**：用户选中代码片段并描述修改意图后，后端通过支持 tool calling 的 Agent 或上下文注入生成编辑结果。
    *   **Request Body**:
        ```json
        {
          "selection": "const color = 'blue'",
          "instruction": "改成红色",
          "referenced_version": 2
        }
        ```
    *   **Response**:
        ```json
        {
          "status": "preview",
          "diff": "...",
          "candidate_content": "...",
          "base_version": 2
        }
        ```

*   **`POST /api/artifacts/{artifact_id}/versions`**
    *   **业务逻辑**：用户确认 Diff 后创建新版本。
    *   **Request Body**:
        ```json
        { "content": "...", "source": "user_edit" }
        ```

### 3.4 Workspace 资源组 (Workspace Group)

MVP 本机 workspace 的权威执行规格见 [PRD-06](./06-MVP_Local_Workspace_Delivery.md) 与 [Phase 6A Workspace Runtime](../specs/phase6/00-workspace-runtime.md)。

*   **`POST /api/workspaces`**
    *   **状态**：已废弃。使用 `POST /api/projects`。

*   **`POST /api/workspaces/bind`**
    *   **状态**：已废弃。使用 `POST /api/projects/pick-folder` 调起系统目录选择器，再用返回的 `folderToken` 调用 `POST /api/projects`。

*   **`POST /api/sessions/{session_id}/workspace`**
    *   **状态**：已废弃。Session 创建时携带 `projectId`，后续 CLI Agent 通过 `GET /api/sessions/{session_id}/workspace` 查询继承的 `Project.workspace_path`。

*   **`POST /api/projects/pick-folder`**
    *   **业务逻辑**：由本机后端打开系统原生目录选择器，返回 `{ workspacePath, folderName, folderToken }`。`folderToken` 是一次性授权，用于允许绑定 `AGENTHUB_WORKSPACE_ROOT` 之外但用户显式选择的目录。

*   **`POST /api/projects`**
    *   **业务逻辑**：创建 Project。无 `workspacePath` 时在 `AGENTHUB_WORKSPACE_ROOT` 下创建空白文件夹；有 `workspacePath` 时必须携带有效 `folderToken` 或位于 allowlist root 内。

*   **`GET /api/projects/{project_id}/tree`**
    *   **业务逻辑**：返回 workspace 内文件树，路径均为相对路径。

*   **`GET /api/projects/{project_id}/files?path=`**
    *   **业务逻辑**：读取 Project workspace 内文本文件。后端必须拒绝 `../`、绝对路径和超大文件。

*   **`GET /api/projects/{project_id}/diff`**
    *   **业务逻辑**：返回执行前后或 snapshot 之间的文件变更摘要。

*   **`POST /api/projects/{project_id}/preview`**
    *   **业务逻辑**：生成静态预览或构建预览，返回 `preview_id`。

### 3.5 标准事件组 (Domain Events)

后端内部和实时通道应共享一组事件名，避免不同模块各自发明状态。

| 事件 | 生产者 | 消费者 | 用途 |
|---|---|---|---|
| `agent.output` | Adapter / AgentExecutor | ChatService, SSE/WebSocket | 普通文本流 |
| `project.created` | ProjectService | Chat UI, HealthCheck | Project 与 workspace 目录已创建或绑定 |
| `workspace.diff_ready` | WorkspaceService | ArtifactDetectionService | 文件变更已计算完成 |
| `preview.ready` | PreviewService | Artifact 预览弹窗 | 预览 URL 已可用 |
| `artifact.detected` | API/CLI Adapter, Orchestrator | ArtifactService | 发现可落库产物 |
| `artifact.created` | ArtifactService | WebSocket, Chat UI | 追加 Artifact Card、刷新产物列表 |
| `artifact.version_created` | ArtifactService | Artifact 版本弹窗 | 刷新版本链并切到新版本 |
| `task.status_changed` | Orchestrator | CollaborationPanel, ApprovalCard | 展示任务状态 |
| `interactive_prompt` | CLI Adapter | InteractivePromptCard | CLI y/n 等交互拦截 |

---

## 4. 全文检索 (M3 Search) 降级方案
在原需求中，提及了基于 SQLite FTS5 的高性能检索。
如果 Phase 3 研发周期紧张：
1.  **首选方案**：后端提供 `GET /api/search?q=keyword`，对 `messages` 表的 `content` 建立 FTS5 虚拟表，实现毫秒级全文高亮。
2.  **优雅降级方案**：取消全量消息检索。仅提供 `GET /api/sessions?title_like=keyword`。即用户只能搜索“会话标题”。这依然能解决 80% 找历史项目的问题，但开发成本降低 90%。

## 5. 架构安全性申明 (Security & Sandboxing)
重申：本 MVP 版本的进程管理直接操作宿主机资源。
*   不允许向公网随意暴露 `0.0.0.0`。
*   所有的 CLI 进程启动时，必须使用系统的非 Root/Administrator 账号权限运行，防止 Agent 被提示词注入后执行恶意删库脚本（如 `rm -rf /`）。
