---
name: agenthub-code-review
description: AgentHub 项目标准代码审查流程。当用户完成模块开发、说"审查一下"、"review"或准备提交前触发。检查：接口契约符合性、UX 状态覆盖、代码规则遵循、测试覆盖、Git 提交规范。
---

# AgentHub 标准代码审查流程

你正在对 AgentHub 项目进行代码审查。按以下清单逐项检查。

## 审查清单

### 1. 接口契约检查
- [ ] 后端适配器/Service 是否实现了对应的 Base 抽象类？
- [ ] 接口方法签名是否与 ADR-0005 中的契约一致？
- [ ] 新增的 API 端点是否在 Spec 中定义过？
- [ ] 前后端类型定义是否一致？（检查 TS interface ↔ Pydantic schema）

### 2. 类型安全检查
- [ ] Python：所有函数有类型注解吗？
- [ ] TypeScript：是否有 `any` 类型？（有则标记为违规）
- [ ] API 路由的请求体和响应体是否使用 Pydantic 模型？

### 3. 代码规则检查（对照 AGENTS.md）
- [ ] 单文件是否职责过多、难以测试或难以局部理解？如只是行数较长但职责清晰，不要求为行数硬拆
- [ ] API 路由是否做了参数校验（空消息 → 400，不存在的资源 → 404）？
- [ ] Python 路由是否全部使用 `async def`？
- [ ] 是否有硬编码的 API Key 或敏感配置？
- [ ] 是否出现了"可能以后用"的提前抽象？

### 4. UX 状态覆盖检查（对照 docs/testing/UX_TEST_SPEC.md）
- [ ] 每个新组件是否覆盖 6 种状态（空/加载/正常/完成/错误/边界）？
- [ ] 加载态：有明确的加载指示器（不是空白框）？
- [ ] 空状态：有引导文案（不是空白区域）？
- [ ] 错误态：中文错误信息 + 操作入口（重试/返回）？
- [ ] 流式过程中：输入框禁用 + 发送按钮禁用 + 打字指示器可见？
- [ ] IM 交互：会话置顶/归档/未读/免打扰/转发/多选是否有真实状态反馈、刷新恢复和错误态？

### 5. Spec 覆盖检查
- [ ] 正常流程是否完全实现？
- [ ] 每个异常场景（Spec 3.2 表格）是否有对应的错误处理？
- [ ] 边界条件是否处理？
- [ ] 没有实现任何 Spec 第 6 节标记为 Non-Goals 的功能？

### 6. 测试覆盖检查（对照 docs/TEST_PROTOCOL.md）
- [ ] 正常流程是否有 API 测试？
- [ ] 每个异常场景是否有测试？
- [ ] 测试能否独立运行（不依赖外部服务、Mock 了 Agent API）？
- [ ] SSE 相关代码是否有 JSON 合法性回归测试？
- [ ] 会话 IM 状态变更是否覆盖 API/Service/前端组件测试？

### 7. Git 提交规范检查（对照 docs/GIT_PROTOCOL.md）
- [ ] Commit 粒度合理吗（一件事，一个 commit）？
- [ ] Commit message 格式正确吗（type: 描述）？
- [ ] AI 提交是否带 `[ai]` 前缀？
- [ ] 是否有敏感文件被提交（`.env`、`node_modules` 等）？

## 输出格式

审查完成后，输出报告：

```

## Phase 7D 审计 (2026-06-07)

- 引用仍有效：`AGENTS.md`、`docs/TEST_PROTOCOL.md`、`docs/GIT_PROTOCOL.md`、`docs/testing/UX_TEST_SPEC.md` 均存在。
- 审查清单已补 IM 体验项：会话置顶/归档/未读/免打扰/转发/多选不能只检查 UI 展示，必须验证 API、持久化和刷新恢复。
- 后续审查 Phase 7D 相关代码时，需额外检查右键菜单 portal 层级、明亮主题纯白辅色、输入框外层透明和执行过程全屏弹窗。

## Phase 9 审计 (2026-06-08)

- 引用仍有效：`AGENTS.md`、`docs/TEST_PROTOCOL.md`、`docs/GIT_PROTOCOL.md`、`docs/testing/UX_TEST_SPEC.md`、`docs/specs/phase9/README.md` 均存在。
- 审查 Phase 9/后续 P2 代码时必须检查：local Project 是否仍不要求登录；cloud Project 是否通过 RBAC；API 是否用 camelCase alias；cloud 响应是否隐藏 `workspacePath`。
- Git 审查新增关注：Phase 9 验收截图位于 `e2e/screenshots/` 且被 `.gitignore` 排除，不应误提交截图、日志、数据库或真实用户 workspace 文件。

## Phase 10 审计 (2026-06-08)

- 引用仍有效：`AGENTS.md`、`docs/TEST_PROTOCOL.md`、`docs/GIT_PROTOCOL.md`、`docs/testing/UX_TEST_SPEC.md`、`docs/specs/phase10/README.md` 均存在。
- 审查 cloud runtime 代码时必须检查：用户可见 Agent 是否仍走真实 CLI/subprocess；`runtime_runs` 与兼容 `runs` 是否同步；`runtime_logs`、SSE、message metadata 是否脱敏。
- P1/P2 兼容新增关注：`runtimeMode=local` 不得要求 `sandboxId`；cloud UI 只能增量显示 runtime 信息，不能 fork MessageList/ArtifactCard。

## Phase 14 审计 (2026-06-09)

- 引用仍有效：`AGENTS.md`、`docs/TEST_PROTOCOL.md`、`docs/GIT_PROTOCOL.md`、`docs/testing/UX_TEST_SPEC.md`、`docs/specs/phase14/README.md` 均存在。
- 审查生产 Auth 代码时必须检查：生产配置不得接受 `x-agenthub-user-*` 开发请求头；token/refresh/logout 不暴露明文密钥或 refresh hash。
- 租户隔离新增关注：cloud 资源列表、详情、写入、删除、审批和转发必须经 `TenantScope` / `TenantGuard`，不能只保护 Project API。
## Code Review Report
- 模块: [名称]
- 审查人: AI (agenthub-code-review)

### 通过项 (N/7)
- [x] 接口契约检查: 通过
- [x] 类型安全检查: 通过
- [ ] 代码规则检查: 1 warning（见下）
- [x] UX 状态覆盖检查: 通过
- [x] Spec 覆盖检查: 通过
- [x] 测试覆盖检查: 通过
- [x] Git 提交规范: 通过

### Warnings
- [文件路径:行号] 问题描述 + 建议修复方案

### 结论
[APPROVED] / [CHANGES REQUESTED]
```
