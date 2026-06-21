# Spec: Phase 7B — 人工审批断点

**版本**: v2.0
**创建日期**: 2026-06-06
**状态**: 验收通过
**关联 ADR/PRD**: [ADR-0008](../../../../adr/0008-revised-development-strategy.md)、[ADR-0010](../../../../adr/0010-message-level-artifact-experience.md)、[PRD-02](../../../../PRD/02-Orchestrator_Engine.md)、[PRD-03](../../../../PRD/03-User_Experience.md)、[PRD-05](../../../../PRD/05-End_to_End_Product_Flow.md)
**依赖模块**: Phase 7A Run/Task 状态、Phase 6F 消息级 Artifact 卡片、Phase 5 Artifact 版本/编辑

> 2026-06-06 实现同步：本模块已落地 `approval_checkpoints` 表、ApprovalService、审批 API、SSE `approval.created` 事件与前端 `ApprovalCard`。审批卡片绑定原消息与关联 Artifact，确认会把 checkpoint 标记为 approved 并完成 task，驳回会记录原因并把 Artifact/代码引用上下文回流到对话修订路径。

---

## 1. 目标

实现 Human-in-the-loop 审批节点。Orchestrator 或单个 CLI Agent 在关键产物完成后，如果任务标记为需要人工确认，系统必须暂停下游执行，在聊天流中展示 Approval Card，让用户基于当前消息级 Artifact、Diff、文件编辑器和版本管理做确认或驳回。

本模块不再打开右侧 Artifact Drawer。审批卡片点击产物区域时，应复用 `ArtifactCard` 的页面级预览弹窗、`FileEditorModal` 和 `ArtifactVersionManager`，保持当前产品的消息级产物心智。

**成功标准**（可证伪）：

- [x] `requiresHumanApproval=true` 的 task 完成后进入 `paused`，下游 task 不会自动开始。
- [x] 前端在关联 assistant 消息下方展示 Approval Card，卡片包含任务标题、摘要、关联 Artifact、确认/驳回按钮。
- [x] 点击确认后 task/checkpoint 变为 `approved`，下游依赖任务被释放。
- [x] 点击驳回后 ChatInput 自动带入当前 Artifact/代码引用，用户可直接输入修改意见。
- [x] 不通过标准：审批只是前端静态按钮，没有持久化 checkpoint；或驳回后丢失 Artifact 上下文。

---

## 2. 全局定位

### 2.1 北极星链路位置

```text
Run/Task 完成
  → [本模块] ApprovalCheckpoint(paused)
  → ApprovalCard + ArtifactCard 预览/编辑
  → approve/reject
  → 下游 task 继续或回到对话修订
```

### 2.2 上下游契约

| 方向 | 模块/事件/API | 本模块的角色 |
|------|-------------|------------|
| **上游输入** | Phase 7A `run_tasks` | 找到需要审批的 task，控制状态转换 |
| **上游输入** | Phase 6F Artifact | 审批必须绑定可审阅 Artifact 或任务摘要 |
| **下游产出** | Approval API / events | 前端 ApprovalCard、ChatInput 引用回流消费 |
| **本模块不通** | 多人审批、权限审计报表 | P2/企业增强 |

---

## 3. 跨模块契约

### 3.1 API 端点

| 端点 | 方法 | 请求体 | 成功响应 | 错误响应 |
|------|------|--------|---------|---------|
| `/api/sessions/{sessionId}/approvals` | GET | 无 | `200: ApprovalCheckpointRead[]` | `404` session 不存在 |
| `/api/approvals/{checkpointId}` | GET | 无 | `200: ApprovalCheckpointRead` | `404` checkpoint 不存在 |
| `/api/approvals/{checkpointId}/approve` | POST | `{ artifactId?, artifactVersion?, comment? }` | `200: ApprovalCheckpointRead(status="approved")` | `409` 状态非法 |
| `/api/approvals/{checkpointId}/reject` | POST | `{ reason, artifactId?, artifactVersion?, codeReference? }` | `200: ApprovalCheckpointRead(status="rejected")` | `400` reason 为空；`409` 状态非法 |

### 3.2 事件

| 事件类型 | 方向 | payload 字段 |
|---------|------|-------------|
| `approval.created` | 后端 → SSE/WS | `{ checkpointId, runId, taskId, sessionId, messageId?, artifactId? }` |
| `approval.status_changed` | 后端 → SSE/WS | `{ checkpointId, status, approvedAt?, rejectedAt?, reason? }` |
| `task.status_changed` | 后端 → SSE/WS | `{ taskId, status: "paused"|"completed"|"running" }` |

### 3.3 数据库 Schema 变更

```sql
CREATE TABLE approval_checkpoints (
    id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL REFERENCES runs(id),
    task_id VARCHAR NOT NULL REFERENCES run_tasks(id),
    session_id VARCHAR NOT NULL REFERENCES sessions(id),
    message_id VARCHAR REFERENCES messages(id),
    artifact_id VARCHAR REFERENCES artifacts(id),
    artifact_version INTEGER,
    title VARCHAR NOT NULL,
    summary TEXT NOT NULL,
    status VARCHAR NOT NULL,
    reason TEXT,
    created_at DATETIME NOT NULL,
    decided_at DATETIME,
    metadata_json TEXT
);
```

状态枚举：

```text
pending_review → approved
pending_review → rejected
rejected → pending_review   -- 新版本产物生成后可重新进入审批
approved/rejected 不允许再次 approve/reject，重复请求返回 409
```

### 3.4 跨组件 TypeScript 类型

```typescript
type ApprovalStatus = "pending_review" | "approved" | "rejected";

interface ApprovalCheckpoint {
  id: string;
  runId: string;
  taskId: string;
  sessionId: string;
  messageId?: string | null;
  artifactId?: string | null;
  artifactVersion?: number | null;
  title: string;
  summary: string;
  status: ApprovalStatus;
  reason?: string | null;
  createdAt: string;
  decidedAt?: string | null;
}
```

---

## 4. 行为规格

### 4.1 正常流程：确认

```text
1. Orchestrator 规划或 task metadata 标记 requiresHumanApproval=true
2. task 完成后不直接标记 completed，而是 status=paused
3. 后端创建 approval_checkpoints(status=pending_review)
4. SSE approval.created
5. 前端在关联消息下方渲染 ApprovalCard
6. 用户点击关联 Artifact 区域
   → 打开 ArtifactCard 现有页面级预览弹窗
7. 用户点击“确认继续”
8. 后端 checkpoint.status=approved，task.status=completed
9. Scheduler 释放依赖该 task 的下游 task
```

### 4.2 正常流程：驳回

```text
1. 用户点击 ApprovalCard “驳回并修改”
2. 前端打开 reject reason 输入，或直接把 ChatInput 切入修订模式
3. ChatInput 自动添加：
   - checkpointId
   - artifactId/version
   - 代码引用块（如用户在 FileEditorModal 中选择过片段）
4. 用户发送修改意见
5. 后端将 reason 写入 checkpoint，task.status=rejected
6. 新消息走普通 CLI Agent 路径，产出新 Artifact 后可重新创建 pending_review checkpoint
```

### 4.3 UX 六态覆盖

| 状态 | 用户看到什么 | 触发条件 |
|------|------------|---------|
| **空态** | 不显示 ApprovalCard | 当前 session 无待审批 checkpoint |
| **加载态** | ApprovalCard skeleton，一行“正在生成审批项” | `task.status=paused` 后 checkpoint 尚未加载 |
| **正常态** | 审批标题、摘要、Artifact 入口、确认/驳回按钮 | `pending_review` |
| **完成态** | 卡片收起为“已确认继续”或“已驳回” | `approved/rejected` |
| **错误态** | 按钮旁显示错误，保留原操作 | approve/reject API 失败 |
| **边界态** | 多个 pending checkpoint 按消息顺序展示；刷新后恢复 | 多任务并行、刷新 |

### 4.4 错误处理

| 错误场景 | 错误码 | 用户可见文案 | 恢复路径 |
|---------|--------|------------|---------|
| checkpoint 不存在 | `404` | “审批项不存在或已被清理” | 刷新会话 |
| 重复审批 | `409 APPROVAL_ALREADY_DECIDED` | “该审批已经处理过” | 显示最新状态 |
| 缺少驳回原因 | `400 REASON_REQUIRED` | “请填写修改原因” | 保持输入 |
| Artifact 已删除 | `404 ARTIFACT_NOT_FOUND` | “关联产物不可用，可基于摘要继续审批” | 允许审批摘要 |
| 下游释放失败 | `RELEASE_FAILED` | “已记录确认，但下游任务启动失败” | 显示重试按钮 |

---

## 5. 前端页面设计

### 5.1 页面布局

```text
MessageBubble
├── Assistant 内容
├── MessageArtifactStrip
└── ApprovalCard
    ├── Header: ShieldCheck icon + title + status
    ├── Summary
    ├── ArtifactReviewLink
    └── Actions: Reject / Approve
```

ApprovalCard 只在需要审批的消息下方出现。它不是全局悬浮层，也不占右侧工作台。

### 5.2 组件树

```text
MessageBubble
└── ApprovalCard
    ├── ApprovalStatusBadge
    ├── ArtifactInlinePreviewButton
    ├── RejectApprovalButton
    └── ApproveApprovalButton

ChatInput
└── RevisionReferenceBar
```

### 5.3 关键视觉元素

| 元素 | 位置 | 视觉规格 |
|------|------|---------|
| 审批卡片 | MessageBubble 底部 | 圆角 8px，1px 琥珀边框，紧凑深色 header |
| 状态图标 | Card header | pending 用 lucide `ShieldAlert`，approved 用 `ShieldCheck`，rejected 用 `ShieldX` |
| 确认按钮 | Card actions | lucide `CheckCircle2` + 文案“确认继续” |
| 驳回按钮 | Card actions | lucide `Undo2` + 文案“驳回修改” |
| Artifact 入口 | Card body | lucide `FileSearch`，点击打开现有 Artifact 弹窗 |

---

## 6. 前端交互序列

```text
用户: 点击 ApprovalCard 的 Artifact 入口
  → 前端: 找到 artifactId 对应 ArtifactCard 数据
  → 前端: 打开 ArtifactCard 现有页面级弹窗

用户: 点击“确认继续”
  → 前端: POST /api/approvals/{id}/approve
  → 后端: checkpoint approved，task completed，释放下游任务
  → SSE: approval.status_changed + task.status_changed
  → 前端: ApprovalCard 收起为已确认状态

用户: 点击“驳回修改”
  → 前端: ChatInput.focus()
  → 前端: 设置 revision reference `{ checkpointId, artifactId, artifactVersion }`
  → 用户: 输入修改意见并发送
  → 后端: POST /reject 或随消息 metadata 写入 rejection reason
  → 前端: 卡片显示已驳回，等待新产物
```

---

## 7. 验收标准

- [ ] AC-7B-01: task metadata `requiresHumanApproval=true` 时，task 完成后状态为 `paused`，不是 `completed`。
- [ ] AC-7B-02: `approval_checkpoints` 记录包含 runId、taskId、sessionId、messageId、artifactId/version。
- [ ] AC-7B-03: 刷新页面后，pending ApprovalCard 仍在原消息下方显示。
- [ ] AC-7B-04: 点击 Artifact 入口打开当前 ArtifactCard 弹窗，不出现右侧 Drawer。
- [ ] AC-7B-05: Approve 后下游 task 开始执行，并在 CollaborationPanel/RuntimeControlStrip 中可见。
- [ ] AC-7B-06: Reject 后 ChatInput 出现代码/Artifact 引用，发送内容携带可追溯 metadata。
- [ ] AC-7B-07: 已处理审批重复点击返回最新状态，不产生重复下游任务。

---

## 8. 测试策略

### 8.1 单元测试（8 条）

| 测试对象 | 条数 | 覆盖内容 |
|---------|------|---------|
| ApprovalService 状态机 | 4 | 创建、approve、reject、非法重复决策 |
| Downstream release | 2 | approved 释放依赖，rejected 不释放 |
| Reference builder | 2 | Artifact/代码引用 metadata |

### 8.2 集成测试

- mock Orchestrator task → artifact created → checkpoint pending → approve → downstream task running。
- reject → ChatInput 引用 payload → 新消息包含 checkpoint/artifact 上下文。

### 8.3 E2E 测试

- 浏览器中触发审批卡片 → 打开 Artifact 弹窗 → 确认继续。
- 审批卡片 → 驳回修改 → ChatInput 自动带引用 → 发送修订。

---

## 9. 架构约束追溯

| 本模块的决策 | 依据 |
|------------|------|
| 任务暂停/审批状态属于 Orchestrator/Run 层，不属于 ArtifactService | PRD-02 §任务状态机 |
| 审批审阅入口复用消息级 ArtifactCard，不打开 Drawer | ADR-0010 |
| 驳回通过对话和代码引用回流，而不是内嵌复杂编辑器 | PRD-03 对话驱动原则；Phase 6F 实现基线 |

---

## 10. 依赖

| 依赖模块 | 需要的接口 | 当前状态 |
|---------|-----------|---------|
| Phase 7A RunService | run_tasks、task.status_changed | 待实现 |
| Artifact API | ArtifactRead、versions、diff | 已就绪 |
| ChatInput code reference | revision/reference UI | Phase 6F 已有代码引用基础 |
| CollaborationPanel | 展示 paused/approved/rejected | 需扩展状态 |

---

## 11. Non-Goals

| 不做的事 | 原因 | 由谁负责 |
|---------|------|---------|
| 不做多人审批权限 | P1 本机单用户 | P2 |
| 不做审计报表 | MVP 只需可追溯状态 | P2 |
| 不实现 Drawer 审阅 | 当前产品基线已切换 | ADR-0010 |

---

## 12. 破坏性变更与迁移

| 维度 | V1 行为 | V2 行为 | 迁移路径 |
|------|--------|--------|---------|
| Orchestrator task | 完成即继续 | 可暂停等待审批 | 新增 `requiresHumanApproval` metadata 与 checkpoint 表 |
| 审批 UI | 无 | 消息下方 ApprovalCard | 新增组件，不影响旧消息 |
| 驳回 | 普通聊天 | 带 checkpoint/artifact 引用的修订消息 | ChatInput metadata 扩展 |

> **版本历史**
> - v1.0 (2026-06-03): 旧版审批断点，依赖 Artifact Drawer。
> - v2.0 (2026-06-06): 移除 Drawer 依赖，改为消息级 ArtifactCard + 页面级弹窗 + ChatInput 引用回流。
> - v2.1 (2026-06-06): 同步 ApprovalCheckpoint 实现基线与验收状态。
