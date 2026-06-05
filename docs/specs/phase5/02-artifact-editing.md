# Spec: Phase 5B — 产物在线编辑

**版本**: v2.0
**创建日期**: 2026-05-28 (v1.0), 2026-06-02 (v2.0 重组)
**状态**: Completed (2026-06-02)
**关联**: [PRD-03: User Experience](../../PRD/03-User_Experience.md) §3.4, [PRD-02: Orchestrator](../../PRD/02-Orchestrator_Engine.md)
**依赖**: Phase 5A (版本链), 后端内部系统模型能力

## 1. 全局链路定位

```text
用户引用/打开已有 Artifact
  -> 选中代码片段并描述修改
  -> 系统模型生成候选内容与 Diff
  -> 用户确认
  -> 创建新版本
  -> Phase 7 Drawer 切换到新版本
```

本模块负责已有 Artifact 的编辑能力。聊天输入框中的自然语言修改入口、右侧 Drawer 内的选区交互和新版本卡片刷新由 Phase 7 承载。

## 2. API

```
POST /api/artifacts/{id}/edit
  Body: { selection, instruction }
  → 200 { new_version, diff, artifact }
```

## 3. Tool: edit_artifact Schema

```json
{
  "name": "edit_artifact",
  "description": "对产物进行局部修改",
  "parameters": {
    "type": "object",
    "properties": {
      "artifact_id": { "type": "string" },
      "selection": { "type": "string", "description": "选中的原始代码片段" },
      "instruction": { "type": "string", "description": "修改意图描述" },
      "edit_type": { "type": "string", "enum": ["replace", "insert_after", "insert_before", "delete"] }
    },
    "required": ["artifact_id", "selection", "instruction", "edit_type"]
  }
}
```

## 4. 编辑流程

```
用户选中代码片段 → 弹出 "描述修改" 输入框 → 输入意图
  │
  ├─ SystemLLM supports_tool_call == True?
  │   └─ YES → system_llm.chat(tools=[edit_artifact]) → 返回 tool_call
  │   └─ NO  → 降级: 上下文注入 "请对代码执行修改: {selection}, 意图: {instruction}"
  │
  └─ 系统模型返回修改结果
       ├─ 后端用 difflib 对比生成 Diff
       ├─ 前端 DiffViewer 展示
       └─ 用户确认 → 创建新版本 | 用户拒绝 → 保持原版
```

## 5. Tool Calling 实现要点

### 请求构建

```python
async def apply_edit(self, artifact_id, selection, instruction):
    if system_llm.is_configured() and system_llm.capability.supports_tool_call:
        response = await system_llm.chat(
            messages=[{"role": "user", "content": f"修改产物 {artifact_id}: {instruction}"}],
            system_prompt="你是一个代码编辑器。使用 edit_artifact tool 进行修改。",
            tools=[EDIT_ARTIFACT_TOOL],
        )
        if response.tool_calls:
            return await self._apply_tool_result(artifact_id, response.tool_calls[0])
        # Tool call 失败 → 降级
        return await self._fallback_context_injection(artifact_id, selection, instruction)
    else:
        return await self._fallback_context_injection(artifact_id, selection, instruction)
```

### Tool 响应解析

系统模型返回 OpenAI-compatible tool_call，由 `ArtifactEditor` 做格式解析：

```python
def _parse_tool_call(self, response: SystemModelResponse) -> dict | None:
    for tc in response.tool_calls:
        if tc.get("name") == "edit_artifact":
            return tc.get("input", {})
    return None
```

## 6. 验收标准

- [x] 选中代码 + 描述修改 → 系统模型返回 Diff → 确认后应用
- [x] 系统模型 tool calling → edit_artifact 调用成功
- [x] 系统模型不可用或不支持 tool calling → 降级为上下文注入，编辑仍可用
- [x] 拒绝 Diff → 保持原版不变

## 7. 测试

- API: tool calling 正常流程、降级流程、selection 异常、确认创建新版本
- 架构契约: Domain 纯编辑器、Service 事件发布、SystemLLM OpenAI-compatible tools 传递
- 前端: CodeSelector 选中交互、Diff 预览、确认/拒绝 UI
- 真实验收: `e2e/phase5_real_acceptance.py`
