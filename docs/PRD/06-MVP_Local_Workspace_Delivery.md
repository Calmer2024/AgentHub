# 需求规格说明书 (PRD)：06 - AgentHub MVP 本机 Workspace 落地方案

**创建日期**: 2026-06-03  
**状态**: Active  
**关联文档**: [PRD-01 CLI Adapter](./01-Architecture_Adapter.md), [PRD-05 End-to-End Flow](./05-End_to_End_Product_Flow.md)

## 1. 文档定位

本文定义 AgentHub MVP 版的最终落地形态：**本机 workspace + 本机后端 + Web 控制台 + 本机 CLI Agent**。

它补齐 PRD-05 中缺失的执行底座问题：用户发起任务后，项目目录在哪里创建，Agent CLI 在哪里运行，文件如何进入 Artifact，预览和部署从哪里取产物。

MVP 版的核心判断是：

```text
浏览器不直接操作用户磁盘。
后端服务绑定本机 workspace。
Agent CLI 由本机后端启动，并以 workspace_path 作为 cwd。
Artifact、预览、导出、部署都从这个 workspace 读取产物。
```

---

## 2. 产品形态

MVP 版不是云 IDE，也不是 SaaS 沙盒。它是一个网页外壳包着的本地 AI 开发工作台：

```text
本机浏览器 / 桌面 WebView
  -> 本机 AgentHub Frontend
  -> 本机 AgentHub Backend
  -> 本机 Agent CLI / API Agent
  -> 本机 workspace 目录
  -> 本机预览 / 构建 / 导出
  -> 可选：上传到部署平台
```

用户看到的是 Web UI；真正读写文件、启动 CLI、运行构建命令的是本机后端。

### 2.1 MVP 明确做什么

- 创建或绑定一个本机 workspace。
- 在 workspace 中生成网页或项目代码。
- 用 Agent CLI 按任务修改 workspace 文件。
- 把文件变更、HTML、Diff、构建产物转换成 Artifact。
- 在聊天流展示 Artifact Card，在右侧 Drawer 预览。
- 支持基于 Artifact 或 workspace 文件继续修改。
- 支持本机预览、源码导出、构建产物导出。
- 支持通过 DeployAdapter 把构建结果上传到第三方静态托管平台。

### 2.2 MVP 不做什么

- 不让浏览器任意访问用户磁盘。
- 不要求 workspace 从一开始放到云端。
- 不提供多租户云端隔离。
- 不默认使用 Docker 沙盒运行每个项目。
- 不把右侧 Drawer 做成完整 VS Code。

---

## 3. Workspace 模型

Workspace 是项目协作的物理工作目录，归属于 Project（非 Session）。Project 是顶层组织实体，Session 是 Project 下的聊天上下文；Project 内所有 Session 共享同一个 workspace。

### 3.1 数据关系

```text
Project
  -> workspace_path (一对一绑定)
  -> project_type
  -> preview_config
  -> build_config
  -> Sessions[] (一对多)
       -> messages
       -> tasks
       -> artifacts
```

一个 Project 绑定一个 workspace 目录。Project 创建时用户选择/新建目录，此后不可更改。Project 内所有 Session 的所有 Agent 共享此目录作为 `cwd`。详见 [ADR-0009](../adr/0009-project-workspace-model.md)。

### 3.2 推荐目录结构

默认根目录由后端配置：

```text
AGENTHUB_WORKSPACE_ROOT=D:\AgentHub\workspaces
```

用户创建 Project 后：

```text
workspaces/
  my-web-app/              ← Project.workspace_path
    .agenthub/
      project.json
      snapshots/
      build-logs/
    package.json
    index.html
    src/
    dist/
```

`.agenthub/workspace.json` 记录 AgentHub 自己的元数据，不要求用户手写：

```json
{
  "workspace_id": "ws_abc123",
  "session_id": "session_abc123",
  "name": "coffee-site",
  "project_type": "vite-react",
  "created_by": "agenthub",
  "preview": {
    "mode": "static_or_vite",
    "port": 5178
  }
}
```

### 3.3 workspace_path 的边界

`workspace_path` 是后端内部字段，不应该让前端直接拼路径访问。

前端只使用：

```text
workspaceId
artifactId
previewUrl
deploymentId
```

后端负责把这些 ID 映射到本机路径，并做路径校验。

---

## 4. MVP 最终功能清单

### 4.1 Workspace 管理

用户可以在 Web UI 中：

- 新建项目 workspace。
- 选择项目模板：单 HTML、Vite React、静态站点。
- 绑定已有本机目录。
- 查看当前会话绑定的 workspace 名称、路径摘要、健康状态。
- 查看文件树和关键文件变更摘要。

后端必须提供：

- workspace 根目录配置。
- 路径 allowlist 校验。
- workspace 创建、绑定、删除、归档。
- workspace 元数据落库。
- 会话与 workspace 的绑定关系。

### 4.2 Agent 执行

用户在聊天里发任务：

```text
做一个咖啡店官网，有首页、菜单、预约按钮。
```

后端执行：

```text
读取 session.project.workspace_path
  -> Orchestrator 选择 Agent
  -> CLI Agent 以 cwd=project.workspace_path 启动
  -> Agent 读写 workspace 文件
  -> 后端监听 stdout、文件变更、退出状态
```

关键规则：

- API Agent 可生成代码文本，由后端写入 workspace。
- CLI Agent 可直接在 workspace 中创建和修改文件。
- Orchestrator 不直接碰文件系统，它只派发任务。
- Adapter 不直接写 Artifact 表，它输出标准事件。

### 4.3 Artifact 生成

Artifact 可以来自三类来源：

| 来源 | 示例 | 处理方式 |
|---|---|---|
| Agent 输出 | Markdown HTML/TSX/diff 代码块 | Artifact Output Bridge 检测并创建 Artifact |
| workspace 文件变更 | 新建 `src/App.tsx`、修改 `index.html` | File Change Detector 汇总变更并创建 file_tree/code_diff Artifact |
| 构建/预览产物 | `dist/`、单 HTML 页面 | Preview Service 创建 web_preview Artifact |

Artifact 必须绑定：

```text
artifact_id
session_id
workspace_id
message_id
task_id
version
file_path 或 preview_url
```

### 4.4 预览

MVP 支持两种预览：

| 类型 | 适用场景 | 实现 |
|---|---|---|
| 单 HTML 预览 | Landing page、小组件 | Drawer iframe `srcDoc` |
| workspace 项目预览 | Vite/React/多文件静态站 | 后端启动 dev server 或 build 后托管 `dist/` |

推荐链路：

```text
用户点击 Artifact Card
  -> 前端请求 /api/previews/{artifact_id}
  -> 后端确认 workspace 最新状态
  -> 如果需要则执行 npm install / npm run build
  -> 暴露本机 preview URL
  -> Drawer iframe 加载 previewUrl
```

本机 preview URL 默认只对本机可用：

```text
http://127.0.0.1:8000/api/previews/{preview_id}/
```

### 4.5 修改与版本化

用户可以通过两种方式修改：

1. 在 Drawer 中选中 Artifact 内容，输入局部修改要求。
2. 在聊天中引用某个 Artifact 或文件，说出修改目标。

系统流程：

```text
用户发起修改
  -> ContextManager 注入 artifact/workspace 摘要
  -> Agent 在 workspace 中修改文件
  -> 后端生成 Diff
  -> Drawer 展示变更
  -> 用户确认
  -> 创建 Artifact v2 / snapshot / git commit
  -> 重新预览
```

MVP 推荐用轻量 Git 或 snapshot 作为版本边界：

- 每次创建 workspace 后初始化 Git。
- 每次用户确认一个版本后创建 commit 或 snapshot。
- 用户拒绝修改时可以回滚到上一个确认版本。

### 4.6 构建、导出、部署

MVP 的交付优先级：

| 能力 | MVP 要求 | 说明 |
|---|---|---|
| 本机预览 | 必须 | 用于演示和迭代 |
| 源码导出 | 必须 | 打包 workspace 或项目源码 zip |
| 构建产物导出 | 必须 | 打包 `dist/` |
| 公网部署 | P1/P2 | 通过 DeployAdapter 对接 Vercel/Netlify/Cloudflare Pages |

部署不要求 workspace 在云端。MVP 可直接从本机构建并上传：

```text
workspace
  -> npm run build
  -> dist/
  -> DeployAdapter 上传
  -> 返回公网 URL
```

也可以走 Git 路线：

```text
workspace
  -> git init / commit
  -> push GitHub
  -> Vercel/Netlify 从 GitHub 构建
  -> 返回公网 URL
```

---

## 5. 用户交互流程

### 5.1 首次启动

```text
用户打开 AgentHub
  -> 左栏显示环境体检
  -> 检测 Node/Python/Git/CLI Agent/API Key
  -> 用户选择或确认 workspace 根目录
  -> 系统进入新建任务界面
```

用户不需要理解 `cwd`、`dist`、`npm`，但 UI 需要把环境缺失解释清楚。

### 5.2 创建网页

```text
用户点击“新建项目”
  -> 选择“静态网页 / Vite React”
  -> 输入：做一个咖啡店官网
  -> 后端创建 workspace
  -> Orchestrator 派发任务
  -> Agent 生成文件
  -> 聊天流出现执行状态和 Artifact Card
  -> Drawer 展示网页预览
```

### 5.3 修改网页

```text
用户在预览里发现按钮颜色不对
  -> 在聊天中说：把预约按钮改成红色
  -> 系统引用当前 Artifact + workspace 摘要
  -> Agent 修改文件
  -> Drawer 展示 Diff 和新预览
  -> 用户确认
  -> Artifact 升级到 v2
```

### 5.4 导出或部署

```text
用户点击“导出源码”
  -> 后端打包 workspace
  -> 返回 zip 下载
```

或：

```text
用户点击“部署”
  -> 后端执行构建
  -> DeployAdapter 上传 dist/
  -> 聊天流显示 Deployment Card
  -> 成功后展示公网 URL
```

---

## 6. 后端接口建议

### 6.1 Workspace API

```text
# Projects（顶层）
POST /api/projects                    创建 Project（绑定 workspace 目录）
GET  /api/projects                    列出 Project
GET  /api/projects/{project_id}       获取 Project 详情（含 workspace_path）

# Workspace（从属于 Project）
GET  /api/projects/{project_id}/tree          文件树
GET  /api/projects/{project_id}/files/{path}  文件内容
GET  /api/projects/{project_id}/diff          文件变更 Diff
POST /api/projects/{project_id}/snapshot      快照
POST /api/projects/{project_id}/rollback      回滚
```

### 6.2 Preview / Build API

```text
POST /api/workspaces/{workspace_id}/build
POST /api/workspaces/{workspace_id}/preview
GET  /api/previews/{preview_id}
GET  /api/previews/{preview_id}/assets/{path}
```

### 6.3 Deployment API

```text
POST /api/deployments
GET  /api/deployments/{deployment_id}
GET  /api/deployments/{deployment_id}/logs
```

---

## 7. 标准事件

Workspace 链路需要在现有 `agent.output`、`artifact.created` 基础上补充事件：

```json
{ "type": "project.created", "projectId": "proj_abc123", "workspacePath": "/home/user/my-app" }
{ "type": "workspace.bound", "projectId": "proj_abc123", "workspacePath": "/home/user/my-app" }
{ "type": "workspace.file_changed", "workspaceId": "ws_abc123", "path": "src/App.tsx", "change": "modified" }
{ "type": "preview.started", "previewId": "preview_abc123", "workspaceId": "ws_abc123" }
{ "type": "build.log", "workspaceId": "ws_abc123", "content": "vite build..." }
{ "type": "deployment.status_changed", "deploymentId": "dep_abc123", "status": "published" }
```

---

## 8. 安全与边界

MVP 虽然是本机工作台，也必须有基本安全边界：

- 只能访问 allowlist 内的 workspace 根目录。
- 禁止通过 `../` 越界读取文件。
- CLI Agent 启动前必须展示当前 workspace。
- 高风险命令需要交互式确认卡片。
- 预览服务只暴露当前 workspace 的构建产物。
- API Key 不写入 workspace 源码。
- 任务结束或页面断开后清理后台进程。

---

## 9. MVP 完成定义

MVP 本机 workspace 版完成时，必须能演示：

1. 用户创建一个新网页项目 workspace。
2. 用户用自然语言生成网页。
3. Agent 在本机 workspace 中创建文件。
4. 聊天流出现 Artifact Card。
5. Drawer 能预览网页或展示 Diff。
6. 用户能继续要求修改，系统生成新版本。
7. 用户能本机预览、导出源码或导出构建产物。
8. 如果启用部署配置，用户能从本机 build 上传并获得公网 URL。

这条链路必须在文档和实现中明确体现：

```text
Project (workspace_path) -> Session (chat context) -> Agent cwd = workspace_path -> File Change -> Artifact -> Preview -> Edit -> Version -> Export/Deploy
```

