# Phase 10 Sandbox Runner 与云端 Agent Runtime 实现快照

## 后端落点

| 模块 | 文件 | 说明 |
|------|------|------|
| 数据模型 | `backend/app/models/runtime.py` | 新增 `sandboxes`、`runtime_runs`、`runtime_logs`、`secrets`、`quota_usages`。 |
| 迁移 | `backend/migrations/025_phase10_sandbox_runtime.sql` | 创建 Phase 10 runtime 表和索引。 |
| 云端存储 | `backend/app/services/cloud_storage.py` | 将 cloud workspace 映射到隔离目录，支持 zip 导入、快照复制、恢复。 |
| Sandbox | `backend/app/services/sandbox_service.py`、`backend/app/api/sandboxes.py` | 创建、查询、停止 sandbox，保留 workspace 数据。 |
| Runtime | `backend/app/services/cloud_agent_runtime.py` | 复用 CLI adapter、ContextPack、RunService、ArtifactOutputBridge，输出 P1 兼容 SSE 事件。 |
| Secret | `backend/app/services/secret_service.py`、`backend/app/api/secrets.py` | 加密保存 Secret，运行时注入 env，日志和事件脱敏。 |
| Quota | `backend/app/services/quota_service.py`、`backend/app/api/quotas.py` | 默认并发、运行时长、内存、磁盘策略；超限返回 409。 |
| 运行 API | `backend/app/api/runs.py` | 新增显式 `POST /sessions/{id}/runs`、`GET /runs/{id}/logs`，cancel 识别 cloud run。 |
| 聊天 API | `backend/app/api/chat.py` | cloud Project 自动走 CloudAgentRuntime，本地 Project 保持原路径。 |
| 体检 | `backend/app/services/system_health_service.py` | cloud Project 不再按本机路径/可执行文件阻断。 |

## 前端落点

| 模块 | 文件 | 说明 |
|------|------|------|
| 类型 | `frontend/src/types/index.ts` | 新增 Sandbox、QuotaSummary、Secret、RuntimeLogs 类型。 |
| API client | `frontend/src/api/client.ts` | 新增 sandboxes/secrets/quotas/logs API，chat stream 带开发态云端 header。 |
| 运行条 | `frontend/src/components/RuntimeControlStrip.tsx` | 从 Run metadata 显示 cloud/local 与 sandbox 短 ID。 |
| 工作区设置 | `frontend/src/components/WorkspaceSettingsPage.tsx` | 新增 runtime 配额概览和 Secret 创建入口。 |

## 工作目录边界

- P1 本地 Project：`Project.workspace_path` 是用户本机真实目录，CLI cwd 仍为该目录。
- P2 云端 Project：前端只看到 `workspaceId` 与 `cloud://` 逻辑 URI；Phase 10 开发实现把它映射到 `data/workspaces/.cloud-workspaces/{workspaceId}`。
- 本阶段的隔离目录是可替换 runner 抽象，不是最终 SaaS 容器或 microVM 实现。Phase 11/后续可替换底层存储与 runner，不改变 API/SSE/DB 契约。

## 明确未做

- 未提供公网 preview/deployment URL，进入 Phase 11。
- 未接正式 OAuth/Session 登录，仍沿用 Phase 9 开发态 header auth。
- 未实现 Docker/microVM 级强隔离；当前切片以本机隔离目录 + 真实 subprocess 证明契约和端到端链路。
