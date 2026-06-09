# Phase 13 开发日志：多端产品壳拆分

**阶段**: Phase 13  
**日期**: 2026-06-09  
**状态**: 已实现，自动化与真实服务验收通过；等待人工验收后提交  
**关联 Spec**: [docs/specs/phase13/README.md](../specs/phase13/README.md)

## 1. 阶段概述

Phase 13 的目标是把 Phase 9-12 累积出的本地版、SaaS 版和移动端能力拆成独立产品壳。本轮完成：

| 模块 | 内容 |
|------|------|
| 能力契约 | 新增 `/api/capabilities` 与前后端 `RuntimeCapabilities` 类型。 |
| Shell 入口 | 新增 `AppRoot`、`ShellProvider`、Local/SaaS/Mobile 三端入口。 |
| Feature 门禁 | ProjectSidebar、WorkspaceSettings、AgentCliForm、ArtifactCard 按 capabilities 隐藏跨端能力。 |
| API client | local 默认 no-auth，SaaS dev auth 由 shell 注入。 |
| 移动壳 | 单列 MobileShell，覆盖会话、通知、审批、产物查看入口。 |
| 构建包装 | 三端 dev/build scripts，Tauri v2 skeleton，Capacitor skeleton，desktop/mobile smoke。 |

## 2. 开发时间线

- Day 0：阅读 `CONTEXT.md`、Phase 13 Spec、Phase 9-12 实现与 UX 测试规范。
- Day 1：新增后端 capabilities endpoint、schema 和测试。
- Day 1：新增前端 capabilities、ShellProvider、AppRoot 与三端 shell。
- Day 1：收口 ProjectSidebar、WorkspaceSettingsPage、AgentCliForm、ArtifactCard 的跨端门禁。
- Day 1：新增 MobileShell 和 native packaging skeleton。
- Day 1：补前后端测试、三端构建、真实服务轮换验收和浏览器截图验收。
- Day 1：新增 Phase 13 交付文档和开发日志。

## 3. Bug 与解决方案

| 问题 | 根因 | 解决 | 教训 |
|------|------|------|------|
| `npm run build:local` 失败 | Vite v5 禁止 `local` 作为 mode 名称，因为会和 `.env.local` 后缀规则冲突 | 保留脚本名 `build:local` / `dev:local`，实际 mode 改为 `local-desktop` | 构建命令的用户语义和工具 mode 名称可以分离。 |
| local API client 会继承 SaaS dev header 风险 | 通用 client 内部写死开发态 cloud header | 改为 `configureApiClient` 注入 auth provider，local 默认 no-auth | 多产品壳必须把认证策略放在 shell 层。 |
| 移动端截图疑似底栏缺一个入口 | Chrome headless 在 Windows 显示缩放下裁切 390px 物理截图 | 用 DevTools Protocol 读取真实布局，确认四按钮在 nav 内；补 `w-screen/min-w-0/overflow-hidden` 约束并保留 484px 验收截图 | UX 验收要同时看截图和布局数值，避免工具缩放误判。 |

## 4. 建立的基础设施

- `backend/test_api/test_phase13_capabilities.py`：覆盖能力矩阵和非法组合基础门禁。
- `frontend/src/app/capabilities.test.ts`：覆盖 env 推断和 capabilities 校验。
- `frontend/src/components/ProjectSidebar.test.tsx`：覆盖 Local/SaaS 项目侧栏互斥入口。
- `frontend/src/hooks/useWorkspaceRuntime.test.tsx`：覆盖 local 不加载 cloud identity。
- `frontend/src/components/ArtifactCard.test.tsx`：覆盖 local/cloud actions 互斥。
- `desktop/scripts/smoke.mjs`、`mobile/scripts/smoke.mjs`：覆盖 native skeleton 存在性和构建入口。

## 5. 方法总结

- Phase 13 的重点不是增加新 runtime，而是把产品语义从 `workspaceMode` 中解耦出来。`workspaceMode` 仍是 Project 数据字段；`ProductEdition + AppSurface + RuntimeCapabilities` 才决定 shell。
- Feature 组件可以判断 capabilities，但不应该自己决定整个产品壳导航。壳级分发要靠 `AppRoot` 和 shell wrappers。
- P1/P2/Mobile 同时存在时，验收必须轮换真实服务，而不是只跑一个前端 build。否则最容易漏掉 proxy、auth header 和 backend capability mismatch。

## 6. 下一步

- 将 Tauri skeleton 扩展为真正管理本地后端进程的桌面特权层。
- 将 Capacitor skeleton 接入平台构建、图标、权限和移动端登录态。
- 引入 Playwright 固定 viewport/device scale，替换当前 Chrome headless 手写截图脚本。
- 在 SaaS auth 进入生产阶段后，把 dev auth provider 替换为正式登录会话。
