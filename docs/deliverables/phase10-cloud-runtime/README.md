# Phase 10 Sandbox Runner 与云端 Agent Runtime 交付文档

**日期**: 2026-06-08  
**范围**: 云端 sandbox 生命周期、CloudAgentRuntime、runtime logs、Secret 注入脱敏、配额、前端 runtime/Secret 入口、P1/P2 双运行时兼容  
**状态**: 已实现，自动化回归与真实服务验收通过

本目录记录 Phase 10 的交付快照。长期规格以 [Phase 10 Spec](../../specs/phase10/README.md) 为准；这里面向验收、交接和 Phase 11 读取。

## 交付清单

| 文档 | 作用 |
|------|------|
| [implementation-snapshot.md](implementation-snapshot.md) | 说明后端模型/API/服务、前端入口、P1/P2 工作目录边界的实际落点。 |
| [acceptance-log.md](acceptance-log.md) | 记录自动化测试、真实服务验收路径和剩余风险。 |
| [../../dev-logs/phase10-dev-log.md](../../dev-logs/phase10-dev-log.md) | Phase 10 开发日志：时间线、Bug/约束、测试矩阵和下一步。 |

## 本轮结论

Phase 10 已把 Phase 9 的 cloud workspace 从“元数据基座”推进到“可运行云端切片”：

```text
cloud Project
  -> workspaceId + cloud://agenthub/workspaces/{id}
  -> 本机隔离云端目录 data/workspaces/.cloud-workspaces/{workspaceId}
  -> sandbox ready
  -> 真实 CLI subprocess 以隔离目录为 cwd
  -> 标准 agent.output / agent.process.* / artifact.created / run.* 事件
  -> runtime_logs 脱敏持久化
```

P1 本地版未被切换到云端。`workspaceMode = "local"` 仍使用本机 `workspace_path`；显式 `runtime = "local"` 不要求 `sandboxId`。`workspaceMode = "cloud"` 才通过 Phase 10 CloudAgentRuntime 启动 sandbox。

## 验收入口

- 后端 Phase 10 API 测试：`pytest backend/test_api/test_phase10_cloud_runtime.py -q`
- Phase 9 云 workspace 回归：`pytest backend/test_api/test_phase9_cloud_workspace.py -q`
- 前端类型检查：`cd frontend && npx tsc --noEmit`
- 前端相关单测：`cd frontend && npx vitest run src/api/client.test.ts src/components/WorkspaceSettingsPage.test.tsx`
- 真实服务访问：
  - 前端：`http://127.0.0.1:5173/`
  - 后端：`http://127.0.0.1:8000/`
  - API Docs：`http://127.0.0.1:8000/docs`
