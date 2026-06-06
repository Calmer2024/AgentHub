# Phase 5 Dev Log: 产物深度管理

**日期**: 2026-06-02  
**状态**: Completed

## 目标

完成产物独立生命周期管理：

- 版本链：每次编辑确认创建新 Artifact 版本，`version += 1`，`parent_artifact_id` 指向前版。
- Diff：任意两个版本可生成 unified diff，前端支持左右/上下两种视图。
- 在线编辑：用户选中代码片段，输入修改意图，生成 Diff，确认后创建新版本，拒绝不改库。
- Tool Calling：OpenAI/DeepSeek 真实传递 `tools` 并解析 tool calls；不支持工具调用的 Agent 自动降级为上下文注入。

## 架构优化

本阶段按 ADR-0005 对当前架构做了收拢，而不是只追加路由补丁：

- 新增 `backend/app/domain/artifact_editor.py`，将 Diff、tool payload 解析、编辑操作等纯逻辑放入 Domain 层。
- 新增 `backend/app/services/artifact_service.py`，Service 层负责 DB 版本链、Agent 调用、事务与事件发布。
- `backend/app/api/artifacts.py` 保持 thin handler，只做请求校验、委托 Service、序列化响应。
- `ArtifactService` 发布 `ARTIFACT_CREATED` / `ARTIFACT_UPDATED` 事件，接入既有 EventBus。
- 会话产物列表只返回版本链头节点，历史版本通过 `/versions` 查询，避免前端把旧版本重复渲染成多个产物卡片。
- 修正 Agent Adapter 能力声明：OpenAI/DeepSeek 实现真实 tool call；Claude/Gemini 暂未实现 tools 传递，因此不再声明 `supports_tool_call=True`。

## 实现摘要

- 后端新增接口：
  - `GET /api/artifacts/{id}/versions`
  - `GET /api/artifacts/{id}/diff?v1=&v2=`
  - `POST /api/artifacts/{id}/edit`
- 前端新增/增强：
  - `VersionHistory.tsx`
  - `DiffViewer.tsx`
  - `CodeSelector.tsx`
  - `ArtifactCard.tsx`
  - `ChatWindow` 接入会话级产物工作台
  - `chatStore` 增加 artifacts 状态
- 新依赖：`react-diff-viewer-continued`
- 新增真实 HTTP 验收脚本：`e2e/phase5_real_acceptance.py`

## 与旧模块打通确认

- 会话模块：`GET /sessions/{id}/artifacts` 按当前会话加载产物，切换会话时前端刷新产物工作台。
- 消息模块：Artifact 继续通过 `message_id` 关联 AI 消息；验收脚本真实插入会话消息并通过公开 API 操作关联产物。
- Agent 模块：编辑服务根据 Artifact → Message → AgentConfig 找到对应 Agent；支持工具调用走 `chat(tools=[...])`，否则降级。
- EventBus：确认创建版本时发布 `artifact.created` 和 `artifact.updated`，与既有基础设施保持一致。
- Phase 4 回归：后端默认测试集 87 条全部通过。

## 验收

```bash
cd backend
.\venv\Scripts\python.exe -m pytest -q
# 87 passed

cd frontend
npx vitest run
# 29 passed

cd frontend
npm run build
# passed；仅 Vite chunk size warning

backend\venv\Scripts\python.exe e2e\phase5_real_acceptance.py
# Phase 5 real acceptance passed
```

## 注意事项

- Phase 5 的在线编辑目前是“预览/确认”两步都走 `POST /edit`：默认只返回 `proposedContent` 与 Diff；确认时传 `apply: true` 和 `proposedContent` 才创建新版本。
- `react-diff-viewer-continued` 增加了前端 bundle 体积，当前构建仅告警。Phase 7 可考虑对产物工作台做动态导入拆包。
