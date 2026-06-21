# Phase 9 Cloud Workspace Foundation 实现快照

**日期**: 2026-06-08  
**状态**: 已实现，P1 local 零回归与 P2 cloud slice 真实服务验收通过

## 1. 后端数据模型

本轮新增 Phase 9 数据模型与迁移：

- `backend/migrations/024_phase9_cloud_workspace_foundation.sql`
- `backend/app/models/user.py`
- `backend/app/models/team.py`
- `backend/app/models/workspace.py`
- `backend/app/models/audit_log.py`

`projects` 表新增 `workspace_mode`、`workspace_id`、`team_id`、`owner_user_id`。本地项目继续使用 `workspace_path`；云端项目内部保存逻辑 `cloud://agenthub/workspaces/{workspaceId}`，但 API 输出不向前端暴露本机或服务器物理路径。

## 2. 后端服务与 API

新增服务：

- `AuthService`：Phase 9 开发态 Header Auth，使用 `X-AgentHub-User-Email` 创建或读取当前用户。
- `TeamService`：团队创建、成员邀请、owner/admin/member/viewer 权限矩阵。
- `CloudWorkspaceProvider`：cloud workspace 元数据、zip/GitHub import、snapshot、restore。
- `AuditService`：统一写入和查询审计日志。

新增 API：

- `GET /api/auth/me`
- `GET/POST /api/teams`
- `POST /api/teams/{teamId}/members`
- `GET /api/workspaces/{workspaceId}`
- `POST /api/workspaces/{workspaceId}/imports/zip`
- `POST /api/workspaces/{workspaceId}/imports/github`
- `POST /api/workspaces/{workspaceId}/snapshots`
- `POST /api/workspaces/{workspaceId}/snapshots/{snapshotId}/restore`
- `GET /api/audit-logs`

`POST /api/projects` 已支持 `workspaceMode = "local" | "cloud"`。cloud Project 创建时必须有登录态，团队项目会校验 RBAC；local Project 继续不要求登录态。

## 3. P1 本地版保护

本轮显式保护本地能力：

- local Project 默认仍创建真实本机目录。
- `ProjectRead.workspacePath` 对 local 继续返回；对 cloud 返回 `null`。
- 本地文件树、文件读写、snapshot/diff、static preview、build/export 继续走已有本机 Provider。
- cloud Project 对本地文件操作返回清晰错误：文件操作留到 Phase 10，build/preview/export 留到 Phase 11。

这保证了用户问题中的核心边界：本地版工作目录与 SaaS 版工作目录不是同一个概念，也不应互相伪装。

## 4. 前端入口

新增和更新的前端能力：

- `ProjectSidebar` 顶部团队切换器，支持个人空间、团队空间和创建团队。
- Project 创建弹窗增加“本机 / 云端”分段选择。
- 项目列表用硬盘/云图标区分 local/cloud。
- 新增 `WorkspaceSettingsPage`，展示：
  - 本机工作区摘要；
  - 云端 workspace ID、逻辑 storage URI、导入记录、快照、恢复记录；
  - 团队成员添加入口；
  - 审计日志。
- `SessionList` 显示 `本机 · workspacePath` 或 `云端 · workspaceId`，避免前端假设所有项目都有路径。

## 5. 后续边界

Phase 9 不做以下事项：

- 不启动云端 CLI Agent。
- 不创建 sandbox / container / microVM。
- 不提供云端文件系统读写 API。
- 不提供云端 preview URL 或 deployment URL。
- 不实现正式 OAuth/密码登录；当前 Header Auth 是本地开发切片。

这些能力分别进入 Phase 10、Phase 11 和后续 SaaS 账号体系。
