# Phase 13：多端产品壳拆分

**版本**: v1.0  
**创建日期**: 2026-06-09  
**状态**: Completed  
**关联 ADR/PRD**: [AgentHub-多Agent协作平台设计](../../archive/AgentHub-多Agent协作平台设计.md)、[ADR-0001](../../adr/0001-tech-stack-selection.md)、[ADR-0009](../../adr/0009-project-workspace-model.md)、[ADR-0010](../../adr/0010-message-level-artifact-experience.md)、[ADR-0011](../../adr/0011-agent-engine-skill-model.md)、[PRD-00](../../PRD/00-Master_Hub.md)、[PRD-03](../../PRD/03-User_Experience.md)、[PRD-05](../../PRD/05-End_to_End_Product_Flow.md)、[PRD-06](../../PRD/06-MVP_Local_Workspace_Delivery.md)、[PRD-07](../../PRD/07-SaaS_Cloud_Workspace_Delivery.md)  
**依赖模块**: Phase 9 Cloud Workspace Foundation、Phase 10 Sandbox Runner 与云端 Agent Runtime、Phase 11 Cloud Preview 与 Deployment、Phase 12 协作、多端与高级 Artifact

> Phase 13 不新增新的 Agent 执行模型，也不改变 Project-first 工作流。它把 Phase 9-12 累积出的本地版、SaaS 版和移动端能力拆成可独立启动、独立构建、独立发布、独立验收的产品壳，消除当前“一个 React 壳里混放本地/云端/移动能力”的体验债。

---

## 1. 目标

Phase 13 解决的是产品形态边界问题，而不是底层运行能力问题。当前前端已经能用 `workspaceMode = "local" | "cloud"` 区分 Project 数据路径，但 UI 仍主要由一个 `App`、一个 `ProjectSidebar`、一个 `WorkspaceSettingsPage` 和同一套 Artifact 操作区承载。本地版用户会看到个人空间、团队、云端工作区设置等 SaaS 概念；SaaS 用户也会被本机路径、本地 preview/export 等概念干扰；移动端则只有部分 API 能力，没有独立移动产品壳。

本阶段目标是把三端拆成三个明确产品入口：

- **Local Desktop Shell**：本地桌面版，本机项目、本机 CLI Agent、本机文件系统、本地预览/构建/导出。
- **SaaS Web Shell**：云端 SaaS 版，个人空间/团队、cloud workspace、sandbox runtime、preview/deployment、协作审计。
- **Mobile Shell**：移动端轻量版，会话、通知、审批、评论、Artifact/Preview 查看，不承担本机 CLI 和完整工作区管理。

**成功标准**（可证伪）：

- [x] 三端有独立入口、独立路由壳、独立构建命令和独立验收矩阵。
- [x] 本地版不显示个人空间、团队、cloud workspace、云端部署、云端配额、云端审计入口。
- [x] SaaS 版不暴露服务器物理路径、本机目录选择、本机 CLI executable、本地 localhost preview/export 作为主操作。
- [x] 移动端不加载桌面三栏工作台，不显示本机文件系统、CLI 进程、workspace settings 全量控制台。
- [x] 所有跨端差异通过 `RuntimeCapabilities` 和 shell 级组件分发控制，不靠组件内部散落的临时判断。
- [x] `ArtifactCard`、Project 创建、设置页、导航栏按 shell/capability 只显示当前端可用动作。
- [x] 本地桌面、SaaS Web、移动端可分别启动、分别构建、分别回归，不要求一次改动必须同时发布三端。
- [x] 不通过标准：只新增几个 `if (workspaceMode === "cloud")`；或移动端只是桌面 UI 的窄屏挤压；或本地版仍要求云端登录/团队上下文。

---

## 2. 当前基线审计

Phase 13 开始前必须承认当前状态，避免把“已有字段分支”误认为“产品壳拆分已完成”。

| 区域 | 当前状态 | Phase 13 要解决的问题 |
|------|---------|----------------------|
| App 入口 | `frontend/src/App.tsx` 是单一应用壳 | 拆成 `LocalDesktopShell`、`SaasWebShell`、`MobileShell` |
| ProjectSidebar | 同时显示个人空间/团队、本机/云端项目创建、本机/云端项目列表 | 本地版隐藏团队空间；SaaS 版隐藏本机目录操作；移动端不用桌面侧栏 |
| WorkspaceSettingsPage | 已按 `workspaceMode` 部分分支，cloud 显示配额/Secrets/导入/快照/成员/审计，local 显示本机路径摘要 | 拆成 `LocalProjectSettings` 与 `CloudWorkspaceSettings`，避免本地版使用云端语义 |
| ArtifactCard | 同一组件承载本地 build/export/preview 和云端 preview/deploy/logs/retry | 抽出 `LocalArtifactActions` 与 `CloudArtifactActions`，按 capability 注入 |
| API Client | cloud 开发态 auth header 逻辑在通用 client 内 | auth/provider 由 shell 注入，local client 不携带 SaaS 用户/团队头 |
| Mobile | 已有 mobile session/approval API 类型和端点 | 缺少独立 `MobileShell`、移动路由、Capacitor 工程和移动验收 |
| Native 包装 | 技术栈锁定 Tauri v2 / Capacitor，但仓库当前未形成独立 native app 壳 | Phase 13 至少建立 packaging skeleton 和 smoke，不要求完成商店发布 |

---

## 3. 术语与边界

| 术语 | 定义 | 不能混淆为 |
|------|------|-----------|
| `workspaceMode` | Project 数据层字段：`local` 表示本机路径，`cloud` 表示云端 workspace | 不是产品壳，不决定整个应用导航 |
| `ProductEdition` | 产品版本：`local` 或 `saas` | 不是某个 Project 的属性 |
| `AppSurface` | 端侧表面：`desktop` 或 `mobile` | 不是 CSS breakpoint |
| `RuntimeCapabilities` | 后端和前端共同确认的能力矩阵 | 不是临时 feature flag 字符串 |
| Shell | 顶层产品壳，决定导航、路由、认证、可用功能、布局密度 | 不是普通页面组件 |

三者关系：

```text
ProductEdition + AppSurface 选择 Shell
Shell 读取 RuntimeCapabilities 决定可用功能
Project.workspaceMode 决定单个 Project 的数据/运行路径
```

示例：

- Local Desktop Shell 只能创建和打开 `workspaceMode = "local"` 的 Project。
- SaaS Web Shell 默认创建 `workspaceMode = "cloud"` 的 Project。
- Mobile Shell 只消费 SaaS/cloud 侧 API；它可以查看 cloud Project，不启动本机 CLI。

---

## 4. 产品壳矩阵

| 产品壳 | 目标用户 | 后端来源 | 主要导航 | 必须显示 | 必须隐藏 |
|--------|---------|----------|---------|---------|---------|
| Local Desktop Shell | 本机使用 AgentHub 的个人用户 | `localhost` 后端 + 本机文件系统 + 本机 CLI | 项目、对话、Agent、本机项目设置 | 新建本机项目、选择文件夹、本地 Agent 环境、本地 preview/build/export | 个人空间/团队、cloud workspace、云部署、团队成员、云审计、云配额 |
| SaaS Web Shell | 云端协作团队和个人云用户 | 云端 API + cloud sandbox + hosting provider | 个人空间/团队、项目、对话、工作区设置、部署、通知 | 团队/RBAC、cloud workspace、Secrets、导入、快照、preview/deploy/logs/rollback、通知评论 | 本机绝对路径、本机目录选择、CLI executable 配置、localhost preview |
| Mobile Shell | 审批者、评论者、轻量协作者 | SaaS API | 会话、通知、审批、Artifact | IM 会话、未读、通知、审批卡片、评论、preview/deployment 链接、附件查看 | 桌面三栏、完整 workspace settings、本机 CLI、本机文件树、部署 pipeline 管理 |

---

## 5. 跨模块契约

### 5.1 API 端点

Phase 13 新增一个能力发现端点。它是 shell 分发和 UI 功能开关的唯一后端契约。

| 端点 | 方法 | 请求体 | 成功响应 | 错误响应 |
|------|------|--------|---------|---------|
| `/api/capabilities` | GET | 无 | `200: RuntimeCapabilities` | `500` |

`RuntimeCapabilities` 响应示例：

```json
{
  "edition": "local",
  "surface": "desktop",
  "authRequired": false,
  "apiBaseUrl": "http://127.0.0.1:8000",
  "features": {
    "localWorkspace": true,
    "localCliRuntime": true,
    "localPreview": true,
    "localBuildExport": true,
    "cloudWorkspace": false,
    "teamSpaces": false,
    "cloudPreview": false,
    "deployment": false,
    "auditLogs": false,
    "notifications": false,
    "mobileApprovals": false
  },
  "limits": {
    "maxUploadBytes": 10485760
  }
}
```

### 5.2 前端构建环境变量

| 变量 | 允许值 | 作用 |
|------|--------|------|
| `VITE_AGENTHUB_EDITION` | `local` / `saas` | 选择本地版或 SaaS 版产品壳 |
| `VITE_AGENTHUB_SURFACE` | `desktop` / `mobile` | 选择桌面或移动端表面 |
| `VITE_AGENTHUB_API_BASE` | URL | 指定 API base；本地默认 `http://127.0.0.1:8000`，SaaS/mobile 由部署环境注入 |
| `VITE_AGENTHUB_DEV_AUTH` | `true` / `false` | 仅 SaaS 开发态可用，禁止 local 默认开启 |

目标 npm scripts：

```json
{
  "dev:local": "vite --mode local-desktop",
  "dev:saas": "vite --mode saas",
  "dev:mobile": "vite --mode mobile",
  "build:local": "tsc && vite build --mode local-desktop",
  "build:saas": "tsc && vite build --mode saas",
  "build:mobile": "tsc && vite build --mode mobile"
}
```

实现说明：Vite v5 不允许使用 `local` 作为 mode 名称，因为它与 `.env.local` 后缀规则冲突。Phase 13 保留 `dev:local` / `build:local` 作为对人的命令入口，实际 Vite mode 使用 `local-desktop`。

### 5.3 TypeScript 类型

```typescript
export type ProductEdition = "local" | "saas";
export type AppSurface = "desktop" | "mobile";

export type FeatureKey =
  | "localWorkspace"
  | "localCliRuntime"
  | "localPreview"
  | "localBuildExport"
  | "cloudWorkspace"
  | "teamSpaces"
  | "cloudPreview"
  | "deployment"
  | "auditLogs"
  | "notifications"
  | "mobileApprovals";

export interface RuntimeCapabilities {
  edition: ProductEdition;
  surface: AppSurface;
  authRequired: boolean;
  apiBaseUrl: string;
  features: Record<FeatureKey, boolean>;
  limits: {
    maxUploadBytes?: number;
  };
}

export interface ShellContextValue {
  capabilities: RuntimeCapabilities;
  edition: ProductEdition;
  surface: AppSurface;
}
```

### 5.4 数据库 Schema 变更

Phase 13 默认不新增业务表。它可以新增配置表或本地设置项，但不得改变 Phase 9-12 的 Project、Workspace、Runtime、Artifact、Deployment、Notification 业务契约。

如果实现中确实需要持久化客户端偏好，只允许新增低风险表：

```sql
CREATE TABLE app_preferences (
  id VARCHAR PRIMARY KEY,
  scope VARCHAR NOT NULL,
  key VARCHAR NOT NULL,
  value_json TEXT NOT NULL,
  updated_at DATETIME NOT NULL
);
```

---

## 6. 目标目录结构

Phase 13 应把“壳”和“业务功能”分层，不把所有产品形态继续堆在 `components/`。

```text
frontend/src/
├── app/
│   ├── AppRoot.tsx
│   ├── ShellProvider.tsx
│   ├── capabilities.ts
│   └── routes.tsx
├── shells/
│   ├── local/
│   │   ├── LocalDesktopShell.tsx
│   │   ├── LocalProjectSidebar.tsx
│   │   └── LocalProjectSettings.tsx
│   ├── saas/
│   │   ├── SaasWebShell.tsx
│   │   ├── SaasProjectSidebar.tsx
│   │   └── CloudWorkspaceSettings.tsx
│   └── mobile/
│       ├── MobileShell.tsx
│       ├── MobileSessionList.tsx
│       ├── MobileChatView.tsx
│       ├── MobileNotificationView.tsx
│       └── MobileApprovalView.tsx
├── features/
│   ├── chat/
│   ├── projects/
│   ├── artifacts/
│   │   ├── ArtifactCard.tsx
│   │   ├── LocalArtifactActions.tsx
│   │   └── CloudArtifactActions.tsx
│   ├── agents/
│   ├── collaboration/
│   └── workspace/
├── api/
├── stores/
└── types/
```

Native packaging skeleton：

```text
desktop/                    # Tauri v2 壳，负责本地后端进程和桌面权限
mobile/                     # Capacitor 壳，负责 iOS/Android 配置
```

如果实现阶段选择把 Tauri/Capacitor 配置放在 `frontend/` 下，必须在 Phase 13 交付说明中记录原因，并保证三端构建命令仍清晰分离。

---

## 7. 行为规格

### 7.1 Shell 选择流程

```text
1. 启动命令注入 VITE_AGENTHUB_EDITION 和 VITE_AGENTHUB_SURFACE。
2. AppRoot 请求 GET /api/capabilities。
3. ShellProvider 校验 env 与后端 capabilities 是否兼容。
4. ShellProvider 选择 LocalDesktopShell / SaasWebShell / MobileShell。
5. Shell 将 capabilities 下发给 feature components。
6. Feature components 只渲染当前 capabilities 允许的动作。
```

兼容规则：

- env 为 `local + desktop`，后端返回 `edition = saas` 时，前端必须显示启动配置错误，不允许进入半混合 UI。
- env 为 `saas + mobile` 或 `saas + desktop`，后端要求 auth 时，必须先走 SaaS auth，不允许注入 local dev header。
- env 为 `local + mobile` 暂不作为正式组合；如果出现，前端显示“不支持本机移动端壳”。

### 7.2 本地版流程

```text
用户启动本地桌面版
  → LocalDesktopShell 打开
  → 侧栏只显示本机项目和 Agent
  → 用户新建空白项目或选择已有文件夹
  → 会话中的 Agent 以 Project.workspace_path 作为 cwd 执行
  → ArtifactCard 显示本地 preview/build/export/edit/version
  → 本地项目设置显示路径、Agent 环境、运行健康状态
```

本地版禁止流程：

- 不出现个人空间/团队切换。
- 不创建 `workspaceMode = "cloud"` 的 Project。
- 不调用 cloud preview/deployment API。
- 不要求登录、团队 ID、cloud workspace ID。

### 7.3 SaaS Web 流程

```text
用户打开 SaaS Web
  → SaasWebShell 进入登录态或开发态 SaaS auth
  → 顶层可切换个人空间/团队
  → 用户创建 cloud Project 或导入仓库
  → Cloud workspace + sandbox runtime 执行 Agent
  → ArtifactCard 显示 cloud preview/deploy/logs/rollback
  → CloudWorkspaceSettings 管理 Secrets、导入、快照、成员、审计、配额
```

SaaS 版禁止流程：

- 不暴露服务器物理路径或用户本机路径。
- 不显示本机目录选择器。
- 不要求用户配置本机 CLI executable。
- 不把 localhost preview/export 作为主要交付动作。

### 7.4 移动端流程

```text
用户打开 MobileShell
  → MobileSessionList 显示会话、未读和待审批数
  → 用户进入 MobileChatView 查看消息和 Artifact 摘要
  → 用户打开通知或审批卡片
  → MobileApprovalView 调用 Phase 12 mobile approval API
  → 用户查看 preview/deployment 链接或评论
```

移动端禁止流程：

- 不显示桌面三栏布局。
- 不打开完整 workspace settings。
- 不启动本机 CLI、本机 build 或本机文件系统操作。
- 不承担复杂 Deployment pipeline 管理；移动端只查看状态、打开链接、处理审批。

---

## 8. 前端页面设计

### 8.1 Local Desktop Shell

```text
┌───────────────┬──────────────────┬────────────────────────────────────┐
│ LocalProjects │ LocalSessions    │ ChatWorkspace                      │
│ Agent list    │                  │ MessageList + LocalArtifactActions │
│ Project setup │                  │ ChatInput                          │
└───────────────┴──────────────────┴────────────────────────────────────┘
```

本地版仍保持生产力三栏布局，但左侧语义必须是“本机项目”，不是“个人空间/团队”。

### 8.2 SaaS Web Shell

```text
┌───────────────┬──────────────────┬────────────────────────────────────┐
│ SpaceSwitcher │ CloudSessions    │ CloudChatWorkspace                 │
│ CloudProjects │ Notifications    │ MessageList + CloudArtifactActions │
│ Team nav      │                  │ ChatInput + Collaboration          │
└───────────────┴──────────────────┴────────────────────────────────────┘
```

SaaS 版的第一层导航是个人空间/团队，项目挂在空间下。工作区设置是 cloud workspace 管理台，不复用本地项目设置页。

### 8.3 Mobile Shell

```text
┌──────────────────────────────┐
│ MobileTopBar                 │
├──────────────────────────────┤
│ MobileRouteContent           │
│ - Sessions                   │
│ - Chat                       │
│ - Notifications              │
│ - Approval                   │
│ - Artifact Preview           │
├──────────────────────────────┤
│ MobileBottomNav              │
└──────────────────────────────┘
```

移动端采用单列路由和底部导航。按钮必须适合触控；长日志、完整设置、复杂表格默认不进入移动端。

### 8.4 组件拆分规则

| 当前组件 | Phase 13 目标 |
|---------|---------------|
| `ProjectSidebar` | 拆为 `LocalProjectSidebar` 与 `SaasProjectSidebar`，共享 `ProjectListItem` |
| `WorkspaceSettingsPage` | 拆为 `LocalProjectSettings` 与 `CloudWorkspaceSettings` |
| `ArtifactCard` | 保留共享主体，动作区拆为 `LocalArtifactActions` / `CloudArtifactActions` / `MobileArtifactActions` |
| `ChatInput` | 保留共享输入核心，附件、拖拽、移动端拍照入口按 capabilities 注入 |
| `api/client.ts` | 拆出 `createApiClient(authProvider, capabilities)`，禁止通用 client 写死 dev cloud header |
| `App.tsx` | 收敛为 `AppRoot`，不承载具体产品导航 |

---

## 9. 能力门禁

### 9.1 功能矩阵

| 功能 | Local Desktop | SaaS Web | Mobile |
|------|---------------|----------|--------|
| 本机目录创建/绑定 | 必须 | 禁止 | 禁止 |
| 本机 CLI runtime | 必须 | 禁止 | 禁止 |
| cloud workspace | 禁止 | 必须 | 只读/消费 |
| 个人空间/团队 | 禁止 | 必须 | 可显示当前空间，但不做完整管理 |
| 本地 preview/build/export | 必须 | 禁止作为主入口 | 禁止 |
| cloud preview/deploy | 禁止 | 必须 | 查看/审批 |
| Secrets/配额/快照/审计 | 禁止 | 必须 | 只读摘要或跳转 Web |
| 评论/通知 | 可保留本地 IM 状态 | 必须 | 必须 |
| 附件输入 | 可用本机文件 | 可用云端上传 | 轻量上传/查看 |
| Agent 模板创建 | 完整 | 完整 | 只读或轻量发起 |

### 9.2 编码规则

- UI 组件不得直接通过 `workspaceMode` 决定产品壳导航。
- Shell 级组件可以读取 `edition/surface/capabilities`。
- Feature 组件只允许通过 `useCapabilities()` 判断动作是否可用。
- `workspaceMode` 只用于 Project 数据、API 请求和单个 Project 的局部展示。
- local shell 中不得导入 cloud-only 设置页；saas shell 中不得导入 native filesystem selector。
- mobile shell 中不得导入桌面 sidebar 或 workspace settings 全量组件。

---

## 10. 启动与发布策略

### 10.1 开发启动命令

目标开发命令：

| 端 | 后端 | 前端 |
|----|------|------|
| 本地桌面版 | `python backend/app/main.py` 或 Tauri 管理的本地后端 | `cd frontend && npm run dev:local` |
| SaaS Web 版 | 云端后端或本地 cloud-dev 后端 | `cd frontend && npm run dev:saas` |
| 移动端 | SaaS API 或 cloud-dev 后端 | `cd frontend && npm run dev:mobile`，Capacitor smoke 使用 `mobile/` 配置 |

Phase 13 完成前，当前项目仍可能只能通过 `npm run dev` 启动单一混合壳；Phase 13 的目标就是让以上命令成为正式开发入口。

### 10.2 构建产物

| 产物 | 构建命令 | 发布对象 | 更新节奏 |
|------|----------|----------|----------|
| `agenthub-local-desktop` | `npm run build:local` + Tauri build | 桌面安装包 | 可晚于 SaaS 独立发布 |
| `agenthub-saas-web` | `npm run build:saas` | Web 静态资源 / SaaS 部署 | 可高频发布 |
| `agenthub-mobile` | `npm run build:mobile` + Capacitor build | iOS/Android/PWA | 按移动端审核节奏发布 |

共享代码变更必须跑三端兼容矩阵；单端壳变更只需跑对应端完整矩阵 + 共享单元测试。

---

## 11. 测试策略

### 11.1 单元测试

| 测试对象 | 覆盖内容 |
|---------|---------|
| `capabilities.ts` | env 解析、后端 capabilities 合并、非法组合报错 |
| `ShellProvider` | 三端 shell 选择、loading/error/unsupported 状态 |
| `LocalProjectSidebar` | 不显示团队/云端项目创建，能创建/选择本机项目 |
| `SaasProjectSidebar` | 显示个人空间/团队，隐藏本机目录选择 |
| `ArtifactActions` | local/cloud/mobile 三套动作互斥 |
| API client factory | local 不注入 cloud dev header，saas dev 才注入开发态 auth |

### 11.2 集成测试

- Local capabilities + local shell：创建本机 Project，发送消息，Artifact 显示本地 actions。
- SaaS capabilities + SaaS shell：创建 cloud Project，Artifact 显示 preview/deploy，工作区设置显示云端管理。
- Mobile capabilities + mobile shell：进入会话、查看通知、处理审批、打开 preview/deployment 链接。

### 11.3 E2E / 真实服务验收

| 验收端 | 最低真实路径 |
|--------|-------------|
| Local Desktop | 启动本地后端 + `dev:local`，创建本机 Project，私聊真实 Agent 或测试 Agent，产物本地 preview/build/export |
| SaaS Web | 启动 cloud-dev 后端 + `dev:saas`，创建 cloud Project，进入团队空间，生成 preview/deployment，查看日志 |
| Mobile | `dev:mobile` 或 Capacitor webview，查看会话/通知/审批，审批状态与 Web 端同步 |

### 11.4 视觉回归

- 桌面宽度：Local/SaaS 两个 shell 分别截图，确认导航词汇和动作区不串端。
- 移动宽度：MobileShell 单列布局截图，确认没有桌面三栏横向挤压。
- ArtifactCard：local/cloud/mobile 三种动作截图对比。

---

## 12. 验收标准

- [x] AC-P13-01: `npm run dev:local` 启动后进入 LocalDesktopShell，页面不出现“个人空间”“团队”“云端部署”“工作区配额”等 SaaS 入口。
- [x] AC-P13-02: LocalDesktopShell 可创建本机 Project 或选择已有文件夹，Project 返回 `workspaceMode = "local"` 且本地聊天/Artifact 链路可用。
- [x] AC-P13-03: Local Artifact 只显示本地 preview/build/export/edit/version，不显示 cloud preview/deploy/logs/rollback。
- [x] AC-P13-04: `npm run dev:saas` 启动后进入 SaasWebShell，显示个人空间/团队和 cloud Project 创建入口。
- [x] AC-P13-05: SaasWebShell 不显示本机目录选择器、本机绝对路径、本机 CLI executable 配置或 localhost preview 作为主入口。
- [x] AC-P13-06: Cloud Artifact 只显示 cloud preview/deploy/logs/rollback，不显示本地 export 作为主要发布动作。
- [x] AC-P13-07: CloudWorkspaceSettings 覆盖 Secrets、导入、快照、成员、审计、配额；LocalProjectSettings 不显示这些云端配置。
- [x] AC-P13-08: `npm run dev:mobile` 启动后进入 MobileShell，使用单列移动布局而不是桌面三栏压缩。
- [x] AC-P13-09: MobileShell 可查看会话、未读、通知、审批、Artifact 摘要和 preview/deployment 链接。
- [x] AC-P13-10: MobileShell 不导入本机文件选择、CLI runtime 控制、完整 workspace settings 或桌面 sidebar。
- [x] AC-P13-11: `/api/capabilities` 返回的能力矩阵能驱动三端功能门禁，非法 env/capabilities 组合显示明确错误。
- [x] AC-P13-12: 通用 API client 不再默认注入 cloud dev auth header；auth provider 由 shell 注入。
- [x] AC-P13-13: `npm run build:local`、`npm run build:saas`、`npm run build:mobile` 均通过 TypeScript 检查并产出独立 bundle。
- [x] AC-P13-14: Tauri skeleton 可包装 local build，并能 smoke 本地后端启动或连接。
- [x] AC-P13-15: Capacitor skeleton 可包装 mobile build，并能 smoke 打开 MobileShell。
- [x] AC-P13-16: P1 local 真实服务回归、P2 SaaS cloud slice 回归、Mobile approval/preview 回归全部通过后，Phase 13 才能标记 Completed。

---

## 13. 分步实施计划

### 13A：能力契约与入口

- 新增 `/api/capabilities`。
- 新增 `RuntimeCapabilities` 类型、`ShellProvider`、env 解析。
- `App.tsx` 收敛为 `AppRoot`，先保持原混合壳作为 fallback。

### 13B：桌面 Local/SaaS 壳拆分

- 拆 `LocalDesktopShell` 和 `SaasWebShell`。
- 拆 ProjectSidebar、WorkspaceSettings、ArtifactActions。
- 移除 local shell 中所有 SaaS-only 入口。
- 移除 saas shell 中所有 local-only 入口。

### 13C：API Client 与能力门禁收口

- 引入 `createApiClient(authProvider, capabilities)`。
- SaaS dev auth 只在 SaaS dev shell 注入。
- 所有 cloud delivery/collaboration API 调用必须通过 capability gate。

### 13D：Mobile Shell

- 新增 MobileShell 路由和移动端页面。
- 接入 Phase 12 mobile session、notification、approval、artifact render/preview API。
- 移动端只实现轻量审批、查看和评论，不实现完整桌面工作台。

### 13E：构建与包装

- 新增三端 dev/build scripts。
- 建立 Tauri v2 skeleton 和 Capacitor skeleton。
- 输出三端 smoke 文档和验收截图。

---

## 14. Non-Goals（明确不做什么）

| 不做的事 | 原因 | 由谁负责 |
|---------|------|---------|
| 重写 Agent runtime | Phase 13 只拆产品壳 | 不做 |
| 改变 Project-first 模型 | 已由 ADR-0009 锁定 | 不做 |
| 新增计费/套餐/SSO | 企业化商业能力 | 后续 |
| 移动端完整 IDE | Mobile 定位轻量协作与审批 | 不做 |
| 三端拆成三个代码仓库 | 当前阶段应共享核心代码，降低维护成本 | 不做 |
| 恢复右侧 Artifact Drawer | 已被 ADR-0010 否决 | 不做 |

---

## 15. 破坏性变更与迁移

| 维度 | 当前行为 | Phase 13 行为 | 迁移路径 |
|------|----------|---------------|---------|
| App 入口 | 单一 `App.tsx` 混合渲染 | `AppRoot` 分发三端 shell | 先保留旧 App 为 fallback，再逐步迁移 |
| 项目侧栏 | 本地/云端/团队混在一个侧栏 | Local/SaaS 侧栏分离 | 抽共享 ProjectListItem，shell 决定创建入口 |
| 设置页 | 一个页面按 workspaceMode 分支 | 本地项目设置与云端工作区设置分离 | 先复用内部 section，再拆页面 |
| Artifact 操作 | 本地和云端动作同卡混放 | actions 按 capabilities 注入 | 保留 ArtifactCard 主体，拆动作区 |
| API auth | 通用 client 含 SaaS dev header | auth provider 由 shell 注入 | local 默认 no-auth，saas dev 显式启用 |
| 移动端 | 移动 API 存在但无独立壳 | MobileShell 单列产品体验 | 从 session/notification/approval 最小闭环开始 |

---

## 16. 完成定义

Phase 13 完成时，开发者必须能回答并演示：

1. 本地版如何启动、构建、验收，且不会出现 SaaS 概念。
2. SaaS 版如何启动、构建、验收，且不会暴露本机路径和本机特权能力。
3. 移动端如何启动、构建、验收，且不是桌面 UI 的窄屏压缩。
4. 一个共享组件改动会触发哪些三端测试。
5. 一个单端壳改动如何只发布对应端，而不强制推送另外两端。

> **版本历史**
> - v1.1 (2026-06-09): 根据 Phase 13 实现与验收结果，将状态更新为 Completed；补充 `local-desktop` Vite mode 说明与交付文档入口。
> - v1.0 (2026-06-09): 创建 Phase 13 多端产品壳拆分 Spec，定义三端 shell、capability 契约、构建发布策略和验收矩阵。
