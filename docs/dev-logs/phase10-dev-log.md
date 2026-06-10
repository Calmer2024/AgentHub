# Phase 10 开发日志：Sandbox Runner 与云端 Agent Runtime

**阶段**: Phase 10  
**日期**: 2026-06-08  
**状态**: 已实现，自动化与真实服务验收通过  
**关联 Spec**: [docs/specs/phase10/README.md](../specs/phase10/README.md)

## 1. 阶段概述

Phase 10 的目标是让 Phase 9 的 cloud Project 具备最小真实执行能力，同时证明 P1 本地版不被云端 runtime 污染。本轮完成：

| 模块 | 内容 |
|------|------|
| Sandbox Runner | 新增 sandbox API、DB 表、生命周期事件和停止语义。 |
| CloudAgentRuntime | cloud chat 路径复用 CLI adapter、RunService、ContextPack、ArtifactOutputBridge，输出 P1 兼容 SSE。 |
| Cloud workspace storage | `cloud://` 逻辑 URI 映射为隔离目录，zip 导入、snapshot、restore 写入真实文件。 |
| Secret/Quota/Logs | Secret 加密保存与脱敏、默认配额、runtime_logs 查询。 |
| 前端 | RuntimeControlStrip 显示 cloud/local，WorkspaceSettingsPage 显示配额并可创建 Secret。 |
| 测试 | Phase 10 API 测试、Phase 9 回归、前端类型与组件/API 测试。 |

## 2. 开发时间线

- Day 0：阅读 `CONTEXT.md`、Phase 10 Spec、Phase 9 实现、CLI runtime/Artifact Bridge/RunService 契约。
- Day 1：新增 runtime 数据模型与迁移，建立 cloud storage、quota、secret、sandbox 服务。
- Day 1：实现 `CloudAgentRuntimeService`，把 cloud Project 的 `/chat` 路径接入真实 CLI subprocess 与标准 SSE。
- Day 1：扩展 runs API：显式 runtime 选择、cloud cancel、runtime logs。
- Day 1：升级 `CloudWorkspaceProvider`，使 zip 导入、snapshot、restore 作用于真实隔离目录。
- Day 1：补前端类型/API、RuntimeControlStrip、WorkspaceSettingsPage runtime/secret 区块。
- Day 1：新增 Phase 10 后端测试与前端测试，更新交付文档。

## 3. Bug 与解决方案

| 问题 | 根因 | 解决 | 教训 |
|------|------|------|------|
| cloud Project 环境体检会按本机路径检查 `cloud://` | Phase 7C health service 只认识本地 workspace | 按 `workspaceMode` 分支：cloud 只检查 `workspaceId`，Agent executable 不阻断本机体检 | P2 引入逻辑 URI 后，所有路径检查必须先识别 Provider。 |
| Phase 9 zip import 只记录元数据，Phase 10 Artifact 无真实文件可扫 | Phase 9 明确未实现物理存储 | 新增 `cloud_storage.py` 并升级 Provider，导入/快照/恢复同步物理隔离目录 | 元数据基座进入 runtime 阶段时必须补真实文件面。 |
| 本地 Run UI 无法感知 cloud sandbox | 现有 `runs` 表是 P1 兼容面，缺少 runtime 字段 | cloud run 继续创建兼容 `runs` 行，并把 `runtimeMode/sandboxId` 放入 metadata；authoritative cloud 状态写 `runtime_runs` | 不为了 P2 新建聊天渲染分支，优先扩展已有兼容面。 |
| Secret 可能出现在 stdout、日志、消息内容 | CLI fixture 会主动打印 env | 在 CloudAgentRuntime 外层统一 redactor，SSE/log/message metadata 均脱敏 | Secret 注入必须和日志脱敏成对实现，不能只做存储加密。 |

## 4. 建立的基础设施

- `backend/test_api/test_phase10_cloud_runtime.py`：覆盖 cloud chat → sandbox → CLI → Artifact → logs → snapshot、配额、本地 runtime 兼容。
- `docs/deliverables/phase10-cloud-runtime/`：交付快照、实现说明、验收日志。
- Phase 10 schemas：Sandbox、Quota、Secret、RuntimeLogs 的前后端类型契约。

## 5. 方法总结

- P2 SaaS 化要以“可运行切片”推进，而不是一次性替换底层 runner。本轮用可替换的本机隔离目录证明 API/DB/SSE/前端链路。
- 保持 P1/P2 共用 MessageList、ArtifactCard、RunService 是正确方向；分叉 UI 会让后续审批、Artifact 和取消链路维护成本翻倍。
- Cloud runtime 的第一风险不是“能不能启动进程”，而是上下文、Secret、日志、文件持久化、取消状态是否一致。

## 6. 下一步

Phase 11 应在 Phase 10 的 `workspaceId`、Artifact 和 runtime logs 基础上接入 Cloud Preview 与 Deployment：

- cloud Artifact preview URL。
- build/deploy pipeline 与部署日志。
- 发布 URL、重试、回滚。
- 生产级 runner/storage/KMS 的替换设计。
