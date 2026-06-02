# 需求规格说明书 (PRD)：01 - 底层适配器架构决策 (CLI Adapter Architecture)

## 1. 文档定位
本文档为 AgentHub 的底层核心通信层设计规范，主要面向**系统架构师**、**后端核心研发人员**。
本章节将详细论述 AgentHub 如何摒弃传统的“裸调 HTTP LLM API”的伪 Agent 模式，转而利用操作系统底层进程管理技术，直接封装 Anthropic 官方的 `claude` CLI、开源的 `opencode` 等真实物理工具。这是本课题取得高分、实现工业级“Agent-as-a-Service”的关键基石。

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
    为防止串联污染，每次启动 CLI 进程时，必须重新构造 `env` 字典，清理掉宿主机的敏感环境变量，仅注入该用户的 API Keys（如 `ANTHROPIC_API_KEY`）。

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

## 4. 容错与生命周期管理 (Lifecycle & Fault Tolerance)

### 4.1 僵尸进程防范 (Zombie Process Mitigation)
由于大模型响应可能极度耗时，用户随时可能关闭网页或刷新。如果后端不加管控，服务器上将会堆积成百上千个失控的 `claude` 进程。
*   **心跳机制**：前端必须与后台维持 WebSocket 心跳。一旦断开连接超过 3 分钟，后端守护进程（Daemon）必须向该 Session 绑定的底层 PID 发送 `SIGTERM` 信号。
*   **超时强杀 (Timeout Kill)**：任何单一的交互轮次，绝对不允许超过 5 分钟的静默期（无 stdout 输出）。一旦超时，判定进程死锁，使用 `SIGKILL` 强杀。

### 4.2 单物理工作区隔离 (Single Physical Workspace)
在 MVP 阶段，我们明确不使用 Docker 进行强隔离。为了保证安全和工程的可访问性：
*   **统一 CWD (Current Working Directory)**：整个 AgentHub 后端启动时，通过 `.env` 或命令行参数指定一个唯一的 `PROJECT_ROOT`。
*   **所有进程都在此处**：无论是前端专家 Agent 还是后端专家 Agent，启动时的 `cwd` 参数全都指向同一个目录。这保证了前端写完代码后，后端立刻能在同一个目录下读到，完全符合真实的人类开发协作模式。

## 5. 本模块开发优先级与排期建议
*   **Phase 3.1**：先跑通最简单的 Python `subprocess.Popen`，使用伪造的一个打字机脚本测试 stdout 的实时推流。
*   **Phase 3.2**：编写并压测 ANSI 转义码清洗器，确保前端收到的是干净的 Markdown。
*   **Phase 3.3**：对接真实的 `claude` 命令，攻克 `(y/n)` 交互式拦截的难点。
