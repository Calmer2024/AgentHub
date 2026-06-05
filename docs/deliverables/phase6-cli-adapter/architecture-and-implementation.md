# CLI Adapter 架构与技术实现原理

**日期**: 2026-06-05
**状态**: 实现基线
**主要代码路径**: `backend/app/agents/`、`backend/app/services/*cli*`、`frontend/src/components/*Agent*`、`frontend/src/components/ExecutionTracePanel.tsx`

## 1. 设计定位

AgentHub 现在将用户可见的 Agent 定义为本机 CLI 好友。产品内置的好友是 Claude Code、Codex、OpenCode。旧版本中的 API 伪 Agent、厂商配置、默认角色助手、用户可见模型/temperature 配置都已退出主流程。

DeepSeek 仍可作为产品内部系统模型，用于自动生成会话标题、群聊最终总结等后端能力。它不是用户可选择、可聊天的 Agent 好友。

核心链路是：

```text
Project -> Session -> CLI Agent process
```

每个 Session 必须归属于一个 Project。CLI 进程启动时使用 `cwd = Project.workspace_path`，因此 Agent 创建和修改的文件会真实落在用户选择的本机项目目录里。

## 2. 运行流程

```text
POST /api/sessions/{sessionId}/chat
  -> ChatServiceImpl
  -> SingleCliChatStream 或 GroupChatStream
  -> CliAgentService
  -> 对应 CLI Adapter
  -> CliProcessManager
  -> 在 Project workspace 中启动真实 subprocess
  -> stdout/stderr pump
  -> StreamSanitizer
  -> PromptInterceptor
  -> CliOutputParser
  -> ParsedOutput + trace metadata
  -> SSE 推送到前端
  -> MessageBubble + ExecutionTracePanel
  -> 写入 message metadata 持久化
```

Adapter 层不直接创建业务 Artifact。它负责输出文本、过程、错误、交互确认和产物信号。Artifact 的落库与卡片创建仍由 Artifact Bridge 和 ArtifactService 负责。

## 3. 后端组件

| 组件 | 职责 |
|------|------|
| `backend/app/services/agent_seed.py` | 启动时种子化三个内置 CLI Agent，并归档非 CLI 的历史 Agent。 |
| `backend/app/services/cli_agent_registry.py` | 校验 CLI Agent 配置，检查 executable，序列化/反序列化 args/env，并避免普通 API 响应泄漏敏感环境变量。 |
| `backend/app/services/cli_agent_service.py` | 将聊天上下文渲染为 CLI prompt，并交给对应 adapter 执行。 |
| `backend/app/services/single_cli_chat_stream.py` | 负责单聊消息持久化、SSE 流式输出与执行轨迹 metadata。 |
| `backend/app/services/cli_agent_executor.py` | 让群聊和 Orchestrator 复用同一套 CLI Agent 执行能力。 |
| `backend/app/services/artifact_output_bridge.py` | CLI 消息完成后扫描回复、执行轨迹和 workspace diff，生成 Artifact 候选并交给 ArtifactService。 |
| `backend/app/services/artifact_service.py` | 负责 Artifact 版本链、Diff、编辑和从 bridge detection 幂等创建 v1 Artifact。 |
| `backend/app/agents/cli_runtime.py` | 管理真实进程创建、cwd 校验、stdin 写入、stdout/stderr 读取、进程注册表、超时、交互回复和终止。 |
| `backend/app/agents/cli_adapters.py` | 实现基础 adapter，以及 Claude Code、Codex、OpenCode 的专属适配逻辑。 |
| `backend/app/agents/cli_output_parser.py` | 保存单次执行的 parser 状态，处理 JSONL、raw fallback、HTML 错误压缩和 stderr 噪声过滤。 |
| `backend/app/agents/cli_stream.py` | 清理 ANSI/TUI 控制字符，并识别交互式确认提示。 |
| `backend/app/agents/cli_trace.py` | 将 CLI 特有事件转为结构化执行轨迹，供前端精致渲染。 |
| `backend/app/services/execution_trace.py` | 构建并裁剪 `message.metadata.executionTrace`，防止单条消息 metadata 膨胀。 |
| `backend/app/agents/codex_config.py` | 从 `CODEX_HOME` 或 `~/.codex` 检测本机 Codex 官方/中转配置。 |
| `backend/app/services/codex_local_config_service.py` | 通过 AgentHub UI 修复和写入本机 Codex `config.toml` 与 `.env`，避免让用户手动改文件。 |

## 4. 前端组件

| 组件 | 职责 |
|------|------|
| `AgentAvatar.tsx` | 为 Claude Code、Codex、OpenCode 和自定义 CLI Agent 提供一致头像。 |
| `AgentCliForm.tsx` | CLI Agent 设置弹窗，包含 executable 检测、默认参数、Codex 官方/中转配置。 |
| `AgentCliRow.tsx` | 好友列表行，展示状态、操作入口和设置入口。 |
| `ExecutionTracePanel.tsx` | 在回复气泡下方渲染过程、工具、命令、错误和产物信号；支持折叠和独立滚动。 |
| `MessageBubble.tsx` | 渲染 Markdown 回复气泡、Agent 头像、执行轨迹、消息操作、引用上下文和消息级 ArtifactStrip。 |
| `MessageArtifactStrip.tsx` | 按 messageId 展示扫描中、失败、低置信候选，并在消息下方渲染 ArtifactCard 卡片流。 |
| `ArtifactCard.tsx` | 消息级产物卡片，支持 web/code/document/file_tree 预览、hover diff 和完整弹窗。 |
| `DiffViewer.tsx` | VS Code/GitHub 风格统一 diff 表格，取消左右/上下模式切换。 |
| `ChatWindow.tsx` | 负责接近 Telegram 的聊天界面、用户新消息定位和 Agent 工作状态。 |
| `useSendMessage.ts` | 消费 SSE 事件，将文本流式写入气泡，持久化执行轨迹，upsert Artifact，并避免长任务期间强制滚到底部。 |

## 5. 数据模型

`agent_configs` 已改为 CLI-first：

| 字段 | 含义 |
|------|------|
| `agent_type` | 用户可见 Agent 应为 `cli_wrapper`。 |
| `cli_tool` | `claude_code`、`codex`、`opencode` 或 `custom`。 |
| `executable` | 命令名或可执行文件路径，例如 `claude`、`codex`、`opencode`。 |
| `init_args` | JSON 数组形式的启动参数。 |
| `env_vars` | JSON 对象形式的高级运行时覆盖。Codex API Key 不作为普通 Agent 配置暴露。 |
| `is_active` | 软删除/归档标记。 |

执行轨迹会持久化到消息 metadata：

```json
{
  "executionTrace": {
    "status": "running|completed|failed",
    "agentName": "Codex",
    "cliTool": "codex",
    "workspacePath": "D:/...",
    "processId": "cli_...",
    "exitCode": 0,
    "items": [
      {
        "kind": "tool|command|process|error|artifact",
        "text": "...",
        "command": "...",
        "target": "...",
        "timestamp": "..."
      }
    ]
  }
}
```

轨迹条目数量和文本长度都有上限，避免单次 CLI 执行撑爆消息记录。

## 6. 各 CLI 适配策略

### Claude Code

默认命令：

```text
claude -p --verbose --output-format stream-json --include-partial-messages --dangerously-skip-permissions
```

Claude Code 会输出包含 assistant 内容、thinking、tool use、tool result 和 result 的 JSON 事件。Adapter 将 assistant 文本映射为回复流，将工具和思考过程映射为执行轨迹。

### Codex

默认命令：

```text
codex exec --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox --color never --json -
```

Codex 需要额外处理，因为用户本机 Codex 可能使用官方 OpenAI，也可能使用第三方 OpenAI-compatible 中转。AgentHub 会检测 `~/.codex/config.toml`、`~/.codex/auth.json`、`~/.codex/.env`、`CODEX_HOME` 和当前进程环境变量。

当 AgentHub 检测到官方或中转配置时，会在运行 Codex 时注入 `--ignore-user-config` 和显式 `-c` 配置。这样既能复用本机可用的连接信息，又能避免旧 profile、错误 provider、HTML 首页或模型列表噪声污染聊天输出。

中转模式必须有中转 API Key。ChatGPT 登录 token 不能用于第三方中转站。AgentHub UI 会把稳定密钥写入 `CODEX_HOME/.env`，并让对应 provider 使用 command-backed auth helper 从 `.env` 按需读取密钥。这样本机 Codex 新会话不依赖 Windows 全局环境变量，也不会被 `auth.json` 后续变成 token 的行为影响。

### OpenCode

默认命令：

```text
opencode run --pure --agent build --format json --dangerously-skip-permissions
```

OpenCode 会规整掉旧的不兼容参数模式。Adapter 会在需要时把用户 prompt 作为 run 参数传入，并解析 JSON part 中的文本、工具调用和 step 事件。

## 7. 进程生命周期

`CliProcessManager` 负责生命周期边界：

- 校验 workspace 存在且是目录；
- 兼容 Windows `.cmd`、`.bat`、`.ps1` 启动方式；
- 构造干净 CLI 环境，并设置 `NO_COLOR=1`、`TERM=dumb`；
- 在 pipe stdin 模式下写入 prompt；
- 并发读取 stdout 和 stderr；
- 发送 process started/completed/timeout 事件；
- 按 session 维护 active process snapshot；
- 支持 `POST /api/sessions/{id}/interactive_reply` 写回 `y`/`n`；
- 对静默超时进程执行终止。

这个服务只处理进程 I/O 和生命周期。每个 CLI 输出的语义解释留在 adapter 与 parser 中。

## 8. 输出与执行轨迹策略

CLI 原始输出不会直接作为一大坨文本展示给用户，而是拆成四层：

- 回复文本：进入 Agent 气泡，按 Markdown 渲染；
- 过程轨迹：进入气泡下方的执行流程块；
- 交互提示：进入确认卡片；
- 产物信号：进入 Artifact Bridge，与 workspace diff 和消息代码块一起创建 Artifact。

执行流程块的目标是比终端日志更好读。只要 CLI 暴露了命令、工具名、目标路径、stderr 信号或 provider 细节，就尽量在结构化轨迹中呈现。

## 9. 配置与密钥处理

AgentHub 刻意区分“用户可见 Agent 身份”和“提供商密钥”：

- Claude Code 和 OpenCode 主要继承用户本机 CLI 登录态；
- Codex 官方模式可使用 OpenAI API Key，也可在兼容时使用本机 ChatGPT auth；
- Codex 中转模式必须使用中转 API Key；
- Codex API Key 写入 `CODEX_HOME/.env`，通常是 `~/.codex/.env`；
- 当前 provider 在 `config.toml` 中使用 command-backed auth helper，不写内联密钥，也不要求全局 `CODEX_API_KEY`；
- 前端 API 响应只展示“是否已配置 key”，不返回密钥明文。

## 10. Artifact Bridge 当前状态

6F 核心闭环已落地：

- 单聊 CLI 完成后，在最终 `done` 前扫描 workspace snapshot diff、消息代码块和执行轨迹；
- `web_preview`、`file_tree`、`code_diff`、`document` 四类 Artifact 统一进入 ArtifactService 创建；
- 低置信候选写入 message metadata，不污染用户的产物列表；
- `POST /api/messages/{messageId}/artifacts/scan` 支持手动重扫，且对同一 message/file/hash 幂等；
- 前端通过 `artifact.scan.*` 和 `artifact.created` 更新消息下方的 MessageArtifactStrip/ArtifactCard；
- 独立产物工作台已移除，文件变更行 hover 展示具体 diff，点击卡片弹窗展示完整 diff；
- 真实 Claude Code 服务验收脚本 `backend/test_real_api_claude_artifact_bridge.py` 已通过。

## 11. 当前剩余风险

- 三个 CLI 的执行轨迹解析仍需要持续补充真实 stdout/stderr fixture，特别是命令和文件操作细节；
- 长任务取消应成为一等 UI 操作，而不只是后端运行时能力；
- 群聊并行 workspace diff 的“每个文件由哪个 Agent 写入”不能完全从共享文件系统推断，当前只自动扫描每个 Agent 子消息的文本/代码块，避免把共享 diff 误挂到总结消息；
- 真实 smoke 依赖用户本机 CLI 安装和认证状态，CI 暂时只能覆盖 parser/runtime fixture，除非准备专用 runner。
