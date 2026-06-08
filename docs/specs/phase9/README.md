# Phase 9：Cloud Workspace Foundation

**版本**: v1.1
**创建日期**: 2026-06-08  
**状态**: Draft  
**关联 ADR/PRD**: [AgentHub-多Agent协作平台设计](../../archive/AgentHub-多Agent协作平台设计.md)、[ADR-0005](../../adr/0005-target-architecture.md)、[ADR-0009](../../adr/0009-project-workspace-model.md)、[PRD-00](../../PRD/00-Master_Hub.md)、[PRD-04](../../PRD/04-Data_API_Contracts.md)、[PRD-07](../../PRD/07-SaaS_Cloud_Workspace_Delivery.md)  
**依赖模块**: Phase 8 P1 发布候选收口、Project-first workspace model、Artifact metadata baseline

> Phase 9 是 P2 SaaS 云版的地基阶段。它只建立云端 Project/Workspace/Team/Auth 的领域模型和 Provider 边界，不运行云端 CLI，不提供公网部署。

---

## 1. 目标

Phase 9 解决 P1 本地 workspace 与 P2 云端 workspace 之间的架构断层。目标用户是 SaaS 版的个人用户和团队用户：他们需要在浏览器中创建云端 Project、导入代码、管理团队访问权限、查看 workspace 快照，并且不看到本机绝对路径。

本阶段的工程目标是引入 `WorkspaceProvider` 抽象，让上层 Project/Session/Artifact 服务通过同一契约访问本地或云端 workspace。Phase 9 只完成云端 workspace 的生命周期与元数据闭环，云端执行由 Phase 10 接入。

**成功标准**（可证伪）：

- [ ] 同一套 Project API 可创建 `workspaceMode = "local"` 或 `"cloud"` 的 Project，前端展示一致但字段边界清晰。
- [ ] 云端 Project 返回 `workspaceId`，不向前端暴露服务器文件系统路径。
- [ ] 用户、团队、成员、角色、Project 权限和审计日志可持久化。
- [ ] 云端 workspace 支持创建、归档、删除、快照、恢复、源码 zip 导入、GitHub 导入占位流程。
- [ ] P1 本机 Project、会话、Artifact、本地 build/preview/export 在真实服务上保持可用。
- [ ] 本阶段 SaaS 最小可运行切片为：登录态 → 创建团队 → 创建 cloud Project → 导入/快照/恢复 workspace 元数据闭环。
- [ ] 不通过标准：为了云端能力改坏 P1 本地 workspace；或在本阶段启动云端 CLI/sandbox 执行。

---

## 2. 全局定位

### 2.1 北极星链路位置

```text
Phase 8 P1 local workspace release candidate
  → [Phase 9: WorkspaceProvider + Cloud Workspace metadata + Auth/Team/RBAC]
  → Phase 10 Sandbox Runner + Cloud Agent Runtime
```

### 2.2 上下游契约

| 方向 | 模块/事件/API | 本模块的角色 |
|------|-------------|------------|
| **上游输入** | Phase 8 `WorkspaceProvider` 本地边界、ProjectService、Artifact metadata | 将本地 workspace 契约扩展为 local/cloud 双实现 |
| **上游输入** | 用户登录态、团队选择、Project 创建请求 | 校验租户权限并创建 cloud workspace |
| **下游产出** | `CloudWorkspaceProvider`、workspace/snapshot/audit APIs | Phase 10 Sandbox Runner 挂载 workspace |
| **下游产出** | 租户隔离字段、RBAC、audit log | Phase 11 Deploy、Phase 12 团队协作消费 |
| **本模块不通** | sandbox 执行、云端 preview、部署发布、多人实时编辑 | Phase 10-12 负责 |

### 2.3 双运行时兼容门禁

Phase 9 是 P2 的入口阶段，因此必须先证明云端抽象不会污染 P1 本机版：

- `workspaceMode = "local"` 仍是本机默认可用路径，不要求登录真实云端账号、不要求团队、不要求 `workspaceId`。
- `workspaceMode = "cloud"` 只能走 CloudWorkspaceProvider，不向前端返回服务器物理路径。
- 前端新增云端入口必须在 P2 环境可用；在 P1 本机环境中可隐藏、禁用或清晰提示，不得阻断本机创建 Project。
- 阶段完成报告必须同时列出 P1 local 回归结果和 Phase 9 cloud slice 真实服务结果。

---

## 3. 跨模块契约

### 3.1 API 端点

| 端点 | 方法 | 请求体 | 成功响应 | 错误响应 |
|------|------|--------|---------|---------|
| `/api/auth/me` | GET | 无 | `200: CurrentUser` | `401` 未登录 |
| `/api/teams` | GET | 无 | `200: { "items": Team[] }` | `401` |
| `/api/teams` | POST | `{ "name": string }` | `201: Team` | `400` / `409` 名称重复 |
| `/api/teams/{teamId}/members` | POST | `{ "email": string, "role": "owner" \| "admin" \| "member" \| "viewer" }` | `201: TeamMember` | `403` 权限不足 |
| `/api/projects` | POST | `{ "name": string, "workspaceMode": "local" \| "cloud", "teamId"?: string, "template"?: string }` | `201: Project` | `400` / `403` |
| `/api/workspaces/{workspaceId}` | GET | 无 | `200: Workspace` | `403` / `404` |
| `/api/workspaces/{workspaceId}/snapshots` | POST | `{ "label"?: string }` | `201: WorkspaceSnapshot` | `403` / `409` workspace 忙碌 |
| `/api/workspaces/{workspaceId}/snapshots/{snapshotId}/restore` | POST | `{ "strategy": "replace" \| "branch" }` | `202: { "restoreId": string }` | `403` / `404` / `409` |
| `/api/workspaces/{workspaceId}/imports/zip` | POST | `multipart/form-data file` | `202: { "importId": string }` | `400` 文件过大 / `415` 类型不支持 |
| `/api/workspaces/{workspaceId}/imports/github` | POST | `{ "repoUrl": string, "branch"?: string }` | `202: { "importId": string, "status": "queued" }` | `400` / `403` |
| `/api/audit-logs` | GET | `projectId`/`teamId` query | `200: { "items": AuditLog[] }` | `403` |

### 3.2 事件

| 事件类型 | 方向 | payload 字段 |
|---------|------|-------------|
| `workspace.created` | WorkspaceProvider → EventBus | `{ workspaceId, projectId, teamId, mode: "cloud" }` |
| `workspace.snapshot.created` | WorkspaceProvider → EventBus | `{ workspaceId, snapshotId, label }` |
| `workspace.restore.completed` | WorkspaceProvider → EventBus | `{ workspaceId, snapshotId, strategy }` |
| `workspace.import.completed` | WorkspaceProvider → EventBus | `{ workspaceId, importId, source: "zip" \| "github" }` |
| `team.member.added` | TeamService → EventBus | `{ teamId, userId, role }` |
| `audit.recorded` | AuditService → EventBus | `{ actorId, action, resourceType, resourceId }` |

### 3.3 数据库 Schema 变更

```sql
CREATE TABLE users (
  id VARCHAR PRIMARY KEY,
  email VARCHAR NOT NULL UNIQUE,
  display_name VARCHAR NOT NULL,
  avatar_url TEXT,
  created_at DATETIME NOT NULL
);

CREATE TABLE teams (
  id VARCHAR PRIMARY KEY,
  name VARCHAR NOT NULL,
  created_by VARCHAR NOT NULL REFERENCES users(id),
  created_at DATETIME NOT NULL
);

CREATE TABLE team_members (
  id VARCHAR PRIMARY KEY,
  team_id VARCHAR NOT NULL REFERENCES teams(id),
  user_id VARCHAR NOT NULL REFERENCES users(id),
  role VARCHAR NOT NULL,
  created_at DATETIME NOT NULL
);

ALTER TABLE projects ADD COLUMN workspace_mode VARCHAR NOT NULL DEFAULT 'local';
ALTER TABLE projects ADD COLUMN workspace_id VARCHAR;
ALTER TABLE projects ADD COLUMN team_id VARCHAR REFERENCES teams(id);
ALTER TABLE projects ADD COLUMN owner_user_id VARCHAR REFERENCES users(id);

CREATE TABLE workspaces (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL REFERENCES projects(id),
  provider VARCHAR NOT NULL,
  status VARCHAR NOT NULL,
  storage_uri TEXT NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE TABLE workspace_snapshots (
  id VARCHAR PRIMARY KEY,
  workspace_id VARCHAR NOT NULL REFERENCES workspaces(id),
  label VARCHAR,
  storage_uri TEXT NOT NULL,
  created_by VARCHAR REFERENCES users(id),
  created_at DATETIME NOT NULL
);

CREATE TABLE audit_logs (
  id VARCHAR PRIMARY KEY,
  actor_user_id VARCHAR REFERENCES users(id),
  team_id VARCHAR REFERENCES teams(id),
  project_id VARCHAR REFERENCES projects(id),
  action VARCHAR NOT NULL,
  resource_type VARCHAR NOT NULL,
  resource_id VARCHAR NOT NULL,
  metadata_json TEXT NOT NULL,
  created_at DATETIME NOT NULL
);
```

### 3.4 跨组件 TypeScript 类型（前端）

```typescript
type WorkspaceMode = 'local' | 'cloud'
type TeamRole = 'owner' | 'admin' | 'member' | 'viewer'

interface CurrentUser {
  id: string
  email: string
  displayName: string
  avatarUrl?: string
}

interface Project {
  id: string
  name: string
  workspaceMode: WorkspaceMode
  workspaceId?: string
  teamId?: string
  createdAt: string
}

interface WorkspaceSnapshot {
  id: string
  workspaceId: string
  label?: string
  createdAt: string
  createdBy?: string
}
```

---

## 4. 行为规格

### 4.1 正常流程

```
1. 用户登录 → 前端获取 /api/auth/me 和 /api/teams → Project 创建面板显示个人/团队作用域。
2. 用户选择创建云端 Project → ProjectService 调用 CloudWorkspaceProvider.create_workspace → 返回 project + workspaceId。
3. 用户导入 zip 或 GitHub repo → WorkspaceProvider 写入 cloud storage → 记录 import 状态和 audit log。
4. 用户创建 snapshot → WorkspaceProvider 保存快照 → 前端 snapshot 列表出现新记录。
5. 用户恢复 snapshot → Provider 创建 restore job → 完成后 workspace 文件树刷新。
6. 后续 Phase 10 启动 sandbox 时，只拿 workspaceId 和 provider mount 信息，不读取本机路径。
```

### 4.2 UX 六态覆盖

| 状态 | 用户看到什么 | 触发条件 |
|------|------------|---------|
| **空态** (Empty) | 没有团队时显示个人空间和创建团队入口；没有快照时显示创建快照按钮 | 首次进入 |
| **加载态** (Loading) | Project 创建、导入、恢复显示进度条和禁用重复提交 | workspace job 运行中 |
| **正常态** (Normal) | Project 列表区分本地/云端标识；workspace 页面显示文件树、快照、导入记录 | 数据加载成功 |
| **完成态** (Complete) | 创建/导入/恢复完成 toast，列表刷新到最新状态 | workspace 事件完成 |
| **错误态** (Error) | 权限不足、导入失败、恢复冲突显示清晰错误与重试入口 | 4xx/5xx 或 job failed |
| **边界态** (Edge) | 大 zip、空 repo、重复团队名、viewer 只读态、快速切换团队 | 边界输入或权限限制 |

### 4.3 错误处理

| 错误场景 | 错误码 | 用户可见文案 | 恢复路径 |
|---------|--------|------------|---------|
| 未登录 | 401 | 请先登录后继续 | 跳转登录 |
| 无团队权限 | 403 | 你没有访问该团队项目的权限 | 切换团队或联系管理员 |
| 云端 workspace 创建失败 | 500 | 云端工作区创建失败 | 重试或保存为本地 Project |
| zip 文件过大 | 400 | 文件超过当前工作区导入限制 | 压缩后重试或使用 GitHub 导入 |
| snapshot 恢复冲突 | 409 | 工作区正在执行其他操作 | 等待当前任务完成 |

---

## 5. 前端页面设计

### 5.1 页面布局

```text
┌───────────────┬──────────────────────────────────────────────┐
│ ProjectSidebar │ WorkspaceSettingsPage                       │
│ TeamSwitcher   │ ┌────────────────────────────────────────┐   │
│ ProjectList    │ │ BasicInfo: Project + Workspace mode    │   │
│               │ ├────────────────────────────────────────┤   │
│               │ │ ImportPanel + SnapshotPanel            │   │
│               │ ├────────────────────────────────────────┤   │
│               │ │ MembersPanel + AuditLogPanel           │   │
│               │ └────────────────────────────────────────┘   │
└───────────────┴──────────────────────────────────────────────┘
```

ProjectSidebar 增加 TeamSwitcher。WorkspaceSettingsPage 使用全宽分区，不把页面 section 包成大浮动卡片；每个重复项如 snapshot/audit log 可用 8px radius 列表项。

### 5.2 组件树

```text
WorkspaceSettingsPage
├── WorkspaceBasicInfo
├── WorkspaceImportPanel
│   ├── ZipImportButton
│   └── GitHubImportForm
├── WorkspaceSnapshotPanel
│   ├── CreateSnapshotButton
│   └── SnapshotList
├── TeamMembersPanel
└── AuditLogPanel
```

### 5.3 关键视觉元素

| 元素 | 位置 | 视觉规格 |
|------|------|---------|
| Workspace mode badge | ProjectList / BasicInfo | local 使用硬盘图标，cloud 使用云图标，文字不加粗 |
| TeamSwitcher | ProjectSidebar 顶部 | 紧凑下拉，hover 高亮，头像/首字母 28px |
| SnapshotList | WorkspaceSnapshotPanel | 时间线式列表，恢复按钮使用 rotate-ccw 图标 |
| AuditLogPanel | 页面底部 | 单行密集列表，actor/action/resource/time 四列 |

---

## 6. 前端交互序列

### 6.1 创建云端 Project

```
用户: 点击新建 Project，选择云端工作区
  → 前端: 显示团队选择、模板选择、Project 名称输入
  → 用户: 提交
  → 前端: POST /api/projects
  → 后端: 创建 Project + cloud workspace + audit log
  → 前端: ProjectList 新项目出现，Chat 创建入口可用
```

### 6.2 创建与恢复快照

```
用户: 在 WorkspaceSnapshotPanel 点击创建快照
  → 前端: POST /api/workspaces/{workspaceId}/snapshots
  → 后端: workspace.snapshot.created
  → 前端: SnapshotList 插入新快照
  → 用户: 点击恢复
  → 前端: POST /restore，页面进入恢复中
  → 后端: workspace.restore.completed
  → 前端: 文件树刷新，显示完成提示
```

---

## 7. 验收标准

- [ ] AC-P9-01: 登录用户可通过 `/api/auth/me` 获取当前用户，未登录返回 401。
- [ ] AC-P9-02: 用户可创建团队、邀请成员并设置角色；viewer 不能创建或删除 Project。
- [ ] AC-P9-03: 创建 cloud Project 后返回 `workspaceMode: "cloud"` 和 `workspaceId`，不返回本机绝对路径。
- [ ] AC-P9-04: `LocalWorkspaceProvider` 的 P1 行为保持不变，P1 E2E 不回归。
- [ ] AC-P9-05: cloud workspace 可创建 snapshot，并能恢复到指定 snapshot。
- [ ] AC-P9-06: zip 导入和 GitHub 导入占位流程有状态、错误和审计日志。
- [ ] AC-P9-07: Project/Workspace/Team/Audit API 均验证租户权限。
- [ ] AC-P9-08: 前端 TeamSwitcher、Workspace 设置页覆盖空/加载/正常/完成/错误/边界六态。
- [ ] AC-P9-09: P1 local Project 创建、会话创建、Artifact 查询、本地 build/preview/export 真实服务回归通过。
- [ ] AC-P9-10: Phase 9 cloud slice 在真实服务上完成创建团队、创建 cloud Project、导入、snapshot、restore 流程。

---

## 8. 测试策略

### 8.1 单元测试（40 条）

| 测试对象 | 条数 | 覆盖内容 |
|---------|------|---------|
| WorkspaceProvider interface | 8 | local/cloud contract、路径不泄漏、状态转换 |
| CloudWorkspaceProvider | 10 | create/archive/delete/snapshot/restore/import |
| Auth/RBAC Service | 10 | owner/admin/member/viewer 权限矩阵 |
| AuditService | 6 | action/resource/actor 记录与查询过滤 |
| ProjectService | 6 | workspaceMode 分支、兼容本地 Project |

### 8.2 集成测试

- 真实 SQLite + CloudWorkspaceProvider fake storage：创建团队、cloud Project、snapshot、restore、audit log。
- 权限测试：不同角色访问同一 Project/Workspace API。
- P1 兼容测试：local Project 创建、tree/files/diff/preview 路径不变。

### 8.3 E2E 测试

- 浏览器创建团队和云端 Project，上传 zip，创建 snapshot，恢复 snapshot。
- viewer 登录后确认创建/删除按钮不可用，直接调用 API 返回 403。

### 8.4 P1/P2 兼容门禁

- P1 local 回归：使用本机 workspace 创建 Project，创建私聊或群聊，确认 Artifact、本地 build、preview、export API 不因新增 auth/team/cloud 字段失败。
- P2 cloud slice：使用真实后端创建团队和 cloud Project，完成 zip 导入、snapshot、restore，并确认前端不展示任何本机绝对路径。
- 多端视口：桌面宽度展示 TeamSwitcher 和 Workspace 设置页；移动宽度下云端入口可用或明确降级，不遮挡聊天输入。

---

## 9. 架构约束追溯

| 本模块的决策 | 依据 |
|------------|------|
| Project-first 仍是顶层工作流 | [ADR-0009](../../adr/0009-project-workspace-model.md) |
| P2 workspace 位于云端隔离环境 | [PRD-00](../../PRD/00-Master_Hub.md)、[PRD-07](../../PRD/07-SaaS_Cloud_Workspace_Delivery.md) |
| Provider 抽象不让上层依赖具体文件系统 | [ADR-0005](../../adr/0005-target-architecture.md) |
| 团队/权限/审计是 SaaS 基础能力 | [PRD-07](../../PRD/07-SaaS_Cloud_Workspace_Delivery.md) |

---

## 10. 依赖

| 依赖模块 | 需要的接口 | 当前状态 |
|---------|-----------|---------|
| Phase 8 WorkspaceProvider 边界 | local provider contract、Project API 兼容 | 📋 计划中 |
| ProjectService | create/list/archive/delete/rename | ✅ 已有 P1 基线 |
| Artifact metadata | artifact/project/session 关联 | ✅ 已有 P1 基线 |
| Object storage adapter | storage_uri 读写 | ❌ 未开始 |
| Auth session provider | CurrentUser 注入 | ❌ 未开始 |

---

## 11. Non-Goals（明确不做什么）

| 不做的事 | 原因 | 由谁负责 |
|---------|------|---------|
| 云端 CLI Agent 执行 | 需要 sandbox 隔离 | Phase 10 |
| preview URL 与部署 URL | 需要运行时和部署服务 | Phase 11 |
| 多人实时协同编辑 | 超出基础 workspace | Phase 12 或更后 |
| 移动端审批推送 | 多端体验阶段 | Phase 12 |
| 完整 Git 同步和 PR 工作流 | 先做导入占位 | Phase 12 |

---

## 12. 破坏性变更与迁移

| 维度 | V1 行为 | V2 行为 | 迁移路径 |
|------|--------|--------|---------|
| Project workspace 字段 | `workspace_path` 是核心字段 | local Project 仍有 `workspace_path`，cloud Project 使用 `workspace_id` | API 输出按 workspaceMode 区分；前端禁止假设一定有路径 |
| Project 权限 | 本地单用户默认全权 | SaaS 引入 owner/team/role | 本地模式注入默认 owner；云端模式强校验 |
| Project 创建 UI | 只选本地目录或空白 workspace | 增加 local/cloud 与团队作用域 | 默认仍推荐 local，云端入口在 P2 环境显示 |

> **版本历史**
> - v1.1 (2026-06-08): 增加 Phase 9 起 P1/P2 双运行时兼容门禁，明确 P1 local 零回归和 cloud slice 真实服务验收。
> - v1.0 (2026-06-08): 按 `SPEC_TEMPLATE.md` 创建 Phase 9 独立 Spec。
