# Phase 5: 产物深度管理 📋 PLANNED

**关联 ADR**: [ADR-0008](../../adr/0008-revised-development-strategy.md) §5
**依赖**: Phase 3 (Artifact 模型: version, parent_artifact_id; BaseAgentAdapter tools)
**状态**: 计划中

---

## 1. 板块目标

产物（代码/文档/网页）拥有完整的生命周期管理：
- **版本历史**：每次重新生成自动创建新版本，可回溯任意历史版本
- **可视化 Diff**：任意两版本间的差异对比，左右/统一视图
- **局部编辑**：选中代码区域，自然语言描述修改意图，Agent 精准修改

---

## 2. 子模块

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

## 3. 验收标准

- [ ] **5A-1**: Agent 重新生成产物 → 自动创建新版本（version += 1）→ 版本下拉选择器出现
- [ ] **5A-2**: 选择版本 v1 和 v3 → DiffViewer 展示 unified diff → 增行绿/删行红
- [ ] **5A-3**: 支持 split (左右对比) 和 unified (上下对比) 双模式
- [ ] **5B-1**: 选中代码片段 → 弹出"描述修改意图"输入框 → 输入指令
- [ ] **5B-2**: Agent supports_tool_call=true → 发送 edit_artifact tool → Agent 返回 tool_use → 后端生成 Diff
- [ ] **5B-3**: Agent supports_tool_call=false → 降级为上下文注入 "请对代码执行修改: {selection}"
- [ ] **5B-4**: Diff 确认 UI → 用户确认 → 创建新版本 | 用户拒绝 → 保持原版不变

---

## 4. 接口契约

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
