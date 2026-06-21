# Phase 9 开发日志：Cloud Workspace Foundation

**阶段**: Phase 9  
**日期**: 2026-06-08  
**状态**: 已实现，自动化回归与真实服务验收通过

## 1. 阶段概述

Phase 9 的目标是建立 P2 SaaS 云版的 workspace 基座，同时证明 P1 本地桌面版不受影响。本轮完成：

| 模块 | 内容 | 规模 |
|------|------|------|
| 数据模型 | users、teams、team_members、workspaces、workspace_snapshots、workspace_imports、workspace_restores、audit_logs | 新增模型与迁移 |
| 后端服务 | AuthService、TeamService、CloudWorkspaceProvider、AuditService | 新增 4 个服务 |
| API | auth、teams、workspaces、audit-logs，Project create/delete local/cloud 分支 | 新增 4 个 router，更新 Project API |
| 前端 | TeamSwitcher、cloud/local Project 创建、WorkspaceSettingsPage、cloud 类型与 API client | 新增工作区设置页面 |
| 测试 | Phase 9 API、前端 API/组件/runtime hook 测试，P1/P2 真实服务验收 | 后端 169 API + 160 unit；前端 91 vitest |

## 2. 与 Spec 验收标准的对应关系

- AC-P9-01 到 AC-P9-03：通过 `/api/auth/me`、团队/RBAC、cloud Project 响应字段验证。
- AC-P9-04 与 AC-P9-09：通过 local Project 文件、snapshot、preview、build、export、Session workspace 真实服务路径验证。
- AC-P9-05 到 AC-P9-07：通过 workspace snapshot/restore/import/audit API 与权限测试验证。
- AC-P9-08：通过 WorkspaceSettingsPage/ProjectSidebar 组件测试和 Chrome headless 冒烟验证。
- AC-P9-10：真实服务完成 cloud slice：登录态 → 团队 → cloud Project → 导入 → 快照 → 恢复 → 审计。

## 3. 开发时间线

### Day 0：规格确认

- 阅读 `CONTEXT.md`、`AGENTS.md`、Phase 9 Spec、PRD-06、PRD-07。
- 确认本轮只做云端 workspace 元数据/RBAC/审计基座，不进入 sandbox、云端 CLI、preview/deploy。

### Day 1：后端基座

- 新增用户、团队、工作区、审计日志模型与迁移。
- 实现开发态 Header Auth、TeamService 权限矩阵、AuditService。
- 实现 CloudWorkspaceProvider 的 create/import/snapshot/restore/delete 元数据闭环。

### Day 2：Project API 与 P1 防回归

- `ProjectCreate` / `ProjectRead` 增加 `workspaceMode`、`workspaceId`、`teamId`。
- local Project 保持默认行为和 `workspacePath` 输出。
- cloud Project 隐藏 `workspacePath`，并对本地文件操作、build/preview/export 给出明确 Phase 边界错误。

### Day 3：前端入口

- ProjectSidebar 增加 TeamSwitcher、本机/云端创建分段、cloud 项目标识。
- 新增 WorkspaceSettingsPage，展示 cloud workspace 基本信息、导入、快照、成员、审计日志。
- API client 统一带开发态 cloud header，local 创建不要求登录。

### Day 4：测试与真实服务验收

- 补齐 Phase 9 API 测试、前端组件/API/hook 测试。
- 运行后端、前端全量回归。
- 清理旧 8000/5173 服务并用当前代码重启。
- 在真实服务上验证 P2 cloud slice 与 P1 local regression。
- 使用 Chrome headless 做桌面/移动 UI 冒烟截图。

## 4. 遇到的 Bug 与解决方案

| 现象 | 根因 | 解决 | 教训 |
|------|------|------|------|
| 后端 API 全量测试第一次命令失败 | 在 `backend/` 工作目录下仍写了 `backend\venv\Scripts\python.exe`，PowerShell 误当模块解析 | 改为 `.\venv\Scripts\python.exe -m pytest test_api\ -q` | 文档中命令要区分仓库根目录和子目录工作目录 |
| SQLAlchemy 关系出现循环依赖警告 | `Project.workspace_id` 与 `Workspace.project_id` 形成外键环 | `workspace_id` 外键使用 `use_alter=True` | local/cloud 双向关联要提前考虑迁移和 ORM flush 顺序 |
| 浏览器截图中短暂显示“云端登录态未就绪” | headless 脚本在 `fetchCurrentUser()` 完成前截图 | 等待 `demo@agenthub.local` 渲染后再截图 | UI 冒烟要等稳定状态，不要把加载态误判成失败 |
| CDP 脚本把 favicon 404 计为错误 | Vite 默认未提供 `/favicon.ico` | 将 network warning 与 React/console error 分开记录 | QA 报告要区分应用错误与浏览器/静态资源噪音 |

## 5. 建立的基础设施

- Phase 9 cloud workspace 元数据 Provider。
- Team/RBAC/Audit 服务基座。
- P1/P2 双工作区响应字段约定：local 使用 `workspacePath`，cloud 使用 `workspaceId`。
- 真实服务 P2 cloud slice 验收脚本化流程。
- Chrome headless CDP 无依赖浏览器冒烟方式。

## 6. 关键方法总结

- P2 云端化必须先加“不能破坏 P1 local”的门禁；每个 cloud-only API 都要明确 local 行为。
- 前端不要把 `workspacePath` 当成 Project 永远存在的字段；cloud Project 的核心锚点是 `workspaceId`。
- Phase 9 的 `cloud://` 是逻辑 URI，不是存储实现承诺；这让 Phase 10/11 可以自由接对象存储、volume 或 sandbox mount。
- 真实服务验收比单元测试更容易暴露 `/api` 代理、启动顺序、登录态加载和 UI 稳定状态问题。

## 7. 下一步

Phase 10 应从 Phase 9 的 `workspaceId`、RBAC 和 audit log 出发，接入 sandbox runner 与云端 Agent Runtime：

- 定义 cloud runtime 如何挂载 workspace。
- 保持 P1 `agent.output` / `artifact.created` / `approval.*` 事件契约兼容。
- 加入 secret、quota、runtime logs 和日志脱敏。
- 继续保留 P1 local CLI runtime、build/preview/export 的真实服务回归。
