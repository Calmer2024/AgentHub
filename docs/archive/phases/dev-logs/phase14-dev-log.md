# Phase 14 开发日志：生产 Auth 与租户隔离收口

## 1. 阶段概述

Phase 14 把 Phase 9 的开发态用户/团队/RBAC 基线推进为生产身份边界：SaaS Web 与 Mobile 使用真实登录态，本地桌面端保持不强制登录；cloud 资源列表、详情、写操作、审批、转发、日志等入口统一经过当前用户和团队成员关系推导出的 `TenantScope`。

| 模块 | 内容 | 主要文件 |
|------|------|----------|
| AuthProvider 与 session token | 本地 email provider、dev header provider 分离，生产禁用开发请求头，支持 login/refresh/logout/me | `backend/app/services/auth_service.py`、`backend/app/api/auth.py`、`backend/app/services/phase14_schemas.py` |
| 租户边界 | `TenantGuard` 统一 cloud Project 读写删除权限，个人项目与团队项目按 owner/team member 过滤 | `backend/app/services/tenant_guard.py`、`backend/app/api/projects.py`、`backend/app/services/project_service.py` |
| Cloud 资源收口 | Sessions、Messages、Artifacts、Runs、Approvals、AuditLogs 等入口按可见 Project 校验 | `backend/app/api/*.py`、`backend/app/services/collaboration_service.py`、`backend/app/services/audit_service.py` |
| 数据模型与迁移 | `auth_identities`、`auth_sessions`、`users.status`、`users.last_login_at` | `backend/app/models/auth.py`、`backend/migrations/028_phase14_auth_tenant_scope.sql` |
| 前端登录门 | SaaS Web 与 Mobile 进入工作台前加载登录态，支持邮箱登录与 token 存储/刷新 | `frontend/src/shells/saas/AuthGate.tsx`、`frontend/src/api/client.ts` |
| 回归测试 | 覆盖生产禁用 dev header、跨租户过滤、viewer 写操作拒绝、移动审批权限、AuthGate | `backend/test_api/test_phase14_auth_tenant.py`、`frontend/src/shells/saas/AuthGate.test.tsx` |

## 2. 验收标准对应关系

| Spec 验收项 | 实现与验证 |
|-------------|------------|
| SaaS Web 与 Mobile 共享生产登录态 | 前端 `AuthGate` 复用 `AuthSession`，Mobile 与 SaaS 壳均进入同一登录门 |
| 生产禁用开发请求头 | `cloud_auth_required()` 与 `DevHeaderAuthProvider.enabled` 根据环境和配置收口；API 测试覆盖生产伪造 header 返回 401 |
| Cloud 资源按租户过滤 | `TenantGuard.visible_project_filter()` 与各 API 入口的 project/session/resource guard 覆盖列表、详情和写操作 |
| 个人与团队 RBAC | 个人 cloud Project 仅 owner 可访问；团队 viewer 可读不可写，owner/admin/member 可写 |
| 本地桌面端不强制登录 | local edition 默认 `agenthub_auth_required=False`，前端 local shell 不包裹 `AuthGate` |
| 401/403 边界 | 未登录返回 401；无项目或团队权限返回 403，并写入权限拒绝 audit log |
| 自动化测试 | Phase 14 后端 API、前端 AuthGate、client session 存储/刷新与跨 Phase cloud 回归均有覆盖 |

## 3. 开发时间线

### Day 0：接口与边界确认

- 读取 Phase 14 Spec，确认本阶段只收口生产 Auth 与 TenantScope，不进入真实 runner/provider。
- 明确本地桌面端与 SaaS/Mobile 的认证边界，避免把本地 Project-first 流程改造成云登录依赖。

### Day 1：后端 Auth 与数据迁移

- 新增 `auth_identities` 与 `auth_sessions`。
- 引入 `AuthProvider` 抽象、local email 登录、refresh/logout/me 契约。
- 生产环境禁用开发态 `x-agenthub-user-*` 请求头。

### Day 2：TenantScope 与 cloud 资源收口

- 新增 `TenantGuard`，从数据库团队成员关系推导可见租户范围。
- 将 Project、Session、Message、Artifact、Run、Approval、AuditLog 等入口接入租户校验。
- 补齐 viewer 只读、owner/admin/member 可写的团队项目权限。

### Day 3：前端登录门与回归测试

- SaaS Web 与 Mobile shell 接入 `AuthGate`。
- 前端 API client 增加 bearer token、refresh 和本地 session 存储。
- 新增 Phase 14 后端 API 测试与 AuthGate 组件测试，并调整 Phase 10-12 cloud 回归测试的认证请求头。

## 4. 遇到的 Bug 与解决方案

| 问题 | 根因 | 解决 | 教训 |
|------|------|------|------|
| 生产环境仍可能通过开发请求头切换用户 | Phase 9 的 mock auth 是云端切片便利入口，未区分环境 | 增加 `agenthub_environment`、`agenthub_dev_auth_enabled`，生产禁用 dev header provider | SaaS 能力进入生产化阶段后，便利入口必须显式降级为 dev-only |
| 只保护写接口仍会泄漏列表和详情 | 早期 RBAC 更偏向写操作，列表/详情没有统一门卫 | 所有 cloud 资源入口都从 `TenantScope` 派生可见范围，不能信任前端过滤 | 租户隔离要从查询源头做，不从 UI 隐藏入口做 |
| viewer 可以读团队项目但不应创建会话或审批 | team member 角色语义未覆盖跨模块写路径 | 将 session create、message forward、mobile approval decision 纳入 project write guard | RBAC 角色要沿业务动作传播，不能只在 Project API 生效 |

## 5. 建立的基础设施

- `AuthProvider` / `AuthSubject` / `AuthSessionResult`：后续接入外部身份提供方时的稳定后端抽象。
- `TenantScope` / `TenantGuard`：cloud 资源查询与写操作的统一租户边界。
- `AuthGate`：SaaS Web 与 Mobile 共享的前端登录门。
- Phase 14 回归测试矩阵：生产禁用 dev header、跨租户过滤、viewer 写阻断、移动端审批权限。

## 6. 关键方法总结

- 生产 Auth 收口不是“加登录页”，而是把所有 cloud 查询入口改成服务端租户过滤。
- 本地版与 SaaS 版必须在能力层分叉：本地 Project 不强制云登录，SaaS/Mobile 不暴露本机路径和本机特权。
- 旧 Phase cloud 测试要随租户边界补认证上下文，否则会把“测试便利”误保留为“产品后门”。

## 7. 下一步

- Phase 15 在可信租户边界之上接入真实云 sandbox/runtime，避免真实容器运行放大越权风险。
- Phase 16 在同一身份和 RBAC 基础上接入真实部署 provider、release、rollback 与移动端审批发布。
- 外部托管身份、企业 SSO、计费订阅仍是后续生产化扩展，不属于 Phase 14 完成范围。
