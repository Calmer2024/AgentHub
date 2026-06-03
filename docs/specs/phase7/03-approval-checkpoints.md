# Spec: Phase 7B — 人工审批断点

**版本**: v1.0  
**创建日期**: 2026-06-03  
**状态**: Draft  
**关联**: [PRD-02](../../PRD/02-Orchestrator_Engine.md) §5, §7, [PRD-03](../../PRD/03-User_Experience.md) §3.5  
**依赖**: Phase 3 Orchestrator DAG, Phase 5 Artifact 版本链, Phase 7A Artifact Drawer

---

## 1. 目标

实现 Human-in-the-loop 审批节点。Orchestrator 任务完成后如果 `requires_human_approval=true`，流水线进入 `PAUSED`，聊天流展示 Approval Card，用户审阅关联 Artifact 或摘要后确认继续，或驳回并要求 Agent 修订。

---

## 2. 全局链路定位

```text
Orchestrator task completed
  -> requires_human_approval
  -> PAUSED
  -> Approval Card
  -> 用户审阅 Artifact
  -> approve/reject
  -> 下游任务继续或当前任务修订
```

| 问题 | 回答 |
|------|------|
| 上游 | `task.status_changed`、任务关联 Artifact、`requires_human_approval` |
| 下游 | `POST /api/tasks/{id}/approve|reject`、下游任务调度、Artifact 引用上下文 |
| 用户可完成任务 | 在架构/设计/关键产物阶段暂停检查，避免错误流入后续任务 |
| 不打通 | 多人权限审批、审批历史审计报表、复杂分支回滚 |

---

## 3. 数据与 API

```typescript
interface ApprovalCheckpoint {
  taskId: string;
  sessionId: string;
  title: string;
  summary: string;
  artifactId?: string;
  artifactVersion?: number;
  status: "paused" | "approved" | "rejected";
}
```

```
POST /api/tasks/{task_id}/approve
  Body: { artifact_id?: string, artifact_version?: number }
  → 200 { task_id, status: "COMPLETED", released_task_ids: [...] }

POST /api/tasks/{task_id}/reject
  Body: { reason: string, artifact_id?: string, artifact_version?: number }
  → 200 { task_id, status: "PENDING" | "RUNNING", revision_message_id: "..." }
```

---

## 4. 行为规格

### 4.1 正常流程：确认

1. Orchestrator 子任务完成，发现 `requires_human_approval=true`。
2. 如果任务有 `expected_outputs`，必须关联 Artifact；否则关联任务摘要。
3. 任务状态变为 `PAUSED`，EventBus 发布 `task.status_changed`。
4. 前端在聊天流底部渲染 Approval Card。
5. 用户点击卡片主区域，Artifact Drawer 打开待审阅 Artifact。
6. 用户点击“确认无误，启动下阶段”。
7. 后端将任务标记为 `COMPLETED`。
8. Scheduler 扫描依赖已满足的下游任务并启动。

### 4.2 正常流程：驳回

1. 用户在 Approval Card 点击“驳回，需重新修改”。
2. 输入框进入修订模式，引用该任务与 Artifact。
3. 用户输入驳回原因。
4. 后端将原因追加为任务上下文，重新派发给原 Agent 或 Orchestrator 指定 Agent。
5. 新版本 Artifact 生成后，任务再次进入 `PAUSED`。

### 4.3 输入框状态

- PAUSED 时，普通发送被遮罩提示“流水线已暂停”。
- 允许用户在修订模式中继续发送针对当前任务/Artifact 的消息。
- 不允许启动不相关的新下游任务。

---

## 5. 验收标准

- [ ] `requires_human_approval=true` 任务完成后进入 `PAUSED`，不会触发下游任务。
- [ ] Approval Card 显示任务名称、摘要、关联 Artifact 入口、确认/驳回按钮。
- [ ] 点击卡片主区域打开 Artifact Drawer。
- [ ] 点击确认后任务变为 `COMPLETED`，依赖它的下游任务开始执行。
- [ ] 点击驳回后输入框进入修订模式，后续消息携带 `task_id` 与 `artifact_id`。
- [ ] 新版本产物生成后再次显示 Approval Card。
- [ ] 刷新页面后 PAUSED 状态和 Approval Card 仍可恢复。

---

## 6. 测试

- Unit: 任务状态转换、依赖释放、reject 上下文构建。
- API: approve/reject 成功、非法状态、无权限/不存在任务。
- E2E: 审批暂停 -> 打开 Drawer -> 确认继续；审批暂停 -> 驳回 -> 新版本 -> 再确认。

---

## 7. Non-Goals

- 不做多人审批权限。
- 不做完整审计报表。
- 不做自动代码冲突合并，冲突处理仍由 Agent/用户对话解决。
