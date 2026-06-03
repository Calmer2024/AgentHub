# Spec: Phase 6A — 本机 Workspace Runtime

**版本**: v1.0  
**创建日期**: 2026-06-03  
**状态**: Draft  
**关联**: [PRD-06 MVP 本机 Workspace](../../PRD/06-MVP_Local_Workspace_Delivery.md), [PRD-05](../../PRD/05-End_to_End_Product_Flow.md), [PRD-01](../../PRD/01-Architecture_Adapter.md)  
**依赖**: Phase 5 ArtifactService, Phase 3 EventBus / SessionService

---

## 1. 背景

Phase 5 已经完成”已有 Artifact 的工作台能力”：版本链、Diff、局部编辑和确认创建新版本。但 Phase 5 仍然缺少一个上游执行底座。

Phase 6 引入 **Project** 作为顶层组织实体（详见 [ADR-0009](../../adr/0009-project-workspace-model.md)），Project 绑定 workspace 目录，Project 下所有 Session 共享此目录。

```text
Project 绑定哪个项目目录？
  → Project.workspace_path（用户创建 Project 时选择）
Agent CLI 在哪里执行？
  → cwd = Project.workspace_path
文件变更如何变成 Artifact？
  → Adapter 检测 → artifact.detected → ArtifactService → artifact.created
```

本 Spec 定义 Phase 6A：MVP 本机 Workspace Runtime 的最小可落地实现。

---

## 2. 全局链路定位

Phase 6A 位于北极星链路的最前段：

```text
创建 Project + 绑定 workspace_path
  -> 在 Project 下创建私聊/群聊 Session
  -> 用户输入 / Orchestrator 子任务
  -> Agent 以 Project.workspace_path 作为 cwd
  -> 文件变更 / Agent 输出检测
  -> Artifact 创建
  -> Artifact Card / Drawer / 编辑 / 版本化
```

完成 Phase 6A 后，系统应具备一个明确事实：

> 每个 Project 都有一个受后端管理的本机 workspace；Project 内所有 Session 的所有 Agent 都在这个 workspace 内执行。

---

## 3. 设计原则

- **不重开 Phase 5**：Phase 5 仍然是已完成的 Artifact 工作台能力。Workspace 是 Phase 6 的前置执行底座。
- **本机优先**：MVP 实现 `LocalWorkspaceProvider`，不做云端 sandbox。
- **ID 优先**：前端只拿 `workspaceId`、`previewId`、`artifactId`，不直接拼本机路径。
- **路径受控**：所有 `workspace_path` 必须位于 `AGENTHUB_WORKSPACE_ROOT` 或用户显式授权目录下。
- **可迁移**：Service 接口保留 `WorkspaceProvider` 抽象，未来 SaaS 可替换为 `CloudWorkspaceProvider`。
- **Artifact 不等于 Workspace**：Artifact 是版本化展示产物；Workspace 是 Agent 读写的项目目录。

---

## 4. 数据模型

### 4.1 新增 `workspaces` 表

```sql
CREATE TABLE IF NOT EXISTS workspaces (
  id VARCHAR PRIMARY KEY,
  name VARCHAR NOT NULL,
  root_path VARCHAR NOT NULL,
  project_type VARCHAR NOT NULL DEFAULT 'static',
  status VARCHAR NOT NULL DEFAULT 'ready',
  created_by VARCHAR NOT NULL DEFAULT 'agenthub',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);
```

字段说明：

| 字段 | 说明 |
|---|---|
| `id` | `ws_...` 或 UUID |
| `name` | 用户可见项目名 |
| `root_path` | 后端内部使用的本机绝对路径 |
| `project_type` | `static` / `vite-react` / `existing` |
| `status` | `creating` / `ready` / `building` / `error` / `archived` |
| `metadata_json` | 预览端口、模板、最后 snapshot 等扩展信息 |

### 4.2 `projects` 表（新增）+ `sessions` 增加 `project_id`

```sql
-- 新增 projects 表
CREATE TABLE projects (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    workspace_path VARCHAR NOT NULL,  -- 本机绝对路径
    project_type VARCHAR DEFAULT 'existing',  -- static / vite-react / existing
    status VARCHAR DEFAULT 'creating',
    metadata_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- sessions 增加 project_id（NOT NULL，所有聊天必须归属 Project）
ALTER TABLE sessions ADD COLUMN project_id VARCHAR NOT NULL REFERENCES projects(id);

-- sessions 移除旧的 workspace_id（如果存在）
-- ALTER TABLE sessions DROP COLUMN workspace_id;
```

规则：

- 所有聊天（Session）必须归属某个 Project。不存在”无 Project 的聊天”。
- Project 创建时绑定 `workspace_path`（用户选择/新建目录），此后不可更改。
- Project 内所有 Session 的所有 Agent 共享 `Project.workspace_path` 作为 `cwd`。
- 详见 [ADR-0009](../../adr/0009-project-workspace-model.md)。

### 4.3 `artifacts` 增加 workspace 关联字段

```sql
ALTER TABLE artifacts ADD COLUMN workspace_id VARCHAR NULL REFERENCES workspaces(id);
ALTER TABLE artifacts ADD COLUMN file_path VARCHAR NULL;
ALTER TABLE artifacts ADD COLUMN preview_id VARCHAR NULL;
```

规则：

- 纯文本/历史 Artifact 可以没有 `workspace_id`。
- 由 workspace 文件或构建产物生成的 Artifact 必须带 `workspace_id`。
- `file_path` 必须是 workspace 内相对路径。

---

## 5. 后端模块

### 5.1 WorkspaceProvider

```python
class WorkspaceProvider:
    async def create_workspace(self, *, name: str, project_type: str) -> Workspace: ...
    async def bind_existing(self, *, path: str, name: str) -> Workspace: ...
    async def get_tree(self, workspace_id: str) -> FileTree: ...
    async def read_file(self, workspace_id: str, file_path: str) -> str: ...
    async def write_file(self, workspace_id: str, file_path: str, content: str) -> None: ...
    async def diff(self, workspace_id: str, base_ref: str | None = None) -> WorkspaceDiff: ...
    async def snapshot(self, workspace_id: str, label: str) -> WorkspaceSnapshot: ...
    async def build(self, workspace_id: str) -> BuildResult: ...
    async def preview(self, workspace_id: str) -> PreviewResult: ...
```

MVP 实现：

```text
LocalWorkspaceProvider
  -> pathlib
  -> local git 或 snapshot
  -> subprocess build
  -> backend static preview
```

### 5.2 WorkspaceService

职责：

- 创建 workspace 记录。
- 创建本机目录和 `.agenthub/workspace.json`。
- 将 session 与 workspace 绑定。
- 提供文件树、文件读取、Diff、snapshot。
- 为 CLI Adapter 提供可信 `workspace_path`。
- 发布 workspace 标准事件。

推荐文件：

```text
backend/app/models/workspace.py
backend/app/services/workspace_service.py
backend/app/infrastructure/local_workspace_provider.py
backend/app/api/workspaces.py
backend/migrations/009_create_workspaces.sql
```

### 5.3 FileChangeDetector

MVP 不需要常驻文件监听。推荐用“执行前后快照 diff”：

```text
Agent 执行前记录文件 hash tree
  -> Agent 执行
  -> 执行后重新扫描 hash tree
  -> 得到 created/modified/deleted 列表
  -> 发布 workspace.file_changed / workspace.diff_ready
```

这样比实时 watcher 更稳定，也更适合 Windows。

### 5.4 PreviewService

MVP 最小支持：

| 项目类型 | 预览方式 |
|---|---|
| `static` | 读取 `index.html` 或 Artifact HTML，iframe `srcDoc` |
| `vite-react` | 执行 `npm install` / `npm run build`，托管 `dist/` |
| `existing` | 用户手动配置 build/preview command，缺失时只显示文件树和 Diff |

后端静态预览路径：

```text
GET /api/previews/{preview_id}/
GET /api/previews/{preview_id}/assets/{path}
```

---

## 6. API 契约

### 6.1 Workspace

```text
POST /api/workspaces
Body: { "name": "coffee-site", "projectType": "vite-react" }
-> 201 { "id": "...", "name": "...", "projectType": "...", "status": "ready" }

POST /api/workspaces/bind
Body: { "name": "existing-app", "path": "D:\\Projects\\existing-app" }
-> 201 { "id": "...", "name": "...", "projectType": "existing" }

GET /api/workspaces/{workspace_id}
GET /api/workspaces/{workspace_id}/tree
GET /api/workspaces/{workspace_id}/files?path=src/App.tsx
GET /api/workspaces/{workspace_id}/diff
POST /api/workspaces/{workspace_id}/snapshot
```

### 6.2 Session 绑定

```text
POST /api/sessions/{session_id}/workspace
Body: { "workspaceId": "ws_abc123" }
-> 200 { "sessionId": "...", "workspaceId": "..." }
```

创建项目型 session 时也可直接传：

```text
POST /api/sessions
Body: {
  "title": "咖啡店官网",
  "mode": "single",
  "workspace": {
    "name": "coffee-site",
    "projectType": "vite-react"
  }
}
```

### 6.3 Build / Preview

```text
POST /api/workspaces/{workspace_id}/build
POST /api/workspaces/{workspace_id}/preview
GET  /api/previews/{preview_id}
```

---

## 7. 标准事件

```json
{ "type": "workspace.created", "workspaceId": "ws_abc123", "sessionId": "session_abc123" }
{ "type": "workspace.bound", "workspaceId": "ws_abc123", "sessionId": "session_abc123" }
{ "type": "workspace.file_changed", "workspaceId": "ws_abc123", "path": "src/App.tsx", "change": "modified" }
{ "type": "workspace.diff_ready", "workspaceId": "ws_abc123", "changedFiles": 3 }
{ "type": "build.started", "workspaceId": "ws_abc123" }
{ "type": "build.log", "workspaceId": "ws_abc123", "content": "vite build..." }
{ "type": "preview.ready", "workspaceId": "ws_abc123", "previewId": "preview_abc123" }
```

Phase 6B-6F 消费这些事件：

- CLI Adapter 使用 `workspace_path` 作为 `cwd`。
- Artifact Output Bridge 使用 `workspace.diff_ready` 和 Agent 输出创建 Artifact。
- Phase 7 Drawer 使用 `preview.ready` 打开网页预览。

---

## 8. 前端交互

### 8.1 Workspace 状态入口

MVP 前端最小展示：

- 会话标题旁显示 workspace 名称。
- 左栏或设置区显示 workspace 健康状态。
- 创建项目型会话时可选模板。
- Artifact Drawer 中能打开文件树、Diff 或预览 URL。

### 8.2 用户流程

```text
用户点击新建项目
  -> 输入项目名和需求
  -> 后端创建 session + workspace
  -> 聊天流显示 workspace.created 状态
  -> 用户发送任务
  -> Agent 在 workspace 中写文件
  -> 生成 Artifact Card / Preview
```

---

## 9. 路径安全

必须满足：

- `root_path` 保存绝对路径。
- `file_path` 只能是 workspace 相对路径。
- 所有读写前都要 `resolve()` 后确认仍在 `root_path` 内。
- 禁止读取 `.env`、密钥文件和 `.agenthub/secrets`。
- 预览服务只暴露 `dist/` 或被允许的静态目录。
- 删除/归档 workspace 不得递归删除用户绑定的外部目录，除非用户显式确认。

---

## 10. 测试策略

### Unit

- `LocalWorkspaceProvider` 创建目录和 `.agenthub/workspace.json`。
- 路径越界被拒绝。
- 文件树忽略 `node_modules/.git/.agenthub`。
- 执行前后 hash diff 能识别 created/modified/deleted。
- session 绑定 workspace 后可查询。

### API

- `POST /api/workspaces` 创建记录和目录。
- `POST /api/sessions/{id}/workspace` 绑定成功。
- `GET /api/workspaces/{id}/tree` 返回相对路径。
- 越界读取 `../secret` 返回 400/403。
- `POST /api/workspaces/{id}/preview` 对静态 HTML 返回 previewId。

### E2E

最小真实验收：

```text
创建项目型 session
  -> workspace 自动创建
  -> mock agent 写入 index.html
  -> file diff 检测到 index.html
  -> 生成 web_preview Artifact
  -> preview API 可访问
```

---

## 11. 验收标准

- [ ] 新建 Project 时绑定 workspace_path，Project 下所有 Session 自动继承。
- [ ] 绑定已有本机目录时，后端做 allowlist/路径越界校验。
- [ ] WorkspaceService 能返回文件树、读取文件、生成 Diff。
- [ ] CLI Adapter 可以从 WorkspaceService 获取可信 `workspace_path`，并以它作为进程 `cwd`。
- [ ] Agent 执行前后能检测文件变更，并发布 `workspace.diff_ready`。
- [ ] 静态 HTML workspace 能生成 previewId，并通过后端预览 URL 打开。
- [ ] Artifact 记录可绑定 `workspace_id/file_path/preview_id`。
- [ ] 所有新增 API 有 Unit/API 测试覆盖。

---

## 12. Non-Goals

- 不做 SaaS 云端 sandbox。
- 不做完整 Web IDE。
- 不做文件实时协同编辑。
- 不做公网部署发布。
- 不在 Phase 6A 实现真正 Claude Code 调用；真实 CLI 由 Phase 6B-6E 承接。

