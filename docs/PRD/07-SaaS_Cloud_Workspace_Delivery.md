# 需求规格说明书 (PRD)：07 - AgentHub SaaS 云端 Workspace 落地方案

**创建日期**: 2026-06-03  
**状态**: Active / Future Track  
**关联文档**: [PRD-06 MVP Local Workspace](./06-MVP_Local_Workspace_Delivery.md), [PRD-05 End-to-End Flow](./05-End_to_End_Product_Flow.md)

## 1. 文档定位

本文定义 AgentHub SaaS 版的最终落地形态：**浏览器 + 云端后端 + 云端隔离 workspace + 云端 Agent CLI / Runner + 云端预览与部署**。

它回答的问题是：如果 AgentHub 作为公网 Web 产品提供给用户，项目代码在哪里创建，Agent CLI 操作谁的文件系统，预览和部署如何对外暴露。

SaaS 版的核心判断是：

```text
浏览器仍然不直接操作用户本机磁盘。
AgentHub 云端后端也不能直接访问用户电脑目录。
因此每个项目必须创建在云端 workspace 中。
Agent CLI 在云端 sandbox/runner 里运行，并以云端 workspace 作为 cwd。
```

---

## 2. 产品形态

SaaS 版是多人可用的云端 AI 开发协作平台：

```text
用户浏览器
  -> AgentHub Cloud Frontend
  -> AgentHub Cloud API
  -> Workspace Service
  -> Sandbox / Runner / Container
  -> Agent CLI / API Agent
  -> Cloud Workspace Volume
  -> Preview Service
  -> Deploy Service
```

用户不需要在本机安装 Node、Python、Git 或 Claude Code。AgentHub 在云端为用户准备运行环境。

---

## 3. 与 MVP 本机版的本质区别

| 维度 | MVP 本机 workspace | SaaS 云端 workspace |
|---|---|---|
| 后端运行位置 | 用户本机 | AgentHub 云端 |
| Agent CLI 运行位置 | 用户本机 | 云端 sandbox/runner |
| workspace 位置 | 用户本机目录 | 云端隔离卷/对象存储 |
| 浏览器能否访问本机目录 | 不能 | 不能 |
| 预览地址 | 本机 URL | 云端 preview URL |
| 部署来源 | 本机 build 或 Git | 云端 build / Git / 托管发布 |
| 隔离要求 | 本机 allowlist + 进程清理 | 多租户隔离、配额、审计、密钥管理 |

SaaS 不是把 MVP 的本机目录“同步一下”那么简单，而是把 workspace runtime 从用户电脑迁移到云端托管环境。

---

## 4. Cloud Workspace 模型

### 4.1 数据关系

```text
User / Team
  -> Project
  -> Session
  -> Workspace
  -> Sandbox
  -> Artifacts
  -> Deployments
```

SaaS 版需要区分 Project 与 Session：

- Project 是长期项目容器。
- Session 是一次聊天协作上下文。
- Workspace 是项目在某个分支、快照或运行环境中的文件系统。
- Sandbox 是执行 Agent 和命令的隔离运行实例。

### 4.2 Workspace 存储

推荐分层：

```text
Metadata DB
  -> users / teams / projects / sessions / workspaces / artifacts / deployments

Workspace Volume
  -> 当前可读写文件系统，供 sandbox 挂载

Object Storage
  -> snapshots / artifacts / build outputs / logs

Git Remote
  -> 用户连接 GitHub/GitLab 后的长期源码归档
```

### 4.3 Workspace URI

SaaS 版不暴露本机路径，也不应该把云端物理路径传给前端。前端只看到：

```text
workspaceId
projectId
branchName
previewUrl
deploymentUrl
```

后端内部使用：

```text
workspace_uri = cloud://agenthub/workspaces/ws_abc123
sandbox_id = sandbox_abc123
storage_key = tenants/{tenant_id}/workspaces/{workspace_id}/...
```

---

## 5. SaaS 最终功能清单

### 5.1 用户与团队

- 登录、注册、退出。
- Team / Project 管理。
- 成员权限：owner、editor、viewer。
- 项目级 API Key、部署 token、GitHub App 授权。
- 操作审计日志。

### 5.2 Workspace 生命周期

用户可以：

- 从模板创建 workspace。
- 从 GitHub/GitLab 导入仓库。
- 从 zip 上传创建 workspace。
- Fork 已有 workspace。
- 创建分支或快照。
- 恢复到历史版本。
- 导出源码或同步到 Git remote。

后端必须支持：

- workspace 创建队列。
- sandbox 启停。
- 文件系统快照。
- 长时间未使用自动休眠。
- 唤醒后恢复 workspace 状态。

### 5.3 云端 Agent 执行

执行流程：

```text
用户输入任务
  -> Cloud API 接收消息
  -> Orchestrator 创建任务
  -> Workspace Service 分配 sandbox
  -> Agent CLI 在 sandbox 中启动
  -> cwd 指向 cloud workspace mount
  -> Agent 修改文件、运行命令、写测试
  -> Runner 推送 stdout/stderr/file changes
  -> ArtifactService 创建 Artifact
```

关键要求：

- 每个 Agent 执行必须绑定 `workspace_id`。
- 每个 sandbox 必须绑定 tenant/project/workspace。
- CLI 不能访问其他租户文件。
- 运行时环境可复现：Node、Python、Git、常用包管理器、浏览器构建工具。

### 5.4 文件、Diff、Artifact

SaaS 版 Artifact 与 MVP 保持同一产品心智：

```text
Agent 改文件
  -> File Watcher 捕获变更
  -> Diff Service 计算变更
  -> ArtifactService 创建 Artifact
  -> 聊天流展示 Artifact Card
  -> Drawer 预览、对比、编辑
```

Artifact 需要额外记录云端存储信息：

```text
artifact_id
workspace_id
project_id
storage_key
file_path
snapshot_id
preview_id
deployment_id
```

### 5.5 云端预览

SaaS 版必须提供云端 preview URL：

```text
https://preview-{preview_id}.agenthub.dev
```

预览支持：

- 静态 HTML iframe。
- Vite/Next/React dev server 代理。
- build 后静态托管。
- 预览鉴权：私有项目默认需要登录。
- 预览失效：workspace 删除或权限变化后 URL 失效。

预览流程：

```text
用户点击 Artifact Card
  -> Preview Service 启动或复用 sandbox dev server
  -> Health check 确认端口可访问
  -> 生成 previewUrl
  -> Drawer iframe 加载
```

### 5.6 云端部署

SaaS 版部署是核心功能，而不是额外导出能力。

静态站部署：

```text
workspace
  -> cloud build
  -> dist/
  -> object storage / edge hosting / third-party provider
  -> deploymentUrl
```

完整应用部署：

```text
workspace
  -> build Docker image
  -> push image registry
  -> run service platform
  -> deploymentUrl
```

部署方式：

- First-party static hosting。
- Vercel / Netlify / Cloudflare Pages。
- GitHub push 后触发第三方 CI。
- Docker image 发布到 Render/Fly.io/Kubernetes。

部署必须有状态卡片：

```text
Deployment Card
  -> Queued
  -> Installing
  -> Building
  -> Uploading
  -> Published / Failed
  -> Logs
  -> URL
```

---

## 6. 用户交互流程

### 6.1 创建云端项目

```text
用户登录 AgentHub
  -> 点击“新建项目”
  -> 选择模板或导入 GitHub
  -> 系统创建 Project + Workspace
  -> 系统启动或预热 sandbox
  -> 用户进入聊天工作台
```

### 6.2 用自然语言生成网页

```text
用户输入：做一个咖啡店官网
  -> Orchestrator 拆解任务
  -> Agent CLI 在云端 sandbox 中写文件
  -> 聊天流展示执行日志和 Artifact Card
  -> Drawer 打开云端 preview URL
```

### 6.3 修改与审批

```text
用户说：把预约按钮改成红色，菜单区增加价格
  -> 系统引用当前 workspace snapshot
  -> Agent 修改云端文件
  -> Diff Service 生成变更
  -> 用户在 Drawer 中确认
  -> 系统创建新 snapshot / commit
  -> Preview 自动刷新
```

复杂项目中：

```text
Orchestrator 完成架构设计
  -> Approval Card 暂停
  -> 用户打开关联 Artifact
  -> 用户确认
  -> 下游 Agent 继续执行
```

### 6.4 一键部署

```text
用户点击“部署”
  -> 选择部署目标
  -> 填写或选择环境变量
  -> 系统执行云端 build
  -> Deployment Card 展示日志
  -> 成功后返回公网 URL
```

用户可以继续说：

```text
把线上版本标题改成“晨光咖啡”，重新部署。
```

系统会：

```text
修改 workspace
  -> 生成新预览
  -> 用户确认
  -> 创建新 deployment
  -> 更新 URL 或生成新版本 URL
```

---

## 7. SaaS 后端服务拆分

### 7.1 核心服务

| 服务 | 职责 |
|---|---|
| API Gateway | REST/SSE/WebSocket、鉴权、速率限制 |
| Workspace Service | 创建、挂载、快照、恢复 workspace |
| Sandbox Runner | 启动容器/微虚拟机，执行命令和 Agent CLI |
| Agent Orchestrator | 任务拆解、Agent 选择、审批断点 |
| Artifact Service | Artifact 落库、版本、Diff、预览元数据 |
| Preview Service | dev server 代理、静态预览、URL 鉴权 |
| Deploy Service | build、上传、第三方部署、状态日志 |
| Secret Service | API Key、部署 token、环境变量加密存储 |

### 7.2 推荐接口

```text
POST /api/projects
POST /api/projects/{project_id}/workspaces
POST /api/workspaces/{workspace_id}/start
POST /api/workspaces/{workspace_id}/stop
GET  /api/workspaces/{workspace_id}/tree
GET  /api/workspaces/{workspace_id}/files/{file_path}
GET  /api/workspaces/{workspace_id}/diff
POST /api/workspaces/{workspace_id}/snapshots
POST /api/workspaces/{workspace_id}/restore
POST /api/workspaces/{workspace_id}/preview
POST /api/deployments
GET  /api/deployments/{deployment_id}
GET  /api/deployments/{deployment_id}/logs
```

### 7.3 标准事件

```json
{ "type": "workspace.provisioning", "workspaceId": "ws_abc123" }
{ "type": "workspace.ready", "workspaceId": "ws_abc123", "sandboxId": "sandbox_abc123" }
{ "type": "sandbox.stdout", "workspaceId": "ws_abc123", "content": "npm install..." }
{ "type": "workspace.file_changed", "workspaceId": "ws_abc123", "path": "src/App.tsx" }
{ "type": "preview.ready", "previewId": "preview_abc123", "url": "https://preview-abc.agenthub.dev" }
{ "type": "deployment.status_changed", "deploymentId": "dep_abc123", "status": "published" }
```

---

## 8. 安全、隔离与成本控制

SaaS 版必须把安全作为基础能力，而不是上线后补丁。

### 8.1 多租户隔离

- 每个 workspace 在独立 sandbox 中执行。
- sandbox 不能挂载其他租户数据。
- 默认最小权限文件系统。
- 网络出口可配置 allowlist。
- 高风险命令需要审批或策略拦截。

### 8.2 Secret 管理

- API Key、部署 token、Git token 加密存储。
- Secret 注入 sandbox 后不可写入日志。
- Artifact 和 build log 自动脱敏。
- 项目成员权限决定谁能查看和修改 Secret。

### 8.3 配额

- CPU、内存、磁盘、执行时长限制。
- 长时间空闲自动休眠。
- build 并发限制。
- preview URL TTL。
- Artifact 和 snapshot 生命周期管理。

---

## 9. 与 MVP 的迁移关系

为了让 MVP 能平滑升级到 SaaS，后端应尽早抽象 WorkspaceProvider：

```python
class WorkspaceProvider:
    async def create_workspace(...): ...
    async def get_file_tree(...): ...
    async def read_file(...): ...
    async def write_file(...): ...
    async def diff(...): ...
    async def snapshot(...): ...
    async def build(...): ...
    async def preview(...): ...
```

MVP 实现：

```text
LocalWorkspaceProvider
  -> pathlib / local git / local subprocess / local preview server
```

SaaS 实现：

```text
CloudWorkspaceProvider
  -> cloud volume / sandbox runner / object storage / cloud preview
```

前端和 Orchestrator 不应该关心 workspace 是本机还是云端。它们只依赖统一 ID 和事件。

---

## 10. SaaS 完成定义

SaaS 云端 workspace 版完成时，必须能演示：

1. 用户登录后创建云端项目。
2. 系统自动创建隔离 workspace 和 sandbox。
3. 用户用自然语言生成网页。
4. Agent CLI 在云端 workspace 中创建文件。
5. 聊天流出现 Artifact Card。
6. Drawer 打开云端 preview URL。
7. 用户发起修改并确认新版本。
8. 用户一键部署到公网 URL。
9. 用户可以导出源码或同步到 GitHub。
10. 管理后台能看到 workspace、sandbox、deployment 的状态和日志。

SaaS 的完整链路是：

```text
User -> Project -> Cloud Workspace -> Sandbox Agent cwd -> File Change -> Artifact -> Preview URL -> Edit -> Snapshot -> Deployment URL
```

