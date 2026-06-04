# Phase 6 Dev Log

**状态**: 进行中  
**当前完成切片**: Phase 6A — Workspace Runtime  
**验收日期**: 2026-06-04  
**人工验收**: 已通过

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

Phase 6 仍未完成：

- 6B-6E：Claude Code / Codex / OpenCode CLI Adapter、PTY/subprocess 管理、ANSI 清洗、交互提示拦截。
- 6F：Agent 输出与 workspace diff 转 `artifact.detected`，再由 ArtifactService 创建 Artifact。
- Phase 7：Artifact Drawer、审批卡片、环境体检和端到端演示闭环。

下一步建议从 [Phase 6B-6E CLI Adapter Spec](../specs/phase6/01-cli-adapter.md) 开始，直接消费已验收的 `Session → Project.workspace_path` 能力。
