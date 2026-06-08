# Phase 6F 验收日志

**日期**: 2026-06-06
**结论**: 本轮验收通过

## 1. 人工验收结论

本轮验收确认以下体验已经达到当前 Phase 6F 标准：

- Artifact 与文件变更以紧凑卡片跟随具体 assistant 消息展示，不再使用独立产物工作台。
- 代码 diff 与文件变更 diff 采用 VS Code/GitHub 风格 unified diff，不再提供左右/上下模式。
- Artifact 全屏弹窗从页面级 overlay 打开，不会被聊天气泡内部容器挤压。
- 每个可编辑产物/文件可进入文件编辑器，编辑器已升级为 IDE 风格 CodeMirror UI，具备行号、语法高亮、状态栏和保存能力。
- 在文件编辑器中选中代码片段后，可以添加到对话输入框，形成代码引用卡片和可发送的引用内容。
- Artifact 版本管理界面支持撤销本次修改和跳转历史版本。
- Chat Header 文件入口可打开当前会话的产物、资产和变更管理界面。
- 三个内置 CLI Agent 头像已替换为具体厂商 logo 图像。
- 群聊中每个 Agent 子消息可基于各自 workspace snapshot 生成 `workspace_diff` Artifact，并绑定到对应 Agent messageId/sourceId。

## 2. 自动测试记录

```powershell
cd backend && .\venv\Scripts\python.exe -m pytest test_api/test_artifact_output_bridge_phase6.py -q
# 10 passed

cd backend && .\venv\Scripts\python.exe -m pytest test_api/test_chat.py test_api/test_group_chat.py test_api/test_artifact_output_bridge_phase6.py test_api/test_artifacts_phase5.py test_api/test_projects_phase6.py test_unit/test_cli_adapter_runtime.py test_unit/test_codex_local_config_service.py -q
# 98 passed

cd frontend && npx tsc --noEmit
# passed

cd frontend && npx vitest run src/components/MessageArtifactStrip.test.tsx src/components/ArtifactCard.test.tsx src/components/ChatInput.test.tsx src/api/client.test.ts
# 23 passed

cd frontend && npm run build
# passed; only Vite chunk-size warning remains
```

2026-06-08 群聊同步回归：

```powershell
cd backend && .\venv\Scripts\python.exe -m pytest test_api\test_group_chat.py test_api\test_artifact_output_bridge_phase6.py test_api\test_phase7_runtime.py -q
# 44 passed

cd backend && .\venv\Scripts\python.exe -m pytest test_api/ -q
# 153 passed

cd frontend && npx tsc --noEmit
# passed

cd frontend && npx vitest run
# 78 passed
```

## 3. 真实服务验收

```powershell
cd backend && .\venv\Scripts\python.exe test_real_api_claude_artifact_bridge.py
# ok=true
```

真实 Claude Code 2.1.165 通过 AgentHub 服务路径在临时 workspace 写入：

- `index.html`
- `package.json`
- `src/App.tsx`

验收断言：最终 `done` SSE 前已经创建 `web_preview`、`file_tree`、`code_diff` 三类 Artifact，并且 `GET /api/sessions/{id}/artifacts` 可查询。

2026-06-08 真实 HTTP 群聊验收：启动当前后端与前端服务后，通过 REST 创建临时 Project、群聊和两个 custom CLI Agent。两个 Agent 分别写入 `real-agent-a-*.html` 与 `real-agent-b-*.html`，`GET /api/sessions/{id}/artifacts` 返回 2 个 `workspace_diff` `web_preview` 与 2 个 `code_diff`，且每个 Artifact 的 `messageId` 对应各自 Agent 消息；`GET /api/agents/runtime/processes?sessionId=...` 返回空数组，未遗留活跃进程。

## 4. 剩余风险

- 真实 CLI stdout/stderr 解析仍需继续收集 fixture，尤其是命令、工具参数和目标文件路径细节。
- 群聊当前通过每个 Agent 调用前 snapshot 解决已支持执行路径的产物归属；若未来引入真正并行写同一 workspace，需要重新审计重叠写入与冲突合并策略。
- 长任务取消、环境体检和审批卡片是 Phase 7 的继续工作。
