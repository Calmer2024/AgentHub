# Phase 6 Dev Log

**状态**: 进行中
**当前完成切片**: Phase 6A — Workspace Runtime；6B-6E CLI Adapter 实现基线
**最近更新**: 2026-06-05
**人工验收**: 6A 已通过；OpenCode 人工验收通过；Claude Code / Codex 真实链路已完成阶段性 smoke

---

## 1. Phase 6A 完成内容

Phase 6A 解决“Agent 到底在哪个目录执行”的底座问题，并把旧的 Session→Workspace 模型切换为 Project-first 模型。

已落地：

- 新增 `Project` 实体与 `projects` 表，Project 绑定唯一 `workspace_path`。
- `sessions.project_id` 接入 Session 创建与列表过滤，Session 通过 Project 继承 workspace。
- `artifacts.project_id / file_path / preview_id / source / confidence / task_id` 兼容字段已迁移。
- 新增 Project API：创建、列表、详情、归档、文件树、文件读取、snapshot、diff、static preview、build started。
- 新增 `/api/projects/pick-folder`：由本机后端打开系统原生目录选择器，返回一次性 `folderToken`。
- 新增 `/api/sessions/{id}/workspace`：返回 Session 继承的 `workspacePath`，供后续 CLI Adapter 作为 cwd。
- 新增 `LocalWorkspaceProvider`：负责目录创建、`.agenthub/project.json` 初始化、路径越界校验、文件树过滤、文本文件读取大小限制。
- 新增 `FileChangeDetector`：用 snapshot + hash diff 检测 created/modified/deleted。
- 新增 `PreviewService`：MVP 静态 `index.html` 预览 URL。
- 前端改为 Codex/Telegram 风格三栏：项目栏、会话列表栏、聊天区。
- 创建项目按钮弹出菜单：`新建空白文件夹` / `选择现有文件夹`。
- 移除用户可选的 `静态网页 / Vite React / 已有项目` 项目属性；`project_type` 只作为数据库兼容字段保留。

---

## 2. 关键决策

- Project 是用户心智入口，Session 是 Project 下的聊天上下文。
- 选择已有文件夹必须使用系统目录选择器授权，不让用户手输路径。
- 默认新建空白文件夹时，后端在 `AGENTHUB_WORKSPACE_ROOT` 下分配目录名。
- 目录安全边界由后端统一执行：workspace 内相对路径、禁止绝对路径、禁止 `../` 越界。
- Phase 6A 只提供运行时底座，不执行真实 CLI，不自动创建 Artifact Card。

---

## 3. 验收与测试入口

已覆盖的测试入口：

```bash
cd backend && python -m pytest test_api/test_projects_phase6.py -v
cd frontend && npx vitest run src/components/ProjectSidebar.test.tsx
```

人工验收关注点：

- UI 设计调整为接近 Codex 客户端和 Telegram 的三栏工作区。
- 创建项目按钮弹出列表，包含 `新建空白文件夹` 与 `选择现有文件夹`。
- `选择现有文件夹` 调起系统目录选择器。
- 项目创建流程不再要求用户选择“静态网页 / Vite React / 已有项目”。

---

## 4. 剩余边界

Phase 6 剩余边界：

- 6B-6E：继续扩充真实 CLI 输出 fixtures，让 Claude Code / Codex / OpenCode 的执行轨迹更完整地呈现具体命令、文件路径、工具参数与 stderr 信号。
- 6F：Agent 输出与 workspace diff 转 `artifact.detected`，再由 ArtifactService 创建 Artifact。
- Phase 7：Artifact Drawer、审批卡片、环境体检和端到端演示闭环。

下一步建议优先从 [Phase 6B-6E CLI Adapter Spec](../specs/phase6/01-cli-adapter.md) 与 [CLI Adapter 交付快照](../deliverables/phase6-cli-adapter/README.md) 开始，继续围绕真实 CLI 输出样本补强解析和 Artifact Bridge。

---

## 5. Phase 6B 进展（2026-06-04）

本轮开始接入真实本机 CLI 工具：

- 新增 CLI Wrapper Agent 配置字段与迁移：`agent_type / cli_tool / executable / init_args / env_vars`。
- 启动时 seed 三个内置 CLI Agent：Claude Code、Codex、OpenCode；只对旧内置默认参数做安全升级，不覆盖用户手动配置。
- 单聊路径改为 `Session → Project.workspace_path → CliAgentService → Per-CLI Adapter → subprocess`，后端不再把 CLI 私聊路由到旧 HTTP Agent 执行路径。
- 群聊执行器在有 workspace 时通过 `CliAgentCallRunner` 执行 CLI Agent，Orchestrator 中枢总结走 DeepSeek 系统模型。
- 拆出真实进程 runtime、输出清洗、交互提示识别、JSONL 输出 parser 和 per-CLI adapter；拆分依据是职责边界，不是行数硬限制。
- 前端 AgentPanel 改为 CLI 工具配置：executable 检测、默认参数、env vars、好友列表发起对话、progress 状态条、interactive prompt 卡片。
- 真实 Claude Code 链路已通过：当前服务 `/api/sessions/{id}/chat` 使用内置 Claude Code 默认参数（`-p --verbose --output-format stream-json --include-partial-messages --dangerously-skip-permissions`），在 Project workspace 写入目标文件。
- Codex 链路的 401 根因已定位：用户级 `~/.codex/config.toml` 将默认 OpenAI provider 指向旧第三方 gateway。AgentHub 内置 Codex 默认参数已加入 `--ignore-user-config`，保留本机 Codex auth 但隔离用户级 provider/profile 污染；直接 smoke 已验证该模式能写入 workspace 文件。
- 新增 `013_rebuild_agent_configs_cli_only.sql`，将本地 `agent_configs` 表收敛为当前 CLI Agent schema，移除旧 `provider/model/temperature` 列，并清理旧默认助手/角色助手配置记录；启动后好友列表只保留 Claude Code、Codex、OpenCode 三个 CLI Agent。

已执行验证：

```bash
cd backend && .\venv\Scripts\python.exe -m pytest test_api/ test_unit/test_cli_adapter_runtime.py -q
cd frontend && npx tsc --noEmit
cd frontend && npx vitest run
cd frontend && npm run build
cd backend && .\venv\Scripts\python.exe test_real_api_claude_smoke.py
cd backend && .\venv\Scripts\python.exe test_real_api_codex_smoke.py
```

---

## 6. Phase 6B-6E 实现基线（2026-06-05）

本阶段把 CLI Adapter 从“计划中的抽象接口”推进到可运行的本机 CLI Agent 基线：

- 清理旧版本 API 伪 Agent 的活动路径：旧 provider adapter、provider/settings API、默认角色助手、用户可见模型综合配置面板均退出主流程。
- 保留 DeepSeek 作为内部系统模型，用于自动标题、群聊最终总结等产品内部能力，不作为用户好友暴露。
- 真实本机 CLI 执行统一进入 `Project → Session → CliAgentService → Per-CLI Adapter → CliProcessManager`。
- `CliProcessManager` 负责 subprocess 生命周期、workspace cwd、stdin/stdout/stderr、Windows `.cmd/.bat/.ps1` 兼容、进程快照、超时和交互式回复。
- Claude Code / Codex / OpenCode 各自拥有专属解析路径；执行过程进入 `message.metadata.executionTrace`，前端在回复气泡下方渲染可折叠、可独立滚动的执行流程块。
- Codex 支持官方 OpenAI 与第三方中转 API；AgentHub 能检测 `CODEX_HOME` / `~/.codex`，并通过 UI 写入 `config.toml` 与 `.env`，避免要求用户手动编辑本机配置文件。
- OpenCode 接入完成真实人工验收，修复了早期参数模式导致“进程结束但气泡等待回复”的问题。
- 前端完成 Agent 设置弹窗、CLI 好友头像、Telegram 风格对话气泡、滚动条、Markdown、搜索/引用/操作与项目删除/重命名等一轮 UI 整体优化。
- 新增阶段交付文档目录：[docs/deliverables/phase6-cli-adapter](../deliverables/phase6-cli-adapter/README.md)。

当前仍需继续推进：

- 6F Artifact Bridge：让代码块、workspace diff、artifact signal、Artifact Card 形成稳定端到端闭环。
- 执行轨迹细节：持续收集真实 Claude Code / Codex / OpenCode stdout/stderr，把命令、工具参数、目标文件路径和执行结果展示得更具体。
- 前端进程控制：为长任务补充显式取消/终止入口。
- 真实 smoke 标准化：每次验收记录 CLI 版本、认证模式、workspace 文件断言与失败日志。
