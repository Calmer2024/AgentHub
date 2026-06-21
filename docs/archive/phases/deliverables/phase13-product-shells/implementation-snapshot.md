# Phase 13 实现快照

**日期**: 2026-06-09  
**状态**: 已实现

## 后端能力契约

- 新增 `GET /api/capabilities`，返回 `RuntimeCapabilities`。
- `ProductEdition = local | saas`，`AppSurface = desktop | mobile`。
- 后端通过 `AGENTHUB_EDITION`、`AGENTHUB_SURFACE`、`AGENTHUB_API_BASE_URL`、`AGENTHUB_AUTH_REQUIRED`、`AGENTHUB_MAX_UPLOAD_BYTES` 输出能力矩阵。
- local/desktop 开启本机 workspace、CLI runtime、本地 preview/build/export。
- saas/desktop 开启 cloud workspace、team spaces、cloud preview/deployment、audit logs、notifications。
- saas/mobile 开启 cloud workspace、cloud preview、notifications、mobile approvals。

## 前端壳拆分

- `frontend/src/app/AppRoot.tsx` 负责顶层分发。
- `frontend/src/app/ShellProvider.tsx` 负责读取 env、配置 API client、请求后端 capabilities、阻断 env/backend 不匹配组合。
- `frontend/src/app/capabilities.ts` 提供默认矩阵、fallback 和校验逻辑。
- `frontend/src/shells/local/LocalDesktopShell.tsx` 进入本机工作台。
- `frontend/src/shells/saas/SaasWebShell.tsx` 进入 SaaS 工作台。
- `frontend/src/shells/mobile/MobileShell.tsx` 提供单列移动端入口。

## 功能门禁

- `ProjectSidebar` 增加 `productEdition`，local 只显示本机项目和本机创建入口，SaaS 只显示个人空间/团队和云端项目入口。
- `WorkspaceSettingsPage` 拆出 `LocalProjectSettings` 与 `CloudWorkspaceSettings`，避免本地版出现 Secrets、配额、审计等云端语义。
- `AgentCliForm` 增加 `runtimeScope`，SaaS 下隐藏本机 executable、init args、env vars 和本机 Codex 登录态配置。
- `ArtifactCard` 通过 `useCapabilities()` 分发本地 actions 和云端 actions，不再同时显示 local build/export 与 cloud deploy。
- API client 改为 `configureApiClient` / auth provider 注入，local 默认不携带 SaaS dev header。

## 构建与包装

前端保留用户语义脚本名，实际 Vite local mode 使用 `local-desktop`，因为 Vite v5 禁止使用 `local` 作为 mode 名称，它会与 `.env.local` 后缀规则冲突。

| 入口 | 命令 | 输出 |
|------|------|------|
| Local Desktop | `npm run dev:local` / `npm run build:local` | `dist-local/` |
| SaaS Web | `npm run dev:saas` / `npm run build:saas` | `dist-saas/` |
| Mobile | `npm run dev:mobile` / `npm run build:mobile` | `dist-mobile/` |

三端并行调试由 `scripts/start-three-shells.ps1` 管理。脚本会分别启动三个后端和三个 Vite 前端，并通过 `VITE_AGENTHUB_PROXY_TARGET` 让每个前端的 `/api`、`/ws` 代理到对应后端：

| 端 | 后端端口 | 前端端口 |
|----|----------|----------|
| Local Desktop | 8000 | 5173 |
| SaaS Web | 8010 | 5174 |
| Mobile | 8020 | 5175 |

Native skeleton：

- `desktop/`：Tauri v2 配置、Cargo skeleton、本地 smoke。
- `mobile/`：Capacitor 配置、mobile build webDir、本地 smoke。

## 移动端实现边界

Mobile Shell 接入 Phase 12 的 mobile session、notification、approval、artifact render API。它提供会话、通知、审批、产物四个底部入口，不导入桌面 sidebar、完整 workspace settings、本机文件选择或 CLI runtime 控制。
