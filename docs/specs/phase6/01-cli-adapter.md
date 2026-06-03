# Spec: Phase 6B-6E — CLI Agent 适配器

**版本**: v2.0
**更新日期**: 2026-06-04
**状态**: Draft
**关联**: [PRD-01](../../PRD/01-Architecture_Adapter.md), [PRD-05](../../PRD/05-End_to_End_Product_Flow.md), [PRD-06](../../PRD/06-MVP_Local_Workspace_Delivery.md), [ADR-0008](../../adr/0008-revised-development-strategy.md) §6, [ADR-0009](../../adr/0009-project-workspace-model.md)
**依赖**: Phase 6A Workspace Runtime, Phase 3 (BaseAgentAdapter 接口, AgentPanel 配置)

---

## 1. 目标

实现 PRD-01 定义的 CLI Agent 封装能力，完整覆盖以下三层：

1. **通用进程管理层**（Module 6B-6D）：PTY/subprocess 孵化、ANSI 清洗、交互式拦截——所有 CLI 工具共享的基础设施。
2. **Per-CLI 适配层**（§8）：为 Claude Code、Codex、OpenCode 三个 CLI 工具分别实现专属 Adapter 子类，各自理解该 CLI 的特定输出格式、交互模式、产物信号。
3. **统一事件输出层**（Module 6E-6F）：所有 Adapter 通过 `BaseAgentAdapter` 接口产出标准化事件（`agent.output` / `artifact.detected` / `interactive_prompt`），实现分层渲染（文本→消息、进度→状态条、产物→Artifact Card、交互→确认卡片）。

CLI Wrapper 是 AgentHub 唯一的 Agent 执行模式。CLI Agent 必须依赖 [00-workspace-runtime.md](00-workspace-runtime.md) 提供的可信 `workspace_path`（来自 `Session → Project.workspace_path`），不得脱离 workspace 执行。

---

## 2. 全局链路定位

```text
Session.project_id
  -> Project.workspace_path
  -> 用户输入 / Orchestrator 子任务
  -> 路由到对应 Adapter 子类:
       ClaudeCodeAdapter | CodexAdapter | OpenCodeAdapter
  -> ProcessManager 使用 cwd=project.workspace_path
  -> StreamSanitizer / PromptInterceptor（通用层）
  -> Per-CLI 分层解析（§8.1-8.3 各自的输出格式规则）
  -> 标准化事件: agent.output / interactive_prompt / artifact.detected
  -> Phase 6F Artifact Output Bridge
  -> artifact.created → Artifact Card → Drawer
```

Agent 输出到 Artifact 的检测、落库和聊天卡片创建由 [02-artifact-output-bridge.md](02-artifact-output-bridge.md) 负责。Per-CLI 适配器的具体接入方案定义于本文档 §8。

---

## 3. 核心架构

```
┌──────────────────────────────────────────────────────────┐
│                    AgentPanel (前端)                       │
│  Agent 类型: [cli_wrapper]                                 │
│  CLI 工具: [Claude Code] [Codex] [OpenCode]               │
│  配置: executable path + init_args + env_vars             │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│        Per-CLI Adapter 子类 (Infrastructure)              │
│                                                           │
│  ┌───────────────┐ ┌──────────────┐ ┌──────────────────┐ │
│  │ClaudeCode     │ │CodexAdapter  │ │OpenCodeAdapter   │ │
│  │Adapter        │ │              │ │                  │ │
│  │ §8.1          │ │ §8.2         │ │ §8.3             │ │
│  └───────┬───────┘ └──────┬───────┘ └────────┬─────────┘ │
│          └────────────────┼──────────────────┘           │
│                           ▼                               │
│            CliAgentAdapter (基类, §7)                      │
│            implements BaseAgentAdapter                    │
│                                                           │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │ Process     │  │ Stream       │  │ Prompt           │ │
│  │ Manager     │─▶│ Sanitizer    │─▶│ Interceptor      │ │
│  │             │  │              │  │                  │ │
│  │ PTY/spawn   │  │ ANSI strip   │  │ (y/n) detection  │ │
│  │ heartbeat   │  │ chunk SSE    │  │ stdin writeback  │ │
│  │ SIGTERM/KILL│  │              │  │                  │ │
│  └─────────────┘  └──────────────┘  └──────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

---

## 4. Module 6B: CLI Process Manager

### 4.1 进程孵化

```python
class CliProcessManager:
    """CLI 进程生命周期管理器。"""

    def __init__(self, executable: str, cwd: str, env: dict[str, str], init_args: list[str]):
        self.executable = executable
        self.cwd = cwd
        self.env = env
        self.init_args = init_args

    async def spawn(self) -> int:
        """孵化新进程，返回 PID。"""
        # Unix: pty.spawn() → 提供真正的 TTY
        # Windows: subprocess.Popen + pipes (fallback)
        ...

    async def write_stdin(self, data: str) -> None:
        """向进程 stdin 写入数据。"""
        ...

    async def read_stdout(self, chunk_size: int = 1024) -> bytes:
        """非阻塞读取 stdout chunk。"""
        ...

    async def terminate(self, signal: str = "SIGTERM") -> None:
        """终止进程。先 SIGTERM，5s 后 SIGKILL。"""
        ...

    @property
    def is_alive(self) -> bool:
        """检查进程是否存活。"""
        ...
```

`cwd` 只能来自 WorkspaceService 解析并校验后的 `workspace_path`。前端请求、AgentConfig 或用户 prompt 都不能直接覆盖进程 `cwd`。

### 4.2 启动参数优化

从 `AgentConfig.init_args` 读取（PRD-01 §3.1）：
- Claude Code: `["--compact", "--theme=light"]`（最小化 UI 渲染符号）
- 通用: `["--no-color"]`（从源头减少 ANSI）

### 4.3 环境变量隔离

```python
def build_env(agent_config: AgentConfig) -> dict:
    """构造隔离的环境变量字典。"""
    env = {}
    if agent_config.provider == "claude":
        env["ANTHROPIC_API_KEY"] = get_api_key("anthropic")
    # 不继承宿主机敏感环境变量
    # 只注入该 Agent 必需的 API Key
    return env
```

### 4.4 超时与清理

| 规则 | 超时 | 动作 |
|------|------|------|
| stdout 静默 | 5 min | 判定死锁 → SIGKILL |
| WebSocket 断开 | 3 min | SIGTERM → 优雅退出 |
| 总执行时间 | 30 min | SIGKILL（防止失控） |

---

## 5. Module 6C: Stream Sanitizer (ANSI 清洗)

### 5.1 清洗规则

```python
import re

ANSI_PATTERN = re.compile(r'\x1b\[([0-9]{1,2}(;[0-9]{1,2})?)?[m|K]')

class StreamSanitizer:
    """ANSI 转义码清洗器 + 分块推送。"""

    def sanitize(self, raw_bytes: bytes) -> str:
        """去除 ANSI 控制符，返回纯净文本。"""
        text = raw_bytes.decode("utf-8", errors="replace")
        return ANSI_PATTERN.sub("", text)

    def chunk_for_sse(self, text: str, max_chunk_size: int = 200) -> list[str]:
        """将文本拆分为适合 SSE 推送的 chunk。"""
        # 优先在换行/句号/空格处断开
        ...
```

### 5.2 TUI 组件降级

- 进度条 `[████░░░░] 50%` → `[进度] 50%`
- 表格边框 `┌──┬──┐` → 跳过或转为文本列表
- 颜色代码全部移除

### 5.3 SSE 推送频率

每 50ms 批量推送一次，平衡延迟与开销。

---

## 6. Module 6D: Interactive Prompt Interception

### 6.1 阻塞特征匹配

```python
# 常见 CLI 工具的阻塞特征正则
BLOCKING_PATTERNS = [
    re.compile(r'Do you want to (run|proceed|continue)\?.*\(y/n\)', re.IGNORECASE),
    re.compile(r'\[y/N\]'),
    re.compile(r'\(yes/no\)'),
    re.compile(r'Press any key to continue'),
]
```

### 6.2 滑动窗口缓冲区

```python
class PromptInterceptor:
    """交互式提示拦截器。"""

    def __init__(self, window_size: int = 500):
        self.buffer = ""  # 滑动窗口缓冲区
        self.window_size = window_size

    def feed(self, chunk: str) -> tuple[bool, str | None, str]:
        """
        返回: (is_blocked, prompt_text, safe_text)
        - is_blocked = True → 检测到阻塞，停止推送
        - prompt_text = 阻塞提示的原文
        - safe_text = 可以安全推送的部分
        """
        self.buffer = (self.buffer + chunk)[-self.window_size:]
        for pattern in BLOCKING_PATTERNS:
            match = pattern.search(self.buffer)
            if match:
                safe = self.buffer[:match.start()]
                prompt = match.group()
                return True, prompt, safe
        return False, None, chunk
```

### 6.3 前后端交互流程

```
后端 stdout 线程检测到 (y/n)
  → 暂停 SSE text_chunk 推送
  → 发送 SSE event: interactive_prompt {"content": "Do you want to run this? (y/n)", "processId": "..."}
  → 前端渲染 InteractivePromptCard (同意/拒绝按钮)
  → 用户点击 [同意] → POST /api/sessions/{id}/interactive_reply {"process_id": "...", "reply": "y"}
  → 后端 process.stdin.write(b'y\n') + process.stdin.flush()
  → 恢复 stdout 读取 + SSE 推送
```

---

## 7. Module 6E: CLI Agent Adapter（基类）

`CliAgentAdapter` 是通用基类，实现 `BaseAgentAdapter` 接口，整合 ProcessManager / StreamSanitizer / PromptInterceptor 三个通用组件。Claude Code、Codex、OpenCode 的专属适配逻辑在各自子类中覆盖——详见 §8。

### 7.1 实现 BaseAgentAdapter

```python
class CliAgentAdapter(BaseAgentAdapter):
    """CLI Agent 适配器 —— 实现 BaseAgentAdapter 接口。"""

    def __init__(self, agent_config: AgentConfig, workspace_path: str):
        self.config = agent_config
        self.workspace = workspace_path
        self.process_manager = CliProcessManager(
            executable=agent_config.executable,
            cwd=workspace_path,
            env=build_env(agent_config),
            init_args=agent_config.init_args or [],
        )
        self.sanitizer = StreamSanitizer()
        self.interceptor = PromptInterceptor()

    @property
    def capability(self) -> AgentCapability:
        return AgentCapability(
            name=f"CLI: {self.config.name}",
            supports_streaming=True,
            supports_file_input=True,   # CLI 工具可直接读写文件系统
            supports_tool_call=True,    # CLI 工具原生具备工具调用能力
            max_context_tokens=200_000,
            tags=["cli", "native-tools", self.config.executable],
        )

    async def chat_stream(self, messages, system_prompt) -> AsyncIterator[str]:
        pid = await self.process_manager.spawn()
        try:
            while self.process_manager.is_alive:
                raw = await self.process_manager.read_stdout()
                if not raw:
                    break
                clean = self.sanitizer.sanitize(raw)
                is_blocked, prompt, safe = self.interceptor.feed(clean)
                if is_blocked:
                    yield self._build_interactive_event(prompt, pid)
                    # 等待前端回复（通过 stdin 写入）
                    break
                if safe:
                    yield safe
        finally:
            await self.process_manager.terminate()
```

调用方必须在创建 `CliAgentAdapter` 前通过 `session_id -> project_id -> workspace_path` 完成解析。所有 Session 必须归属某个 Project，因此始终存在可用的 workspace_path。如果查询链路异常，CLI Adapter 应拒绝执行并返回可读错误：”无法解析 workspace 路径，请检查 Project 配置”。

### 7.2 AgentConfig 表扩展

在现有 `agents` 表中，`agent_type` 新增枚举值 `'cli_wrapper'`：

```sql
-- 新增字段（如果不存在）
ALTER TABLE agent_configs ADD COLUMN executable VARCHAR(255);
ALTER TABLE agent_configs ADD COLUMN init_args JSON;
```

### 7.3 前端配置面板

AgentPanel 中：
- Agent 类型下拉: `API 代理` / `CLI 包装器` ← 新增
- 选择 CLI 包装器时 → 显示可执行文件路径输入框 + 启动参数输入框
- 启动前检测可执行文件是否存在于 PATH 中 → 红/绿指示灯

---

## 8. Per-CLI 接入方案

以上 Module 6B-6E 定义了通用抽象层。本节定义三个 CLI 工具各自的具体接入方式。每个 CLI 子类化 `CliAgentAdapter`，覆盖启动参数、环境变量、交互模式匹配、产物检测规则。

### 8.1 ClaudeCodeAdapter — 接入 Anthropic `claude` CLI

**工具信息**：
- 安装：`npm install -g @anthropic-ai/claude-code`
- 可执行文件：`claude`
- 认证：`ANTHROPIC_API_KEY` 环境变量（或 `claude login` OAuth）
- 交互模式：REPL 式对话 + 工具调用循环 + 权限确认

**启动参数**：

```python
# ClaudeCodeAdapter 默认 init_args
CLAUDE_CODE_DEFAULT_ARGS = [
    "--compact",           # 精简输出，减少装饰性 UI
    "--no-color",          # 从源头关闭 ANSI 颜色
    "--output-format=text", # 确保输出为纯文本/Markdown（如果 CLI 支持）
]
```

**环境变量**：

```python
def build_claude_env(agent_config: AgentConfig) -> dict:
    return {
        "ANTHROPIC_API_KEY": get_api_key("anthropic"),
        "CLAUDE_CODE_NO_COLOR": "1",     # 备用：二次确认关闭颜色
        "NO_COLOR": "1",                 # 遵循 no-color.org 约定
        "TERM": "dumb",                  # 降级终端能力，减少 TUI 渲染
    }
```

**stdin 注入格式**：

Claude Code 在 REPL 模式下接受多行文本输入。AgentHub 将用户的自然语言消息包装为初始 prompt，通过 stdin 写入：

```python
async def inject_prompt(self, prompt: str, system_prompt: str = "") -> None:
    """向 Claude Code CLI 注入任务 prompt。"""
    # Claude Code 不通过 stdin 接收 system prompt（它有自己的系统指令）
    # system_prompt 通过环境变量或配置文件注入
    full_prompt = f"{prompt}\n"  # 末尾换行触发执行
    await self.process_manager.write_stdin(full_prompt)
```

**输出特征与分层解析**：

| Claude Code 输出模式 | stdout 特征 | 解析为 |
|---------------------|------------|--------|
| 思考/分析文本 | 普通 Markdown 段落 | `agent.output` → 消息气泡 |
| 工具调用日志 | `⏺ 正在读取文件...`、`⎿ 调用工具: Read` | 状态条（非消息） |
| 文件修改 diff | `@@ -10,6 +10,8 @@`、彩色 diff 块 | `artifact.detected` (code_diff) |
| 创建的代码块 | fenced code block (```html, ```tsx 等) | `artifact.detected` (web_preview / document) |
| 权限确认 | `Do you want to run this? (y/n)` | `interactive_prompt` → 确认卡片 |
| 任务完成摘要 | `✓ 已完成:` 开头 | `agent.output` → 消息气泡 |

**交互模式特征**（PromptInterceptor 专用规则）：

```python
CLAUDE_CODE_BLOCKING_PATTERNS = [
    re.compile(r'Do you want to (run|proceed|continue|allow)\b.*\?', re.IGNORECASE),
    re.compile(r'\[y/n\]'),
    re.compile(r'\(y/n\)'),
    re.compile(r'Press Enter to continue'),
]
```

**产物检测规则**：

```python
# Claude Code 输出中的产物信号
CLAUDE_CODE_ARTIFACT_SIGNALS = {
    "code_diff": [
        r'@@ -\d+,\d+ \+\d+,\d+ @@',        # unified diff hunk
        r'```diff\n.*?```',                   # fenced diff block
    ],
    "web_preview": [
        r'```html\n.*?```',                   # HTML 代码块
        r'```tsx\n.*?```',                    # React 组件
        r'```jsx\n.*?```',                    # JSX 组件
    ],
    "file_tree": [
        r'(Created|Modified|Deleted)\s+files?:',  # 文件变更摘要
        r'📝\s*(Created|Updated)',            # Claude Code emoji 标记
    ],
}
```

---

### 8.2 CodexAdapter — 接入 OpenAI `codex` CLI

**工具信息**：
- 安装：`npm install -g @openai/codex`（待 CLI 正式发布后确认包名）
- 可执行文件：`codex`
- 认证：`OPENAI_API_KEY` 环境变量
- 交互模式：任务驱动 + 执行计划 + 结果报告

> ⚠️ OpenAI Codex CLI 目前处于早期阶段，以下方案基于公开文档和预期行为设计。需要在 Phase 6 开发时根据 CLI 实际行为校准。

**启动参数**：

```python
CODEX_DEFAULT_ARGS = [
    "--no-color",
    "--plain",             # 纯文本模式，减少 TUI
]
```

**环境变量**：

```python
def build_codex_env(agent_config: AgentConfig) -> dict:
    return {
        "OPENAI_API_KEY": get_api_key("openai"),
        "NO_COLOR": "1",
        "TERM": "dumb",
    }
```

**stdin 注入格式**：

```python
async def inject_prompt(self, prompt: str, system_prompt: str = "") -> None:
    """向 Codex CLI 注入任务。"""
    # Codex CLI 通常接受单行任务描述
    full_prompt = f"{system_prompt}\n\n{prompt}\n" if system_prompt else f"{prompt}\n"
    await self.process_manager.write_stdin(full_prompt)
```

**输出特征与分层解析**：

| Codex 输出模式 | stdout 特征 | 解析为 |
|---------------|------------|--------|
| 执行计划 | `## Plan`、`### Step 1:` | `agent.output` → 消息气泡 |
| 代码生成 | fenced code block | `artifact.detected` |
| 进度指示 | `Working...`、`⠋ ⠙ ⠹ ⠸` spinner | 状态条 |
| 文件操作确认 | `Create file X?` | `interactive_prompt` |
| 结果报告 | `## Result` | `agent.output` |

**交互模式特征**：

```python
CODEX_BLOCKING_PATTERNS = [
    re.compile(r'Create (file|directory)\s+.*\?', re.IGNORECASE),
    re.compile(r'Proceed with (changes|modifications)\?', re.IGNORECASE),
    re.compile(r'\[y/N\]'),
]
```

**产物检测规则**：

```python
CODEX_ARTIFACT_SIGNALS = {
    "code_diff": [
        r'```diff\n.*?```',
        r'--- a/.*?\n\+\+\+ b/.*?',         # git diff header
    ],
    "web_preview": [
        r'```html\n.*?```',
        r'```(tsx|jsx)\n.*?```',
    ],
    "file_tree": [
        r'(Creating|Writing)\s+file:\s+',   # Codex 文件操作日志
    ],
}
```

---

### 8.3 OpenCodeAdapter — 接入开源 `opencode` CLI

**工具信息**：
- 安装：`pip install opencode`（或 `pipx install opencode`）
- 可执行文件：`opencode`
- 认证：通过配置文件或环境变量（支持多厂商 API Key）
- 交互模式：Agent 循环 + 工具调用 + 审查反馈

**启动参数**：

```python
OPENCODE_DEFAULT_ARGS = [
    "--no-color",
    "--plain",
]
```

**环境变量**：

```python
def build_opencode_env(agent_config: AgentConfig) -> dict:
    """OpenCode 支持多模型厂商，根据 AgentConfig.provider 注入对应 Key。"""
    env = {"NO_COLOR": "1", "TERM": "dumb"}
    provider_key_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
    }
    key_name = provider_key_map.get(agent_config.provider)
    if key_name:
        env[key_name] = get_api_key(agent_config.provider)
    return env
```

**stdin 注入格式**：

```python
async def inject_prompt(self, prompt: str, system_prompt: str = "") -> None:
    """向 OpenCode CLI 注入任务。"""
    # OpenCode 支持通过 stdin 传入初始 prompt
    # system_prompt 可通过 -s 参数或配置文件注入
    await self.process_manager.write_stdin(f"{prompt}\n")
```

**输出特征与分层解析**：

| OpenCode 输出模式 | stdout 特征 | 解析为 |
|------------------|------------|--------|
| Agent 思考 | `## Thinking`、分析段落 | `agent.output` |
| 工具调用 | `[Tool: Read]`、`[Tool: Write]` | 状态条 |
| 代码块/patch | fenced code block、`--- a/` diff | `artifact.detected` |
| 审查反馈 | `## Review`、问题列表 | `agent.output` |
| 确认提示 | `Continue?`、`Apply these changes?` | `interactive_prompt` |

**交互模式特征**：

```python
OPENCODE_BLOCKING_PATTERNS = [
    re.compile(r'(Continue|Proceed|Apply)\s+(with\s+)?(changes|modifications)?\?', re.IGNORECASE),
    re.compile(r'\[y/N\]'),
    re.compile(r'Accept (this|these) (change|modification)s?\?', re.IGNORECASE),
]
```

**产物检测规则**：

```python
OPENCODE_ARTIFACT_SIGNALS = {
    "code_diff": [
        r'```diff\n.*?```',
        r'--- a/.*?\n\+\+\+ b/.*?',
    ],
    "web_preview": [
        r'```html\n.*?```',
        r'```(tsx|jsx)\n.*?```',
        r'```vue\n.*?```',                  # OpenCode 可能输出 Vue SFC
        r'```svelte\n.*?```',
    ],
    "file_tree": [
        r'(Created|Modified|Deleted):\s+',  # OpenCode 文件操作前缀
    ],
}
```

---

### 8.4 三 CLI 对比总结

| 维度 | Claude Code (`claude`) | Codex (`codex`) | OpenCode (`opencode`) |
|------|----------------------|-----------------|----------------------|
| **可执行文件** | `claude` | `codex` | `opencode` |
| **安装方式** | `npm install -g @anthropic-ai/claude-code` | `npm install -g @openai/codex` | `pip install opencode` |
| **API Key 变量** | `ANTHROPIC_API_KEY` | `OPENAI_API_KEY` | 多厂商（`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`） |
| **系统提示注入** | 配置文件 / 环境变量 | stdin 前缀 | `-s` 参数 / 配置文件 |
| **diff 输出格式** | unified diff (git-style) | fenced diff block + git header | 两者混合 |
| **交互特征** | `Do you want to run? (y/n)` | `Create file X?` / `Proceed? [y/N]` | `Apply these changes?` |
| **进度指示** | `⏺` / `⎿` 符号 + 工具名 | `Working...` + spinner | `[Tool: X]` 标签 |
| **任务完成标记** | `✓ 已完成:` | `## Result` | 无固定标记（需从输出结束判定） |
| **Adapter 类** | `ClaudeCodeAdapter` | `CodexAdapter` | `OpenCodeAdapter` |
| **后端文件** | `backend/app/agents/claude_code_adapter.py` | `backend/app/agents/codex_adapter.py` | `backend/app/agents/opencode_adapter.py` |

### 8.5 新增 CLI 工具的扩展流程

当需要接入第 4 个 CLI 工具时：

1. 在 `AgentConfig` 中确认/新增 `executable` 值
2. 新建 `XxxAdapter(ClaudeCodeAdapter)` 或 `XxxAdapter(CliAgentAdapter)`，覆盖：
   - `DEFAULT_ARGS` — 启动参数
   - `build_env()` — 环境变量
   - `inject_prompt()` — stdin 注入格式（如果与基类不同）
   - `BLOCKING_PATTERNS` — 交互特征正则
   - `ARTIFACT_SIGNALS` — 产物检测规则
3. 在 AgentPanel 的 executable 下拉列表中添加该工具
4. 添加单元测试（Mock 该 CLI 的典型输出）

---

## 9. 测试策略

### 单元测试 (50 条)

| 组件 | 测试数 | 测试内容 |
|------|--------|---------|
| CliProcessManager | 8 | spawn/terminate/超时/环境变量构造 |
| StreamSanitizer | 8 | ANSI 去除/中文/混合/TUI 降级 |
| PromptInterceptor | 6 | 匹配/不匹配/滑动窗口/边界 |
| CliAgentAdapter (基类) | 8 | chat_stream/错误处理/中断/恢复 |
| ClaudeCodeAdapter | 5 | Claude Code 输出解析/diff 检测/交互匹配/产物信号 |
| CodexAdapter | 5 | Codex 输出解析/计划识别/文件创建确认/产物信号 |
| OpenCodeAdapter | 5 | OpenCode 输出解析/工具调用日志/审查反馈/产物信号 |
| AgentConfig 模型 | 5 | validation/agent_type 枚举/init_args/executable 校验 |

### 集成测试

- Mock CLI 脚本（输出 ANSI + 阻塞提示）→ 验证全流程
- 用三个 Adapter 各自的 mock 输出验证：Claude Code 格式 → 正确解析分层；Codex 格式 → 正确解析分层；OpenCode 格式 → 正确解析分层
- 真实 CLI Smoke test（如果对应 API key 可用）：`claude` / `codex` / `opencode` 各一条

### E2E

- 前端配置 Claude Code Agent → 发送消息 → 打字机效果 + 状态条 → Diff 变为 Artifact Card → 交互卡片点击 → 进程继续
- 前端配置 Codex Agent → 同上流程
- 前端配置 OpenCode Agent → 同上流程
