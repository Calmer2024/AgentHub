# Phase 16：真实一键部署 Provider

**版本**: v0.1
**创建日期**: 2026-06-09
**状态**: Completed
**关联 ADR/PRD**: [AgentHub-多Agent协作平台设计](../../../AgentHub-多Agent协作平台设计.md)、[ADR-0010](../../../../archive/adr/0010-message-level-artifact-experience.md)、[PRD-03](../../../../PRD/03-User_Experience.md)、[PRD-05](../../../../PRD/05-End_to_End_Product_Flow.md)、[PRD-07](../../../../PRD/07-SaaS_Cloud_Workspace_Delivery.md)
**依赖模块**: Phase 11 Cloud Preview 与 Deployment、Phase 14 生产 Auth 与租户隔离收口、Phase 15 真实云 Sandbox Runtime

> Phase 16 把 Phase 11 的 preview/deployment 状态闭环替换为真实公网发布能力。用户从 Artifact Card 点击一次发布后，应得到可访问、可回滚、可审计的线上 URL。

---

## 1. 目标

Phase 11 已经建立 preview、deployment、日志、重试和回滚的数据契约，但当前 URL 与 pipeline 仍是开发态占位。Phase 16 的目标是接入真实部署 provider：把 cloud workspace 或 Artifact version 构建为可发布包，上传到托管目标，返回真实 HTTPS URL，并保留发布日志、版本绑定、权限、回滚和失败诊断。

**成功标准**（可证伪）：

- [ ] SaaS Web 中的 cloud Artifact 可以一键发布到真实 HTTPS URL，不再返回 `agenthub.local` 占位地址。
- [ ] 发布 pipeline 在真实 cloud runner 中执行 install/build/package/upload/publish/verify 阶段。
- [ ] Deployment 与 Artifact version 绑定；同一版本重复发布有幂等或冲突保护。
- [ ] 失败时返回阶段、日志、错误摘要和重试入口；成功后可复制、打开、回滚。
- [ ] 支持至少一个生产 provider：对象存储 + CDN、平台自托管静态站点，或第三方 hosting provider。
- [ ] 访问控制与租户权限一致：只有有权用户能创建、查看、回滚、撤销部署。
- [ ] Mobile 可以查看部署状态、打开 preview/deployment URL、处理需要人工批准的发布。
- [ ] P1 Local Desktop 的本地 build/export/preview 不被替换或强制上传云端。
- [ ] 不通过标准：只生成静态假 URL；或部署成功但公网不可访问；或任何用户可回滚他人部署。

---

## 2. 全局定位

```text
Phase 15 Real Cloud Runtime
  -> [Phase 16: DeploymentProvider + real hosting target + release lifecycle]
  -> 后续生产运维、计费、域名和企业治理
```

Phase 16 是 P2 SaaS “一键线上部署”的生产闭环。它只负责 AgentHub 产物的发布链路，不扩展为完整通用 CI/CD 平台。

---

## 3. 范围

### 3.1 必做

- 新增 `DeploymentProvider` 抽象，区分开发态 provider 与生产 provider。
- 至少接入一个真实 provider，优先支持静态 Web Artifact：对象存储 + CDN 或等价静态托管。
- 使用 Phase 15 runner 执行构建和打包，禁止在 API 服务器进程内执行用户构建脚本。
- Preview URL 与 Deployment URL 都必须是真实 HTTPS URL，并支持 TTL、撤销或访问策略。
- Deployment stage 事件和日志持续回传 Artifact Card。
- 回滚到上一成功 release；失败 release 不覆盖当前线上稳定版本。
- Provider 凭据作为 Secret 管理，按 team/project scope 注入，日志脱敏。
- 运维配置包含 provider endpoint、region、bucket/site、CDN、默认可见性、最大部署大小。

### 3.2 非目标

- 不实现完整域名购买和 DNS 托管平台；可以预留 custom domain 字段。
- 不实现计费与用量账单。
- 不支持所有后端服务类型；本阶段优先静态站点和前端应用构建产物。
- 不让 Local Desktop 的本地导出必须走云端 provider。

---

## 4. 核心设计

### 4.1 DeploymentProvider

```python
class DeploymentProvider:
    async def create_preview(self, request: PreviewRequest) -> PreviewResult: ...
    async def build_release(self, request: BuildReleaseRequest) -> ReleaseBundle: ...
    async def publish(self, bundle: ReleaseBundle, target: DeploymentTarget) -> PublishResult: ...
    async def rollback(self, deployment_id: str, target_release_id: str) -> PublishResult: ...
    async def revoke_preview(self, preview_id: str, reason: str | None = None) -> None: ...
```

`CloudDeliveryService` 只编排 provider，不直接耦合某个云厂商 SDK。

### 4.2 发布生命周期

```text
requested
  -> queued
  -> installing
  -> building
  -> packaging
  -> uploading
  -> publishing
  -> verifying
  -> published | failed | rolled_back
```

`published` 必须经过公网可达性或 provider verify 检查。失败后保留当前线上稳定 release，不做半成品覆盖。

### 4.3 Artifact 版本绑定

```text
Artifact
  -> ArtifactVersion
      -> ReleaseBundle
          -> Deployment
              -> DeploymentRelease[]
```

用户发布的是具体 Artifact version，而不是模糊的“当前 workspace”。如果用户在发布过程中继续修改 workspace，不影响正在发布的 release bundle。

---

## 5. 跨模块契约

### 5.1 API 端点

Phase 16 复用 Phase 11 的核心端点，并补充 provider/target 管理：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/deployment-providers` | GET | 返回当前租户可用 provider 和能力 |
| `/api/deployment-targets` | GET | 返回当前用户可见的发布目标 |
| `/api/deployment-targets` | POST | 创建 team/project 级发布目标 |
| `/api/artifacts/{artifactId}/previews` | POST | 创建真实 preview URL |
| `/api/deployments` | POST | 创建真实发布任务 |
| `/api/deployments/{deploymentId}` | GET | 查询部署状态、URL、版本、provider |
| `/api/deployments/{deploymentId}/logs` | GET | 查询构建/上传/发布日志 |
| `/api/deployments/{deploymentId}/retry` | POST | 从指定阶段重试失败部署 |
| `/api/deployments/{deploymentId}/rollback` | POST | 回滚到上一成功 release |
| `/api/deployments/{deploymentId}/revoke` | POST | 撤销公开访问或禁用当前部署 |

### 5.2 数据库变更

```sql
CREATE TABLE deployment_targets (
  id VARCHAR PRIMARY KEY,
  scope VARCHAR NOT NULL,
  owner_id VARCHAR NOT NULL,
  provider VARCHAR NOT NULL,
  name VARCHAR NOT NULL,
  config_json TEXT NOT NULL,
  status VARCHAR NOT NULL,
  created_by VARCHAR REFERENCES users(id),
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE TABLE deployment_releases (
  id VARCHAR PRIMARY KEY,
  deployment_id VARCHAR NOT NULL REFERENCES deployments(id),
  artifact_id VARCHAR NOT NULL REFERENCES artifacts(id),
  artifact_version_id VARCHAR NOT NULL,
  target_id VARCHAR NOT NULL REFERENCES deployment_targets(id),
  bundle_uri TEXT NOT NULL,
  public_url TEXT,
  status VARCHAR NOT NULL,
  provider_metadata_json TEXT NOT NULL,
  created_at DATETIME NOT NULL
);

ALTER TABLE deployments ADD COLUMN target_id VARCHAR REFERENCES deployment_targets(id);
ALTER TABLE deployments ADD COLUMN active_release_id VARCHAR;
ALTER TABLE deployments ADD COLUMN provider VARCHAR;
```

### 5.3 事件

| 事件类型 | payload |
|---------|---------|
| `deployment.requested` | `{ deploymentId, artifactId, artifactVersionId, targetId }` |
| `deployment.stage_changed` | `{ deploymentId, stage, status }` |
| `deployment.log` | `{ deploymentId, sequence, stream, text }` |
| `deployment.published` | `{ deploymentId, releaseId, url }` |
| `deployment.failed` | `{ deploymentId, stage, errorSummary }` |
| `deployment.rolled_back` | `{ deploymentId, activeReleaseId, url }` |
| `deployment.revoked` | `{ deploymentId, reason }` |

---

## 6. UX 行为

| 场景 | 用户看到 |
|------|---------|
| 首次发布 | Artifact Card 显示发布目标选择和“发布”主按钮 |
| 发布中 | 阶段进度、实时日志、当前 stage、取消入口 |
| 发布成功 | 线上 URL、复制、打开、回滚、查看日志 |
| 发布失败 | 错误摘要、失败阶段、日志、从失败阶段重试 |
| 无权限 | 全局权限弹窗或页面级错误，不显示可执行发布按钮 |
| Mobile 审批 | 审批卡片显示发布目标、Artifact version、风险摘要和预览 URL |

---

## 7. 安全与运维要求

| 风险 | 要求 |
|------|------|
| Provider 凭据泄漏 | 凭据通过 SecretService 注入，日志和事件脱敏 |
| 越权部署 | 创建、查看、回滚、撤销都必须经过 Phase 14 租户权限 |
| 半成品覆盖 | verify 失败不能切换 active release |
| 公网暴露错误内容 | private/team visibility 必须执行访问控制或签名 URL |
| 部署资源滥用 | 限制 bundle 大小、构建时长、并发部署数 |
| URL 健康 | published 前必须执行 provider verify 或 HTTP 可达性检查 |

---

## 8. 验收矩阵

| 验收项 | 方法 | 通过标准 |
|--------|------|---------|
| 真实公网 URL | 真实服务 E2E | 发布后返回 HTTPS URL，浏览器可访问真实内容 |
| 构建运行位置 | 日志与进程检查 | 构建发生在 Phase 15 runner，不在 API 服务器 |
| 版本绑定 | API + UI | 发布固定 Artifact version，后续 workspace 修改不影响该 release |
| 失败诊断 | 故障注入 | 构建失败返回 stage、日志、错误摘要，可重试 |
| 回滚 | E2E | 回滚后线上 URL 指向上一成功 release |
| 权限隔离 | API 测试 | 无权限用户不能查看、发布、回滚他人部署 |
| Mobile 审批 | 移动壳 smoke | 移动端可审批发布并查看最终 URL |
| P1 零回归 | 三端验收 | Local Desktop 本地 preview/export/build 仍可用 |

---

## 9. 完成后的解锁项

- SaaS Web 获得生产级一键线上部署能力。
- Mobile 可以参与真实发布审批和发布状态跟踪。
- AgentHub 的 P2 交付链路从“云端生成产物”闭环到“公网可访问 URL”。
- 后续可以在此基础上扩展自定义域名、访问统计、计费与企业治理。

---

## 10. 归档状态

2026-06-20：Phase 16 已完成并归档。本文保留历史规格、验收矩阵和设计边界，后续产品优化不再以 Phase 流程推进。
