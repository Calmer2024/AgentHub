# Phase 12：协作、多端与高级 Artifact

**版本**: v1.1
**创建日期**: 2026-06-08  
**状态**: Draft  
**关联 ADR/PRD**: [AgentHub-多Agent协作平台设计](../../archive/AgentHub-多Agent协作平台设计.md)、[ADR-0009](../../adr/0009-project-workspace-model.md)、[ADR-0010](../../adr/0010-message-level-artifact-experience.md)、[ADR-0011](../../adr/0011-agent-engine-skill-model.md)、[PRD-03](../../PRD/03-User_Experience.md)、[PRD-05](../../PRD/05-End_to_End_Product_Flow.md)、[PRD-07](../../PRD/07-SaaS_Cloud_Workspace_Delivery.md)  
**依赖模块**: Phase 9 Cloud Workspace + Team/RBAC、Phase 10 Cloud Agent Runtime、Phase 11 Cloud Preview/Deployment

> Phase 12 补齐早期核心设计中的团队协作、多端触达和多类型 Artifact 能力。它建立在 P2 云端 workspace、sandbox runtime 和 preview/deploy 已经可用的基础上。

---

## 1. 目标

Phase 12 解决 AgentHub 从“单人云端 Agent 工作台”走向“团队多端协作平台”的体验缺口。目标用户包括团队成员、审批者、移动端轻量用户和需要处理多类型产物的使用者。他们需要共享 Project、评论和审计关键变更，在移动端查看运行状态和审批，在聊天中上传文件/图片作为上下文，浏览 PPT/文档类 Artifact，并把部署结果、Artifact 和 Agent 模板在团队内流转。

本阶段不改变 Phase 9-11 的底层运行架构，而是在其上补齐协作对象、通知对象、附件对象、高级 Artifact 对象和对话式 Agent 创建流程。

**成功标准**（可证伪）：

- [ ] 团队成员可按权限访问共享 Project，并对消息、Artifact、Deployment 添加评论或引用。
- [ ] Web 为完整工作台，Mobile 至少支持 IM、运行状态、审批、Artifact/Preview 查看和通知。
- [ ] 用户可上传文件/图片并作为 Agent 上下文，上传内容有权限、大小、类型和安全校验。
- [ ] PPT/文档类 Artifact 可浏览、版本化、导出，并可被消息引用。
- [ ] Artifact 可转发并保留级联引用关系，不只转发文本快照。
- [ ] 用户可通过对话创建或调整 Agent 模板，最终仍落到 Agent = System Prompt + Rules + Toolset + Runtime Config + Engine。
- [ ] P1 本机 IM、未读/免打扰、消息级 Artifact、local runtime 和本地导出能力继续可用，不被 SaaS 通知/协作模型覆盖。
- [ ] 本阶段 SaaS 最小可运行切片为：Web/Mobile 查看同一 cloud Project、审批/通知状态同步、preview/deployment 链接可查看。
- [ ] 不通过标准：只做社交 UI，不接权限/审计/真实 Artifact 引用；或移动端只展示营销页。

---

## 2. 全局定位

### 2.1 北极星链路位置

```text
Phase 11 cloud preview/deploy
  → [Phase 12: team collaboration + mobile approval/preview + attachments + advanced artifacts + conversational agent creation]
  → 后续企业化/市场化阶段
```

### 2.2 上下游契约

| 方向 | 模块/事件/API | 本模块的角色 |
|------|-------------|------------|
| **上游输入** | Team/RBAC、Workspace、Runtime、Preview/Deployment | 在已可运行和发布的 Project 上增加协作与多端 |
| **上游输入** | Message、Artifact、Agent Profile、Deployment metadata | 为评论、附件、转发、通知、Agent 创建提供对象关系 |
| **下游产出** | notifications、comments、attachments、artifact references、mobile views | Web/Mobile UI、审计日志、后续企业能力消费 |
| **本模块不通** | 复杂 marketplace、企业 SSO、计费、实时多人代码编辑 | 后续企业化阶段 |

### 2.3 双运行时与多端兼容门禁

Phase 12 是多端协作阶段，但不能把移动端或团队协作误做成新的主运行时：

- Web 端继续是完整生产力工作台；Mobile 只消费云端 API，不能依赖本机文件系统、PTY 或 CLI 权限。
- P1 本机版继续使用已有 IM 未读、免打扰、会话置顶/归档和消息级 Artifact 体验；SaaS NotificationService 只在 cloud/team 场景启用或作为兼容增强。
- MobileApprovalCard 调用现有 ApprovalService，不创建一套移动端专用审批状态机。
- 阶段完成报告必须同时列出 P1 local IM/runtime 回归结果、Phase 12 Web cloud 协作结果和 MobileShell/移动视口结果。

---

## 3. 跨模块契约

### 3.1 API 端点

| 端点 | 方法 | 请求体 | 成功响应 | 错误响应 |
|------|------|--------|---------|---------|
| `/api/projects/{projectId}/comments` | POST | `{ "targetType": "message" \| "artifact" \| "deployment", "targetId": string, "body": string }` | `201: Comment` | `400` / `403` / `404` |
| `/api/projects/{projectId}/comments` | GET | `targetType`/`targetId` query | `200: { "items": Comment[] }` | `403` |
| `/api/attachments` | POST | `multipart/form-data file + projectId + sessionId?` | `201: Attachment` | `400` / `403` / `415` |
| `/api/messages/{messageId}/forward` | POST | `{ "targetSessionIds": string[], "includeArtifacts": boolean }` | `201: { "messages": Message[] }` | `400` / `403` |
| `/api/notifications` | GET | 无 | `200: { "items": Notification[] }` | `401` |
| `/api/notifications/{notificationId}/read` | POST | 无 | `204` | `404` |
| `/api/mobile/sessions` | GET | 无 | `200: MobileSessionSummary[]` | `401` |
| `/api/mobile/approvals/{approvalId}/decision` | POST | `{ "decision": "approve" \| "reject", "comment"?: string }` | `202: Approval` | `400` / `403` |
| `/api/artifacts/{artifactId}/render` | GET | `format=html|pdf|image` | `200: RenderedArtifact` | `400` / `404` |
| `/api/agent-template-sessions` | POST | `{ "seedPrompt": string }` | `201: AgentTemplateSession` | `400` |
| `/api/agent-template-sessions/{id}/finalize` | POST | `{ "name": string, "engine": string }` | `201: Agent` | `400` |
| `/api/projects/{projectId}/git/sync` | POST | `{ "remote": string, "branch": string, "mode": "pull" \| "push" }` | `202: GitSyncJob` | `400` / `403` / `409` |

### 3.2 事件

| 事件类型 | 方向 | payload 字段 |
|---------|------|-------------|
| `comment.created` | CommentService → EventBus | `{ commentId, projectId, targetType, targetId, authorId }` |
| `attachment.created` | AttachmentService → EventBus | `{ attachmentId, projectId, mimeType, sizeBytes }` |
| `message.forwarded` | MessageService → EventBus | `{ sourceMessageId, targetMessageIds, includeArtifacts }` |
| `notification.created` | NotificationService → EventBus | `{ notificationId, userId, type, resourceId }` |
| `artifact.rendered` | ArtifactRenderService → EventBus | `{ artifactId, format, renderId }` |
| `agent_template.finalized` | AgentTemplateService → EventBus | `{ sessionId, agentId, engine }` |
| `git.sync.completed` | GitService → EventBus | `{ projectId, jobId, mode, commitSha? }` |

### 3.3 数据库 Schema 变更

```sql
CREATE TABLE comments (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL REFERENCES projects(id),
  target_type VARCHAR NOT NULL,
  target_id VARCHAR NOT NULL,
  author_user_id VARCHAR NOT NULL REFERENCES users(id),
  body TEXT NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE TABLE attachments (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL REFERENCES projects(id),
  session_id VARCHAR REFERENCES sessions(id),
  uploaded_by VARCHAR NOT NULL REFERENCES users(id),
  filename VARCHAR NOT NULL,
  mime_type VARCHAR NOT NULL,
  size_bytes INTEGER NOT NULL,
  storage_uri TEXT NOT NULL,
  created_at DATETIME NOT NULL
);

CREATE TABLE artifact_references (
  id VARCHAR PRIMARY KEY,
  source_type VARCHAR NOT NULL,
  source_id VARCHAR NOT NULL,
  artifact_id VARCHAR NOT NULL REFERENCES artifacts(id),
  artifact_version_id VARCHAR,
  relation VARCHAR NOT NULL,
  created_at DATETIME NOT NULL
);

CREATE TABLE notifications (
  id VARCHAR PRIMARY KEY,
  user_id VARCHAR NOT NULL REFERENCES users(id),
  type VARCHAR NOT NULL,
  resource_type VARCHAR NOT NULL,
  resource_id VARCHAR NOT NULL,
  title VARCHAR NOT NULL,
  body TEXT,
  read_at DATETIME,
  created_at DATETIME NOT NULL
);

CREATE TABLE agent_template_sessions (
  id VARCHAR PRIMARY KEY,
  created_by VARCHAR NOT NULL REFERENCES users(id),
  status VARCHAR NOT NULL,
  draft_json TEXT NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE TABLE git_sync_jobs (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL REFERENCES projects(id),
  mode VARCHAR NOT NULL,
  remote TEXT NOT NULL,
  branch VARCHAR NOT NULL,
  status VARCHAR NOT NULL,
  commit_sha VARCHAR,
  error_summary TEXT,
  created_at DATETIME NOT NULL
);
```

### 3.4 跨组件 TypeScript 类型（前端）

```typescript
interface Comment {
  id: string
  projectId: string
  targetType: 'message' | 'artifact' | 'deployment'
  targetId: string
  authorUserId: string
  body: string
  createdAt: string
}

interface Attachment {
  id: string
  projectId: string
  sessionId?: string
  filename: string
  mimeType: string
  sizeBytes: number
  createdAt: string
}

interface Notification {
  id: string
  type: 'approval' | 'mention' | 'deployment' | 'comment' | 'run_failed'
  resourceType: string
  resourceId: string
  title: string
  body?: string
  readAt?: string
}

interface MobileSessionSummary {
  id: string
  projectId: string
  title: string
  unreadCount: number
  latestMessageAt?: string
  pendingApprovalCount: number
}
```

---

## 4. 行为规格

### 4.1 正常流程

```
1. 用户在团队 Project 中 @ 成员或评论 Artifact → CommentService 校验权限并创建 comment → NotificationService 通知目标用户。
2. 用户上传图片或文件 → AttachmentService 存储并生成 Attachment → ChatInput 可把 attachment 引入下一条 Agent prompt。
3. 用户转发带 Artifact 的消息 → MessageService 创建目标消息和 artifact_references → 目标会话显示可追踪 Artifact Card。
4. 移动端用户收到审批通知 → 打开 MobileApprovalView → approve/reject 调用现有 ApprovalService。
5. 用户打开 PPT/文档 Artifact → ArtifactRenderService 生成 HTML/PDF/image render → 前端浏览并可导出。
6. 用户用自然语言创建 Agent → AgentTemplateSession 逐步生成 System Prompt、Rules、Toolset、Runtime Config → finalize 后创建 Agent。
7. 用户触发 Git sync → GitService 在 workspace 中执行 pull/push → 记录 job、日志和通知。
```

### 4.2 UX 六态覆盖

| 状态 | 用户看到什么 | 触发条件 |
|------|------------|---------|
| **空态** (Empty) | 无评论、无通知、无附件时显示紧凑空态和主操作入口 | 列表为空 |
| **加载态** (Loading) | 上传、渲染、Git sync、Agent 模板生成显示进度 | job running |
| **正常态** (Normal) | 评论线程、附件卡片、通知列表、移动端会话、文档浏览正常展示 | 数据加载成功 |
| **完成态** (Complete) | 上传完成、审批完成、Agent 创建完成、Git sync 完成提示 | 操作完成 |
| **错误态** (Error) | 文件类型不支持、渲染失败、权限不足、Git 冲突显示恢复路径 | 4xx/5xx/job failed |
| **边界态** (Edge) | 大文件、重复通知、离线移动端、Artifact 引用链过深、Git 冲突 | 边界条件 |

### 4.3 错误处理

| 错误场景 | 错误码 | 用户可见文案 | 恢复路径 |
|---------|--------|------------|---------|
| 文件类型不支持 | 415 | 当前文件类型暂不支持 | 更换文件或压缩后上传 |
| 文件过大 | 400 | 文件超过当前项目限制 | 压缩文件或联系管理员 |
| 评论目标不存在 | 404 | 目标内容不存在或已删除 | 返回会话 |
| 移动端审批已处理 | 409 | 该审批已被处理 | 刷新状态 |
| 文档渲染失败 | render.failed | 文档渲染失败 | 下载原文件或重试 |
| Git 冲突 | git.conflict | 同步时出现冲突 | 打开冲突详情并选择策略 |
| Agent 模板不完整 | 400 | Agent 配置缺少必要字段 | 回到模板对话继续补充 |

---

## 5. 前端页面设计

### 5.1 页面布局

```text
Web
┌───────────────┬──────────────────┬────────────────────────────────────┐
│ ProjectSidebar │ SessionSidebar   │ ChatWorkspace                      │
│ Team/Notify    │                  │ MessageList + Artifact/Comments    │
│               │                  │ ChatInput + AttachmentTray         │
└───────────────┴──────────────────┴────────────────────────────────────┘

Mobile
┌──────────────────────────────┐
│ MobileSessionList            │
├──────────────────────────────┤
│ MobileChatView               │
│ ApprovalCard / PreviewLink   │
└──────────────────────────────┘
```

Web 继续保持生产力工具布局；Mobile 不做完整 IDE，只保留 IM、审批、状态、预览和通知。

### 5.2 组件树

```text
App
├── WebShell
│   ├── NotificationCenter
│   ├── CommentThreadPanel
│   ├── AttachmentTray
│   ├── AdvancedArtifactViewer
│   ├── AgentTemplateWizard
│   └── GitSyncPanel
└── MobileShell
    ├── MobileSessionList
    ├── MobileChatView
    ├── MobileApprovalCard
    └── MobilePreviewView
```

### 5.3 关键视觉元素

| 元素 | 位置 | 视觉规格 |
|------|------|---------|
| NotificationCenter | WebShell 顶部/侧边入口 | bell 图标，未读数小圆点，列表密集展示 |
| CommentThreadPanel | Artifact/Message 操作区 | 右侧页面级 panel，不覆盖主消息输入 |
| AttachmentTray | ChatInput 上方 | 文件 chip，mime 图标，上传进度细条 |
| AdvancedArtifactViewer | 页面级 Modal | PPT/文档分页浏览，顶部工具栏含导出/版本 |
| MobileApprovalCard | MobileChatView | 单列布局，大触控按钮，保留审批上下文摘要 |
| AgentTemplateWizard | Agent 设置页 | 对话式生成区 + 最终配置预览，不放入好友列表 |

---

## 6. 前端交互序列

### 6.1 上传附件并作为上下文

```
用户: 拖拽图片到 ChatInput
  → 前端: AttachmentTray 显示上传进度
  → 前端: POST /api/attachments
  → 后端: attachment.created
  → 前端: 文件 chip 变为完成态
  → 用户: 发送消息
  → 后端: ContextPackBuilder 将 attachment 摘要/引用加入 prompt
```

### 6.2 移动端审批

```
系统: approval.created 触发 notification.created
  → 移动端: NotificationCenter 显示审批通知
  → 用户: 打开 MobileApprovalCard
  → 用户: 点击批准
  → 前端: POST /api/mobile/approvals/{approvalId}/decision
  → 后端: ApprovalService 继续原计划
  → 移动端: 显示已批准，Web 端同步状态
```

### 6.3 对话式创建 Agent

```
用户: 在添加 Agent 中选择“通过对话创建”
  → 前端: POST /api/agent-template-sessions
  → 用户: 描述职责、规则、工具需求
  → 后端: 生成 draft_json，包含 System Prompt、Rules、Toolset、Runtime Config
  → 前端: 展示配置预览
  → 用户: 点击创建
  → 前端: POST /finalize
  → 后端: 创建 Agent Profile，出现在自定义 Agent 分区
```

### 6.4 转发带 Artifact 的消息

```
用户: 右键消息选择转发，勾选包含 Artifact
  → 前端: POST /api/messages/{messageId}/forward
  → 后端: 创建目标消息与 artifact_references
  → 前端: 目标会话显示转发消息和 Artifact 引用卡片
```

---

## 7. 验收标准

- [ ] AC-P12-01: 团队成员可对 message/artifact/deployment 评论，权限不足返回 403。
- [ ] AC-P12-02: 评论、@ 提及、审批、部署完成、运行失败会生成 Notification。
- [ ] AC-P12-03: 文件/图片上传后可作为下一条 Agent 消息上下文，非法类型和超限文件被阻断。
- [ ] AC-P12-04: 转发消息选择 includeArtifacts=true 时，目标会话保留 Artifact 引用链。
- [ ] AC-P12-05: Mobile 可查看会话、未读、运行状态、审批卡片和 preview/deployment 链接。
- [ ] AC-P12-06: 移动端审批与 Web 端状态实时一致，重复审批返回 409。
- [ ] AC-P12-07: PPT/文档 Artifact 可 render、分页浏览、版本切换和导出。
- [ ] AC-P12-08: 对话式 Agent 创建最终落到 Agent Profile，而不是旧 Skill 模板或好友内置项。
- [ ] AC-P12-09: Git sync job 有状态、日志、冲突错误和审计记录。
- [ ] AC-P12-10: P1 local IM、会话置顶/归档/未读/免打扰、local runtime、消息级 Artifact 和本地导出回归通过。
- [ ] AC-P12-11: Phase 12 cloud multi-end slice 在真实服务上完成 Web 与 Mobile 共享会话、通知、审批、preview/deployment 链接状态同步。

---

## 8. 测试策略

### 8.1 单元测试（55 条）

| 测试对象 | 条数 | 覆盖内容 |
|---------|------|---------|
| CommentService | 8 | target 校验、权限、更新、删除 |
| AttachmentService | 10 | mime/size、存储、病毒扫描占位、上下文引用 |
| NotificationService | 8 | 创建、去重、已读、移动端摘要 |
| MessageForwardService | 7 | 文本转发、Artifact 引用级联、权限 |
| ArtifactRenderService | 8 | 文档/PPT render、失败、缓存 |
| AgentTemplateService | 8 | draft 生成、字段校验、finalize |
| GitSyncService | 6 | pull/push、冲突、日志 |

### 8.2 集成测试

- 评论 + 通知：创建评论后目标用户收到 notification。
- 附件 + Context Pack：上传图片后发送消息，prompt 中包含附件引用。
- 转发 + Artifact：跨会话转发后 artifact_references 正确。
- 移动端审批：mobile API approve 后 Web approval 状态同步。

### 8.3 E2E 测试

- Web：上传附件、发送给 Agent、查看 Artifact、评论、转发。
- Mobile viewport：收到审批、批准、打开 preview URL。
- Agent 创建：对话生成模板、finalize、出现在添加 Agent/自定义 Agent 分区。

### 8.4 P1/P2 兼容门禁

- P1 local 回归：本机 IM 基线、local runtime、消息级 Artifact、build/preview/export、审批续跑全部通过真实服务验收。
- P2 Web cloud slice：团队 Project 中完成评论、通知、附件、Artifact 引用、deployment 链接查看。
- P2 Mobile slice：MobileShell 或 mobile viewport 下查看会话、审批、运行状态、preview/deployment 链接，审批结果与 Web 端同步。
- 壳兼容：移动端不调用本机文件选择、PTY、CLI 启动等桌面特权能力；桌面壳不因 NotificationService/Auth cloud 依赖阻断本机默认流程。

---

## 9. 架构约束追溯

| 本模块的决策 | 依据 |
|------------|------|
| 多端协作和移动端轻量审批来自早期核心设计 | [AgentHub-多Agent协作平台设计](../../archive/AgentHub-多Agent协作平台设计.md) |
| 所有聊天必须属于 Project | [ADR-0009](../../adr/0009-project-workspace-model.md) |
| Artifact 仍是消息级体验，可引用和转发 | [ADR-0010](../../adr/0010-message-level-artifact-experience.md) |
| Agent 模板最终落到 Agent = System Prompt + Rules + Toolset + Runtime Config + Engine | [ADR-0011](../../adr/0011-agent-engine-skill-model.md) |
| SaaS 团队/权限/云端 workspace 基线 | [PRD-07](../../PRD/07-SaaS_Cloud_Workspace_Delivery.md) |

---

## 10. 依赖

| 依赖模块 | 需要的接口 | 当前状态 |
|---------|-----------|---------|
| Phase 9 Team/RBAC | team members、roles、audit logs | ✅ 已就绪 |
| Phase 10 Runtime | run status、approval、artifact detection | 📋 计划中 |
| Phase 11 Preview/Deployment | preview/deploy URL、deployment events | 📋 计划中 |
| Agent Profile model | System Prompt、Rules、Toolset、Engine | ✅ P1 基线 |
| ContextPackBuilder | attachments/artifact references 注入 | 📋 Phase 8 |

---

## 11. Non-Goals（明确不做什么）

| 不做的事 | 原因 | 由谁负责 |
|---------|------|---------|
| 企业 SSO/SAML/SCIM | 企业化阶段 | 后续 |
| 计费和套餐 | 商业化阶段 | 后续 |
| 实时多人代码编辑 | 复杂协同编辑独立课题 | 后续 |
| 公开 Agent Marketplace | 先做好自定义 Agent 和团队模板 | 后续 |
| 移动端完整 IDE/文件编辑 | Mobile 定位轻量审批和预览 | 不作为 Phase 12 目标 |

---

## 12. 破坏性变更与迁移

| 维度 | V1 行为 | V2 行为 | 迁移路径 |
|------|--------|--------|---------|
| 转发 | 文本快照为主 | 可包含 Artifact 引用链 | 旧转发继续显示文本，新转发写 artifact_references |
| Agent 创建 | 用户在配置卡片内选择模板并保存 | 增加对话式创建入口，最终仍保存 Agent Profile | 保留现有模板入口，对话入口作为新增方式 |
| Artifact 类型 | code/web/file_tree/document 基线 | 增加 PPT/文档 render 与附件上下文 | 扩展 Artifact viewer，不改变消息级卡片 |
| 通知 | 本地 IM 未读/免打扰 | SaaS 通知中心 + 移动端摘要 | 本地模式继续使用原 IM 状态，云端启用 NotificationService |

> **版本历史**
> - v1.1 (2026-06-08): 增加 P1 本机 IM/runtime 零回归与 Phase 12 Web/Mobile cloud 协作可运行切片门禁。
> - v1.0 (2026-06-08): 按 `SPEC_TEMPLATE.md` 创建 Phase 12 独立 Spec。
