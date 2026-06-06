# AgentHub v1.0.0 发布摘要

**日期**: 2026-06-07
**版本**: v1.0.0
**范围**: 本机 MVP 基线、Phase 1-7 已实现主能力、Phase 7D IM 与 UI 加固
**状态**: 发布准备完成；真实 Claude Code 完整自动化 E2E 作为后续增强项继续沉淀

本文件用于记录 v1.0.0 发布时的实现边界、验证状态和后续风险。长期规格仍以 [CONTEXT.md](../../../CONTEXT.md)、[Phase 7 Spec](../../specs/phase7/README.md) 和各 Phase deliverables 为准。

## 1. v1.0.0 发布范围

v1.0.0 是 AgentHub 的本机 MVP 基线版本，覆盖以下用户可见闭环：

- Project-first workspace：创建/绑定本机 workspace，并在 Project 下创建私聊/群聊。
- CLI Agent 执行：接入真实 Claude Code / Codex / OpenCode CLI 路径，保留执行轨迹。
- Artifact Bridge：CLI 输出、代码块和 workspace diff 可生成消息级 Artifact Card。
- Artifact 操作：文件预览、代码编辑、片段引用、版本管理和 diff 查看。
- 运行控制：run/task/process 状态持久化，支持取消真实 CLI 进程并释放输入框。
- 人工审批：Approval Card 支持确认继续、驳回并携带 Artifact/代码引用回流。
- 环境体检：统一检查 CLI、workspace、Node/Python、系统模型和活跃进程，发送前可阻断不可执行环境。
- IM 基线：会话搜索、置顶、归档箱、未读数、免打扰、最近活跃排序、右键菜单、转发、多选、完整时间戳。
- UI 加固：明亮主题纯白辅色、圆角卡片层级、透明输入框外层、执行过程全屏查看。

## 2. 本轮开发总结

本轮重点完成 Phase 7D 的 IM 软件增强项和 v1.0 视觉收敛：

- 后端扩展 `sessions` 状态字段：`is_pinned`、`archived_at`、`unread_count`、`last_read_at`、`is_muted`。
- 新增会话状态与转发 API：`PATCH /api/sessions/{id}`、`POST /api/sessions/{id}/read`、`POST /api/sessions/forward`。
- 前端会话列表增加置顶分组、归档入口、未读/免打扰徽标和搜索。
- 消息操作从 hover 工具条收敛为右键菜单，支持引用、重新生成、Pin、复制、转发、多选。
- 转发创建真实目标会话消息，并写入 `forwardSource` 快照。
- 消息气泡显示完整中国时区时间戳，Agent 名称标签去掉绿点和下边框。
- 明亮主题辅色改为纯白，输入框外层透明，项目栏/聊天栏形成飞书式圆角层级。
- `ExecutionTracePanel` 增加全屏弹窗，便于查看长执行过程。

## 3. 验证记录

本轮发布保留以下验证记录：

```powershell
cd backend
python -m pytest test_unit/ test_api/ -q

cd frontend
npx tsc --noEmit
npx vitest run
npm run build
```

截至本轮文档收尾，Phase 7D 交付快照已记录一次完整自动化回归：

- Backend: 272 passed
- Frontend typecheck: passed
- Frontend tests: 14 files / 70 tests passed
- Frontend build: passed；Vite 仅提示部分 chunk 超过 500 kB

最终提交前会重新运行回归命令，并以实际命令输出为准。

## 4. 未纳入 v1.0.0 的后续项

以下事项不伪装为已完成，继续作为 v1.0 后的增强和风险清单：

- 真实 Claude Code 完整自动化 E2E：Project → Claude Code → Artifact → 编辑/引用 → 审批 → 总结。
- UI 截图审计脚本：桌面/移动宽度下检查文字溢出、遮挡和弹窗裁剪。
- Store 领域拆分：继续将 session IM、runtime、approval、system、search 状态从较大的组件状态中拆出。
- 多端通知策略：未读数与免打扰当前是本机持久化 IM 状态，尚不包含多端推送。
- Artifact 级联转发：本轮转发文本消息快照，不做附件或 Artifact 递归转发。

## 5. 相关入口

- [Phase 7D IM 体验与 UI 加固交付文档](../phase7-im-hardening/README.md)
- [Phase 7 Runtime Control / Approval / Health 交付文档](../phase7-runtime-control/README.md)
- [Phase 6 Artifact Bridge 交付文档](../phase6-artifact-bridge/README.md)
- [Phase 7 Dev Log](../../dev-logs/phase7-dev-log.md)
