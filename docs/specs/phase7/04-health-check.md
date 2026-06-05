# Spec: Phase 7C — 环境体检卡片

**版本**: v1.0  
**创建日期**: 2026-06-03  
**状态**: Draft  
**关联**: [PRD-03](../../PRD/03-User_Experience.md) §3.1, [PRD-05](../../PRD/05-End_to_End_Product_Flow.md) §6  
**依赖**: Phase 6 Workspace Runtime + CLI Adapter, AgentConfig, 系统模型内部配置

---

## 1. 目标

在左侧栏底部展示 AgentHub 运行环境体检结果，让用户在发起复杂任务前知道 CLI 工具、Node/Python 运行时、workspace 是否可用。它是 MVP 演示稳定性的保障，也是非技术用户理解“为什么 Agent 不能执行”的第一入口。

DeepSeek 只作为后端内部系统模型能力检查项出现，用于标题生成、中枢总结、产物编辑辅助等后台能力；它不是用户可配置 Agent，也不进入 AgentPanel。

---

## 2. 全局链路定位

```text
系统启动 / 新建会话
  -> /api/system/health
  -> HealthCheckCard
  -> 用户修复 CLI/运行时/workspace
  -> Agent 执行链路可用
```

| 问题 | 回答 |
|------|------|
| 上游 | AgentConfig、可执行文件探测、运行时版本、workspace 状态、系统模型内部配置 |
| 下游 | HealthCheckCard 状态、AgentPanel 可用性提示、创建任务前告警 |
| 用户可完成任务 | 在发起任务前发现并修复缺失条件 |
| 不打通 | 自动安装依赖、系统级权限修复、云端沙盒检测 |

---

## 3. API

```
GET /api/system/health
  → 200 {
    "overall": "ok" | "warning" | "error",
    "items": [
      {
        "key": "system_model_deepseek",
        "label": "System model: DeepSeek",
        "status": "ok",
        "detail": "configured internally"
      },
      {
        "key": "claude_cli",
        "label": "Claude Code CLI",
        "status": "missing",
        "detail": "executable not found in PATH"
      }
    ]
  }
```

### 3.1 检测项

| key | 检测方式 | 状态 |
|---|---|---|
| `system_model_deepseek` | 检查后端内部 DeepSeek 配置，不向用户暴露密钥 | ok/warning |
| `claude_cli` | `where claude` / configured executable path | ok/missing/error |
| `codex_cli` | `where codex` / configured executable path | ok/missing/error |
| `opencode_cli` | `where opencode` / configured executable path | ok/missing/error |
| `python_runtime` | `python --version` 或当前后端解释器 | ok/error |
| `node_runtime` | `node --version` | ok/missing |
| `workspace_path` | 会话 workspace 是否存在且可写 | ok/error |

---

## 4. 前端行为

### 4.1 HealthCheckCard

- 常驻左侧栏底部。
- 默认折叠，只显示 overall 状态和 1 行摘要。
- 点击展开后显示检测项列表。
- `ok` 用绿色状态点，`warning` 用黄色，`error/missing` 用红色。
- 对缺失 CLI 的项，提供“去配置”入口，跳转 AgentPanel。
- DeepSeek 内部配置缺失只显示系统能力降级提示，不提供用户 Agent 配置入口。

### 4.2 新建任务前告警

- 如果用户选择 CLI Agent，但对应 CLI 状态为 `missing/error`，创建会话弹窗显示阻断提示。
- 不存在 HTTP Agent 降级路径；真实 CLI 不可用时，用户聊天 Agent 执行应被阻断并给出本机安装/登录提示。

---

## 5. 验收标准

- [ ] 左侧栏底部显示整体健康状态。
- [ ] DeepSeek 内部配置缺失时，只提示标题/总结/编辑辅助能力降级，不暴露密钥输入。
- [ ] 缺失 CLI 工具时，CLI Agent 在 AgentPanel 中标记不可用。
- [ ] Node/Python/workspace 检测结果展示清晰。
- [ ] 新建 CLI 会话前会阻断或提示缺失条件。
- [ ] 健康检查失败不会导致主页面白屏。

---

## 6. 测试

- API: mock PATH/env，覆盖 ok/missing/error。
- Component: 折叠/展开、状态颜色、跳转按钮。
- E2E: 缺 CLI 时创建 CLI Agent 会话显示阻断提示；无 HTTP Agent 降级入口。

---

## 7. Non-Goals

- 不自动安装 CLI 或 Node。
- 不保存用户系统凭据。
- 不检测 Docker 沙盒池，MVP 默认宿主机环境。
