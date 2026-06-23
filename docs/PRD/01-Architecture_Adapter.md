# 需求规格说明书 (PRD)：01 - 底层适配器架构决策 (CLI Adapter Architecture)

## 1. 文档定位
本文档为 AgentHub 的底层核心通信层设计规范，主要面向**系统架构师**、**后端核心研发人员**。
本章节将详细论述 AgentHub 如何摒弃传统的”裸调 HTTP LLM API”的伪 Agent 模式，转而利用操作系统底层进程管理技术，直接封装 Anthropic 官方的 `claude` CLI、OpenAI 的 `codex` CLI、开源的 `opencode` 三个真实物理工具。涵盖：通用进程管理层（PTY/subprocess、ANSI 清洗、交互拦截）、每个 CLI 的专属适配策略（各自理解其输出格式和交互模式）、分层渲染方案（文本/进度/产物/交互 → 前端不同渲染形态）。这是本课题取得高分、实现工业级”Agent-as-a-Service”的关键基石。

> **2026-06-05 口径修订**：本 PRD 中的 CLI 工具应理解为 **Engine**，而不是用户最终调度的 Agent 本体。用户可见 Agent Profile = Engine + Toolset + Context Policy + Runtime Config。详见 [ADR-0011 Agent = Engine + Toolset 建模](../archive/adr/0011-agent-engine-skill-model.md)。

---

## 2. 核心架构冲突与路线选择 (Architecture Pivot)

### 2.1 传统方案的局限性 (The "Fake Agent" Problem)
在项目初期的 `ADR-0005` 设想中，系统通过一个名为 `BaseAgentAdapter` 的基类，向 OpenAI 或 Anthropic 发送带有 `tools` 参数的 HTTP 请求。
**致命痛点**：
1. **造轮子成本极高**：后端需要自己实现一个庞大的 `while True` 循环来解析 `tool_calls`，还需要自己在服务器上跑 Docker 沙盒去执行模型生成的 Python 代码。
2. **脱离主流开源生态**：目前市面上最强悍的代码 Agent 工具（如 Claude Code、SWE-Agent）本身就是高度封装好的本地命令行程序。如果不用它们，等同于放弃了业界最先进的 Agent 执行逻辑。
3. **违反课题初衷**：课题明确要求“接入市面主流 Agent 平台（Claude Code 等）”。

### 2.2 确立 CLI 挂载模式 (The CLI-Wrapper Pattern)
经需求对齐，系统后端必须转向**“多进程管家模式（Process Manager）”**。
AgentHub 后端（FastAPI）不再负责思考“怎么写代码”，它只负责两件事：
1. **进程启停**：在操作系统的后台，静默启动这些原生的终端黑框框（CLI）。
2. **I/O 桥接**：截获黑框框里吐出的文字（stdout），通过 WebSockets/SSE 推给前端；把前端用户打的字，以流的形式塞回黑框框的输入流（stdin）。

---

## 3. 核心机制详细设计 (Detailed Mechanism Design)

### 3.1 伪终端 (PTY) 与 Subprocess 管理
由于诸如 `claude` 这种 CLI 工具在设计时是针对人类交互的，它们常常会检测当前的运行环境是否为一个真正的终端（TTY）。如果使用普通的 `subprocess.Popen`，可能会导致工具直接退出或拒绝响应互动式按键。

*   **技术选型**：在 Unix 系统下，强烈推荐使用 Python 标准库 `pty` 或第三方库 `pexpect` 来孵化进程。在 Windows 平台下，可使用 `winpty` 或 `subprocess` 的高级封装。
*   **启动参数 (Init Args)**：为了让 CLI 更适合被代码包裹，必须在数据库的 `agents` 表中维护每个工具的最优启动参数。
    *   例如 Claude Code：`["--compact", "--theme=light"]`，尽量减少无用的 UI 渲染符号。
*   **上下文环境隔离 (Environment Variables)**：
    为防止串联污染，每次启动 CLI 进程时，必须重新构造 `env` 字典。用户可见 Agent 配置不接收厂商 API Key；Claude Code / Codex / OpenCode 的认证来自用户本机 CLI 登录态。DeepSeek API Key 仅作为后端内部系统模型配置读取，不进入 Agent env。

### 3.2 标准输入输出的重定向与清洗 (I/O Redirection & ANSI Stripping)
CLI 工具吐出的文字绝对不是纯净的纯文本，而是充满了用于在终端里画表格、画颜色的 ANSI 转义控制符（ANSI Escape Codes）。

*   **脏数据洪流**：如果你在终端看到红色的 "Error"，程序实际输出的字节流可能是 `\x1b[31mError\x1b[0m`。
*   **清洗流 (Stream Sanitization)**：后端必须在拦截到 `stdout` 的 byte 块后，经过一层强大的正则表达式过滤器。
    *   正则参考：`r'\x1b\[([0-9]{1,2}(;[0-9]{1,2})?)?[m|K]'`
*   **分块传输 (Chunked SSE)**：清洗后的纯净文本，必须以 Server-Sent Events (SSE) 的形式，以极低的延迟（如每 50ms 一批）推送到前端，保证前端打字机效果的流畅性。

### 3.3 交互式拦截与前端放行 (Prompt Interception)
这是整个架构中最具挑战的业务难点（Human-in-the-loop 在 CLI 层的体现）。

*   **业务场景**：当 Agent 在后台运行 `claude` 时，它决定要执行一句危险命令 `rm -rf ./temp`。此时 CLI 进程会在终端里挂起，并打印 `Do you want to run this? (y/n): `，然后无限期等待用户的键盘输入。
*   **实现契约**：
    1.  **特征匹配**：后端的读线程（Read Thread）在解析 `stdout` 时，必须维护一个滑动窗口缓冲区。一旦正则表达式匹配到类似 `(y/n)` 或 `[Y/n]` 的阻塞特征。
    2.  **暂停推流**：立即停止向前端的纯文本流推送。
    3.  **发送信令**：通过独立的控制通道，向前端发送一条特殊的 JSON 信令：`{"type": "interactive_prompt", "content": "Do you want to run this? (y/n)"}`。
    4.  **前端响应**：前端中间的聊天流里会弹出一个带有【同意(Y)】【拒绝(N)】的卡片。
    5.  **管道写入**：用户点击后，前端发请求给后端，后端通过 `process.stdin.write(b'y\n')` 并且 `process.stdin.flush()`，唤醒挂起的 CLI 进程继续执行。

---

### 3.4 标准事件输出：CLI 到消息与 Artifact 的桥接

CLI Adapter 的职责是管理真实进程和标准 I/O，不直接写业务表。为避免 CLI、HTTP Agent、Orchestrator 各自发明一套产物创建逻辑，所有 Adapter 必须把可被上层消费的结果转换为统一事件：

```json
{
  "type": "agent.output|artifact.detected|interactive_prompt|task_status_change",
  "session_id": "session-id",
  "message_id": "message-id-or-null",
  "task_id": "task-id-or-null",
  "agent_id": "agent-id",
  "payload": {}
}
```

其中 `artifact.detected` 是打通产物链路的关键事件。Adapter 可以通过以下信号识别产物：
- Markdown fenced code block，语言为 `html`、`tsx`、`jsx`、`python`、`diff` 等。
- CLI 工具输出的文件变更摘要、patch、created/modified file list。
- Orchestrator 派发任务时预期的 `expected_artifact_type`。

Adapter 只负责”发现并上报”，不负责版本链、消息卡片、抽屉预览。后续由 `ArtifactService` 统一落库、建立版本关系并发布 `artifact.created`。

### 3.5 分层渲染策略 (Layered Rendering)

CLI 工具的输出不是均质的纯文本——它包含文本回复、进度动画、代码块、交互提示等多种类型。Adapter 必须对 stdout 做语义解析，按类型分层渲染到前端：

| 输出类型 | CLI 中的形态 | 前端渲染形态 |
|---------|-------------|------------|
| 纯文本/对话 | Markdown 文本流 | 聊天消息气泡（打字机流式） |
| 进度指示器 | spinner 动画、`\r` 覆盖更新的进度行 | Agent 消息气泡下方的执行轨迹面板，运行时展开、完成后自动折叠，并随消息 metadata 持久化 |
| 代码 Diff | fenced code block (`diff`/`patch`) 或 CLI 原生 diff 输出 | Artifact Card（code_diff 类型），进入产物版本链 |
| 网页/组件 | fenced code block (`html`/`tsx`/`jsx`) | Artifact Card（web_preview 类型），页面级 iframe 预览 |
| 文件变更摘要 | CLI 输出的 created/modified/deleted list | Artifact Card（file_tree 类型） |
| 交互式提示 | `(y/n)` 或 `[Y/n]` 阻塞等待 | 确认卡片（同意/拒绝按钮），用户点击后回复注入 stdin |

### 3.6 每个 CLI 单独适配 (Per-CLI Adapter Strategy)

不同 CLI 工具的输出格式、进度表示、交互模式完全不同。AgentHub 为每个 CLI 工具实现专属 Adapter，各自理解该工具的输出语义：

| Adapter | 封装的 CLI | 输出特征 | 特殊处理 |
|---------|-----------|---------|---------|
| `ClaudeCodeAdapter` | `claude` (Anthropic CLI) | Markdown + ANSI color + `(y/n)` 交互 + 文件 diff | 识别 Claude Code 的工具调用日志格式、权限确认模式 |
| `CodexAdapter` | `codex` (OpenAI CLI) | 代码块 + 进度指示 + 文件操作确认 | 识别 Codex 的执行计划和工具输出格式 |

Codex 默认启动参数应贴近用户本机终端行为：读取用户 Codex 配置和认证态，仅追加非交互执行所需的 `exec --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox --color never --json -`。AgentHub 不通过 Agent 配置暴露厂商 API Key，DeepSeek API Key 只属于后端内部系统模型配置。
| `OpenCodeAdapter` | `opencode` (开源) | 终端 spinners + 工具调用日志 + patch 输出 | 识别 OpenCode 的 agent loop 和审查反馈模式 |

所有 Adapter 通过统一 CLI 事件契约产出标准化事件（`agent.output` / `artifact.detected` / `interactive_prompt`）。新增 CLI 工具只需写一个新 Adapter。

CLI 工具由用户在操作系统层面安装（如 `npm install -g @anthropic-ai/claude-code`），AgentHub 只管理 Engine runtime 配置：在 AgentPanel 中配置 `executable` 路径、`init_args` 启动参数和非敏感环境变量覆盖。用户创建的“前端专家”“架构专家”“调度器”等 Agent Profile 会在该 Engine 之上绑定 primary skill、auxiliary skills 和 context policy。

## 4. 容错与生命周期管理 (Lifecycle & Fault Tolerance)

### 4.1 僵尸进程防范 (Zombie Process Mitigation)
由于大模型响应可能极度耗时，用户随时可能关闭网页或刷新。如果后端不加管控，服务器上将会堆积成百上千个失控的 `claude` 进程。
*   **心跳机制**：前端必须与后台维持 WebSocket 心跳。一旦断开连接超过 3 分钟，后端守护进程（Daemon）必须向该 Session 绑定的底层 PID 发送 `SIGTERM` 信号。
*   **超时强杀 (Timeout Kill)**：任何单一的交互轮次，绝对不允许超过 5 分钟的静默期（无 stdout 输出）。一旦超时，判定进程死锁，使用 `SIGKILL` 强杀。

### 4.2 本机 Workspace 隔离 (Local Workspace Isolation)
在 MVP 阶段，我们明确不使用 Docker 进行强隔离。为了保证安全和工程的可访问性，系统采用本机 workspace 目录作为 Agent 的物理执行边界。Workspace 归属于 Project（非 Session），完整产品链路见 [PRD-06 MVP 本机 Workspace](./06-MVP_Local_Workspace_Delivery.md) 和 [ADR-0009 Project-Workspace 模型](../archive/adr/0009-project-workspace-model.md)。

*   **Workspace Root**：整个 AgentHub 后端启动时，通过 `.env` 或命令行参数指定 `AGENTHUB_WORKSPACE_ROOT`，例如 `D:\AgentHub\workspaces`。这是 AgentHub 可以创建和绑定项目目录的根目录，不等同于某一个具体项目。
*   **Project Workspace**：用户创建 Project 时选择/新建一个目录作为其 workspace。新建目录默认位于 `AGENTHUB_WORKSPACE_ROOT`；绑定已有目录必须由系统原生目录选择器授权。`projects.workspace_path` 记录绝对路径。一个 Project 绑定一个 workspace，不可更改。
*   **统一 CWD (Current Working Directory)**：同一 Project 下的所有 Session（私聊/群聊）中的所有 Agent 进程，启动时的 `cwd` 参数全都指向 `Project.workspace_path`。这保证多个 Agent 在同一个物理项目目录内协作。
*   **路径边界**：后端必须校验 `workspace_path` 位于 `AGENTHUB_WORKSPACE_ROOT` 或用户显式授权的目录内，禁止通过相对路径越界读取其他文件。

## 5. 本模块开发优先级与排期建议

CLI 适配器的实现在 Phase 6（Workspace Runtime + CLI 适配器 + 产物入口桥接）中完成：

*   **Phase 6.1**：实现 CLIProcessManager — PTY/subprocess 孵化、stdout 实时推流。先用测试 CLI fixture 验证流式管道畅通，再接真实 CLI。
*   **Phase 6.2**：实现 StreamSanitizer — ANSI 转义码清洗器，确保前端收到的是干净的 Markdown。压测各种 CLI 工具的典型输出格式。
*   **Phase 6.3**：实现 PromptInterceptor — 对接真实的 `claude` 命令，攻克 `(y/n)` 交互式拦截的难点。
*   **Phase 6.4**：实现 CliAgentAdapter — 集成进程管理、流清洗、交互拦截，输出标准 CLI 事件。
