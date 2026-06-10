# Phase 14：生产 Auth 与租户隔离收口

**版本**: v0.1  
**创建日期**: 2026-06-09  
**状态**: Completed  
**关联 ADR/PRD**: [AgentHub-多Agent协作平台设计](../../archive/AgentHub-多Agent协作平台设计.md)、[ADR-0005](../../adr/0005-target-architecture.md)、[ADR-0009](../../adr/0009-project-workspace-model.md)、[PRD-04](../../PRD/04-Data_API_Contracts.md)、[PRD-07](../../PRD/07-SaaS_Cloud_Workspace_Delivery.md)  
**依赖模块**: Phase 9 Cloud Workspace Foundation、Phase 12 协作与通知、Phase 13 多端产品壳拆分

> Phase 14 把 Phase 9 的开发态用户/团队/RBAC 收口为生产可用的身份认证与多租户边界。它不改变本机版 Project-first 工作流：本地桌面端仍可离线访问本机目录；SaaS Web 与 Mobile 必须使用同一个云端身份体系。

---

## 1. 目标

当前后端已经有 `users`、`teams`、`team_members` 和部分 RBAC 校验，但登录态由开发请求头模拟，Project 列表等入口仍存在未按租户收口的风险。Phase 14 的目标是建立生产身份边界：用户能真实登录，团队空间能真实隔离，所有云端资源访问都必须经过租户范围校验。

**成功标准**（可证伪）：

- [ ] SaaS Web 与 Mobile 共享同一个生产登录态，能跨端识别同一用户、团队、项目和通知。
- [ ] 生产环境禁用开发态 `x-agenthub-user-*` 登录头；开发态 mock auth 只能在显式 dev 配置下启用。
- [ ] 所有 cloud Project、Workspace、Session、Artifact、Deployment、Notification、Secret、AuditLog 列表和详情 API 都按当前用户/团队过滤。
- [ ] 个人 cloud Project 只能被 owner 访问；团队 Project 只能被成员访问，viewer 不能执行写操作。
- [ ] 本地桌面端不强制登录；用户登录云账号后只能访问云项目，不改变本机项目目录权限模型。
- [ ] 未登录用户访问 SaaS/Mobile 受保护资源返回 `401`；无租户权限返回 `403`；资源不存在或不可见时不泄漏敏感元数据。
- [ ] 自动化测试覆盖跨租户越权、列表过滤、详情读取、写操作、删除操作、移动端审批、开发态 auth 禁用。
- [ ] 不通过标准：只在前端隐藏入口；或仍允许生产环境通过请求头伪造用户；或仅保护写接口、不保护列表和详情接口。

---

## 2. 全局定位

```text
Phase 13 三端 shell
  -> [Phase 14: Production Auth + TenantScope + RBAC hardening]
  -> Phase 15 真实云 sandbox/runtime
  -> Phase 16 真实一键部署 provider
```

Phase 14 是 Phase 15/16 的前置条件。真实云运行和真实部署会放大越权风险，因此必须先把身份、租户和资源可见性收口。

---

## 3. 范围

### 3.1 必做

- 引入 `AuthProvider` 抽象，支持生产身份提供方和开发态 mock provider 分离。
- 建立 session/cookie 或 bearer token 认证链路，包含登录、刷新、登出、当前用户查询。
- 统一后端依赖：SaaS/Mobile cloud API 使用 `require_current_user`；local-only API 不强制云登录。
- 引入 `TenantScope`：当前用户、个人空间、可访问团队、可访问 Project/Workspace 的查询边界。
- 收口所有 cloud 资源 API 的列表、详情、创建、修改、删除和事件订阅权限。
- 修正 Project 列表：SaaS/Mobile 只能返回当前用户个人项目和所属团队项目；Local Desktop 只返回本机项目。
- 前端壳按能力和登录态显示登录页、个人空间、团队选择、无权限状态。
- 审计日志记录登录、登出、团队成员变更、权限拒绝、敏感资源访问。

### 3.2 非目标

- 不实现计费、订阅套餐、企业 SSO 完整管理台。
- 不实现真实容器运行时；Phase 15 负责。
- 不实现真实部署 provider；Phase 16 负责。
- 不让本地桌面端强制依赖云账号。

---

## 4. 核心设计

### 4.1 身份模型

```text
AuthProvider subject
  -> User
      -> Personal cloud projects
      -> TeamMember[]
          -> Team
              -> Team cloud projects
```

生产环境中，`User.email` 不再是唯一认证凭据本身，而是用户展示和邀请字段；真实身份由 `auth_identities.provider + subject` 绑定。开发态可以继续用固定 mock 用户，但必须通过配置显式开启。

### 4.2 租户范围

`TenantScope` 是后端服务层的通用输入，不是前端传来的过滤参数：

```text
TenantScope {
  actorUserId
  personalProjectOwnerId
  teamIds[]
  edition
  surface
}
```

任何 cloud 资源查询必须从 `TenantScope` 推导可见资源，不接受前端直接声明“我是某团队成员”。团队权限以数据库 `team_members` 为准。

### 4.3 本地版与云端版边界

| 场景 | 认证要求 | 数据范围 |
|------|---------|---------|
| Local Desktop 本机项目 | 不要求登录 | 本机后端数据库中的 local Project |
| Local Desktop 云项目入口 | 要求云登录 | 云后端中当前用户可见 cloud Project |
| SaaS Web | 要求云登录 | 当前用户个人和团队 cloud Project |
| Mobile | 要求云登录 | 当前用户可见 cloud Project、会话、通知、审批 |

---

## 5. 跨模块契约

### 5.1 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/auth/providers` | GET | 返回当前部署启用的登录方式 |
| `/api/auth/login` | POST | 开始登录；email/password 或外部 provider 均走同一入口 |
| `/api/auth/callback` | GET/POST | 外部 provider 回调 |
| `/api/auth/refresh` | POST | 刷新访问令牌或 session |
| `/api/auth/logout` | POST | 注销当前 session |
| `/api/auth/me` | GET | 返回当前用户、团队列表、默认空间 |
| `/api/projects` | GET | SaaS/Mobile 必须按 `TenantScope` 过滤；Local Desktop 只返回 local Project |
| `/api/teams` | GET | 只返回当前用户所属团队 |
| `/api/audit-logs` | GET | 只返回当前用户有权查看的团队或 Project 日志 |

### 5.2 后端服务契约

```python
class AuthProvider:
    async def resolve_request(self, request) -> AuthSubject | None: ...

class TenantScope:
    actor_user_id: str
    team_ids: list[str]
    edition: str
    surface: str

class TenantGuard:
    async def scope_for_user(self, user: User) -> TenantScope: ...
    async def assert_project_read(self, scope: TenantScope, project: Project) -> None: ...
    async def assert_project_write(self, scope: TenantScope, project: Project) -> None: ...
```

服务层不得绕过 `TenantGuard` 直接用 `project_id` 查询并返回 cloud 资源。

### 5.3 数据库变更

```sql
CREATE TABLE auth_identities (
  id VARCHAR PRIMARY KEY,
  user_id VARCHAR NOT NULL REFERENCES users(id),
  provider VARCHAR NOT NULL,
  subject VARCHAR NOT NULL,
  email VARCHAR,
  created_at DATETIME NOT NULL,
  last_login_at DATETIME,
  UNIQUE(provider, subject)
);

CREATE TABLE auth_sessions (
  id VARCHAR PRIMARY KEY,
  user_id VARCHAR NOT NULL REFERENCES users(id),
  refresh_token_hash TEXT NOT NULL,
  user_agent TEXT,
  ip_hash TEXT,
  expires_at DATETIME NOT NULL,
  revoked_at DATETIME,
  created_at DATETIME NOT NULL
);

ALTER TABLE users ADD COLUMN status VARCHAR NOT NULL DEFAULT 'active';
ALTER TABLE users ADD COLUMN last_login_at DATETIME;
```

如果采用外部托管认证，也必须保留 `auth_identities` 映射，保证 AgentHub 内部 RBAC 不依赖外部 provider 的临时字段。

---

## 6. UX 与前端状态

| 状态 | SaaS Web | Mobile | Local Desktop |
|------|----------|--------|---------------|
| 未登录 | 登录页，不加载工作台数据 | 登录页，不加载审批/通知 | 可进入本机项目；云入口显示登录 |
| 已登录无团队 | 个人空间 + 创建团队入口 | 个人项目/通知 | 本机项目 + 云项目切换入口 |
| 无权限 | 403 页面或弹窗，说明联系团队管理员 | 轻量 403 状态 | 不影响本机项目 |
| session 过期 | 自动 refresh，失败后回登录页 | 同左 | 云入口回登录，本机项目不受影响 |

---

## 7. 验收矩阵

| 验收项 | 方法 | 通过标准 |
|--------|------|---------|
| 生产 auth 禁用 dev header | API 测试 + 真实服务 | 生产配置下伪造 header 不会创建/切换用户 |
| 跨租户项目列表隔离 | API 测试 | 用户 A 看不到用户 B 的个人项目和团队外项目 |
| 详情越权拦截 | API 测试 | 读取他人 workspace/artifact/deployment 返回 403 或不可见 404 |
| 写操作权限 | API 测试 | viewer 不能写 workspace、部署、删除项目 |
| 三端登录态 | 真实服务 + 浏览器/移动壳 smoke | SaaS Web 与 Mobile 识别同一用户；Local Desktop 本机项目不要求登录 |
| 事件订阅隔离 | WebSocket/SSE 测试 | 用户只收到可见 Project 的事件 |
| 审计日志 | API 测试 | 登录、拒绝访问、团队成员变更写入 audit log |

---

## 8. 完成后的解锁项

- Phase 15 可以在可信租户边界内启动真实云 sandbox。
- Phase 16 可以按用户/团队权限发布真实公网 URL。
- SaaS Web 与 Mobile 可以共享生产用户系统和云 workspace。
- 桌面端可以作为“本机项目 + 可选云账号”的混合入口继续演进。

---

## 9. Phase 14 文档审计记录

**审计日期**: 2026-06-09

### 9.1 发现的问题

- Phase 14 实现已完成并通过人工验收，但本 Spec 仍标记为 `Planned`。
- `CONTEXT.md`、`AGENTS.md`、`CLAUDE.md` 与 `.trae/rules/project_rules.md` 的阶段感知仍停留在 Phase 13 或 Phase 14-16 规划期，未体现 Phase 14 已完成。
- Phase 14 缺少阶段开发日志入口。
- 全量 Markdown 断链扫描发现历史 planning 文档与 QA Skill 中存在过时相对链接。

### 9.2 已执行的修复

- 本文件状态更新为 `Completed`，并新增本审计记录。
- 新增 `docs/dev-logs/phase14-dev-log.md`，记录生产 Auth、TenantScope、RBAC 收口、前端登录门和测试覆盖。
- 更新 `CONTEXT.md` 阶段状态与开发日志索引；同步更新入口规则文档的阶段感知。
- 修复 QA Skill 与历史 planning 文档中的断链，并为 `.agents/skills/` 与 `.claude/skills/` 镜像追加 Phase 14 审计段落。

### 9.3 资产沉淀结论

- 本阶段无新增独立 Skill；生产 Auth 与租户隔离的可复用检查项已沉淀到现有 module-dev、code-review、qa-audit、phase-wrapup 四个 Skill。
- 本阶段无新增独立 Rule；“生产环境禁用开发请求头 auth、所有 cloud 资源经 TenantScope 过滤”已由本 Spec 与测试固化。
