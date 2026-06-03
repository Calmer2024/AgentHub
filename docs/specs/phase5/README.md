# Phase 5: 产物工作台能力 ✅ COMPLETED

**关联 ADR**: [ADR-0008](../../adr/0008-revised-development-strategy.md) §5
**依赖**: Phase 3 (Artifact 模型: version, parent_artifact_id; BaseAgentAdapter tools)
**状态**: 已完成 (2026-06-02)

---

## 1. 全局定位

Phase 5 位于北极星链路的 **Artifact 工作台能力** 段：

```text
Artifact 已存在
  -> 版本链 / Diff / 局部编辑
  -> 用户确认创建新版本
  -> 下游 Phase 7 在 Drawer 中承载完整体验
```

Phase 5 的真实完成定义是：**对已有 Artifact，用户可以回溯版本、比较差异、选中局部内容并生成编辑 Diff，确认后创建新版本。**

它不代表以下链路已经完整打通：
- Agent/CLI 输出自动识别并创建 Artifact Card。
- Artifact Card 到右侧 Drawer 的产品级打开体验。
- Orchestrator 审批节点与 Artifact 审阅绑定。

这些链路分别由 Phase 6 和 Phase 7 补齐。

---

## 2. 板块目标

产物（代码/文档/网页）拥有完整的生命周期管理：
- **版本历史**：每次重新生成自动创建新版本，可回溯任意历史版本
- **可视化 Diff**：任意两版本间的差异对比，左右/统一视图
- **局部编辑**：选中代码区域，自然语言描述修改意图，Agent 精准修改

---

## 3. 子模块

### Module 5A: 产物版本 + Diff

| 维度 | 内容 |
|------|------|
| **Spec** | [01-artifact-versioning.md](01-artifact-versioning.md) |
| **API** | `GET /artifacts/{id}/versions`, `GET /artifacts/{id}/diff?v1=&v2=` |
| **后端** | `ArtifactService.get_versions()` (版本链递归追溯), `ArtifactService.get_diff()` (difflib) |
| **前端** | `VersionHistory.tsx` (版本下拉选择器), `DiffViewer.tsx` (react-diff-viewer-continued) |

### Module 5B: 产物在线编辑

| 维度 | 内容 |
|------|------|
| **Spec** | [02-artifact-editing.md](02-artifact-editing.md) |
| **API** | `POST /artifacts/{id}/edit` |
| **后端** | `edit_artifact` tool schema → Agent Tool Calling → Diff 生成 → 版本创建 |
| **前端** | `CodeSelector.tsx` (代码区域选中 + 修改意图输入), Diff 确认/拒绝 UI |

---

## 4. 验收标准

- [x] **5A-1**: Agent/用户确认编辑产物 → 自动创建新版本（version += 1）→ 版本下拉选择器出现
- [x] **5A-2**: 选择版本 v1 和 v2 → DiffViewer 展示 diff → 增删行高亮
- [x] **5A-3**: 支持 split (左右对比) 和 unified (上下对比) 双模式
- [x] **5B-1**: 选中代码片段 → 输入"描述修改意图" → 提交指令
- [x] **5B-2**: Agent supports_tool_call=true → 发送 edit_artifact tool → Agent 返回 tool_use → 后端生成 Diff
- [x] **5B-3**: Agent supports_tool_call=false → 降级为上下文注入 "请对代码执行修改: {selection}"
- [x] **5B-4**: Diff 确认 UI → 用户确认 → 创建新版本 | 用户拒绝 → 保持原版不变

---

## 5. 上下游契约

| 方向 | 契约 |
|------|------|
| 上游输入 | `Artifact` 记录已存在，包含 `id/session_id/message_id/type/title/content/version/parent_artifact_id` |
| 本阶段输出 | `artifact.version_created` 事件、新版本 Artifact、DiffResult |
| 下游消费 | Phase 7 ArtifactDrawer 展示版本链/Diff；Orchestrator 下游任务应引用最新版本 |
| 未覆盖边界 | `artifact.detected` / `artifact.created` 标准事件的生产与聊天卡片创建由 Phase 6/7 补齐 |

### 从聊天回流到编辑

Phase 5 提供 `POST /api/artifacts/{id}/edit` 能力，但自然语言入口不局限于代码选择器。Phase 7 需要把以下用户动作转成该 API：

1. 用户在 Artifact Card 点击“引用此版本”。
2. 输入框带 `referenced_artifact_id` 发送“把按钮改成红色”。
3. 前端或 ChatService 判断为 Artifact edit intent，调用 Phase 5 编辑流程。

---

## 6. 接口契约

### 新增 ArtifactService 方法

```python
class ArtifactService:
    async def get_versions(self, artifact_id: str) -> list[ArtifactVersion]
    async def get_diff(self, artifact_id: str, v1: int, v2: int) -> DiffResult
    async def apply_edit(self, artifact_id: str, selection: str, instruction: str, edit_type: str) -> ArtifactEditResult
```

### 与 Phase 3 的契约

- 复用 `BaseAgentAdapter.chat(tools=[...])` 接口（Module 1 已添加 tools 参数）
- 复用 `Artifact` 模型的 `version` + `parent_artifact_id` 字段

---

## 7. 完成记录

### 架构实现

- `domain/artifact_editor.py`: 纯 Diff、tool payload 解析、编辑操作逻辑。
- `services/artifact_service.py`: 版本链、Agent 编辑编排、事务、EventBus 发布。
- `api/artifacts.py`: thin handler，仅负责 HTTP 契约。
- `agents/openai_adapter.py` / `deepseek_adapter.py`: 已实现真实 tools 传递和 tool_calls 解析。
- Claude/Gemini 暂未实现工具调用传递，因此能力声明修正为 `supports_tool_call=false`，服务层自动降级。

### 测试与验收

```bash
cd backend && .\venv\Scripts\python.exe -m pytest -q
# 87 passed

cd frontend && npx vitest run
# 29 passed

cd frontend && npm run build
# passed

backend\venv\Scripts\python.exe e2e\phase5_real_acceptance.py
# Phase 5 real acceptance passed
```

详见 [Phase 5 Dev Log](../../dev-logs/phase5-dev-log.md)。
