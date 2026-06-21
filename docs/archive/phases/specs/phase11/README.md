# Phase 11：Cloud Preview 与 Deployment

**版本**: v1.1
**创建日期**: 2026-06-08
**状态**: Completed
**关联 ADR/PRD**: [AgentHub-多Agent协作平台设计](../../../AgentHub-多Agent协作平台设计.md)、[ADR-0010](../../../../adr/0010-message-level-artifact-experience.md)、[PRD-03](../../../../PRD/03-User_Experience.md)、[PRD-05](../../../../PRD/05-End_to_End_Product_Flow.md)、[PRD-06](../../../../PRD/06-MVP_Local_Workspace_Delivery.md)、[PRD-07](../../../../PRD/07-SaaS_Cloud_Workspace_Delivery.md)
**依赖模块**: Phase 9 Cloud Workspace Foundation、Phase 10 Sandbox Runner 与 Cloud Agent Runtime、Phase 8 Build/Export/Preview baseline

> Phase 11 把 P2 的 Artifact 交付从“云端执行后有文件”推进到“可打开 preview URL、可批准发布、可查看部署日志和最终 URL”。它不负责多端通知和团队协作评论。

---

## 1. 目标

Phase 11 解决云端产物的外部可访问性和发布闭环。目标用户是 SaaS 版中通过 Agent 生成 Web Artifact 的用户：他们需要从聊天流中直接打开云端预览，确认后发布到公开或受限访问 URL，并在失败时看到部署阶段、日志、恢复路径和回滚入口。

本阶段必须延续消息级 Artifact 体验：Preview Card 和 Deployment Card 跟随具体 assistant 消息，不恢复独立右侧 Drawer。Phase 11 的部署能力是 P2 核心能力，和 Phase 8 的 P1 本地导出能力不同。

**成功标准**（可证伪）：

- [ ] Agent 生成的 Web Artifact 能生成带鉴权和 TTL 的 cloud preview URL。
- [ ] Preview 支持静态目录、构建产物目录、dev server 代理三种来源。
- [ ] 用户批准后可创建 Deployment，前端显示 queued/install/build/upload/published/failed 阶段。
- [ ] Deployment 成功后返回最终 URL，并与 Artifact 版本绑定。
- [ ] Deployment 失败时有日志、错误摘要、重试和回滚路径。
- [ ] P1 本地 preview/export/build 能力继续可用，不被 cloud preview/deploy 替换或隐藏。
- [ ] 本阶段 SaaS 最小可运行切片为：cloud Artifact → preview URL → deployment job → stage 事件 → published/failed 终态。
- [ ] 不通过标准：只给出本地 localhost 链接，或部署状态只做静态 UI 不接真实事件。

---

## 2. 全局定位

### 2.1 北极星链路位置

```text
Phase 10 cloud Agent modifies workspace
  → [Phase 11: Cloud preview URL + Deployment pipeline + Deployment Card]
  → Phase 12 collaboration / mobile approval / advanced artifacts
```

### 2.2 上下游契约

| 方向 | 模块/事件/API | 本模块的角色 |
|------|-------------|------------|
| **上游输入** | Phase 10 workspace files、build artifacts、Artifact metadata | 为可交付产物创建 preview 和 deployment |
| **上游输入** | ApprovalService、Artifact version、SecretProvider | 发布前审批、版本绑定、部署密钥注入 |
| **下游产出** | preview URL、deployment URL、deploy logs、deployment events | Artifact Card、Deployment Card、后续移动端通知消费 |
| **本模块不通** | 团队评论、移动端推送、PPT/文档高级浏览 | Phase 12 负责 |

### 2.3 双运行时兼容门禁

Phase 11 的 cloud preview/deploy 是 P2 新能力，不替代 P1 本地交付能力：

- local Project 的 preview 仍可使用 localhost 或本地服务地址，export 仍可生成本地包。
- cloud Project 的 preview 必须返回非 localhost 的 cloud URL，并带鉴权、TTL 或 revoke 能力。
- ArtifactCard 操作区可以扩展 DeploymentCard，但不得恢复右侧 Drawer，也不得移除 P1 本地预览/导出入口。
- 阶段完成报告必须同时列出 P1 local build/preview/export 回归结果和 Phase 11 cloud preview/deploy 真实服务结果。

---

## 3. 跨模块契约

### 3.1 API 端点

| 端点 | 方法 | 请求体 | 成功响应 | 错误响应 |
|------|------|--------|---------|---------|
| `/api/artifacts/{artifactId}/previews` | POST | `{ "source": "static" \| "build" \| "dev_server", "artifactVersionId"?: string, "ttlSeconds"?: number }` | `201: PreviewSession` | `400` / `403` / `404` |
| `/api/previews/{previewId}` | GET | 无 | `200: PreviewSession` | `403` / `404` / `410` expired |
| `/api/previews/{previewId}/revoke` | POST | `{ "reason"?: string }` | `202: { "status": "revoked" }` | `403` / `404` |
| `/api/deployments` | POST | `{ "artifactId": string, "artifactVersionId": string, "target": "static_hosting" \| "third_party", "visibility": "public" \| "team" \| "private" }` | `202: Deployment` | `400` / `403` / `409` |
| `/api/deployments/{deploymentId}` | GET | 无 | `200: Deployment` | `403` / `404` |
| `/api/deployments/{deploymentId}/logs` | GET | 无 | `200: { "chunks": DeploymentLogChunk[] }` | `403` / `404` |
| `/api/deployments/{deploymentId}/retry` | POST | `{ "fromStage"?: string }` | `202: Deployment` | `400` / `403` / `409` |
| `/api/deployments/{deploymentId}/rollback` | POST | `{ "targetDeploymentId": string }` | `202: Deployment` | `400` / `403` / `404` |

### 3.2 事件

| 事件类型 | 方向 | payload 字段 |
|---------|------|-------------|
| `preview.created` | PreviewService → EventBus | `{ previewId, artifactId, url, expiresAt, visibility }` |
| `preview.revoked` | PreviewService → EventBus | `{ previewId, reason }` |
| `deployment.queued` | DeployService → EventBus | `{ deploymentId, artifactId, target }` |
| `deployment.stage_changed` | DeployService → EventBus | `{ deploymentId, stage, status }` |
| `deployment.log` | DeployService → EventBus | `{ deploymentId, sequence, stream, text }` |
| `deployment.published` | DeployService → EventBus | `{ deploymentId, url, artifactVersionId }` |
| `deployment.failed` | DeployService → EventBus | `{ deploymentId, stage, errorSummary }` |
| `deployment.rolled_back` | DeployService → EventBus | `{ deploymentId, targetDeploymentId, url }` |

### 3.3 数据库 Schema 变更

```sql
CREATE TABLE preview_sessions (
  id VARCHAR PRIMARY KEY,
  artifact_id VARCHAR NOT NULL REFERENCES artifacts(id),
  artifact_version_id VARCHAR,
  workspace_id VARCHAR NOT NULL REFERENCES workspaces(id),
  source VARCHAR NOT NULL,
  status VARCHAR NOT NULL,
  url TEXT NOT NULL,
  visibility VARCHAR NOT NULL,
  expires_at DATETIME,
  created_by VARCHAR REFERENCES users(id),
  created_at DATETIME NOT NULL
);

CREATE TABLE deployments (
  id VARCHAR PRIMARY KEY,
  artifact_id VARCHAR NOT NULL REFERENCES artifacts(id),
  artifact_version_id VARCHAR NOT NULL,
  project_id VARCHAR NOT NULL REFERENCES projects(id),
  target VARCHAR NOT NULL,
  visibility VARCHAR NOT NULL,
  status VARCHAR NOT NULL,
  stage VARCHAR NOT NULL,
  url TEXT,
  error_summary TEXT,
  created_by VARCHAR REFERENCES users(id),
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE TABLE deployment_logs (
  id VARCHAR PRIMARY KEY,
  deployment_id VARCHAR NOT NULL REFERENCES deployments(id),
  sequence INTEGER NOT NULL,
  stream VARCHAR NOT NULL,
  text TEXT NOT NULL,
  created_at DATETIME NOT NULL
);
```

### 3.4 跨组件 TypeScript 类型（前端）

```typescript
interface PreviewSession {
  id: string
  artifactId: string
  artifactVersionId?: string
  source: 'static' | 'build' | 'dev_server'
  status: 'creating' | 'ready' | 'expired' | 'revoked' | 'failed'
  url: string
  visibility: 'public' | 'team' | 'private'
  expiresAt?: string
}

interface Deployment {
  id: string
  artifactId: string
  artifactVersionId: string
  target: 'static_hosting' | 'third_party'
  visibility: 'public' | 'team' | 'private'
  status: 'queued' | 'running' | 'published' | 'failed' | 'rolled_back'
  stage: 'queued' | 'install' | 'build' | 'upload' | 'publish' | 'verify'
  url?: string
  errorSummary?: string
}
```

---

## 4. 行为规格

### 4.1 正常流程

```
1. Agent 在 cloud workspace 生成 Web Artifact → Artifact Card 出现在消息流。
2. 用户点击预览 → PreviewService 为 artifact/version 创建 preview session → 返回 preview URL。
3. 用户在 preview 中确认结果 → 点击发布 → DeploymentService 创建 deployment queued。
4. DeployService 依次执行 install/build/upload/publish/verify → 通过事件更新 Deployment Card。
5. 成功后返回最终 URL → Deployment Card 显示打开、复制、回滚入口。
6. 失败时保留日志和 stage → 用户可从失败阶段重试或回滚到上一成功版本。
```

### 4.2 UX 六态覆盖

| 状态 | 用户看到什么 | 触发条件 |
|------|------------|---------|
| **空态** (Empty) | Artifact 尚无 preview/deployment 时显示预览和发布入口 | 新 Artifact |
| **加载态** (Loading) | Preview 创建中、Deployment 阶段进度条和日志流 | preview/deploy running |
| **正常态** (Normal) | Preview iframe/新窗口入口、Deployment Card 阶段状态 | preview ready / deployment running |
| **完成态** (Complete) | Published URL、复制链接、回滚入口 | deployment.published |
| **错误态** (Error) | 失败阶段、错误摘要、日志、重试按钮 | preview/deploy failed |
| **边界态** (Edge) | URL 过期、权限不足、重复发布、构建目录缺失、部署 secret 缺失 | expired/403/409 |

### 4.3 错误处理

| 错误场景 | 错误码 | 用户可见文案 | 恢复路径 |
|---------|--------|------------|---------|
| Preview 已过期 | 410 | 预览链接已过期 | 重新生成预览 |
| Artifact 版本不存在 | 404 | 该产物版本不存在 | 返回版本列表 |
| 部署 secret 缺失 | 400 | 发布目标缺少必要密钥 | 打开 Secret 设置 |
| 构建失败 | deployment.failed | 发布构建失败 | 查看日志并重试 |
| 重复部署冲突 | 409 | 当前版本已有部署任务运行中 | 查看当前部署 |
| 权限不足 | 403 | 你没有发布该项目的权限 | 联系项目管理员 |

---

## 5. 前端页面设计

### 5.1 页面布局

```text
┌──────────────────────────────────────────────────────────────┐
│ ChatWorkspace                                                │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ MessageList                                              │ │
│ │  ├─ ArtifactCard                                         │ │
│ │  │   ├─ Preview actions                                  │ │
│ │  │   └─ DeploymentCard                                   │ │
│ │  └─ ApprovalCard (发布前确认，可选)                       │ │
│ └──────────────────────────────────────────────────────────┘ │
│ PreviewModal / DeploymentLogModal                           │
└──────────────────────────────────────────────────────────────┘
```

PreviewModal 可使用 iframe 但必须有固定高度、加载态和错误态；DeploymentLogModal 使用页面级 overlay，不嵌套在 ArtifactCard 内。

### 5.2 组件树

```text
ArtifactCard
├── PreviewActionGroup
│   ├── CreatePreviewButton
│   └── OpenPreviewButton
├── DeploymentCard
│   ├── DeploymentStageStepper
│   ├── DeploymentUrlActions
│   └── DeploymentErrorActions
├── PreviewModal
└── DeploymentLogModal
```

### 5.3 关键视觉元素

| 元素 | 位置 | 视觉规格 |
|------|------|---------|
| PreviewActionGroup | ArtifactCard 操作区 | eye/external-link 图标按钮，hover 显示 tooltip |
| DeploymentStageStepper | DeploymentCard | 水平紧凑步骤，当前步骤用品牌色细线，不使用大面积渐变 |
| Published URL | DeploymentCard 完成态 | 单行可复制链接，open/copy 图标按钮 |
| DeploymentLogModal | 页面级 overlay | 日志等宽字体，stage filter 使用 tabs |

---

## 6. 前端交互序列

### 6.1 创建预览

```
用户: 在 ArtifactCard 点击预览
  → 前端: POST /api/artifacts/{artifactId}/previews
  → 后端: PreviewService 创建 preview session
  → SSE/WebSocket: preview.created
  → 前端: 打开 PreviewModal 或新窗口，显示 URL 和过期时间
```

### 6.2 发布部署

```
用户: 在 ArtifactCard 点击发布
  → 前端: 显示发布确认，选择 visibility/target
  → 前端: POST /api/deployments
  → 后端: DeployService 排队并发布 deployment.stage_changed
  → 前端: DeploymentCard 实时更新阶段和日志入口
  → 后端: deployment.published
  → 前端: 显示最终 URL、复制、打开、回滚按钮
```

### 6.3 部署失败重试

```
用户: 打开失败 DeploymentCard
  → 前端: 展示失败阶段和日志摘要
  → 用户: 点击从失败阶段重试
  → 前端: POST /api/deployments/{deploymentId}/retry
  → 后端: 从指定 stage 重新进入 pipeline
  → 前端: Card 从 failed 变为 running
```

---

## 7. 验收标准

- [ ] AC-P11-01: cloud Web Artifact 可以创建 preview session，并返回非 localhost 的 preview URL。
- [ ] AC-P11-02: preview URL 支持鉴权、TTL 和 revoke，过期后返回 410。
- [ ] AC-P11-03: Preview 支持 static/build/dev_server 三种 source，非法 source 返回 400。
- [ ] AC-P11-04: 创建 deployment 后，Deployment Card 按 stage 实时更新。
- [ ] AC-P11-05: deployment.published 后返回最终 URL，并绑定 artifactVersionId。
- [ ] AC-P11-06: 部署失败时可查询日志、显示失败阶段、重试。
- [ ] AC-P11-07: 用户权限不足时不能创建 preview/deployment。
- [ ] AC-P11-08: Artifact Card 仍是消息级体验，不引入右侧 Drawer。
- [ ] AC-P11-09: P1 local build、localhost preview、export zip/source bundle 真实服务回归通过。
- [ ] AC-P11-10: Phase 11 cloud slice 在真实服务上完成 preview URL 创建、deployment stage 事件、published 或 failed 终态展示。

---

## 8. 测试策略

### 8.1 单元测试（38 条）

| 测试对象 | 条数 | 覆盖内容 |
|---------|------|---------|
| PreviewService | 10 | source 校验、TTL、revoke、权限、URL 生成 |
| DeployService | 12 | stage 状态机、成功、失败、重试、回滚 |
| DeploymentLogService | 5 | 日志序列、过滤、脱敏 |
| DeploymentPermissionService | 5 | owner/admin/member/viewer 权限 |
| ArtifactDeploymentMapper | 6 | artifact/version/deployment 绑定 |

### 8.2 集成测试

- Fake hosting provider：创建 deployment，模拟每个 stage，验证事件和 DB。
- Preview auth：不同用户访问 public/team/private preview。
- Deployment failure：build stage 失败后日志可查询，retry 后成功。

### 8.3 E2E 测试

- 浏览器生成 preview，打开 PreviewModal，确认 iframe 非空。
- 点击发布，观察 Deployment Card 从 queued 到 published。
- 模拟失败部署，查看日志并重试。

### 8.4 P1/P2 兼容门禁

- P1 local 回归：对本地 Artifact 执行 build、preview、export，确认 local URL 和导出包不依赖 CloudWorkspaceProvider。
- P2 cloud slice：对 cloud Artifact 创建 preview 和 deployment，确认 URL 非 localhost，deployment stage 事件驱动 DeploymentCard。
- 多端视口：桌面宽度验证 PreviewModal/DeploymentLogModal；移动宽度验证 preview/deploy 链接可查看或明确提示需在 Web 打开。

---

## 9. 架构约束追溯

| 本模块的决策 | 依据 |
|------------|------|
| P2 支持云端 preview URL 与一键部署 | [PRD-00](../../../../PRD/00-Master_Hub.md)、[PRD-07](../../../../PRD/07-SaaS_Cloud_Workspace_Delivery.md) |
| Artifact 体验仍跟随消息级卡片 | [ADR-0010](../../../../adr/0010-message-level-artifact-experience.md) |
| 端到端闭环包含 preview/edit/version/approval/summary | [PRD-05](../../../../PRD/05-End_to_End_Product_Flow.md) |
| P1 本地导出与 P2 公网发布边界不同 | [PRD-06](../../../../PRD/06-MVP_Local_Workspace_Delivery.md)、[PRD-07](../../../../PRD/07-SaaS_Cloud_Workspace_Delivery.md) |

---

## 10. 依赖

| 依赖模块 | 需要的接口 | 当前状态 |
|---------|-----------|---------|
| Phase 10 Sandbox/Runtime | build output、workspace files、artifact detection | ✅ 已就绪（开发态 runner + 真实 CLI + Artifact/logs 契约） |
| Phase 9 Cloud Workspace | workspaceId、storage_uri、RBAC | ✅ 已就绪（元数据基座；真实 preview/deploy 产物存储由 Phase 11 接入） |
| ArtifactService | artifact/version metadata | ✅ P1 基线 |
| SecretProvider | deploy target secrets | ✅ Phase 10 已提供开发态 Secret 存储/注入/脱敏；生产 KMS 后续替换 |
| Hosting provider adapter | static hosting publish/revoke | ❌ 未开始 |

---

## 11. Non-Goals（明确不做什么）

| 不做的事 | 原因 | 由谁负责 |
|---------|------|---------|
| 团队评论和通知 | 协作体验阶段 | Phase 12 |
| 移动端 preview UI | 多端阶段 | Phase 12 |
| Docker/application deploy 全量能力 | 第一版先 static/third-party | 后续部署增强 |
| 域名市场和复杂证书管理 | 超出第一版发布闭环 | 后续平台阶段 |
| 恢复右侧 Artifact Drawer | 已被 ADR-0010 否决 | 永不恢复为 P1/P2 主体验 |

---

## 12. 破坏性变更与迁移

| 维度 | V1 行为 | V2 行为 | 迁移路径 |
|------|--------|--------|---------|
| Preview URL | P1 localhost preview | P2 cloud preview URL + TTL + auth | 前端按 workspaceMode 选择 provider，ArtifactCard 操作不变 |
| Deploy 能力 | P1 无一键公网部署 | P2 DeploymentService 核心能力 | 新增 DeploymentCard，不影响本地导出 |
| Artifact Card | 仅预览/编辑/版本 | 增加 preview/deploy 状态 | 扩展现有 MessageArtifactStrip |

> **版本历史**
> - v1.2 (2026-06-09): 根据 Phase 11 实现与验收结果，将状态更新为 Completed；完整实现以当前代码和验收记录为准。
> - v1.1 (2026-06-08): 增加 P1 本地交付能力零回归与 Phase 11 cloud preview/deploy 可运行切片门禁。
> - v1.0 (2026-06-08): 按 `SPEC_TEMPLATE.md` 创建 Phase 11 独立 Spec。
