# 需求规格说明书 (PRD)：04 - 数据结构与 API 契约 (Data Model & API Contracts)

## 1. 文档定位
本文档专为**全栈研发工程师**及**数据库管理员 (DBA)** 编写。
它将前文所有的宏观产品愿景、复杂的 Orchestrator DAG 调度算法，收敛为了具体、可执行的数据表结构与 REST/SSE 接口规范。这里是代码落地的第一站。

---

## 2. 数据库实体关系 (Entity Relationship Schema)

建议使用 PostgreSQL 或 SQLite。以下采用标准的 SQL 或 ORM 伪代码描述核心业务表。

### 2.1 Agent 实体表 (`agents`)
代表了平台中“专家”的物理身份。注意，我们剥离了传统的 LLM Provider 概念，Agent 实体强绑定本地的 CLI 可执行文件。

```sql
CREATE TABLE agents (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL, -- 展示名称，如 "前端专家"
    avatar_url VARCHAR(1024),   -- 头像
    agent_type VARCHAR(50) NOT NULL, -- 枚举: 'cli_wrapper', 'orchestrator'
    executable VARCHAR(255),    -- 当 type 为 cli_wrapper 时必填，如 'claude', 'opencode'
    init_args JSONB,            -- CLI 启动参数，如 ["--theme=dark", "--compact"]
    system_prompt TEXT,         -- 角色设定（注入到 CLI 的第一句话）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2.2 会话与历史记录 (`sessions` & `messages`)
由于我们需要高度复用传统 IM 聊天的 UI，会话表设计接近微信/Slack。

```sql
CREATE TABLE sessions (
    id UUID PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    workspace_path VARCHAR(1024) NOT NULL, -- 关键！该会话绑定的绝对物理路径
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
    status VARCHAR(50) DEFAULT 'PENDING', -- PENDING, RUNNING, PAUSED, COMPLETED, FAILED
    requires_approval BOOLEAN DEFAULT FALSE,
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
为右侧的产物抽屉提供渲染物料。

*   **`GET /api/artifacts/{artifact_id}/content`**
    *   **业务逻辑**：当前端右侧抽屉打开时，获取产物的具体内容（如 HTML 源码，或 Markdown 长文）。
    *   **注意**：如果是 `full_project` 级别的修改，此接口返回的应该是文件树结构 (Tree) 和 Diff patch 数组，供 Monaco Editor 渲染。

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
