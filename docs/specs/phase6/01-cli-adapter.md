# Spec: Phase 6 — CLI Agent 适配器

**版本**: v1.0
**创建日期**: 2026-06-02
**状态**: Draft
**关联**: [PRD-01](../../PRD/01-Architecture_Adapter.md), [ADR-0008](../../adr/0008-revised-development-strategy.md) §6
**依赖**: Phase 3 (BaseAgentAdapter 接口, AgentPanel 配置)

---

## 1. 目标

实现 PRD-01 定义的 CLI Agent 封装能力。通过 PTY/subprocess 管理真实 CLI 工具（Claude Code 等），提供 stdout 流式推送、ANSI 转义码清洗、交互式提示拦截。以新增 `agent_type='cli_wrapper'` 的方式与现有 HTTP 适配器并存。

---

## 2. 核心架构

```
┌──────────────────────────────────────────────────────────┐
│                    AgentPanel (前端)                       │
│  Agent 类型: [api_proxy] [cli_wrapper] ← 新增             │
│  配置: executable path + init_args + env_vars             │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│               CliAgentAdapter (Infrastructure)            │
│  implements BaseAgentAdapter                              │
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

## 3. Module 6A: CLI Process Manager

### 3.1 进程孵化

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

### 3.2 启动参数优化

从 `AgentConfig.init_args` 读取（PRD-01 §3.1）：
- Claude Code: `["--compact", "--theme=light"]`（最小化 UI 渲染符号）
- 通用: `["--no-color"]`（从源头减少 ANSI）

### 3.3 环境变量隔离

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

### 3.4 超时与清理

| 规则 | 超时 | 动作 |
|------|------|------|
| stdout 静默 | 5 min | 判定死锁 → SIGKILL |
| WebSocket 断开 | 3 min | SIGTERM → 优雅退出 |
| 总执行时间 | 30 min | SIGKILL（防止失控） |

---

## 4. Module 6B: Stream Sanitizer (ANSI 清洗)

### 4.1 清洗规则

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

### 4.2 TUI 组件降级

- 进度条 `[████░░░░] 50%` → `[进度] 50%`
- 表格边框 `┌──┬──┐` → 跳过或转为文本列表
- 颜色代码全部移除

### 4.3 SSE 推送频率

每 50ms 批量推送一次，平衡延迟与开销。

---

## 5. Module 6C: Interactive Prompt Interception

### 5.1 阻塞特征匹配

```python
# 常见 CLI 工具的阻塞特征正则
BLOCKING_PATTERNS = [
    re.compile(r'Do you want to (run|proceed|continue)\?.*\(y/n\)', re.IGNORECASE),
    re.compile(r'\[y/N\]'),
    re.compile(r'\(yes/no\)'),
    re.compile(r'Press any key to continue'),
]
```

### 5.2 滑动窗口缓冲区

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

### 5.3 前后端交互流程

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

## 6. Module 6D: CLI Agent Adapter

### 6.1 实现 BaseAgentAdapter

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

### 6.2 AgentConfig 表扩展

在现有 `agents` 表中，`agent_type` 新增枚举值 `'cli_wrapper'`：

```sql
-- 新增字段（如果不存在）
ALTER TABLE agent_configs ADD COLUMN executable VARCHAR(255);
ALTER TABLE agent_configs ADD COLUMN init_args JSON;
```

### 6.3 前端配置面板

AgentPanel 中：
- Agent 类型下拉: `API 代理` / `CLI 包装器` ← 新增
- 选择 CLI 包装器时 → 显示可执行文件路径输入框 + 启动参数输入框
- 启动前检测可执行文件是否存在于 PATH 中 → 红/绿指示灯

---

## 7. 测试策略

### 单元测试 (35 条)

| 组件 | 测试数 | 测试内容 |
|------|--------|---------|
| CliProcessManager | 8 | spawn/terminate/超时/环境变量构造 |
| StreamSanitizer | 8 | ANSI 去除/中文/混合/TUI 降级 |
| PromptInterceptor | 6 | 匹配/不匹配/滑动窗口/边界 |
| CliAgentAdapter | 8 | chat_stream/错误处理/中断/恢复 |
| AgentConfig 模型 | 5 | validation/agent_type 枚举/init_args |

### 集成测试

- Mock CLI 脚本（输出 ANSI + 阻塞提示）→ 验证全流程
- 真实 Claude Code（如果 API key 可用）→ Smoke test

### E2E

- 前端配置 CLI Agent → 发送消息 → 打字机效果 → 交互卡片点击 → 进程输出继续
