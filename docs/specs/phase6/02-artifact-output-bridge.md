# Spec: Phase 6F — Agent 输出到 Artifact 桥接

**版本**: v1.0  
**创建日期**: 2026-06-03  
**状态**: Draft  
**关联**: [PRD-01](../../PRD/01-Architecture_Adapter.md) §3.4, [PRD-05](../../PRD/05-End_to_End_Product_Flow.md) §4, [PRD-06](../../PRD/06-MVP_Local_Workspace_Delivery.md)  
**依赖**: Phase 6A Workspace Runtime, Phase 3 EventBus, Phase 5 ArtifactService, Phase 6B-6E CliAgentAdapter

---

## 1. 目标

补齐“Agent 输出和 workspace 文件变更如何变成产物”的缺口。Phase 6F 将 API/CLI Agent 的文本流、代码块、patch、workspace diff 和文件变更摘要转换为标准 `artifact.detected` 事件，并由 ArtifactService 创建可预览、可编辑、可版本化的 Artifact。

---

## 2. 全局链路定位

```text
Agent stdout / API response / workspace.diff_ready
  -> ArtifactDetectionService
  -> artifact.detected
  -> ArtifactService.create_from_event()
  -> artifact.created
  -> 聊天流 Artifact Card
  -> Phase 7 Artifact Drawer
```

| 问题 | 回答 |
|------|------|
| 上游 | `agent.output` 文本流、`workspace.diff_ready`、CLI 文件变更摘要、Orchestrator `expected_outputs` |
| 下游 | `artifact.detected` / `artifact.created` 事件、Artifact 记录、Artifact Card 消息 |
| 用户可完成任务 | 让真实 Agent 生成的网页/代码自动出现在聊天里，并可进入 Phase 5/7 的预览编辑链路 |
| 不打通 | Drawer 视觉布局、部署发布、文件附件上传 |

---

## 3. 输入输出

### 3.1 标准事件

```python
class ArtifactDetectedEvent(BaseModel):
    type: Literal["artifact.detected"]
    session_id: str
    message_id: str | None = None
    task_id: str | None = None
    agent_id: str
    artifact_type: Literal["code_diff", "web_preview", "document", "file_tree"]
    title: str
    content: str
    source: Literal["api_agent", "cli_agent", "orchestrator"]
    confidence: float
    metadata: dict[str, Any] = {}
    workspace_id: str | None = None
    file_path: str | None = None
    preview_id: str | None = None
```

```python
class ArtifactCreatedEvent(BaseModel):
    type: Literal["artifact.created"]
    artifact_id: str
    session_id: str
    message_id: str
    task_id: str | None
    version: int
    workspace_id: str | None = None
```

### 3.2 Service 接口

```python
class ArtifactDetectionService:
    async def inspect_agent_output(
        self,
        *,
        session_id: str,
        message_id: str | None,
        task_id: str | None,
        agent_id: str,
        text: str,
        expected_outputs: list[ExpectedOutput] | None = None,
        source: str,
    ) -> list[ArtifactDetectedEvent]: ...

    async def inspect_workspace_diff(
        self,
        *,
        workspace_id: str,
        session_id: str,
        message_id: str | None,
        task_id: str | None,
        changed_files: list[WorkspaceChangedFile],
    ) -> list[ArtifactDetectedEvent]: ...

class ArtifactService:
    async def create_from_detected_event(
        self,
        event: ArtifactDetectedEvent,
    ) -> ArtifactRead: ...
```

---

## 4. 检测规则

| 输入信号 | artifact_type | 规则 |
|---|---|---|
| fenced code block: `html` | `web_preview` | 内容包含 `<html`、`<body` 或可独立渲染片段 |
| fenced code block: `tsx/jsx/vue/svelte` | `web_preview` 或 `file_tree` | 有组件导出时优先 `web_preview` |
| fenced code block: `diff/patch` | `code_diff` | 包含 `---/+++` 或 `@@` hunk |
| CLI 文件摘要 | `file_tree` | 包含 created/modified/deleted 文件路径 |
| Markdown 长文 | `document` | `expected_outputs` 指明 document，或文本超过阈值且结构化标题明显 |

### 4.1 置信度

- `confidence >= 0.8`: 自动创建 Artifact。
- `0.5 <= confidence < 0.8`: 仅发送候选事件，不自动创建；前端可在 Phase 7 后续增强中让用户确认。
- `< 0.5`: 保持为普通文本消息。

### 4.2 expected_outputs 辅助

Orchestrator 子任务若带有：

```json
{ "type": "artifact", "artifact_type": "web_preview", "title_hint": "LoginPage" }
```

检测服务应降低对应类型阈值，并用 `title_hint` 生成标题。

---

## 5. 行为规格

### 5.1 正常流程

1. CLI Adapter 推送清洗后的输出 chunk。
2. ChatService 聚合完整 Agent 消息。
3. 消息落库后调用 ArtifactDetectionService。
4. 检测服务返回 0-N 个 `artifact.detected` 事件。
5. ArtifactService 创建 Artifact，填充 `session_id/message_id/task_id/source/version=1`。
6. MessageService 追加 `content_type='artifact_card'` 的消息或将卡片作为 Agent 消息附件。
7. EventBus 发布 `artifact.created`，前端刷新会话产物列表。

### 5.2 异常流程

| 场景 | 预期行为 |
|------|----------|
| 代码块未闭合 | 不创建 Artifact，保留原文本 |
| 产物内容超过大小限制 | 创建 `status='error'` 的 Artifact，并在卡片显示“内容过大” |
| 多个代码块 | 按块创建多个 Artifact，标题加序号 |
| ArtifactService 落库失败 | Agent 文本消息保留，事件记录错误日志，不阻断聊天 |
| 低置信度误判风险 | 不自动创建，只保留文本 |

---

## 6. 验收标准

- [ ] CLI 输出完整 HTML 代码块后，会话产物列表出现 `web_preview` Artifact。
- [ ] Agent 消息下方出现 Artifact Card，卡片包含标题、类型、版本、预览入口。
- [ ] Orchestrator 子任务带 `expected_outputs` 时，生成的 Artifact 关联 `task_id`。
- [ ] 不完整代码块不会生成错误 Artifact。
- [ ] 多个代码块能生成多个独立 Artifact。
- [ ] Artifact 创建后可直接调用 Phase 5 versions/diff/edit API。

---

## 7. 测试

- Unit: 代码块检测、patch 检测、expected_outputs 阈值、低置信度过滤。
- API/Service: `create_from_detected_event()` 落库、Artifact Card 消息创建、EventBus 发布。
- E2E: Mock CLI 输出 HTML -> 聊天卡片 -> Artifact API 可读取。

---

## 8. Non-Goals

- 不做真正部署。
- 不做图片/附件上传。
- 不在 Adapter 内直接写数据库。
- 不实现 Drawer 视觉体验，交给 Phase 7。
