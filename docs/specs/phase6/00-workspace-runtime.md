# Spec: Phase 6A — Workspace Runtime

**版本**: v2.1
**更新日期**: 2026-06-04
**状态**: ✅ 已验收（Phase 6A）
**关联 ADR/PRD**: [ADR-0009](../../adr/0009-project-workspace-model.md)、[PRD-06](../../PRD/06-MVP_Local_Workspace_Delivery.md)、[PRD-05](../../PRD/05-End_to_End_Product_Flow.md)
**依赖模块**: Phase 5 ArtifactService、Phase 3 EventBus / SessionService

---

## 1. 目标

Phase 5 已完成 Artifact 的版本链、Diff 和在线编辑。但它缺少一个根本性的上游执行底座——用户的任务具体在哪个目录执行？Agent 的文件变更如何被追踪？

本模块引入 **Project** 作为顶层组织实体，绑定 workspace 目录，为后续 CLI Adapter 和 Artifact Bridge 提供可信的文件系统上下文。

**成功标准**（可证伪）：

- [x] 用户创建 Project 后，本机对应目录被创建，`.agenthub/project.json` 存在且内容正确
- [x] Session 可通过 `Session → Project.workspace_path` 取得同一个 workspace 目录，供后续 CLI Adapter 作为 cwd
- [x] `GET /api/projects/{id}/tree` 返回真实文件树，snapshot/diff 可证明文件变更被追踪
- [x] 对 `GET /api/projects/{id}/files?path=../../secret` 返回 403
- [x] `POST /api/projects/{id}/preview` 对含 `index.html` 的静态 workspace 返回可访问的 preview URL
- [x] 不通过标准已覆盖：任何一个 API 端点未经 workspace 内路径校验即允许读取 workspace 外文件

---

## 2. 全局定位

### 2.1 北极星链路位置

```text
用户创建 Project（选择/新建目录）
  → [本模块] Project 记录 workspace_path + 创建目录结构
  → 用户创建 Session（私聊/群聊）
  → CLI Adapter 获取 Project.workspace_path 作为 cwd
  → Agent 读写 workspace 文件
  → FileChangeDetector 生成 diff
  → Artifact Output Bridge 创建 Artifact
  → 消息级 Artifact Card → 页面级预览/编辑弹窗
```

### 2.2 上下游契约

| 方向 | 模块/事件/API | 本模块的角色 |
|------|-------------|------------|
| **上游输入** | 用户通过前端创建 Project（选目录/命名）；Phase 3 SessionService | 接收 Project 创建请求，初始化目录和元数据 |
| **下游产出** | `project.created` 事件；`workspace.file_changed` 事件；`workspace.diff_ready` 事件；CLI Adapter 通过 `WorkspaceService.get_workspace_path()` 获取 cwd；Artifact Bridge 通过 `workspace.diff_ready` 检测文件变更 | 产出可信的 workspace_path、文件树、Diff、预览 URL |
| **本模块不通** | 不执行 Agent（→ CLI Adapter）；不创建 Artifact（→ Artifact Bridge）；不渲染消息级 Artifact UI（→ Phase 6F）；不做 SaaS 云端 sandbox（→ P2） | |

---

## 3. 跨模块契约

### 3.1 API 端点

| 端点 | 方法 | 请求体 | 成功响应 | 错误响应 |
|------|------|--------|---------|---------|
| `/api/projects/pick-folder` | POST | — | `200: { "workspacePath", "folderName", "folderToken" }` | `400`（取消选择）、`500`（系统目录选择器不可用） |
| `/api/projects` | POST | `{ "name": string, "workspacePath"?: string, "folderToken"?: string }` | `201: { "id", "name", "workspacePath", "status", "createdAt" }` | `400: { "error": "msg" }`、`409` |
| `/api/projects` | GET | — | `200: [{ "id", "name", "workspacePath", "status", "createdAt" }]` | — |
| `/api/projects/{project_id}` | GET | — | `200: { "id", "name", "workspacePath", "status", "fileCount", "totalSizeBytes" }` | `404` |
| `/api/projects/{project_id}` | DELETE | — | `200: { "status": "archived" }` | `404` |
| `/api/projects/{project_id}/tree` | GET | `?subpath=` | `200: { "tree": [{ "path", "type": "file"|"dir", "size" }] }` | `403`（越界）、`404` |
| `/api/projects/{project_id}/files` | GET | `?path=src/App.tsx` | `200: { "path", "content", "size" }` | `403`、`404` |
| `/api/projects/{project_id}/diff` | GET | `?baseRef=` | `200: { "changedFiles": [{ "path", "change": "created"|"modified"|"deleted", "diffPreview" }] }` | `404` |
| `/api/projects/{project_id}/snapshot` | POST | `{ "label": string }` | `201: { "snapshotId", "label", "createdAt" }` | `400` |
| `/api/projects/{project_id}/preview` | POST | `{ "type": "static" }` | `200: { "previewId", "previewUrl" }` | `400`、`404` |
| `/api/projects/{project_id}/build` | POST | — | `200: { "buildId", "status": "building" }` | `400`、`500` |
| `/api/sessions/{session_id}/workspace` | GET | — | `200: { "workspacePath" }` | `404` |

### 3.2 事件

| 事件类型 | 方向 | payload 字段 |
|---------|------|-------------|
| `project.created` | ProjectService → EventBus | `{ projectId, name, workspacePath }` |
| `workspace.file_changed` | FileChangeDetector → EventBus | `{ projectId, sessionId, changes: [{ path, change }] }` |
| `workspace.diff_ready` | FileChangeDetector → EventBus | `{ projectId, sessionId, changedFiles: int, diffSummary }` |
| `preview.ready` | PreviewService → EventBus | `{ projectId, previewId, previewUrl }` |
| `build.started` / `build.log` / `build.completed` | BuildService → EventBus | `{ projectId, buildId, status/content }` |

### 3.3 数据库 Schema 变更

```sql
CREATE TABLE projects (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    workspace_path VARCHAR NOT NULL,
    project_type VARCHAR DEFAULT 'existing', -- 兼容字段，不进入用户创建流程
    status VARCHAR DEFAULT 'creating',
    metadata_json TEXT DEFAULT '{}',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE sessions ADD COLUMN project_id VARCHAR REFERENCES projects(id);
ALTER TABLE artifacts ADD COLUMN project_id VARCHAR REFERENCES projects(id);
ALTER TABLE artifacts ADD COLUMN file_path VARCHAR;
ALTER TABLE artifacts ADD COLUMN preview_id VARCHAR;
```

迁移期 `sessions.project_id` 允许为空，以兼容旧数据；业务层创建新 Session 时会通过显式 `projectId` 或默认 Project 自动补齐，CLI Adapter 启动前必须能解析到 Project。

### 3.4 跨组件 TypeScript 类型

```typescript
interface ProjectRead {
  id: string;
  name: string;
  workspacePath: string;
  status: 'creating' | 'ready' | 'building' | 'error' | 'archived';
  fileCount: number;
  totalSizeBytes: number;
  createdAt: string;
}
```

---

## 4. 行为规格

### 4.1 正常流程

```
1. 用户 → 项目栏点击创建按钮
2. 前端 → 弹出两项菜单：`新建空白文件夹` / `选择现有文件夹`
3. 用户选择 `新建空白文件夹` → 前端直接 `POST /api/projects { name }`，后端在 `AGENTHUB_WORKSPACE_ROOT` 下创建目录
4. 用户选择 `选择现有文件夹` → 前端调用 `POST /api/projects/pick-folder`，由本机后端打开系统原生目录选择器，返回授权 `folderToken`
5. 前端 → `POST /api/projects { name, workspacePath, folderToken }`
6. 后端 → ProjectService.create(): 校验路径、创建目录 + `.agenthub/project.json`、写入 DB、发布 `project.created`
7. 前端 → Project 出现在项目栏并自动选中，Session 列表按 `projectId` 过滤
8. 用户 → 在 Project 内创建私聊/群聊 Session → Session 自动绑定 `project_id`
9. CLI Adapter → 调用 `SessionService/ProjectService.get_workspace_path(session_id)` → 获取 `Project.workspace_path` → 作为 cwd
10. Agent 执行 → 读写 workspace 文件
11. FileChangeDetector → 执行前后 hash diff → 发布 `workspace.diff_ready`
12. Artifact Bridge → 消费 `workspace.diff_ready` → 创建 Artifact
13. 用户 → 在消息级 ArtifactCard 页面级弹窗中预览 workspace 内的 `index.html` / 查看 Diff
```

### 4.2 UX 六态覆盖

| 状态 | 用户看到什么 | 触发条件 |
|------|------------|---------|
| **空态** | 左侧项目区显示"暂无项目"；对话页面提示"创建 Project 后开始" | 用户首次使用，无 Project |
| **加载态** | 创建按钮禁用；Project 创建动作进行中 | Project 创建中 / 文件树加载中 / 构建中 |
| **正常态** | 三栏布局正常：项目栏显示所有 Project（当前选中高亮）；对话列表栏显示当前 Project 下的 Session 列表；对话页面显示聊天消息流 | Project 就绪，正常工作 |
| **完成态** | 预览 ready：`previewUrl` 可访问，后续 ArtifactCard 弹窗 iframe 可加载 | 构建成功 / 预览就绪 |
| **错误态** | 见 §4.3 | |
| **边界态** | Project 名称为空 → [创建项目] 按钮置灰；workspace 路径包含非法字符 → 输入框红框 + 提示；删除 Project → 右键菜单选择"归档项目"→ 弹出二次确认"工作目录不会被删除"→ 确认后 Project 从列表消失（status=archived）；同一目录被两个 Project 绑定 → 创建时 409 + 提示；Project 列表过长 → 项目栏可滚动，当前选中 Project 始终可见 | |

### 4.3 错误处理

| 错误场景 | 错误码 | 用户可见文案 | 恢复路径 |
|---------|--------|------------|---------|
| 用户取消系统目录选择 | 400 | "folder selection cancelled" | 重新选择 |
| 未经授权绑定 allowlist 外目录 | 400 | "workspace path is outside allowlist root" | 通过系统目录选择器重新授权 |
| 路径越界（`../` 攻击） | 403 | "无权访问此路径" | — |
| 目录已被其他 Project 绑定 | 409 | "此目录已被项目 '{name}' 使用" | 选择其他目录 |
| 磁盘空间不足 | 500 | "磁盘空间不足，无法创建项目" | 清理磁盘后重试 |
| 预览目标文件不存在 | 404 | "未找到可预览的文件（需要 index.html 或构建产物）" | 让 Agent 生成文件 |
| 文件读取超限（>10MB） | 400 | "文件过大，无法在编辑器中打开" | — |

---

## 5. 前端交互序列

### 5.0 全局布局：三栏结构

AgentHub 主界面采用三栏布局（参考 Codex + Telegram 的混合范式）：

```
┌──────────┬───────────────┬──────────────────────────────┐
│ 项目栏    │ 对话列表栏      │ 对话页面                       │
│ (Projects│ (Sessions)    │ (Chat View)                  │
│  Sidebar)│               │                              │
│          │               │                              │
│ 👥 好友   │ 🔍 搜索       │  ┌──────────────────────────┐ │
│  Claude  │               │  │ 消息气泡                   │ │
│  Code    │ 📁 Project A  │  │                          │ │
│  Codex   │  ├ 私聊: 前端  │  │ 用户: 写一个登录页面       │ │
│  OpenCode│  ├ 私聊: 后端  │  │                          │ │
│          │  ├ 群聊: 全栈  │  │ Claude Code: 好的...     │ │
│ ──────── │  │            │  │                          │ │
│ 📁 项目   │  │ [+ 新建聊天]│  │ ┌────────────────────┐   │ │
│  ├ 我的  │               │  │ │ Artifact Card      │   │ │
│  │ 网站  │               │  │ │ 🌐 登录页面  v1    │   │ │
│  ├ 后台  │               │  │ │ [👀 预览] [💬 引用] │   │ │
│  │ 系统  │               │  │ └────────────────────┘   │ │
│  │       │               │  │                          │ │
│  └ [+ 新│               │  └──────────────────────────┘ │
│     项目]│               │                              │
└──────────┴───────────────┴──────────────────────────────┘
```

**项目栏**（最左，宽 ~220px）：
- 顶部：**好友区**（见 [01-cli-adapter.md](01-cli-adapter.md) §5）— 展示已接入的 Agent CLI 工具
- 底部分隔线
- 下部：**项目区** — 每个 Project 显示为一个文件夹图标 + 项目名称（如 `📁 我的网站`）。当前选中的 Project 高亮。底部 `[+ 新建项目]` 按钮

**对话列表栏**（中间，宽 ~260px）：
- 顶部：当前选中 Project 的名称（如"我的网站"）+ workspace 路径缩略显示
- 搜索框：可搜索当前 Project 下的对话
- 对话列表：每条对话显示 Agent 头像 + 对话标题 + 最后消息预览 + 时间。私聊显示单个 Agent 头像，群聊显示重叠头像
- 底部：`[+ 新建聊天]` 按钮

**对话页面**（右侧，剩余宽度）：
- 顶部栏：当前对话标题 + Agent 状态指示灯（🟢 运行中 / ⚪ 空闲 / 🔴 超时）
- 中间：消息流（用户消息右对齐，Agent 消息左对齐 + Artifact Card）
- 底部：消息输入框 + 发送按钮

### 5.1 创建 Project

```
用户: 在项目栏点击创建项目按钮
  → 前端: 弹出小菜单
    - "新建空白文件夹"
    - "选择现有文件夹"
  → 用户选择 "新建空白文件夹"
  → 前端: 使用时间戳生成默认项目名，POST /api/projects { name }
  → 后端: 在 AGENTHUB_WORKSPACE_ROOT 下创建目录 → 写入 .agenthub/project.json → 返回 201
  → 用户选择 "选择现有文件夹"
  → 前端: POST /api/projects/pick-folder
  → 后端: 调起系统原生目录选择器 → 返回 workspacePath / folderName / folderToken
  → 前端: POST /api/projects { name: folderName, workspacePath, folderToken }
  → 前端: 菜单收起 → 项目栏出现新 Project → 自动选中新 Project → 对话列表栏切换为该 Project 的 Session 列表（初始为空）
  → SSE: project.created 事件 → 其他打开的客户端同步更新
```

### 5.2 切换 Project

```
用户: 在项目栏点击另一个 Project（如 📁 后台系统）
  → 前端: 被点击的 Project 高亮 → 上一个 Project 取消高亮
  → 前端: 对话列表栏刷新 → 显示"后台系统"下的所有 Session
  → 前端: 对话页面切换为该 Project 下最近一次打开的 Session（或空态）
```

### 5.3 在 Project 下创建聊天

```
用户: 在对话列表栏底部点击 [+ 新建聊天]
  → 前端: 按钮展开为两个选项（上滑动画）：
    [👤 私聊]  [👥 群聊]
  → 用户: 点击 [👤 私聊]
  → 前端: 弹出 Agent 选择列表 — 展示已配置的 CLI Agent（Claude Code / Codex / OpenCode），每个显示头像 + 名称 + 状态指示灯
  → 用户: 选择一个 Agent（如 Claude Code）
  → 前端: POST /api/sessions { projectId, mode: "single", agentId, title: "Claude Code" }
  → 后端: 创建 Session（自动继承 project_id）→ 返回 201
  → 前端: 对话列表栏刷新 → 新 Session 出现在列表顶部（头像 + "Claude Code" + 时间戳）
  → 前端: 自动进入该聊天 → 对话页面显示 Agent 信息 + 空消息流

（群聊流程类似 [👥 群聊] 则选择多个 Agent + 可选启用 Orchestrator）
```

### 5.4 预览 workspace 产物

```
用户: 在消息下方看到 Artifact Card，点击 [预览]
  → 前端: 判断 artifactType
    - web_preview: POST /api/projects/{project_id}/preview
    - code_diff: GET /api/projects/{project_id}/diff
  → 后端 PreviewService: 以静态 `index.html` 为 MVP 预览入口
  → SSE: preview.ready { previewId, previewUrl }
  → 前端: 页面级 Artifact 弹窗切换为 iframe（src=previewUrl）或 DiffViewer
```

---

## 6. 验收标准

- [x] AC-01: `POST /api/projects { name }` 返回 201 + 本机目录被创建 + `.agenthub/project.json` 存在
- [x] AC-02: Codex/Telegram 风格三栏布局正确渲染：项目栏 → 对话列表栏 → 对话页面
- [x] AC-03: 项目栏创建按钮弹出菜单：`新建空白文件夹` / `选择现有文件夹`
- [x] AC-04: `选择现有文件夹` 通过 `/api/projects/pick-folder` 调起系统原生目录选择器，并使用 `folderToken` 授权外部目录绑定
- [x] AC-05: 点击不同 Project → 对话列表栏切换到该 Project 下的 Session 列表
- [x] AC-06: `GET /api/projects/{id}/tree` 返回文件树（不含 `.agenthub/`、`node_modules/`、`.git/`）
- [x] AC-07: `GET /api/projects/{id}/files?path=../../secret` 返回 403
- [x] AC-08: 在 Project 下创建 Session 后，`GET /api/sessions/{id}/workspace` 返回同一 `workspacePath`
- [x] AC-09: snapshot/diff 正确识别 created/modified/deleted 文件
- [x] AC-10: `POST /api/projects/{id}/preview { type: "static" }` 返回可访问的 previewUrl
- [x] AC-11: `DELETE /api/projects/{id}` → status=archived → 不删除实际目录 → Project 从列表消失

---

## 7. 测试策略

### 7.1 单元测试 (22 条)

| 测试对象 | 条数 | 覆盖内容 |
|---------|------|---------|
| ProjectService | 8 | create/bind existing/delete/get_tree/路径校验/重名 |
| LocalWorkspaceProvider | 6 | 创建目录/.agenthub 初始化/文件树过滤/路径越界拒绝 |
| FileChangeDetector | 5 | hash diff/created/modified/deleted/空变更 |
| PreviewService | 3 | static 预览/缺失文件错误/路径校验 |

### 7.2 集成测试

- Project 创建 → Session 绑定 → Agent cwd 校验 → 文件写入 → hash diff 检测 → 事件发布全流程

### 7.3 E2E 测试

- 真实浏览器：创建 Project → 选择已有目录 → 在 Project 下创建私聊 → 测试 CLI fixture 写入 index.html → 消息级 ArtifactCard 预览网页

---

## 8. 架构约束追溯

| 本模块的决策 | 依据 |
|------------|------|
| Project 作为顶层实体，workspace 绑定 Project 而非 Session | ADR-0009 §核心规则 1-3 |
| 所有 Session 必须归属 Project | ADR-0009 §核心规则 1 |
| cwd 从 Session → Project.workspace_path 获取 | ADR-0009 §核心规则 3 |
| WorkspaceProvider 抽象接口，本机用 LocalWorkspaceProvider | ADR-0009 §配套决策 |
| 路径校验必须在 allowlist 范围内 | PRD-06 §4.2 |
| Agent 不直接写数据库，通过事件解耦 | ADR-0005 §接口契约 |

---

## 9. 依赖

| 依赖模块 | 需要的接口 | 当前状态 |
|---------|-----------|---------|
| Phase 3 SessionService | `create_session(project_id)` 自动绑定；`GET /api/sessions/{id}/workspace` 查询 cwd | ✅ 已就绪 |
| Phase 3 EventBus | `publish(event_type, payload)` | ✅ 已就绪 |
| Phase 5 ArtifactService | Artifact 模型（project_id/file_path/preview_id/source/confidence/task_id 兼容字段） | ✅ 已就绪 |
| FileChangeDetector | snapshot + hash diff | ✅ 已就绪 |
| PreviewService | 静态 `index.html` previewUrl | ✅ 已就绪 |

---

## 10. Non-Goals（明确不做什么）

| 不做的事 | 原因 | 由谁负责 |
|---------|------|---------|
| 不执行 Agent 进程 | 不是本模块职责 | Phase 6B-6E CLI Adapter |
| 不创建 Artifact | 不是本模块职责 | Phase 6F Artifact Bridge |
| 不渲染消息级 Artifact UI | 下游链路 | Phase 6F |
| 不做 SaaS 云端 sandbox | P2 范围 | P2 CloudWorkspaceProvider |
| 不做 Docker 容器隔离 | P1 本机版不需要 | P2 |
| 不做实时文件监听（fs watcher） | Windows 兼容性 + 稳定性 | 用执行前后 hash diff 替代 |
| 不做多 Project 共享同一 workspace | MVP 简化 | 未来扩展 |

---

## 11. 破坏性变更与迁移

| 维度 | V1 行为 | V2 行为 | 迁移路径 |
|------|--------|--------|---------|
| 数据模型 | `sessions.workspace_id` 直接绑定 workspace | 新增 `projects` 表；`sessions.project_id` FK | 数据迁移脚本：创建默认 Project → 迁移旧 session 的 workspace_id → 删除 workspace_id 列 |
| API | `POST /api/sessions/{id}/workspace` | `POST /api/projects` + Session 自动继承；`GET /api/sessions/{id}/workspace` 查询运行目录 | 前端同步更新 API 调用路径 |
| 事件 | `workspace.created { sessionId }` | `project.created { projectId }` | 消费者同步更新事件类型 |

> **版本历史**
> - v1.0 (2026-06-03): 初始版本（Session→Workspace 直接绑定）
> - v2.0 (2026-06-04): 按 ADR-0009 重构为 Project→Workspace 模型
> - v2.1 (2026-06-04): Phase 6A 验收通过；创建项目菜单改为“新建空白文件夹 / 选择现有文件夹”，后者调起系统目录选择器；项目类型从用户流程和前端类型中移除
