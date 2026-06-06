# CLI Adapter 使用指南

**日期**: 2026-06-05
**读者**: AgentHub 用户与开发者
**适用范围**: Claude Code、Codex、OpenCode 本机 CLI Agent

## 1. 用户指南

### 1.1 前置条件

请先在本机安装并认证你要使用的 CLI 工具：

| Agent | 可执行命令 | 认证方式 |
|-------|------------|----------|
| Claude Code | `claude` | 使用 Claude Code 官方本机登录/认证流程。 |
| Codex | `codex` | 使用官方 OpenAI 配置，或通过 AgentHub 配置第三方中转。 |
| OpenCode | `opencode` | 使用 OpenCode 本机配置/认证流程。 |

AgentHub 不负责安装这些 CLI。它只检测并运行用户本机已有的命令。

### 1.2 创建或选择 Project

1. 打开 AgentHub。
2. 在 workspace 侧边栏创建空项目，或选择一个已有文件夹。
3. AgentHub 会把该 Project 绑定到本机 `workspacePath`。
4. 该 Project 下的所有聊天都会在这个目录里启动 CLI 进程。

这意味着 Agent 生成和修改的文件是真实落在你电脑上的。

### 1.3 配置 CLI Agent

从侧边栏的 Agent 好友设置进入配置弹窗。

常见字段：

| 字段 | 含义 |
|------|------|
| CLI 工具 | Claude Code、Codex、OpenCode 或 custom。 |
| 可执行文件 | 命令或可执行路径，例如 `codex`。 |
| 启动参数 | AgentHub 启动 CLI 时传入的参数。内置 Agent 已提供默认值。 |
| 环境变量 | 高级覆盖项。Codex API Key 不建议作为普通 Agent env vars 配置。 |

配置后可以点击检测按钮，确认 AgentHub 能找到对应命令。

### 1.4 配置 Codex 官方或中转模式

Codex 有额外的连接配置区域。

官方 OpenAI 模式：

- Base URL 默认是 `https://api.openai.com/v1`；
- 可以填写 OpenAI API Key；
- 如果本机 Codex 支持，也可以继续使用本机 ChatGPT auth。

中转模式：

- 填写第三方中转站 Base URL；
- AgentHub 会尽量将 URL 规范化为 OpenAI-compatible `/v1` API 端点；
- 填写中转 API Key；
- AgentHub 会把 key 写入本机 Codex `.env`，通常是 `~/.codex/.env`，变量名为 `CODEX_API_KEY`；
- AgentHub 会更新 `~/.codex/config.toml`，让 provider 使用 command-backed auth helper 从 `.env` 按需读取 key；本机新开的 Codex 会话不需要全局 `CODEX_API_KEY` 环境变量。

注意：中转模式不能使用本机 ChatGPT token。如果中转站返回 `401 Unauthorized`，请重新打开 Codex 设置并更新中转 API Key。

### 1.5 发起聊天

1. 选择一个 Project。
2. 点击 CLI Agent 好友并发起私聊，或创建群聊。
3. 输入 prompt 并发送。
4. AgentHub 会在 Project workspace 中启动真实 CLI 进程。
5. Agent 回复会显示为聊天气泡。
6. 执行过程会显示在气泡下方的可折叠流程块中。

Agent 工作时，界面会定位到用户新发送的消息，而不是强制滚到 Agent 输出末尾。执行流程块有自己的滚动区域，长过程不会把整个聊天窗口拖到底。

### 1.6 阅读执行流程块

执行流程块会随消息一起保存。它可能包含：

- 进程启动和结束；
- 执行命令；
- 工具名；
- 目标文件或路径；
- 有意义的 CLI stderr 警告；
- 交互式确认提示；
- Artifact 或 diff 信号。

回复完成后，流程块可以自动折叠，让对话保持可读。

### 1.7 常见问题

| 现象 | 可能原因 | 处理方式 |
|------|----------|----------|
| `未找到 'codex' 命令` | executable 不在 PATH 中。 | 安装 CLI，或在 Agent 设置里填写完整 executable 路径。 |
| Codex 中转 URL 返回 `401 Unauthorized` | 中转 API Key 缺失或失效。 | 在 AgentHub 的 Codex 设置里重新保存中转 API Key。 |
| Codex 输出 HTML 页面 | Base URL 指向网页首页，不是 API 端点。 | 使用中转站 API Base URL，通常以 `/v1` 结尾。 |
| 进程已结束但气泡仍等待回复 | SSE/message finalization 或 parser completion 识别异常。 | 查看后端日志和 `/api/agents/runtime/processes`，再跑对应 CLI smoke。 |
| 执行流程细节太少 | 当前 parser 还不理解该 CLI 的具体输出格式。 | 用真实输出样本补 parser fixture，再扩展 `cli_trace.py` / `cli_adapters.py`。 |

## 2. 开发者指南

### 2.1 主要 API

| 端点 | 方法 | 作用 |
|------|------|------|
| `/api/agents` | GET | 列出活动 CLI Agent。 |
| `/api/agents` | POST | 创建 CLI Agent。 |
| `/api/agents/{agentId}` | PATCH | 更新 CLI Agent。 |
| `/api/agents/{agentId}` | DELETE | 软删除/归档 CLI Agent。 |
| `/api/agents/check-executable?path=...` | GET | 检查 CLI executable 是否可用。 |
| `/api/agents/codex-config` | GET | 读取本机 Codex 连接状态。 |
| `/api/agents/codex-config` | PUT | 写入或修复本机 Codex 官方/中转配置。 |
| `/api/agents/runtime/processes` | GET | 查看活动 CLI 进程，可按 `sessionId` 过滤。 |
| `/api/sessions/{sessionId}/chat` | POST | 发起流式聊天执行。 |
| `/api/sessions/{sessionId}/interactive_reply` | POST | 对等待中的 CLI prompt 回复 `y` 或 `n`。 |

### 2.2 Agent 配置示例

```json
{
  "name": "Codex",
  "description": "OpenAI Codex CLI",
  "agentType": "cli_wrapper",
  "cliTool": "codex",
  "executable": "codex",
  "initArgs": [
    "exec",
    "--skip-git-repo-check",
    "--dangerously-bypass-approvals-and-sandbox",
    "--color",
    "never",
    "--json",
    "-"
  ],
  "envVars": {}
}
```

Codex 中转密钥优先使用 `/api/agents/codex-config` 配置，不要塞进普通 `envVars`。

### 2.3 新增一个 CLI Adapter

1. 在 `backend/app/agents/cli_defaults.py` 增加默认配置；
2. 在 `backend/app/agents/cli_adapters.py` 实现专属 adapter；
3. 注册到 `_ADAPTERS`；
4. 在 `backend/app/agents/cli_trace.py` 增加轨迹解析 helper；
5. 用真实输出样本补 parser/runtime 单元测试；
6. 如果要成为一等好友，在前端补 preset 和 avatar；
7. 补充真实本机 CLI smoke 验证说明。

进程生命周期逻辑应留在 `CliProcessManager`，CLI 特有语义应留在 adapter 和 trace parser。

### 2.4 本地验证命令

后端：

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest test_api/ test_unit/test_cli_adapter_runtime.py test_unit/test_codex_local_config_service.py -q
```

前端：

```powershell
cd frontend
npm run build
npx vitest run
```

真实本机 smoke 需要本机已安装并认证对应 CLI：

```powershell
cd backend
.\venv\Scripts\python.exe test_real_api_claude_smoke.py
.\venv\Scripts\python.exe test_real_api_claude_artifact_bridge.py
.\venv\Scripts\python.exe test_real_api_codex_smoke.py
.\venv\Scripts\python.exe test_real_cli_smoke.py
```

不要把 mock CLI 测试当作该模块的最终验收。mock 测试适合回归，但验收必须接真实本机 CLI。

`test_real_api_claude_artifact_bridge.py` 会通过 AgentHub 真实服务路径调用 Claude Code，在临时 workspace 写入 `index.html`、`package.json`、`src/App.tsx`，并断言最终 `done` 前已经创建 `web_preview`、`file_tree`、`code_diff` Artifact。
